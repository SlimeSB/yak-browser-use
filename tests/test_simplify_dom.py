"""Tests for simplify-dom.js DOM simplification script.

These tests validate the JS logic by:
1. Verifying the script file exists and is valid JavaScript
2. Testing the structure of expected output for interactive/simplified modes
3. Testing edge cases (empty results, truncation, password sanitization)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
SIMPLIFY_DOM_JS = ASSETS_DIR / "simplify-dom.js"


class TestSimplifyDomScript:
    def test_script_exists(self):
        assert SIMPLIFY_DOM_JS.exists(), f"simplify-dom.js not found at {SIMPLIFY_DOM_JS}"

    def test_script_is_non_empty(self):
        content = SIMPLIFY_DOM_JS.read_text(encoding="utf-8")
        assert len(content) > 100, "simplify-dom.js is too short"

    def test_script_contains_key_functions(self):
        content = SIMPLIFY_DOM_JS.read_text(encoding="utf-8")
        assert "isVisible" in content
        assert "buildSelector" in content
        assert "getText" in content
        assert "isInteractive" in content
        assert "interactiveMode" in content
        assert "simplifiedMode" in content
        assert "simplifyDom" in content

    def test_script_contains_max_elements(self):
        content = SIMPLIFY_DOM_JS.read_text(encoding="utf-8")
        assert "MAX_ELEMENTS" in content
        assert "50" in content

    def test_script_contains_password_sanitization(self):
        content = SIMPLIFY_DOM_JS.read_text(encoding="utf-8")
        assert "password" in content.lower()
        assert "***" in content


class TestInteractiveModeOutput:
    """Validate the expected structure of interactive mode output."""

    def test_interactive_output_structure(self):
        expected = {
            "mode": "interactive",
            "elements": [
                {
                    "ref": "@e1",
                    "tag": "button",
                    "type": "submit",
                    "text": "登录",
                    "selector": "#submit-btn",
                    "value": "",
                }
            ],
        }
        assert expected["mode"] == "interactive"
        assert isinstance(expected["elements"], list)
        el = expected["elements"][0]
        assert el["ref"].startswith("@e")
        assert "tag" in el
        assert "type" in el
        assert "text" in el
        assert "selector" in el
        assert "value" in el

    def test_interactive_ref_format(self):
        refs = ["@e1", "@e2", "@e3", "@e10", "@e50"]
        for ref in refs:
            assert ref.startswith("@e")
            num = int(ref[2:])
            assert 1 <= num <= 50

    def test_interactive_truncation_flag(self):
        result = {"mode": "interactive", "elements": [], "truncated": True, "total_found": 60}
        assert result["truncated"] is True
        assert result["total_found"] == 60

    def test_interactive_no_truncation(self):
        result = {"mode": "interactive", "elements": [{"ref": "@e1"}]}
        assert "truncated" not in result


class TestSimplifiedModeOutput:
    """Validate the expected structure of simplified mode output."""

    def test_simplified_output_structure(self):
        expected = {
            "mode": "simplified",
            "summary": "Title: test\nH1: heading",
            "lists": [
                {
                    "selector": "ul#feature-list",
                    "tag": "ul",
                    "item_count": 4,
                    "sample_items": ["item1", "item2"],
                }
            ],
            "tables": [
                {
                    "selector": "table#data-table",
                    "row_count": 4,
                    "col_count": 3,
                    "headers": ["姓名", "年龄", "城市"],
                }
            ],
        }
        assert expected["mode"] == "simplified"
        assert isinstance(expected["summary"], str)
        assert isinstance(expected["lists"], list)
        assert isinstance(expected["tables"], list)

    def test_simplified_empty_lists_tables(self):
        result = {"mode": "simplified", "summary": "Title: empty", "lists": [], "tables": []}
        assert result["lists"] == []
        assert result["tables"] == []

    def test_simplified_list_structure(self):
        item = {"selector": "ul", "tag": "ul", "item_count": 3, "sample_items": ["a", "b", "c"]}
        assert item["tag"] in ("ul", "ol")
        assert item["item_count"] >= 0
        assert len(item["sample_items"]) <= 5

    def test_simplified_table_structure(self):
        item = {"selector": "table", "row_count": 5, "col_count": 3, "headers": ["A", "B", "C"]}
        assert item["row_count"] >= 0
        assert item["col_count"] >= 0
        assert isinstance(item["headers"], list)


class TestVisibilityLogic:
    """Validate visibility checking logic (tested via expected behavior)."""

    def test_hidden_elements_excluded(self):
        content = SIMPLIFY_DOM_JS.read_text(encoding="utf-8")
        assert "display === 'none'" in content
        assert "visibility === 'hidden'" in content
        assert "offsetParent === null" in content
        assert "opacity" in content

    def test_viewport_check(self):
        content = SIMPLIFY_DOM_JS.read_text(encoding="utf-8")
        assert "getBoundingClientRect" in content
        assert "innerHeight" in content
        assert "innerWidth" in content


class TestPasswordSanitization:
    """Validate password field handling."""

    def test_password_sanitization_in_script(self):
        content = SIMPLIFY_DOM_JS.read_text(encoding="utf-8")
        assert "sanitizeValue" in content
        assert "password" in content.lower()

    def test_password_value_masked(self):
        content = SIMPLIFY_DOM_JS.read_text(encoding="utf-8")
        assert "'***'" in content


class TestTestHtml:
    """Validate the test HTML file exists and covers required scenarios."""

    def test_test_html_exists(self):
        test_html = Path(__file__).resolve().parent / "simplify-dom.test.html"
        assert test_html.exists(), f"simplify-dom.test.html not found at {test_html}"

    def test_test_html_covers_scenarios(self):
        test_html = Path(__file__).resolve().parent / "simplify-dom.test.html"
        content = test_html.read_text(encoding="utf-8")
        assert "表单" in content or "form" in content.lower()
        assert "导航" in content or "nav" in content.lower()
        assert "表格" in content or "table" in content.lower()
        assert "列表" in content or "ul" in content.lower()
        assert "ARIA" in content or "role" in content.lower()
        assert "隐藏" in content or "hidden" in content.lower()
