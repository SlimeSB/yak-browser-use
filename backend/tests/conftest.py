"""Shared fixtures and test data for yak-browser-use tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# ── Common test data ──────────────────────────────────────────

SAMPLE_PIPELINE_YAML = {
    "name": "test_pipeline",
    "description": "A test pipeline for unit tests",
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
def sample_pipeline_yaml(tmp_path) -> Path:
    """Create a valid pipeline.yaml file in tmp_path."""
    path = tmp_path / "test_pipeline.pipeline.yaml"
    path.write_text(
        yaml.dump(SAMPLE_PIPELINE_YAML, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


# ── StepDef and PipelineDef fixtures ──────────────────────────

from compiler.models import StepDef, PipelineDef


@pytest.fixture
def sample_step_defs() -> list[StepDef]:
    """Return a list of StepDefs for graph/parser tests."""
    return [
        StepDef(key="s1", name="Navigate", step_type="browser",
                browser_ops=[{"type": "goto", "value": "https://x.com"}]),
        StepDef(key="s2", name="Search", step_type="browser",
                browser_ops=[{"type": "fill", "selector": "#q", "value": "test"}],
                depends_on=["s1"]),
        StepDef(key="s3", name="Extract", tool_name="extract_table", step_type="tool",
                depends_on=["s2"]),
        StepDef(key="s4", name="Analyze", step_type="goal",
                goal_description="Analyze results", is_goal=True),
    ]


@pytest.fixture
def sample_pipeline_def(sample_step_defs) -> PipelineDef:
    return PipelineDef(
        name="test",
        description="Test pipeline",
        steps=sample_step_defs,
        frontmatter={"name": "test", "description": "Test pipeline"},
    )


# ── Step dicts for executor tests ─────────────────────────────

@pytest.fixture
def sample_browser_step() -> dict:
    return {
        "name": "navigate_and_search",
        "step_type": "browser",
        "browser_ops": [
            {"type": "goto", "value": "https://example.com"},
            {"type": "fill", "selector": "#q", "value": "test"},
        ],
        "params": {},
    }


@pytest.fixture
def sample_tool_step() -> dict:
    return {
        "name": "extract_data",
        "step_type": "tool",
        "tool_name": "extract_table",
        "input": {"table": "step_1.table_data"},
        "output": ["result.json"],
        "params": {"format": "csv"},
    }


@pytest.fixture
def sample_goal_step() -> dict:
    return {
        "name": "analyze_results",
        "step_type": "goal",
        "goal_description": "Analyze the extracted data and generate a summary",
        "system_prompt": "You are a data analyst.",
    }
