"""Green tests: characterization tests that lock down current behavior before PipelineStore refactoring.

Phase 1 — tests pass against CURRENT code. After PipelineStore is built (Phase 2),
these same tests will be migrated to use PipelineStore APIs and must STILL pass.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from yak_browser_use.compiler.schema import (
    PipelineYaml,
    StepYaml,
    _convert_browser_op,
    ops_to_yaml,
)
from yak_browser_use.compiler.models import StepDef
from yak_browser_use.engine._harness.pipeline_tools import (
    _dump_pipeline_yaml,
    _load_pipeline_yaml,
)


# ═══════════════════════════════════════════════════════════════════
# 1. 格式转换 round-trip：_convert_browser_op ↔ ops_to_yaml
# ═══════════════════════════════════════════════════════════════════

class TestFormatConversionRoundTrip:
    """Test that current conversion functions are inverses of each other."""

    def test_goto_roundtrip(self):
        internal = [{"type": "goto", "value": "https://example.com"}]
        yaml_ops = ops_to_yaml(internal)
        assert yaml_ops == [{"goto": "https://example.com"}]
        back = [_convert_browser_op(op) for op in yaml_ops]
        assert back == internal

    def test_fill_roundtrip(self):
        internal = [{"type": "fill", "selector": "#q", "value": "search term"}]
        yaml_ops = ops_to_yaml(internal)
        assert yaml_ops == [{"fill": {"selector": "#q", "value": "search term"}}]
        back = [_convert_browser_op(op) for op in yaml_ops]
        assert back == internal

    def test_click_scalar_roundtrip(self):
        internal = [{"type": "click", "value": "#submit-btn"}]
        yaml_ops = ops_to_yaml(internal)
        assert yaml_ops == [{"click": "#submit-btn"}]
        back = [_convert_browser_op(op) for op in yaml_ops]
        assert back == internal

    def test_click_dict_roundtrip(self):
        internal = [{"type": "click", "selector": "#a", "index": 2}]
        yaml_ops = ops_to_yaml(internal)
        assert yaml_ops == [{"click": {"selector": "#a", "index": 2}}]
        back = [_convert_browser_op(op) for op in yaml_ops]
        assert back == internal

    def test_scroll_roundtrip(self):
        internal = [{"type": "scroll", "value": 300}]
        yaml_ops = ops_to_yaml(internal)
        assert yaml_ops == [{"scroll": 300}]
        back = [_convert_browser_op(op) for op in yaml_ops]
        assert back == internal

    def test_js_roundtrip(self):
        internal = [{"type": "js", "value": "document.title"}]
        yaml_ops = ops_to_yaml(internal)
        assert yaml_ops == [{"js": "document.title"}]
        back = [_convert_browser_op(op) for op in yaml_ops]
        assert back == internal

    def test_wait_for_network_roundtrip(self):
        internal = [{"type": "wait_for_network", "value": "idle"}]
        yaml_ops = ops_to_yaml(internal)
        assert yaml_ops == [{"wait_for_network": "idle"}]
        back = [_convert_browser_op(op) for op in yaml_ops]
        assert back == internal

    def test_snapshot_roundtrip(self):
        internal = [{"type": "snapshot", "value": "interactive"}]
        yaml_ops = ops_to_yaml(internal)
        assert yaml_ops == [{"snapshot": "interactive"}]
        back = [_convert_browser_op(op) for op in yaml_ops]
        assert back == internal

    def test_ops_to_yaml_empty_value(self):
        internal = [{"type": "click", "value": ""}]
        yaml_ops = ops_to_yaml(internal)
        # If value is "" and no other keys, it becomes {click: ""} (single remaining key)
        assert yaml_ops == [{"click": ""}]
        back = [_convert_browser_op(op) for op in yaml_ops]
        assert back == internal

    def test_ops_to_yaml_no_value_key(self):
        internal = [{"type": "click"}]
        yaml_ops = ops_to_yaml(internal)
        # No "value" key and no other keys → falls through to else: {click: op.get("value", "")}
        assert yaml_ops == [{"click": ""}]
        back = [_convert_browser_op(op) for op in yaml_ops]
        # Round-trip: type=click, value="" — keys besides type/value are just "value": ""
        assert back[0]["type"] == "click"
        assert back[0]["value"] == ""


# ═══════════════════════════════════════════════════════════════════
# 2. browser_ops 各类型覆盖 + meta key（retry, optional）
# ═══════════════════════════════════════════════════════════════════

class TestBrowserOpsTypeCoverage:
    """Cover all known browser op types through _convert_browser_op and ops_to_yaml."""

    @pytest.mark.parametrize("op_type,yaml_input,expected_internal", [
        ("goto", {"goto": "https://x.com"}, {"type": "goto", "value": "https://x.com"}),
        ("fill", {"fill": {"selector": "#q", "value": "hello"}}, {"type": "fill", "selector": "#q", "value": "hello"}),
        ("click", {"click": "#btn"}, {"type": "click", "value": "#btn"}),
        ("scroll", {"scroll": 500}, {"type": "scroll", "value": 500}),
        ("js", {"js": "console.log(1)"}, {"type": "js", "value": "console.log(1)"}),
    ])
    def test_yaml_to_internal(self, op_type, yaml_input, expected_internal):
        result = _convert_browser_op(yaml_input)
        assert result == expected_internal
        assert result["type"] == op_type

    def test_meta_key_retry_roundtrip(self):
        """retry and optional meta keys survive round-trip."""
        yaml_input = {"goto": "https://x.com", "retry": 3, "optional": True}
        internal = _convert_browser_op(yaml_input)
        assert internal == {"type": "goto", "value": "https://x.com", "retry": 3, "optional": True}
        yaml_back = ops_to_yaml([internal])
        assert yaml_back[0] == {"goto": "https://x.com", "retry": 3, "optional": True}

    def test_meta_key_only_retry_roundtrip(self):
        yaml_input = {"click": "#btn", "retry": 2}
        internal = _convert_browser_op(yaml_input)
        assert internal == {"type": "click", "value": "#btn", "retry": 2}
        yaml_back = ops_to_yaml([internal])
        assert yaml_back[0] == {"click": "#btn", "retry": 2}

    def test_already_internal_format_passthrough(self):
        """_convert_browser_op should pass through already-internal format."""
        internal = {"type": "goto", "value": "https://x.com", "retry": 1}
        result = _convert_browser_op(internal)
        assert result == internal

    def test_empty_op_converts_to_empty(self):
        result = _convert_browser_op({})
        assert result == {}


# ═══════════════════════════════════════════════════════════════════
# 3. PipelineYaml load → model_dump → yaml_text → load round-trip
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
    """Test that loading YAML, dumping it, and re-loading produces equivalent data."""

    def test_load_from_yaml_text(self):
        pipeline = PipelineYaml.model_validate(yaml.safe_load(SAMPLE_YAML_TEXT))
        assert pipeline.name == "roundtrip_test"
        assert len(pipeline.steps) == 4

        assert pipeline.steps[0].browser_ops == [{"goto": "https://example.com"}]
        assert pipeline.steps[1].browser_ops == [{"fill": {"selector": "#q", "value": "test"}}]
        assert pipeline.steps[2].tool_name == "my_tool"
        assert pipeline.steps[3].goal_description == "Analyze results"

    def test_dump_with_exclude_defaults(self):
        """Snapshot: what _dump_pipeline_yaml removes with exclude_defaults=True."""
        pipeline = PipelineYaml.model_validate(yaml.safe_load(SAMPLE_YAML_TEXT))
        yaml_str = _dump_pipeline_yaml(pipeline)

        assert "name: roundtrip_test" in yaml_str
        assert "goto: https://example.com" in yaml_str
        # system_prompt default "" should NOT appear
        assert "system_prompt" not in yaml_str

    def test_dump_reload_semantic_equivalence(self, tmp_path):
        """Dump → write to file → reload → to_step_def produces same StepDef."""
        pipeline = PipelineYaml.model_validate(yaml.safe_load(SAMPLE_YAML_TEXT))

        yaml_str = _dump_pipeline_yaml(pipeline)
        path = tmp_path / "test_pipe" / "pipeline.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml_str, encoding="utf-8")

        reloaded_raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        reloaded = PipelineYaml.model_validate(reloaded_raw)

        assert reloaded.name == pipeline.name
        assert reloaded.description == pipeline.description
        assert len(reloaded.steps) == len(pipeline.steps)
        assert reloaded.required_params == pipeline.required_params

        for orig, reload in zip(pipeline.steps, reloaded.steps):
            assert orig.name == reload.name
            assert orig.description == reload.description

    def test_dump_reload_to_step_def_equivalence(self, tmp_path):
        """The StepDef produced before and after dump+reload should be identical."""
        pipeline = PipelineYaml.model_validate(yaml.safe_load(SAMPLE_YAML_TEXT))
        original_defs = [s.to_step_def() for s in pipeline.steps]

        yaml_str = _dump_pipeline_yaml(pipeline)
        path = tmp_path / "test_pipe" / "pipeline.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml_str, encoding="utf-8")

        reloaded_raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        reloaded = PipelineYaml.model_validate(reloaded_raw)
        reloaded_defs = [s.to_step_def() for s in reloaded.steps]

        for orig_sd, reload_sd in zip(original_defs, reloaded_defs):
            assert orig_sd.key == reload_sd.key
            assert orig_sd.step_type == reload_sd.step_type
            assert orig_sd.is_goal == reload_sd.is_goal
            assert orig_sd.browser_ops == reload_sd.browser_ops
            assert orig_sd.tool_name == reload_sd.tool_name
            assert orig_sd.goal_description == reload_sd.goal_description


# ═══════════════════════════════════════════════════════════════════
# 4. exclude_defaults 快照测试 — 记录当前输出行为
# ═══════════════════════════════════════════════════════════════════

class TestExcludeDefaultsSnapshot:
    """Document what exclude_defaults=True currently removes from output."""

    def test_default_fields_excluded(self):
        """Top-level defaults (system_prompt, url_aliases, required_params) excluded."""
        pipeline = PipelineYaml(
            name="snap_test",
            steps=[
                StepYaml(name="s1", browser_ops=[{"goto": "https://x.com"}]),
            ],
        )
        yaml_str = _dump_pipeline_yaml(pipeline)

        # Top-level default fields should NOT appear
        assert "system_prompt" not in yaml_str, "default system_prompt='' should be excluded"
        assert "url_aliases" not in yaml_str, "default url_aliases={} should be excluded"
        assert "required_params" not in yaml_str, "default required_params=[] should be excluded"

    def test_description_empty_excluded(self):
        """Pipeline description='' is excluded, but step description='x' must remain."""
        pipeline = PipelineYaml(
            name="snap_test",
            description="",
            steps=[
                StepYaml(name="s1", description="keep_me", browser_ops=[{"goto": "x"}]),
                StepYaml(name="s2", description="", browser_ops=[{"click": "y"}]),
            ],
        )
        dump = pipeline.model_dump(exclude_defaults=True)
        # Pipeline-level description="" → excluded
        assert "description" not in dump, dump
        # Step-level: s1 has non-default desc → present; s2 has default → excluded
        assert dump["steps"][0]["description"] == "keep_me"
        assert "description" not in dump["steps"][1]

    def test_empty_params_excluded(self):
        """Params={} in a step is excluded by exclude_defaults."""
        step = StepYaml(
            name="s1",
            browser_ops=[{"goto": "x"}],
            params={},
        )
        pipeline = PipelineYaml(name="test", steps=[step])
        dump = pipeline.model_dump(exclude_defaults=True)
        assert "params" not in dump["steps"][0]

    def test_empty_input_schema_excluded(self):
        step = StepYaml(
            name="s1",
            browser_ops=[{"goto": "x"}],
            input_schema={},
            output_schema={},
        )
        pipeline = PipelineYaml(name="test", steps=[step])
        dump = pipeline.model_dump(exclude_defaults=True)
        assert "input_schema" not in dump["steps"][0]
        assert "output_schema" not in dump["steps"][0]

    def test_empty_depends_on_excluded(self):
        step = StepYaml(
            name="s1",
            description="no deps",
            browser_ops=[{"goto": "x"}],
            depends_on=[],
        )
        pipeline = PipelineYaml(name="test", steps=[step])
        yaml_str = _dump_pipeline_yaml(pipeline)

        assert "depends_on" not in yaml_str, "empty list depends_on should be excluded"

    def test_non_default_values_preserved(self):
        step = StepYaml(
            name="s1",
            description="has deps",
            browser_ops=[{"goto": "x"}],
            depends_on=["s0"],
            params={"format": "csv"},
        )
        pipeline = PipelineYaml(name="test", steps=[step])
        yaml_str = _dump_pipeline_yaml(pipeline)

        assert "depends_on" in yaml_str
        assert "s0" in yaml_str
        assert "params" in yaml_str
        assert "format" in yaml_str

    def test_model_dump_without_exclude_shows_all(self):
        """model_dump() without exclude_defaults includes default values."""
        step = StepYaml(
            name="s1",
            description="test",
            browser_ops=[{"goto": "x"}],
        )
        pipeline = PipelineYaml(name="test", steps=[step])
        dump = pipeline.model_dump()
        assert dump["system_prompt"] == ""
        assert dump["url_aliases"] == {}
        assert dump["required_params"] == []


# ═══════════════════════════════════════════════════════════════════
# 5. to_step_def 当前行为 — 确认内部格式转换在 to_step_def 中
# ═══════════════════════════════════════════════════════════════════

class TestToStepDefCurrentBehavior:
    """Document what to_step_def currently does — format conversion lives here now."""

    def test_to_step_def_converts_goto(self):
        step = StepYaml.model_validate({
            "name": "open",
            "browser_ops": [{"goto": "https://example.com"}],
        })
        sd = step.to_step_def()
        assert sd.browser_ops == [{"type": "goto", "value": "https://example.com"}]

    def test_to_step_def_converts_fill(self):
        step = StepYaml.model_validate({
            "name": "search",
            "browser_ops": [{"fill": {"selector": "#q", "value": "hello"}}],
        })
        sd = step.to_step_def()
        assert sd.browser_ops == [{"type": "fill", "selector": "#q", "value": "hello"}]

    def test_to_step_def_converts_with_meta_keys(self):
        step = StepYaml.model_validate({
            "name": "click_retry",
            "browser_ops": [{"click": "#btn", "retry": 3, "optional": True}],
        })
        sd = step.to_step_def()
        assert sd.browser_ops == [
            {"type": "click", "value": "#btn", "retry": 3, "optional": True}
        ]

    def test_to_step_def_type_detection(self):
        """Step type is inferred correctly from field presence."""
        browser_step = StepYaml.model_validate({
            "name": "s1",
            "browser_ops": [{"goto": "x"}],
        })
        tool_step = StepYaml.model_validate({
            "name": "s2",
            "tool_name": "extract",
        })
        goal_step = StepYaml.model_validate({
            "name": "s3",
            "goal_description": "do it",
        })

        assert browser_step.to_step_def().step_type == "browser"
        assert tool_step.to_step_def().step_type == "tool"
        assert goal_step.to_step_def().step_type == "goal"

    def test_to_step_def_no_type_fields_defaults_goal(self):
        step = StepYaml.model_validate({"name": "bare"})
        sd = step.to_step_def()
        assert sd.step_type == "goal"
        assert sd.is_goal is True


# ═══════════════════════════════════════════════════════════════════
# 6. _load_pipeline_yaml 与 browser_ops 原始格式
# ═══════════════════════════════════════════════════════════════════

class TestLoadPipelineYamlBrowserOps:
    """_load_pipeline_yaml returns YAML-format browser_ops — NOT internal format."""

    def test_browser_ops_is_yaml_format_after_load(self, tmp_path):
        """After loading, StepYaml.browser_ops is still in YAML single-key format."""
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

        import yak_browser_use.engine._harness.pipeline_tools as pt
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(pt, "_WORKSPACES_DIR", tmp_path)
            validated = _load_pipeline_yaml("test_pipe")

        step = validated.steps[0]
        assert step.browser_ops == [
            {"goto": "https://x.com"},
            {"fill": {"selector": "#q", "value": "text"}},
        ]
        # CONFIRM: this is YAML format, not internal format
        assert "type" not in step.browser_ops[0]
        assert "goto" in step.browser_ops[0]


# ═══════════════════════════════════════════════════════════════════
# 7. PipelineYaml.model_validate 字段默认值
# ═══════════════════════════════════════════════════════════════════

class TestModelValidateDefaults:
    """Pydantic fills default values after validation."""

    def test_minimal_validate_fills_defaults(self):
        pipeline = PipelineYaml.model_validate({
            "name": "min",
            "steps": [{"name": "s1"}],
        })
        assert pipeline.description == ""
        assert pipeline.required_params == []
        assert pipeline.system_prompt == ""
        assert pipeline.url_aliases == {}

    def test_step_minimal_fills_defaults(self):
        step = StepYaml.model_validate({"name": "s1"})
        assert step.description == ""
        assert step.depends_on == []
        assert step.browser_ops is None
        assert step.tool_name is None
        assert step.goal_description is None
        assert step.params == {}
