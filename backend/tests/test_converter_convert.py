"""Tests for converter.convert — NL to pipeline.yaml document conversion helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from converter.convert import _read_document, _extract_json, _extract_ops


# ── _read_document ────────────────────────────────────────────


class TestReadDocument:
    def test_reads_md_file(self, tmp_path):
        path = tmp_path / "doc.md"
        path.write_text("# Hello\nThis is a test.", encoding="utf-8")
        result = _read_document(str(path))
        assert "# Hello" in result
        assert "test" in result

    def test_reads_txt_file(self, tmp_path):
        path = tmp_path / "doc.txt"
        path.write_text("Plain text content", encoding="utf-8")
        result = _read_document(str(path))
        assert result == "Plain text content"

    def test_returns_raw_text_for_non_file(self):
        result = _read_document("just some plain text content")
        assert result == "just some plain text content"

    def test_returns_raw_text_for_nonexistent_file(self):
        result = _read_document("/nonexistent/path.md")
        assert result == "/nonexistent/path.md"


# ── _extract_json ─────────────────────────────────────────────


class TestExtractJson:
    def test_extract_from_fenced_block(self):
        text = 'Some text\n```json\n{"key": "value", "num": 42}\n```\nMore text'
        result = _extract_json(text)
        assert result is not None
        assert result["key"] == "value"
        assert result["num"] == 42

    def test_extract_from_raw_json(self):
        text = 'Here is the result: {"name": "test", "count": 3}. End.'
        result = _extract_json(text)
        assert result is not None
        assert result["name"] == "test"

    def test_extract_nested_json(self):
        text = '{"outer": {"inner": [1, 2, 3]}}'
        result = _extract_json(text)
        assert result is not None
        assert result["outer"]["inner"] == [1, 2, 3]

    def test_no_json_found(self):
        text = "This text has no JSON at all."
        assert _extract_json(text) is None

    def test_incomplete_brackets(self):
        text = '{"key": "value"'
        assert _extract_json(text) is None

    def test_malformed_json(self):
        text = '{"key": invalid, "num": 42}'
        assert _extract_json(text) is None

    def test_multiple_json_blocks_takes_first(self):
        text = '```json\n{"first": true}\n```\n```json\n{"second": true}\n```'
        result = _extract_json(text)
        assert result is not None
        assert result["first"] is True
        assert "second" not in result

    def test_json_in_code_block_with_language(self):
        text = 'Response:\n```json\n{"steps": [{"name": "s1"}]}\n```'
        result = _extract_json(text)
        assert result is not None
        assert len(result["steps"]) == 1

    def test_json_with_array_at_top(self):
        """Top-level arrays should not be parsed as dict."""
        text = '["a", "b", "c"]'
        result = _extract_json(text)
        assert result is None  # _extract_json expects a dict

    def test_empty_json_object(self):
        text = "{}"
        result = _extract_json(text)
        assert result == {}


# ── _extract_ops ───────────────────────────────────────────


class TestExtractOps:
    def test_extract_from_fenced_json(self):
        text = '```json\n[{"type": "goto", "value": "https://x.com"}]\n```'
        result = _extract_ops(text)
        assert len(result) == 1
        assert result[0]["type"] == "goto"
        assert result[0]["value"] == "https://x.com"

    def test_extract_raw_array(self):
        text = '[{"type": "click", "value": "#btn"}, {"type": "fill", "value": "#input"}]'
        result = _extract_ops(text)
        assert len(result) == 2

    def test_empty_array(self):
        text = "[]"
        result = _extract_ops(text)
        assert result == []

    def test_no_array_returns_empty(self):
        text = "No ops here."
        result = _extract_ops(text)
        assert result == []

    def test_fallback_regex_extraction(self):
        """When JSON parsing fails, fall back to regex pattern."""
        text = 'Some ops: {"type": "goto", "value": "https://x.com"} and {"type": "click", "value": "#btn"}'
        result = _extract_ops(text)
        assert len(result) >= 1  # might find some via regex fallback

    def test_malformed_array(self):
        text = '[{"type": "goto", "value": broken}]'
        result = _extract_ops(text)
        assert result == []  # fallback regex might find nothing

    def test_multiple_ops_in_fence(self):
        text = """```json
[
  {"type": "goto", "value": "https://example.com"},
  {"type": "fill", "selector": "#q", "value": "search term"},
  {"type": "click", "value": "#submit"}
]
```"""
        result = _extract_ops(text)
        assert len(result) == 3

    def test_ops_with_complex_params(self):
        text = """```json
[{"type": "fill", "selector": "#login", "value": "user@example.com"}]
```"""
        result = _extract_ops(text)
        assert len(result) == 1
        assert result[0]["selector"] == "#login"
        assert result[0]["value"] == "user@example.com"

    def test_non_array_json_object(self):
        text = '{"type": "goto", "value": "x"}'
        result = _extract_ops(text)
        # Should try to parse as JSON, find it's not a list, then fallback to regex
        # The regex looks for {"type":"...","value":"..."} pattern
        assert len(result) >= 1  # fallback regex should catch it
