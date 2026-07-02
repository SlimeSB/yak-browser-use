"""Tests for PipelineStore — format conversion, round-trip, strip, CRUD, meta.

Phase 2: tests use PipelineStore APIs directly (replaced oracle from Phase 1).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from yak_browser_use.compiler.pipeline_store import PipelineMeta, PipelineStore
from yak_browser_use.compiler.schema import PipelineYaml, StepYaml


# ═══════════════════════════════════════════════════════════════════
# 1. 格式转换 round-trip：_from_yaml_ops ↔ _to_yaml_ops
# ═══════════════════════════════════════════════════════════════════

class TestFormatConversionRoundTrip:
    """PipelineStore format conversion methods are inverses of each other."""

    def test_goto_roundtrip(self):
        internal = [{"type": "goto", "value": "https://example.com"}]
        yaml_ops = PipelineStore._to_yaml_ops(internal)
        assert yaml_ops == [{"goto": "https://example.com"}]
        back = PipelineStore._from_yaml_ops(yaml_ops)
        assert back == internal

    def test_fill_roundtrip(self):
        internal = [{"type": "fill", "selector": "#q", "value": "search term"}]
        yaml_ops = PipelineStore._to_yaml_ops(internal)
        assert yaml_ops == [{"fill": {"selector": "#q", "value": "search term"}}]
        back = PipelineStore._from_yaml_ops(yaml_ops)
        assert back == internal

    def test_click_scalar_roundtrip(self):
        internal = [{"type": "click", "value": "#submit-btn"}]
        yaml_ops = PipelineStore._to_yaml_ops(internal)
        assert yaml_ops == [{"click": "#submit-btn"}]
        back = PipelineStore._from_yaml_ops(yaml_ops)
        assert back == internal

    def test_click_dict_roundtrip(self):
        internal = [{"type": "click", "selector": "#a", "index": 2}]
        yaml_ops = PipelineStore._to_yaml_ops(internal)
        assert yaml_ops == [{"click": {"selector": "#a", "index": 2}}]
        back = PipelineStore._from_yaml_ops(yaml_ops)
        assert back == internal

    def test_scroll_roundtrip(self):
        internal = [{"type": "scroll", "value": 300}]
        yaml_ops = PipelineStore._to_yaml_ops(internal)
        assert yaml_ops == [{"scroll": 300}]
        back = PipelineStore._from_yaml_ops(yaml_ops)
        assert back == internal

    def test_js_roundtrip(self):
        internal = [{"type": "js", "value": "document.title"}]
        yaml_ops = PipelineStore._to_yaml_ops(internal)
        assert yaml_ops == [{"js": "document.title"}]
        back = PipelineStore._from_yaml_ops(yaml_ops)
        assert back == internal

    def test_wait_for_network_roundtrip(self):
        internal = [{"type": "wait_for_network", "value": "idle"}]
        yaml_ops = PipelineStore._to_yaml_ops(internal)
        assert yaml_ops == [{"wait_for_network": "idle"}]
        back = PipelineStore._from_yaml_ops(yaml_ops)
        assert back == internal

    def test_snapshot_roundtrip(self):
        internal = [{"type": "snapshot", "value": "interactive"}]
        yaml_ops = PipelineStore._to_yaml_ops(internal)
        assert yaml_ops == [{"snapshot": "interactive"}]
        back = PipelineStore._from_yaml_ops(yaml_ops)
        assert back == internal

    def test_ops_to_yaml_empty_value(self):
        internal = [{"type": "click", "value": ""}]
        yaml_ops = PipelineStore._to_yaml_ops(internal)
        assert yaml_ops == [{"click": ""}]
        back = PipelineStore._from_yaml_ops(yaml_ops)
        assert back == internal

    def test_ops_to_yaml_no_value_key(self):
        internal = [{"type": "click"}]
        yaml_ops = PipelineStore._to_yaml_ops(internal)
        assert yaml_ops == [{"click": ""}]
        back = PipelineStore._from_yaml_ops(yaml_ops)
        assert back[0]["type"] == "click"
        assert back[0]["value"] == ""


# ═══════════════════════════════════════════════════════════════════
# 2. browser_ops 各类型覆盖 + meta key（retry, optional）
# ═══════════════════════════════════════════════════════════════════

class TestBrowserOpsTypeCoverage:
    """Cover all known browser op types through PipelineStore format conversion."""

    @pytest.mark.parametrize("op_type,yaml_input,expected_internal", [
        ("goto", {"goto": "https://x.com"}, {"type": "goto", "value": "https://x.com"}),
        ("fill", {"fill": {"selector": "#q", "value": "hello"}}, {"type": "fill", "selector": "#q", "value": "hello"}),
        ("click", {"click": "#btn"}, {"type": "click", "value": "#btn"}),
        ("scroll", {"scroll": 500}, {"type": "scroll", "value": 500}),
        ("js", {"js": "console.log(1)"}, {"type": "js", "value": "console.log(1)"}),
    ])
    def test_yaml_to_internal(self, op_type, yaml_input, expected_internal):
        result = PipelineStore._from_yaml_ops([yaml_input])[0]
        assert result == expected_internal
        assert result["type"] == op_type

    def test_meta_key_retry_roundtrip(self):
        yaml_input = {"goto": "https://x.com", "retry": 3, "optional": True}
        internal = PipelineStore._from_yaml_ops([yaml_input])[0]
        assert internal == {"type": "goto", "value": "https://x.com", "retry": 3, "optional": True}
        yaml_back = PipelineStore._to_yaml_ops([internal])
        assert yaml_back[0] == {"goto": "https://x.com", "retry": 3, "optional": True}

    def test_meta_key_only_retry_roundtrip(self):
        yaml_input = {"click": "#btn", "retry": 2}
        internal = PipelineStore._from_yaml_ops([yaml_input])[0]
        assert internal == {"type": "click", "value": "#btn", "retry": 2}
        yaml_back = PipelineStore._to_yaml_ops([internal])
        assert yaml_back[0] == {"click": "#btn", "retry": 2}

    def test_already_internal_format_passthrough(self):
        internal = {"type": "goto", "value": "https://x.com", "retry": 1}
        result = PipelineStore._from_yaml_ops([internal])[0]
        assert result == internal

    def test_empty_op_is_skipped(self):
        result = PipelineStore._from_yaml_ops([{}])
        assert result == []


# ═══════════════════════════════════════════════════════════════════
# 3. PipelineYaml validate → to_yaml → validate round-trip
# ═══════════════════════════════════════════════════════════════════

SAMPLE_YAML_TEXT = textwrap.dedent("""\
    name: roundtrip_test
    description: Test round-trip behavior
    required_params:
    - keyword
    steps:
    - name: step_1
      description: Navigate
      browser_ops:
      - goto: https://example.com
    - name: step_2
      description: Search
      browser_ops:
      - fill:
          selector: '#q'
          value: test
      depends_on:
      - step_1
    - name: step_3
      description: Tool step
      tool_name: my_tool
      params:
        format: csv
    - name: step_4
      description: Goal
      goal_description: Analyze results
""")


class TestPipelineLoadDumpRoundTrip:
    """Test that PipelineStore.validate + to_yaml produces equivalent data."""

    def test_from_yaml_converts_to_internal_format(self):
        """PipelineStore.from_yaml should convert browser_ops to internal format."""
        pipeline = PipelineStore.from_yaml(SAMPLE_YAML_TEXT)
        assert pipeline.name == "roundtrip_test"
        assert len(pipeline.steps) == 4

        assert pipeline.steps[0].browser_ops == [{"type": "goto", "value": "https://example.com"}]
        assert pipeline.steps[1].browser_ops == [{"type": "fill", "selector": "#q", "value": "test"}]
        assert pipeline.steps[2].tool_name == "my_tool"
        assert pipeline.steps[3].goal_description == "Analyze results"

    def test_dump_strips_defaults(self):
        """PipelineStore.to_yaml removes default values via _strip_defaults."""
        pipeline = PipelineStore.from_yaml(SAMPLE_YAML_TEXT)
        yaml_str = PipelineStore.to_yaml(pipeline)

        assert "name: roundtrip_test" in yaml_str
        assert "goto: https://example.com" in yaml_str
        assert "system_prompt" not in yaml_str

    def test_dump_reload_semantic_equivalence(self, tmp_path):
        pipeline = PipelineStore.from_yaml(SAMPLE_YAML_TEXT)
        yaml_str = PipelineStore.to_yaml(pipeline)
        path = tmp_path / "test_pipe" / "pipeline.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml_str, encoding="utf-8")

        reloaded = PipelineStore.validate(path.read_text(encoding="utf-8"))

        assert reloaded.name == pipeline.name
        assert reloaded.description == pipeline.description
        assert len(reloaded.steps) == len(pipeline.steps)
        assert reloaded.required_params == pipeline.required_params

        for orig, reload in zip(pipeline.steps, reloaded.steps):
            assert orig.name == reload.name
            assert orig.description == reload.description

    def test_dump_reload_to_step_def_equivalence(self, tmp_path):
        pipeline = PipelineStore.from_yaml(SAMPLE_YAML_TEXT)
        original_defs = [s.to_step_def() for s in pipeline.steps]

        yaml_str = PipelineStore.to_yaml(pipeline)
        path = tmp_path / "test_pipe" / "pipeline.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml_str, encoding="utf-8")

        reloaded = PipelineStore.validate(path.read_text(encoding="utf-8"))
        reloaded_defs = [s.to_step_def() for s in reloaded.steps]

        for orig_sd, reload_sd in zip(original_defs, reloaded_defs):
            assert orig_sd.key == reload_sd.key
            assert orig_sd.step_type == reload_sd.step_type
            assert orig_sd.is_goal == reload_sd.is_goal
            assert orig_sd.browser_ops == reload_sd.browser_ops
            assert orig_sd.tool_name == reload_sd.tool_name
            assert orig_sd.goal_description == reload_sd.goal_description


# ═══════════════════════════════════════════════════════════════════
# 4. _strip_defaults 快照测试 — 替代 exclude_defaults=True
# ═══════════════════════════════════════════════════════════════════

class TestStripDefaults:
    """Document what PipelineStore._strip_defaults removes from output."""

    def test_default_fields_excluded(self):
        pipeline = PipelineYaml(
            name="snap_test",
            steps=[
                StepYaml(name="s1", browser_ops=[{"goto": "https://x.com"}]),
            ],
        )
        yaml_str = PipelineStore.to_yaml(pipeline)
        assert "system_prompt" not in yaml_str
        assert "url_aliases" not in yaml_str
        assert "required_params" not in yaml_str

    def test_description_empty_excluded(self):
        pipeline = PipelineYaml(
            name="snap_test",
            description="",
            steps=[
                StepYaml(name="s1", description="keep_me", browser_ops=[{"goto": "x"}]),
                StepYaml(name="s2", description="", browser_ops=[{"click": "y"}]),
            ],
        )
        data = pipeline.model_dump()
        stripped = PipelineStore._strip_defaults(data)
        assert "description" not in stripped
        assert stripped["steps"][0]["description"] == "keep_me"
        assert "description" not in stripped["steps"][1]

    def test_empty_params_excluded(self):
        step = StepYaml(name="s1", browser_ops=[{"goto": "x"}], params={})
        pipeline = PipelineYaml(name="test", steps=[step])
        data = pipeline.model_dump()
        stripped = PipelineStore._strip_defaults(data)
        assert "params" not in stripped["steps"][0]

    def test_empty_input_schema_excluded(self):
        step = StepYaml(name="s1", browser_ops=[{"goto": "x"}], input_schema={}, output_schema={})
        pipeline = PipelineYaml(name="test", steps=[step])
        data = pipeline.model_dump()
        stripped = PipelineStore._strip_defaults(data)
        assert "input_schema" not in stripped["steps"][0]
        assert "output_schema" not in stripped["steps"][0]

    def test_empty_depends_on_excluded(self):
        step = StepYaml(name="s1", description="no deps", browser_ops=[{"goto": "x"}], depends_on=[])
        pipeline = PipelineYaml(name="test", steps=[step])
        yaml_str = PipelineStore.to_yaml(pipeline)
        assert "depends_on" not in yaml_str

    def test_non_default_values_preserved(self):
        step = StepYaml(
            name="s1", description="has deps", browser_ops=[{"goto": "x"}],
            depends_on=["s0"], params={"format": "csv"},
        )
        pipeline = PipelineYaml(name="test", steps=[step])
        yaml_str = PipelineStore.to_yaml(pipeline)

        assert "depends_on" in yaml_str
        assert "s0" in yaml_str
        assert "params" in yaml_str
        assert "format" in yaml_str

    def test_strip_defaults_behavior(self):
        step = StepYaml(name="s1", description="test", browser_ops=[{"goto": "x"}])
        pipeline = PipelineYaml(name="test", steps=[step])
        data = pipeline.model_dump()
        stripped = PipelineStore._strip_defaults(data)
        assert "system_prompt" not in stripped
        assert "url_aliases" not in stripped
        assert "required_params" not in stripped


# ═══════════════════════════════════════════════════════════════════
# 5. PipelineStore.load 返回内部格式 browser_ops
# ═══════════════════════════════════════════════════════════════════

class TestPipelineStoreLoad:
    """PipelineStore.load returns internal-format browser_ops."""

    def test_browser_ops_is_internal_format_after_load(self, tmp_path):
        dir_path = tmp_path / "test_pipe"
        dir_path.mkdir(parents=True, exist_ok=True)
        yaml_text = textwrap.dedent("""\
            name: test
            steps:
            - name: step1
              browser_ops:
              - goto: https://x.com
              - fill:
                  selector: '#q'
                  value: text
        """)
        pipe_path = dir_path / "pipeline.yaml"
        pipe_path.write_text(yaml_text, encoding="utf-8")

        store = PipelineStore(workspaces_root=tmp_path)
        validated = store.load("test_pipe")

        step = validated.steps[0]
        assert step.browser_ops == [
            {"type": "goto", "value": "https://x.com"},
            {"type": "fill", "selector": "#q", "value": "text"},
        ]
        assert "type" in step.browser_ops[0]
        assert "goto" not in step.browser_ops[0]

    def test_load_raises_on_missing(self):
        store = PipelineStore()
        with pytest.raises(FileNotFoundError):
            store.load("nonexistent_pipeline")


# ═══════════════════════════════════════════════════════════════════
# 6. PipelineStore.load_meta
# ═══════════════════════════════════════════════════════════════════

class TestPipelineStoreLoadMeta:
    """PipelineStore.load_meta returns lightweight PipelineMeta."""

    def test_load_meta_basic(self, tmp_path):
        dir_path = tmp_path / "test_meta"
        dir_path.mkdir(parents=True, exist_ok=True)
        yaml_text = textwrap.dedent("""\
            name: test_meta
            description: A test
            steps:
            - name: s1
              browser_ops:
              - goto: x
            - name: s2
              browser_ops:
              - click: y
        """)
        pipe_path = dir_path / "pipeline.yaml"
        pipe_path.write_text(yaml_text, encoding="utf-8")

        store = PipelineStore(workspaces_root=tmp_path)
        meta = store.load_meta("test_meta")
        assert meta.name == "test_meta"
        assert meta.description == "A test"
        assert meta.step_count == 2

    def test_load_meta_handles_parse_error(self, tmp_path):
        dir_path = tmp_path / "bad_meta"
        dir_path.mkdir(parents=True, exist_ok=True)
        pipe_path = dir_path / "pipeline.yaml"
        pipe_path.write_text("{{invalid yaml", encoding="utf-8")

        store = PipelineStore(workspaces_root=tmp_path)
        meta = store.load_meta("bad_meta")
        assert meta.description == "(parse error)"
        assert meta.step_count == 0


# ═══════════════════════════════════════════════════════════════════
# 7. PipelineStore CRUD: update_step, add_step, remove_step
# ═══════════════════════════════════════════════════════════════════

class TestPipelineStoreCrud:
    """PipelineStore add/update/remove step operations."""

    def test_update_step_browser_ops(self):
        pipeline = PipelineStore.from_yaml(SAMPLE_YAML_TEXT)
        store = PipelineStore()
        store.update_step(pipeline, "step_1", {"browser_ops": [{"click": "#btn"}]})
        assert pipeline.steps[0].browser_ops == [{"type": "click", "value": "#btn"}]

    def test_update_step_description_and_depends(self):
        pipeline = PipelineStore.from_yaml(SAMPLE_YAML_TEXT)
        store = PipelineStore()
        store.update_step(pipeline, "step_1", {"description": "updated", "depends_on": ["step_0"]})
        assert pipeline.steps[0].description == "updated"
        assert pipeline.steps[0].depends_on == ["step_0"]

    def test_add_step(self):
        pipeline = PipelineStore.from_yaml(SAMPLE_YAML_TEXT)
        store = PipelineStore()
        new_step = StepYaml(name="new_step", browser_ops=[{"goto": "https://new.com"}])
        store.add_step(pipeline, new_step)
        assert len(pipeline.steps) == 5
        assert pipeline.steps[4].name == "new_step"
        assert pipeline.steps[4].browser_ops == [{"type": "goto", "value": "https://new.com"}]

    def test_add_step_after(self):
        pipeline = PipelineStore.from_yaml(SAMPLE_YAML_TEXT)
        store = PipelineStore()
        new_step = StepYaml(name="after_step", browser_ops=[{"scroll": 100}])
        store.add_step(pipeline, new_step, after="step_1")
        assert len(pipeline.steps) == 5
        assert pipeline.steps[1].name == "after_step"

    def test_add_step_duplicate_raises(self):
        pipeline = PipelineStore.from_yaml(SAMPLE_YAML_TEXT)
        store = PipelineStore()
        dup = StepYaml(name="step_1", browser_ops=[{"goto": "x"}])
        with pytest.raises(ValueError, match="already exists"):
            store.add_step(pipeline, dup)

    def test_remove_step(self):
        pipeline = PipelineStore.from_yaml(SAMPLE_YAML_TEXT)
        store = PipelineStore()
        store.remove_step(pipeline, "step_1")
        assert len(pipeline.steps) == 3
        assert pipeline.steps[0].name == "step_2"

    def test_remove_step_cleans_depends_on(self):
        pipeline = PipelineStore.from_yaml(SAMPLE_YAML_TEXT)
        store = PipelineStore()
        store.remove_step(pipeline, "step_1")
        assert "step_1" not in pipeline.steps[0].depends_on

    # ── deep-path updates ──

    def test_update_step_deep_path_browser_ops(self):
        pipeline = PipelineStore.from_yaml(SAMPLE_YAML_TEXT)
        store = PipelineStore()
        store.update_step(pipeline, "step_2", {"browser_ops[0].value": "patched"})
        assert pipeline.steps[1].browser_ops[0]["value"] == "patched"
        assert pipeline.steps[1].browser_ops[0]["type"] == "fill"

    def test_update_step_deep_path_with_hyphen(self):
        pipeline = PipelineStore.from_yaml(SAMPLE_YAML_TEXT)
        store = PipelineStore()
        store.update_step(pipeline, "step_1", {"browser_ops[0].value": "https://patched.com"})
        assert pipeline.steps[0].browser_ops[0]["value"] == "https://patched.com"

    def test_update_step_deep_path_index_out_of_range(self):
        pipeline = PipelineStore.from_yaml(SAMPLE_YAML_TEXT)
        store = PipelineStore()
        with pytest.raises(ValueError, match="out of range"):
            store.update_step(pipeline, "step_1", {"browser_ops[99].value": "x"})

    def test_update_step_deep_path_not_a_list(self):
        pipeline = PipelineStore.from_yaml(SAMPLE_YAML_TEXT)
        store = PipelineStore()
        with pytest.raises(ValueError, match="not a list"):
            store.update_step(pipeline, "step_1", {"description[0].x": "y"})

    def test_update_step_deep_path_mixed_with_normal(self):
        pipeline = PipelineStore.from_yaml(SAMPLE_YAML_TEXT)
        store = PipelineStore()
        store.update_step(pipeline, "step_2", {
            "browser_ops[0].value": "deep_val",
            "description": "new description",
        })
        assert pipeline.steps[1].browser_ops[0]["value"] == "deep_val"
        assert pipeline.steps[1].description == "new description"


# ═══════════════════════════════════════════════════════════════════
# 8. PipelineStore.save round-trip via file
# ═══════════════════════════════════════════════════════════════════

class TestPipelineStoreSave:
    """PipelineStore.save writes to disk and can be read back."""

    def test_save_and_reload(self, tmp_path):
        pipeline = PipelineStore.from_yaml(SAMPLE_YAML_TEXT)
        store = PipelineStore(workspaces_root=tmp_path)
        store.save("save_test", pipeline)

        reloaded = store.load("save_test")
        assert reloaded.name == pipeline.name
        assert len(reloaded.steps) == len(pipeline.steps)
        assert reloaded.steps[0].browser_ops == pipeline.steps[0].browser_ops


# ═══════════════════════════════════════════════════════════════════
# 9. PipelineStore.ops_to_yaml 公开工具
# ═══════════════════════════════════════════════════════════════════

class TestOpsToYamlPublic:
    """PipelineStore.ops_to_yaml is a public utility."""

    def test_ops_to_yaml(self):
        internal = [{"type": "goto", "value": "https://x.com"}]
        yaml_ops = PipelineStore.ops_to_yaml(internal)
        assert yaml_ops == [{"goto": "https://x.com"}]
