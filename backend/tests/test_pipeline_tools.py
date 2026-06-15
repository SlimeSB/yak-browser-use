"""Tests for pipeline_tools module."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from engine._harness.pipeline_tools import (
    pipeline_load,
    pipeline_list,
    pipeline_update_step,
    pipeline_add_step,
    pipeline_remove_step,
    pipeline_create,
    _resolve_pipeline_path,
    _load_pipeline_yaml,
    _dump_pipeline_yaml,
)


SAMPLE_PIPELINE = {
    "name": "test_pipeline",
    "description": "A test pipeline",
    "required_params": ["keyword"],
    "steps": [
        {
            "name": "step_1",
            "description": "Navigate to site",
            "browser_ops": [{"goto": "https://example.com"}],
        },
        {
            "name": "step_2",
            "description": "Search for keyword",
            "browser_ops": [{"fill": {"selector": "#q", "value": "test"}}],
            "depends_on": ["step_1"],
        },
        {
            "name": "step_3",
            "description": "Run a custom tool",
            "tool_name": "my_tool",
        },
        {
            "name": "step_4",
            "description": "Goal step",
            "goal_description": "Analyze the results",
        },
    ],
}


@pytest.fixture
def temp_presets_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "engine._harness.pipeline_tools.PRESETS_DIR",
        tmp_path,
    )
    return tmp_path


@pytest.fixture
def sample_pipeline_file(temp_presets_dir):
    path = temp_presets_dir / "test_pipeline.pipeline.yaml"
    path.write_text(yaml.dump(SAMPLE_PIPELINE, default_flow_style=False, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _mock_write_via_edit():
    from engine._harness.pipeline_tools import PRESETS_DIR as pd

    async def _fake_edit(pipeline_name, content, explanation=""):
        path = pd / f"{pipeline_name}.pipeline.yaml"
        path.write_text(content, encoding="utf-8")
        return "ok"

    return patch(
        "tools.edit_pipeline.edit_pipeline",
        side_effect=_fake_edit,
    )


# ── pipeline_load ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_load_exists(sample_pipeline_file):
    result = await pipeline_load(pipeline_name="test_pipeline")
    data = json.loads(result)
    assert data["ok"] is True
    assert data["name"] == "test_pipeline"
    assert data["description"] == "A test pipeline"
    assert data["step_count"] == 4
    assert data["required_params"] == ["keyword"]
    assert len(data["steps"]) == 4
    assert data["steps"][0]["name"] == "step_1"
    assert data["steps"][0]["type"] == "browser"
    assert data["steps"][0]["browser_op_count"] == 1
    assert data["steps"][2]["type"] == "tool"
    assert data["steps"][2]["tool_name"] == "my_tool"
    assert data["steps"][3]["type"] == "goal"


@pytest.mark.asyncio
async def test_pipeline_load_not_found(temp_presets_dir):
    result = await pipeline_load(pipeline_name="nonexistent")
    data = json.loads(result)
    assert data["ok"] is False
    assert "not found" in data["error"]


@pytest.mark.asyncio
async def test_pipeline_load_empty_name():
    result = await pipeline_load(pipeline_name="")
    data = json.loads(result)
    assert data["ok"] is False
    assert "required" in data["error"]


@pytest.mark.asyncio
async def test_pipeline_load_corrupted(temp_presets_dir):
    path = temp_presets_dir / "corrupt.pipeline.yaml"
    path.write_text(": invalid yaml: :", encoding="utf-8")
    result = await pipeline_load(pipeline_name="corrupt")
    data = json.loads(result)
    assert data["ok"] is False


# ── pipeline_list ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_list_empty(temp_presets_dir):
    result = await pipeline_list()
    data = json.loads(result)
    assert data["ok"] is True
    assert data["presets"] == []


@pytest.mark.asyncio
async def test_pipeline_list_with_files(sample_pipeline_file):
    result = await pipeline_list()
    data = json.loads(result)
    assert data["ok"] is True
    assert len(data["presets"]) == 1
    assert data["presets"][0]["name"] == "test_pipeline"
    assert data["presets"][0]["description"] == "A test pipeline"
    assert data["presets"][0]["step_count"] == 4


@pytest.mark.asyncio
async def test_pipeline_list_partial_corrupt(temp_presets_dir, sample_pipeline_file):
    corrupt = temp_presets_dir / "corrupt.pipeline.yaml"
    corrupt.write_text(": bad yaml", encoding="utf-8")
    result = await pipeline_list()
    data = json.loads(result)
    assert data["ok"] is True
    assert len(data["presets"]) == 2
    corrupt_entry = next(p for p in data["presets"] if p["name"] == "corrupt")
    assert corrupt_entry["description"] == "(parse error)"
    assert corrupt_entry["step_count"] == 0


# ── pipeline_update_step ───────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_update_step_description(sample_pipeline_file):
    with _mock_write_via_edit():
        result = await pipeline_update_step(
            pipeline_name="test_pipeline",
            step_name="step_1",
            updates={"description": "Updated description"},
            explanation="test",
        )
    data = json.loads(result)
    assert data["ok"] is True

    validated = _load_pipeline_yaml("test_pipeline")
    assert validated.steps[0].description == "Updated description"


@pytest.mark.asyncio
async def test_pipeline_update_step_browser_ops(sample_pipeline_file):
    with _mock_write_via_edit():
        result = await pipeline_update_step(
            pipeline_name="test_pipeline",
            step_name="step_3",
            updates={"browser_ops": [{"click": "#btn"}]},
            explanation="test",
        )
    data = json.loads(result)
    assert data["ok"] is True

    validated = _load_pipeline_yaml("test_pipeline")
    assert validated.steps[2].browser_ops == [{"click": "#btn"}]
    assert validated.steps[2].tool_name is None


@pytest.mark.asyncio
async def test_pipeline_update_step_tool_name(sample_pipeline_file):
    with _mock_write_via_edit():
        result = await pipeline_update_step(
            pipeline_name="test_pipeline",
            step_name="step_1",
            updates={"tool_name": "other_tool"},
            explanation="test",
        )
    data = json.loads(result)
    assert data["ok"] is True

    validated = _load_pipeline_yaml("test_pipeline")
    assert validated.steps[0].tool_name == "other_tool"
    assert validated.steps[0].browser_ops is None


@pytest.mark.asyncio
async def test_pipeline_update_step_goal_description(sample_pipeline_file):
    with _mock_write_via_edit():
        result = await pipeline_update_step(
            pipeline_name="test_pipeline",
            step_name="step_1",
            updates={"goal_description": "Do something"},
            explanation="test",
        )
    data = json.loads(result)
    assert data["ok"] is True

    validated = _load_pipeline_yaml("test_pipeline")
    assert validated.steps[0].goal_description == "Do something"
    assert validated.steps[0].browser_ops is None
    assert validated.steps[0].tool_name is None


@pytest.mark.asyncio
async def test_pipeline_update_step_depends_on(sample_pipeline_file):
    with _mock_write_via_edit():
        result = await pipeline_update_step(
            pipeline_name="test_pipeline",
            step_name="step_1",
            updates={"depends_on": ["step_3"]},
            explanation="test",
        )
    data = json.loads(result)
    assert data["ok"] is True

    validated = _load_pipeline_yaml("test_pipeline")
    assert validated.steps[0].depends_on == ["step_3"]


@pytest.mark.asyncio
async def test_pipeline_update_step_empty_updates(sample_pipeline_file):
    result = await pipeline_update_step(
        pipeline_name="test_pipeline",
        step_name="step_1",
        updates={},
    )
    data = json.loads(result)
    assert data["ok"] is False
    assert "must not be empty" in data["error"]


@pytest.mark.asyncio
async def test_pipeline_update_step_not_found(sample_pipeline_file):
    result = await pipeline_update_step(
        pipeline_name="test_pipeline",
        step_name="nonexistent",
        updates={"description": "x"},
    )
    data = json.loads(result)
    assert data["ok"] is False
    assert "not found" in data["error"]


@pytest.mark.asyncio
async def test_pipeline_update_step_pipeline_not_found(temp_presets_dir):
    result = await pipeline_update_step(
        pipeline_name="nonexistent",
        step_name="step_1",
        updates={"description": "x"},
    )
    data = json.loads(result)
    assert data["ok"] is False
    assert "not found" in data["error"]


@pytest.mark.asyncio
async def test_pipeline_update_step_type_conflict(sample_pipeline_file):
    result = await pipeline_update_step(
        pipeline_name="test_pipeline",
        step_name="step_1",
        updates={"browser_ops": [{"goto": "x"}], "tool_name": "t"},
        explanation="test",
    )
    data = json.loads(result)
    assert data["ok"] is False
    assert "mutually exclusive" in data["error"].lower() or "validation" in data["error"].lower()


@pytest.mark.asyncio
async def test_pipeline_update_step_unknown_keys(sample_pipeline_file):
    result = await pipeline_update_step(
        pipeline_name="test_pipeline",
        step_name="step_1",
        updates={"description": "x", "unknown_field": "bad"},
    )
    data = json.loads(result)
    assert data["ok"] is False
    assert "Unknown update keys" in data["error"]
    assert "unknown_field" in data["error"]


# ── pipeline_add_step ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_add_step_append(sample_pipeline_file):
    with _mock_write_via_edit():
        result = await pipeline_add_step(
            pipeline_name="test_pipeline",
            step_name="step_5",
            description="Appended step",
            browser_ops=[{"snapshot": {}}],
            explanation="test",
        )
    data = json.loads(result)
    assert data["ok"] is True

    validated = _load_pipeline_yaml("test_pipeline")
    assert len(validated.steps) == 5
    assert validated.steps[-1].name == "step_5"


@pytest.mark.asyncio
async def test_pipeline_add_step_insert_after(sample_pipeline_file):
    with _mock_write_via_edit():
        result = await pipeline_add_step(
            pipeline_name="test_pipeline",
            step_name="step_1b",
            description="Inserted step",
            browser_ops=[{"click": "#x"}],
            after="step_1",
            explanation="test",
        )
    data = json.loads(result)
    assert data["ok"] is True

    validated = _load_pipeline_yaml("test_pipeline")
    assert validated.steps[1].name == "step_1b"


@pytest.mark.asyncio
async def test_pipeline_add_step_anchor_not_found(sample_pipeline_file):
    result = await pipeline_add_step(
        pipeline_name="test_pipeline",
        step_name="step_x",
        description="x",
        browser_ops=[{"goto": "x"}],
        after="nonexistent",
    )
    data = json.loads(result)
    assert data["ok"] is False
    assert "not found" in data["error"]


@pytest.mark.asyncio
async def test_pipeline_add_step_pipeline_not_found(temp_presets_dir):
    result = await pipeline_add_step(
        pipeline_name="nonexistent",
        step_name="step_1",
        description="x",
        browser_ops=[{"goto": "x"}],
    )
    data = json.loads(result)
    assert data["ok"] is False
    assert "not found" in data["error"]


@pytest.mark.asyncio
async def test_pipeline_add_step_with_depends_on(sample_pipeline_file):
    with _mock_write_via_edit():
        result = await pipeline_add_step(
            pipeline_name="test_pipeline",
            step_name="step_5",
            description="With deps",
            browser_ops=[{"click": "#x"}],
            depends_on=["step_1", "step_2"],
            explanation="test",
        )
    data = json.loads(result)
    assert data["ok"] is True

    validated = _load_pipeline_yaml("test_pipeline")
    assert validated.steps[-1].depends_on == ["step_1", "step_2"]


@pytest.mark.asyncio
async def test_pipeline_add_step_type_conflict(sample_pipeline_file):
    result = await pipeline_add_step(
        pipeline_name="test_pipeline",
        step_name="step_5",
        description="Conflict",
        browser_ops=[{"goto": "x"}],
        tool_name="t",
    )
    data = json.loads(result)
    assert data["ok"] is False


@pytest.mark.asyncio
async def test_pipeline_add_step_duplicate_name(sample_pipeline_file):
    result = await pipeline_add_step(
        pipeline_name="test_pipeline",
        step_name="step_1",
        description="Duplicate",
        browser_ops=[{"goto": "x"}],
    )
    data = json.loads(result)
    assert data["ok"] is False
    assert "already exists" in data["error"]


# ── pipeline_remove_step ───────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_remove_step(sample_pipeline_file):
    with _mock_write_via_edit():
        result = await pipeline_remove_step(
            pipeline_name="test_pipeline",
            step_name="step_2",
            explanation="test",
        )
    data = json.loads(result)
    assert data["ok"] is True

    validated = _load_pipeline_yaml("test_pipeline")
    assert len(validated.steps) == 3
    names = [s.name for s in validated.steps]
    assert "step_2" not in names


@pytest.mark.asyncio
async def test_pipeline_remove_step_cleans_depends_on(sample_pipeline_file):
    with _mock_write_via_edit():
        result = await pipeline_remove_step(
            pipeline_name="test_pipeline",
            step_name="step_1",
            explanation="test",
        )
    data = json.loads(result)
    assert data["ok"] is True

    validated = _load_pipeline_yaml("test_pipeline")
    for s in validated.steps:
        assert "step_1" not in s.depends_on


@pytest.mark.asyncio
async def test_pipeline_remove_step_not_found(sample_pipeline_file):
    result = await pipeline_remove_step(
        pipeline_name="test_pipeline",
        step_name="nonexistent",
    )
    data = json.loads(result)
    assert data["ok"] is False
    assert "not found" in data["error"]


@pytest.mark.asyncio
async def test_pipeline_remove_step_pipeline_not_found(temp_presets_dir):
    result = await pipeline_remove_step(
        pipeline_name="nonexistent",
        step_name="step_1",
    )
    data = json.loads(result)
    assert data["ok"] is False
    assert "not found" in data["error"]


@pytest.mark.asyncio
async def test_pipeline_remove_last_step(temp_presets_dir):
    single_step = {
        "name": "single",
        "description": "Only one step",
        "steps": [
            {"name": "only", "description": "The only step", "browser_ops": [{"goto": "x"}]},
        ],
    }
    path = temp_presets_dir / "single.pipeline.yaml"
    path.write_text(yaml.dump(single_step, default_flow_style=False, allow_unicode=True, sort_keys=False), encoding="utf-8")

    result = await pipeline_remove_step(
        pipeline_name="single",
        step_name="only",
    )
    data = json.loads(result)
    assert data["ok"] is False
    assert "validation" in data["error"].lower() or "min_length" in data["error"].lower()


# ── pipeline_create ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_create(temp_presets_dir):
    with patch("engine._harness.pipeline_tools._push_ws_event", return_value=None):
        result = await pipeline_create(
            pipeline_name="new_pipeline",
            description="A new pipeline",
            steps=[
                {"name": "s1", "description": "Step 1", "browser_ops": [{"goto": "https://x.com"}]},
                {"name": "s2", "description": "Step 2", "tool_name": "my_tool"},
            ],
            explanation="test",
        )
    data = json.loads(result)
    assert data["ok"] is True

    path = temp_presets_dir / "new_pipeline.pipeline.yaml"
    assert path.exists()

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert raw["name"] == "new_pipeline"
    assert len(raw["steps"]) == 2


@pytest.mark.asyncio
async def test_pipeline_create_duplicate(sample_pipeline_file):
    result = await pipeline_create(
        pipeline_name="test_pipeline",
        description="dup",
        steps=[{"name": "s1", "description": "x", "browser_ops": [{"goto": "x"}]}],
    )
    data = json.loads(result)
    assert data["ok"] is False
    assert "already exists" in data["error"]


@pytest.mark.asyncio
async def test_pipeline_create_invalid_name(temp_presets_dir):
    result = await pipeline_create(
        pipeline_name="bad/name",
        description="x",
        steps=[{"name": "s1", "description": "x", "browser_ops": [{"goto": "x"}]}],
    )
    data = json.loads(result)
    assert data["ok"] is False
    assert "Invalid" in data["error"]


@pytest.mark.asyncio
async def test_pipeline_create_empty_steps(temp_presets_dir):
    result = await pipeline_create(
        pipeline_name="empty_steps",
        description="x",
        steps=[],
    )
    data = json.loads(result)
    assert data["ok"] is False


@pytest.mark.asyncio
async def test_pipeline_create_type_conflict(temp_presets_dir):
    result = await pipeline_create(
        pipeline_name="conflict",
        description="x",
        steps=[
            {"name": "s1", "description": "x", "browser_ops": [{"goto": "x"}], "tool_name": "t"},
        ],
    )
    data = json.loads(result)
    assert data["ok"] is False


# ── helpers ────────────────────────────────────────────────────

def test_resolve_pipeline_path():
    path = _resolve_pipeline_path("my_pipeline")
    assert path.name == "my_pipeline.pipeline.yaml"


def test_resolve_pipeline_path_invalid():
    with pytest.raises(ValueError):
        _resolve_pipeline_path("bad/name")


def test_dump_pipeline_yaml_roundtrip():
    from compiler.schema import PipelineYaml, StepYaml

    pipeline = PipelineYaml(
        name="test",
        description="desc",
        steps=[
            StepYaml(name="s1", description="d1", browser_ops=[{"goto": "https://x.com"}]),
        ],
    )
    yaml_str = _dump_pipeline_yaml(pipeline)
    assert "name: test" in yaml_str
    assert "browser_ops" in yaml_str
