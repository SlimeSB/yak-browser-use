"""Tests for converter.render — step rendering to pipeline.yaml format."""

from __future__ import annotations

import pytest
import yaml

from converter.render import (
    render_steps_to_pipeline,
    _validate_input,
    _dict_to_step_yaml,
)
from compiler.schema import StepYaml


class TestValidateInput:
    def test_valid_steps(self):
        steps = [{"name": "s1"}, {"name": "s2", "description": "test"}]
        _validate_input(steps)  # Should not raise

    def test_not_a_list(self):
        with pytest.raises(TypeError, match="must be a list"):
            _validate_input("not a list")

    def test_step_not_a_dict(self):
        with pytest.raises(TypeError, match="must be a dict"):
            _validate_input(["string instead of dict"])

    def test_step_missing_name(self):
        with pytest.raises(ValueError, match="missing required field"):
            _validate_input([{"description": "no name"}])

    def test_empty_steps_list(self):
        _validate_input([])  # Should not raise (empty list is fine)


class TestDictToStepYaml:
    def test_browser_step(self):
        step = {"name": "navigate", "step_type": "browser",
                "description": "Go to site", "ops": [{"type": "goto", "value": "https://x.com"}]}
        result = _dict_to_step_yaml(step)
        assert isinstance(result, StepYaml)
        assert result.name == "navigate"
        assert result.browser_ops == [{"goto": "https://x.com"}]

    def test_tool_step(self):
        step = {"name": "extract", "step_type": "tool", "tool_name": "extract_table",
                "description": "Extract data"}
        result = _dict_to_step_yaml(step)
        assert result.tool_name == "extract_table"
        assert result.browser_ops is None

    def test_goal_step(self):
        step = {"name": "analyze", "step_type": "goal",
                "description": "Analyze results"}
        result = _dict_to_step_yaml(step)
        assert result.goal_description == "Analyze results"

    def test_no_step_type_defaults_to_goal(self):
        step = {"name": "default", "description": "Auto goal"}
        result = _dict_to_step_yaml(step)
        assert result.goal_description == "Auto goal"

    def test_unknown_step_type_uses_goal(self):
        step = {"name": "custom", "step_type": "custom_type", "description": "Custom"}
        result = _dict_to_step_yaml(step)
        assert result.goal_description == "Custom"

    def test_with_input_ref(self):
        step = {"name": "process", "step_type": "tool", "tool_name": "my_tool",
                "input": "s1.result"}
        result = _dict_to_step_yaml(step)
        assert result.input_ref == "s1.result"

    def test_with_dict_input(self):
        step = {"name": "process", "step_type": "tool", "tool_name": "my_tool",
                "input": {"file": "s1.result"}}
        result = _dict_to_step_yaml(step)
        assert result.input_ref == {"file": "s1.result"}

    def test_with_output_ref(self):
        step = {"name": "extract", "step_type": "tool", "tool_name": "extract",
                "output": ["result.json", "summary.csv"]}
        result = _dict_to_step_yaml(step)
        assert len(result.output_ref) == 2
        assert "result.json" in result.output_ref or "result.csv" in str(result.output_ref)

    def test_with_depends_on(self):
        step = {"name": "s2", "step_type": "browser", "depends_on": ["s1"],
                "ops": [{"type": "click", "value": "#btn"}]}
        result = _dict_to_step_yaml(step)
        assert result.depends_on == ["s1"]

    def test_with_params(self):
        step = {"name": "s1", "step_type": "browser",
                "params": {"max_retries": 3, "timeout": 30},
                "ops": [{"type": "goto", "value": "https://x.com"}]}
        result = _dict_to_step_yaml(step)
        assert result.params == {"max_retries": 3, "timeout": 30}

    def test_browser_step_without_ops(self):
        """A browser step without ops produces no browser_ops."""
        step = {"name": "s1", "step_type": "browser", "ops": []}
        result = _dict_to_step_yaml(step)
        assert result.browser_ops is None  # empty ops list → None

    def test_unnamed_step_gets_default(self):
        step = {"step_type": "browser", "ops": [{"type": "goto", "value": "x"}]}
        result = _dict_to_step_yaml(step)
        assert result.name == "unnamed_step"


class TestRenderStepsToPipeline:
    def test_render_simple_pipeline(self):
        steps = [
            {"name": "navigate", "step_type": "browser",
             "description": "Go to site", "ops": [{"type": "goto", "value": "https://x.com"}]},
            {"name": "search", "step_type": "browser",
             "description": "Search", "ops": [{"type": "fill", "selector": "#q", "value": "test"}]},
        ]
        result = render_steps_to_pipeline(steps, pipeline_name="my_pipe", description="Test")
        assert isinstance(result, str)
        assert "name: my_pipe" in result
        assert "Test" in result
        data = yaml.safe_load(result)
        assert data["name"] == "my_pipe"
        assert len(data["steps"]) == 2

    def test_render_with_required_params(self):
        steps = [{"name": "s1", "step_type": "browser",
                  "ops": [{"type": "goto", "value": "{{url}}"}]}]
        result = render_steps_to_pipeline(steps, pipeline_name="param_pipe",
                                          required_params=["url"])
        data = yaml.safe_load(result)
        assert data["required_params"] == ["url"]

    def test_render_without_pipeline_name_defaults(self):
        steps = [{"name": "s1", "step_type": "goal", "description": "Do something"}]
        result = render_steps_to_pipeline(steps)
        assert "auto_generated" in result or "name:" in result

    def test_roundtrip(self):
        """Render then re-parse should produce same structure."""
        steps = [
            {"name": "s1", "step_type": "browser",
             "ops": [{"type": "goto", "value": "https://x.com"}]},
            {"name": "s2", "step_type": "tool", "tool_name": "extract"},
            {"name": "s3", "step_type": "goal", "description": "Analyze"},
        ]
        yaml_text = render_steps_to_pipeline(steps, pipeline_name="rt_test")
        data = yaml.safe_load(yaml_text)
        assert data["name"] == "rt_test"
        assert len(data["steps"]) == 3
        # Step types preserved
        assert data["steps"][0]["browser_ops"] is not None
        assert data["steps"][1]["tool_name"] == "extract"
        assert data["steps"][2]["goal_description"] is not None

    def test_render_preserves_depends_on(self):
        steps = [
            {"name": "s1", "step_type": "browser", "ops": [{"type": "goto", "value": "x"}]},
            {"name": "s2", "step_type": "browser", "depends_on": ["s1"],
             "ops": [{"type": "click", "value": "#btn"}]},
        ]
        result = render_steps_to_pipeline(steps, pipeline_name="deps")
        data = yaml.safe_load(result)
        assert data["steps"][1]["depends_on"] == ["s1"]
