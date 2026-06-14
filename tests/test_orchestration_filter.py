"""Tests for orchestration filter — heavy data extraction and pre-execution hooks."""

from __future__ import annotations

from engine._harness.tool_executor import (
    _apply_heavy_data_filter,
    _try_scratchpad_element_lookup,
    _try_scratchpad_source_read,
    _normalize_ref,
)
from engine.scratchpad import _scratchpads, store, store_raw_html


class TestNormalizeRef:
    def test_at_prefix(self):
        assert _normalize_ref("@e5") == "@e5"

    def test_e_prefix(self):
        assert _normalize_ref("e3") == "@e3"

    def test_number_only(self):
        assert _normalize_ref("7") == "@e7"

    def test_with_whitespace(self):
        assert _normalize_ref("  @e12  ") == "@e12"


class TestScratchpadElementLookup:
    def test_hit_returns_element_info(self):
        _scratchpads.clear()
        store({
            "elements": [
                {"ref": "@e1", "tag": "button", "type": "submit", "text": "Go", "selector": "button#go"},
            ],
            "url": "https://x.com",
            "title": "X",
        })
        result = _try_scratchpad_element_lookup({"ref": "@e1"})
        assert result is not None
        assert result["ok"] is True
        assert result["result"]["ref"] == "@e1"
        assert result["result"]["selector"] == "button#go"

    def test_miss_returns_none(self):
        _scratchpads.clear()
        store({"elements": [{"ref": "@e1", "selector": "btn"}], "url": "", "title": ""})
        result = _try_scratchpad_element_lookup({"ref": "@e99"})
        assert result is None

    def test_empty_element_map_returns_none(self):
        _scratchpads.clear()
        result = _try_scratchpad_element_lookup({"ref": "@e1"})
        assert result is None

    def test_normalized_ref_lookup(self):
        _scratchpads.clear()
        store({"elements": [{"ref": "@e3", "selector": "input[name='q']"}], "url": "", "title": ""})
        result = _try_scratchpad_element_lookup({"ref": "3"})
        assert result is not None
        assert result["result"]["selector"] == "input[name='q']"

    def test_e_prefix_end_to_end_lookup(self):
        _scratchpads.clear()
        store({"elements": [{"ref": "@e5", "tag": "a", "text": "Link", "selector": "a.link"}], "url": "", "title": ""})
        result = _try_scratchpad_element_lookup({"ref": "e5"})
        assert result is not None
        assert result["result"]["ref"] == "@e5"
        assert result["result"]["selector"] == "a.link"

    def test_no_ref_returns_none(self):
        _scratchpads.clear()
        result = _try_scratchpad_element_lookup({})
        assert result is None


class TestScratchpadSourceRead:
    def test_cache_hit(self):
        _scratchpads.clear()
        store_raw_html("<html><body>test</body></html>")
        result = _try_scratchpad_source_read()
        assert result is not None
        assert result["ok"] is True
        assert result["result"]["length"] == 30
        assert result["result"]["cached"] is True
        assert result["html"] == "<html><body>test</body></html>"

    def test_cache_miss(self):
        _scratchpads.clear()
        result = _try_scratchpad_source_read()
        assert result is None


class TestApplyHeavyDataFilter:
    def test_source_cached_preserved(self):
        _scratchpads.clear()
        result_dict = {
            "ok": True,
            "result": {"length": 30, "cached": True},
            "html": "<html><body>test</body></html>",
        }
        _apply_heavy_data_filter("browser_source", {"cached": True}, result_dict)
        assert result_dict["result"]["cached"] is True
        assert result_dict["result"]["length"] == 30
        assert "note" not in result_dict["result"]

    def test_source_cached_fallback(self):
        _scratchpads.clear()
        result_dict = {
            "ok": True,
            "result": {},
            "html": "<html>x</html>",
        }
        _apply_heavy_data_filter("browser_source", {"cached": True}, result_dict)
        assert result_dict["result"]["cached"] is False
        assert "无缓存" in result_dict["result"]["note"]

    def test_interactive_snapshot_filter(self):
        _scratchpads.clear()
        result_dict = {
            "ok": True,
            "result": {
                "elements": [
                    {"ref": "@e1", "tag": "button", "text": "OK", "selector": "button#ok"},
                ],
                "url": "https://example.com",
                "title": "Example",
                "mode": "interactive",
            },
        }
        _apply_heavy_data_filter("browser_snapshot", {"mode": "interactive"}, result_dict)
        assert isinstance(result_dict["result"], str)
        assert "Example" in result_dict["result"]
        assert "1个可交互元素" in result_dict["result"]

    def test_interactive_degraded_filter(self):
        _scratchpads.clear()
        result_dict = {
            "ok": True,
            "result": {
                "elements": [],
                "url": "https://x.com",
                "title": "X",
                "mode": "interactive",
                "degraded": True,
                "screenshot_base64": "aaaa",
                "html": "<html></html>",
            },
        }
        _apply_heavy_data_filter("browser_snapshot", {"mode": "interactive"}, result_dict)
        assert "降级" in result_dict["result"]
        assert isinstance(result_dict["result"], str)

    def test_full_snapshot_filter(self):
        _scratchpads.clear()
        result_dict = {
            "ok": True,
            "result": {"url": "https://x.com", "title": "X"},
            "screenshot_base64": "bbbb",
            "html": "<html></html>",
        }
        _apply_heavy_data_filter("browser_snapshot", {"mode": "full"}, result_dict)
        assert "screenshot_base64" not in result_dict
        assert "html" not in result_dict
        assert "完整快照" in str(result_dict["result"])

    def test_simplified_no_filter(self):
        _scratchpads.clear()
        result_dict = {
            "ok": True,
            "result": "简化摘要",
        }
        _apply_heavy_data_filter("browser_snapshot", {"mode": "simplified"}, result_dict)
        assert result_dict["result"] == "简化摘要"

    def test_source_filter_strips_html(self):
        _scratchpads.clear()
        result_dict = {
            "ok": True,
            "result": {},
            "html": "<html>test</html>",
        }
        _apply_heavy_data_filter("browser_source", {}, result_dict)
        assert "html" not in result_dict
        assert result_dict["result"]["length"] == 17

    def test_non_snapshot_not_filtered(self):
        result_dict = {"ok": True, "result": {"url": "https://x.com"}}
        _apply_heavy_data_filter("browser_goto", {"url": "https://x.com"}, result_dict)
        assert result_dict["result"]["url"] == "https://x.com"

    def test_error_not_filtered(self):
        result_dict = {"ok": False, "error": "timeout", "result": "..."}
        _apply_heavy_data_filter("browser_snapshot", {"mode": "interactive"}, result_dict)
        assert result_dict["ok"] is False
