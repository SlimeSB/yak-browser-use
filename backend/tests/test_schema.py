from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from yak_browser_use.compiler.schema import PipelineYaml, StepYaml, _convert_browser_op, ops_to_yaml
from yak_browser_use.compiler.models import StepDef, PipelineDef


class TestPipelineYaml:
    def test_minimal_valid(self):
        pipeline = PipelineYaml.model_validate({
            "name": "test",
            "steps": [{"name": "step1", "check": {"ignore": True}}],
        })
        assert pipeline.name == "test"
        assert len(pipeline.steps) == 1

    def test_missing_name(self):
        with pytest.raises(ValidationError) as exc:
            PipelineYaml.model_validate({
                "steps": [{"name": "step1", "check": {"ignore": True}}],
            })
        assert "name" in str(exc.value)

    def test_empty_steps(self):
        with pytest.raises(ValidationError) as exc:
            PipelineYaml.model_validate({
                "name": "test",
                "steps": [],
            })
        assert "steps" in str(exc.value)

    def test_mutual_exclusion_browser_and_goal(self):
        with pytest.raises(ValidationError) as exc:
            PipelineYaml.model_validate({
                "name": "test",
                "steps": [{
                    "name": "step1",
                    "browser_ops": [{"goto": "https://example.com"}],
                    "goal_description": "do something",
                    "check": {"ignore": True},
                }],
            })
        assert "mutually exclusive" in str(exc.value).lower()

    def test_no_type_fields_defaults_goal(self):
        pipeline = PipelineYaml.model_validate({
            "name": "test",
            "steps": [{"name": "step1", "check": {"ignore": True}}],
        })
        step = pipeline.steps[0]
        sd = step.to_step_def()
        assert sd.step_type == "goal"
        assert sd.is_goal is True


class TestStepYamlToStepDef:
    def test_browser_step(self):
        step = StepYaml.model_validate({
            "name": "打开首页",
            "browser_ops": [{"goto": "https://example.com"}],
            "check": {"ignore": True},
        })
        sd = step.to_step_def()
        assert sd.key == "打开首页"
        assert sd.step_type == "browser"
        assert sd.is_goal is False
        assert len(sd.browser_ops) == 1
        assert sd.browser_ops[0]["type"] == "goto"
        assert sd.browser_ops[0]["value"] == "https://example.com"

    def test_tool_step(self):
        step = StepYaml.model_validate({
            "name": "extract",
            "tool_name": "extract_table",
            "check": {"ignore": True},
        })
        sd = step.to_step_def()
        assert sd.step_type == "tool"
        assert sd.tool_name == "extract_table"
        assert sd.is_goal is False

    def test_goal_step(self):
        step = StepYaml.model_validate({
            "name": "analyze",
            "goal_description": "分析数据并生成报告",
            "check": {"ignore": True},
        })
        sd = step.to_step_def()
        assert sd.step_type == "goal"
        assert sd.is_goal is True
        assert sd.goal_description == "分析数据并生成报告"

    def test_key_from_name(self):
        step = StepYaml.model_validate({
            "name": "登录页面",
            "browser_ops": [{"click": "#login"}],
            "check": {"ignore": True},
        })
        sd = step.to_step_def()
        assert sd.key == "登录页面"

    def test_browser_op_goto(self):
        result = _convert_browser_op({"goto": "https://example.com"})
        assert result == {"type": "goto", "value": "https://example.com"}

    def test_browser_op_fill(self):
        result = _convert_browser_op({"fill": {"selector": "#input", "value": "hello"}})
        assert result == {"type": "fill", "selector": "#input", "value": "hello"}

    def test_browser_op_unknown_scalar(self):
        result = _convert_browser_op({"scroll": 300})
        assert result == {"type": "scroll", "value": 300}

    def test_ops_to_yaml_roundtrip(self):
        internal_ops = [
            {"type": "goto", "value": "https://example.com"},
            {"type": "fill", "selector": "#x", "value": "text"},
        ]
        yaml_ops = ops_to_yaml(internal_ops)
        assert yaml_ops == [
            {"goto": "https://example.com"},
            {"fill": {"selector": "#x", "value": "text"}},
        ]
        converted_back = [_convert_browser_op(op) for op in yaml_ops]
        assert converted_back == internal_ops


class TestCheckValidator:
    def test_valid_keys_pass(self):
        step = StepYaml.model_validate({
            "name": "s1",
            "check": {"url_contains": "example.com"},
        })
        assert step.check == {"url_contains": "example.com"}

    def test_ignore_valid(self):
        step = StepYaml.model_validate({
            "name": "s1",
            "check": {"ignore": True},
        })
        assert step.check == {"ignore": True}

    def test_empty_dict_rejected(self):
        with pytest.raises(ValidationError) as exc:
            StepYaml.model_validate({
                "name": "s1",
                "check": {},
            })
        assert "不能为空字典" in str(exc.value)

    def test_invalid_key_rejected(self):
        with pytest.raises(ValidationError) as exc:
            StepYaml.model_validate({
                "name": "s1",
                "check": {"foo": "bar"},
            })
        assert "不支持" in str(exc.value)

    def test_missing_check_rejected(self):
        with pytest.raises(ValidationError) as exc:
            StepYaml.model_validate({
                "name": "s1",
            })
        assert "check" in str(exc.value)


class TestPipelineYamlToPipelineDef:
    def test_to_pipeline_def(self):
        pipeline = PipelineYaml.model_validate({
            "name": "my_pipeline",
            "description": "test desc",
            "steps": [
                {"name": "step1", "browser_ops": [{"goto": "https://x.com"}], "check": {"ignore": True}},
                {"name": "step2", "tool_name": "extract", "check": {"ignore": True}},
            ],
        })
        agent = pipeline.to_pipeline_def()
        assert isinstance(agent, PipelineDef)
        assert agent.name == "my_pipeline"
        assert agent.description == "test desc"
        assert len(agent.steps) == 2
        assert agent.steps[0].step_type == "browser"
        assert agent.steps[1].step_type == "tool"
        assert "name" in agent.frontmatter

    def test_roundtrip(self):
        pipeline = PipelineYaml.model_validate({
            "name": "rt_test",
            "description": "round trip",
            "steps": [
                {"name": "s1", "browser_ops": [{"goto": "https://a.com"}], "check": {"ignore": True}},
                {"name": "s2", "goal_description": "do it", "check": {"ignore": True}},
            ],
        })
        agent = pipeline.to_pipeline_def()
        assert len(agent.steps) == 2
        assert agent.steps[0].step_type == "browser"
        assert agent.steps[1].step_type == "goal"
        assert agent.steps[1].is_goal is True
