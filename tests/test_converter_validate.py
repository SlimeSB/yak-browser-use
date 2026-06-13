"""Tests for converter.validate — pipeline.yaml validation."""

from __future__ import annotations

import pytest

from converter.validate import validate_pipeline, validate_pipeline_strict


SAMPLE_VALID_YAML = """name: test_pipe
description: A test
steps:
  - name: step_1
    browser_ops:
      - goto: https://example.com
"""

SAMPLE_INVALID_YAML = """name: test
steps: []
"""


class TestValidatePipeline:
    def test_valid_yaml(self):
        assert validate_pipeline(SAMPLE_VALID_YAML) is True

    def test_empty_string(self):
        assert validate_pipeline("") is False

    def test_whitespace_only(self):
        assert validate_pipeline("   ") is False

    def test_invalid_yaml_syntax(self):
        assert validate_pipeline(": invalid: yaml:") is False

    def test_not_a_mapping(self):
        assert validate_pipeline("[1, 2, 3]") is False

    def test_missing_required_fields(self):
        assert validate_pipeline("name: test\ndescription: x") is False  # no steps

    def test_empty_steps(self):
        assert validate_pipeline(SAMPLE_INVALID_YAML) is False

    def test_mutual_exclusion_violation(self):
        yaml_text = """name: bad
steps:
  - name: s1
    browser_ops:
      - goto: https://x.com
    goal_description: do something
"""
        assert validate_pipeline(yaml_text) is False


class TestValidatePipelineStrict:
    def test_valid_yaml(self):
        valid, errors = validate_pipeline_strict(SAMPLE_VALID_YAML)
        assert valid is True
        assert errors == []

    def test_empty_string(self):
        valid, errors = validate_pipeline_strict("")
        assert valid is False
        assert len(errors) > 0
        assert "empty" in errors[0].lower()

    def test_invalid_yaml_syntax(self):
        valid, errors = validate_pipeline_strict(": invalid yaml:")
        assert valid is False
        assert errors[0].startswith("YAML syntax")

    def test_not_a_mapping(self):
        valid, errors = validate_pipeline_strict("[1, 2, 3]")
        assert valid is False
        assert "mapping" in errors[0].lower()

    def test_schema_validation_failure(self):
        valid, errors = validate_pipeline_strict(SAMPLE_INVALID_YAML)
        assert valid is False
        assert any("validation" in e.lower() for e in errors)

    def test_multiple_errors(self):
        """Empty string should produce at least one error."""
        valid, errors = validate_pipeline_strict("")
        assert valid is False
        assert len(errors) >= 1
