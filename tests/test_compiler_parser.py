"""Tests for compiler.parser — pipeline YAML parser."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from compiler.parser import (
    parse_pipeline,
    inject_params_to_pipeline,
    _replace_placeholders,
    _inject_recursive,
)


SAMPLE_YAML = """name: test_pipeline
description: A test pipeline
required_params:
  - keyword
steps:
  - name: navigate
    description: Go to the site
    browser_ops:
      - goto: https://example.com
  - name: search
    description: Search for keyword
    depends_on:
      - navigate
    browser_ops:
      - fill:
          selector: "#q"
          value: "{{keyword}}"
  - name: extract
    description: Extract data
    tool_name: extract_table
"""

SAMPLE_YAML_WITH_TEMPLATES = """name: my_pipeline
steps:
  - name: step_1
    system_prompt: "{{template:default-system-prompt}}"
    browser_ops:
      - goto: https://example.com
"""


# ── parse_pipeline ────────────────────────────────────────────


class TestParsePipeline:
    def test_parse_valid_yaml(self):
        result = parse_pipeline(SAMPLE_YAML)
        assert result.name == "test_pipeline"
        assert result.description == "A test pipeline"
        assert len(result.steps) == 3
        assert result.steps[0].key == "navigate"
        assert result.steps[0].step_type == "browser"
        assert result.steps[1].step_type == "browser"
        assert result.steps[2].step_type == "tool"
        assert result.steps[2].tool_name == "extract_table"
        assert result.frontmatter["name"] == "test_pipeline"
        assert result.frontmatter["required_params"] == ["keyword"]

    def test_parse_with_url_aliases(self):
        yaml_text = """name: aliased
steps:
  - name: s1
    browser_ops:
      - goto: "{{alias:home}}"
"""
        result = parse_pipeline(yaml_text)
        assert result.name == "aliased"
        assert len(result.steps) == 1

    def test_parse_empty_steps(self):
        yaml_text = "name: no_steps\nsteps: []"
        with pytest.raises(Exception):
            parse_pipeline(yaml_text)

    def test_parse_missing_name(self):
        yaml_text = "steps:\n  - name: s1"
        with pytest.raises(Exception):
            parse_pipeline(yaml_text)

    def test_parse_invalid_yaml(self):
        with pytest.raises(yaml.YAMLError):
            parse_pipeline(": invalid yaml: :")

    def test_parse_not_a_mapping(self):
        with pytest.raises(yaml.YAMLError, match="must be a mapping"):
            parse_pipeline("[1, 2, 3]")

    def test_parse_mutual_exclusion_enforced(self):
        yaml_text = """name: bad
steps:
  - name: s1
    browser_ops:
      - goto: https://x.com
    goal_description: do something
"""
        with pytest.raises(Exception, match="mutually exclusive"):
            parse_pipeline(yaml_text)

    def test_parse_tool_step(self):
        yaml_text = """name: tool_pipe
steps:
  - name: s1
    tool_name: extract_table
    description: Extract data
"""
        result = parse_pipeline(yaml_text)
        assert result.steps[0].tool_name == "extract_table"
        assert result.steps[0].step_type == "tool"

    def test_parse_goal_step(self):
        yaml_text = """name: goal_pipe
steps:
  - name: s1
    goal_description: Analyze the results
"""
        result = parse_pipeline(yaml_text)
        assert result.steps[0].is_goal is True
        assert result.steps[0].goal_description == "Analyze the results"

    def test_parse_bare_step_defaults_to_goal(self):
        yaml_text = """name: bare
steps:
  - name: s1
    description: Just a step
"""
        result = parse_pipeline(yaml_text)
        assert result.steps[0].is_goal is True
        assert result.steps[0].goal_description == "Just a step"

    def test_parse_with_depends_on(self):
        yaml_text = """name: deps
steps:
  - name: s1
    browser_ops:
      - goto: https://x.com
  - name: s2
    browser_ops:
      - click: "#btn"
    depends_on:
      - s1
  - name: s3
    depends_on:
      - s2
"""
        result = parse_pipeline(yaml_text)
        assert result.steps[0].depends_on == []
        assert result.steps[1].depends_on == ["s1"]
        assert result.steps[2].depends_on == ["s2"]


# ── inject_params_to_pipeline ─────────────────────────────────


class TestInjectParams:
    SAMPLE = """name: test
required_params:
  - keyword
steps:
  - name: search
    browser_ops:
      - fill:
          selector: "#q"
          value: "{{keyword}}"
"""

    def test_basic_injection(self):
        result = inject_params_to_pipeline(self.SAMPLE, {"keyword": "hello"})
        # Result should have "hello" instead of "{{keyword}}"
        assert "{{keyword}}" not in result
        assert "hello" in result

    def test_no_params_provided(self):
        result = inject_params_to_pipeline(self.SAMPLE, None)
        assert "{{keyword}}" in result  # unchanged

    def test_empty_params_dict(self):
        result = inject_params_to_pipeline(self.SAMPLE, {})
        assert "{{keyword}}" in result  # unchanged

    def test_empty_yaml_text(self):
        assert inject_params_to_pipeline("", {"k": "v"}) == ""

    def test_yaml_with_only_comments(self):
        result = inject_params_to_pipeline("# just a comment\n", {"k": "v"})
        assert "# just a comment" in result

    def test_multiple_placeholders(self):
        text = """name: "{{name}}"
steps:
  - name: s1
    browser_ops:
      - goto: "{{url}}"
    description: "{{desc}}"
"""
        result = inject_params_to_pipeline(text, {"name": "my_pipe", "url": "https://x.com", "desc": "hello"})
        assert "{{name}}" not in result
        assert "{{url}}" not in result
        assert "{{desc}}" not in result
        assert "my_pipe" in result
        assert "https://x.com" in result
        assert "hello" in result

    def test_unmatched_placeholder_kept(self):
        text = """name: test
steps:
  - name: s1
    browser_ops:
      - goto: "{{missing_url}}"
"""
        result = inject_params_to_pipeline(text, {"other": "val"})
        assert "{{missing_url}}" in result

    def test_injection_into_nested_structures(self):
        """Placeholders in nested dicts should be replaced."""
        text = """name: test
steps:
  - name: s1
    params:
      api_key: "{{key}}"
      endpoint: "{{url}}/api"
"""
        result = inject_params_to_pipeline(text, {"key": "abc123", "url": "https://x.com"})
        assert "{{key}}" not in result
        assert "abc123" in result
        assert "https://x.com/api" in result


# ── _replace_placeholders ─────────────────────────────────────


class TestReplacePlaceholders:
    def test_basic_replacement(self):
        assert _replace_placeholders("{{name}}", {"name": "Alice"}) == "Alice"

    def test_no_placeholder(self):
        assert _replace_placeholders("plain text", {"k": "v"}) == "plain text"

    def test_missing_param_keeps_placeholder(self):
        result = _replace_placeholders("{{missing}}", {"other": "v"})
        assert result == "{{missing}}"

    def test_empty_text(self):
        assert _replace_placeholders("", {"k": "v"}) == ""

    def test_multiple_placeholders(self):
        result = _replace_placeholders("{{a}} and {{b}}", {"a": "X", "b": "Y"})
        assert result == "X and Y"

    def test_param_numeric_value(self):
        assert _replace_placeholders("{{num}}", {"num": 42}) == "42"


# ── _inject_recursive ─────────────────────────────────────────


class TestInjectRecursive:
    def test_dict_injection(self):
        data = {"key": "{{value}}", "other": "static"}
        _inject_recursive(data, {"value": "replaced"})
        assert data["key"] == "replaced"
        assert data["other"] == "static"

    def test_nested_dict(self):
        data = {"outer": {"inner": "{{val}}"}}
        _inject_recursive(data, {"val": "hello"})
        assert data["outer"]["inner"] == "hello"

    def test_list_injection(self):
        data = ["{{a}}", "{{b}}"]
        _inject_recursive(data, {"a": "1", "b": "2"})
        assert data == ["1", "2"]

    def test_nested_list_in_dict(self):
        data = {"items": ["{{x}}", "{{y}}"]}
        _inject_recursive(data, {"x": "A", "y": "B"})
        assert data["items"] == ["A", "B"]

    def test_non_string_values_untouched(self):
        data = {"count": 42, "active": True, "tags": [1, 2, 3]}
        _inject_recursive(data, {})
        assert data == {"count": 42, "active": True, "tags": [1, 2, 3]}

    def test_mixed_types_in_list(self):
        data = [42, "{{x}}", False, {"nested": "{{y}}"}]
        _inject_recursive(data, {"x": "hello", "y": "world"})
        assert data == [42, "hello", False, {"nested": "world"}]
