"""Tests for orchestration filter — heavy data extraction and pre-execution hooks."""

from __future__ import annotations

from yak_browser_use.engine._harness.tool_executor import (
    _apply_heavy_data_filter,
)


class TestApplyHeavyDataFilter:
    def test_source_cached_fallback(self):
        result_dict = {
            "ok": True,
            "result": {},
            "html": "<html>x</html>",
        }
        _apply_heavy_data_filter("browser_source", {"cached": True}, result_dict)
        assert result_dict["result"]["cached"] is False
        assert "无缓存" in result_dict["result"]["note"]

    def test_a11y_snapshot_filter(self):
        result_dict = {
            "ok": True,
            "result": {
                "elements": [
                    {"role": "button", "name": "OK", "value": "", "description": "",
                     "checked": None, "disabled": False, "nth": 0, "prog_label": "a_0",
                     "selector": 'role=button[name="OK"]'},
                ],
                "url": "https://example.com",
                "title": "Example",
                "mode": "a11y",
            },
        }
        _apply_heavy_data_filter("browser_snapshot", {"mode": "a11y"}, result_dict)
        assert isinstance(result_dict["result"], str)
        assert "Example" in result_dict["result"]
        assert "1个可交互元素" in result_dict["result"]

    def test_a11y_degraded_filter(self):
        result_dict = {
            "ok": True,
            "result": {
                "elements": [],
                "url": "https://x.com",
                "title": "X",
                "mode": "a11y",
                "degraded": True,
                "screenshot_base64": "aaaa",
                "html": "<html></html>",
            },
        }
        _apply_heavy_data_filter("browser_snapshot", {"mode": "a11y"}, result_dict)
        assert "降级" in result_dict["result"]
        assert isinstance(result_dict["result"], str)

    def test_full_snapshot_filter(self):
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
        result_dict = {
            "ok": True,
            "result": "简化摘要",
        }
        _apply_heavy_data_filter("browser_snapshot", {"mode": "simplified"}, result_dict)
        assert result_dict["result"] == "简化摘要"

    def test_source_filter_strips_html(self):
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
        _apply_heavy_data_filter("browser_snapshot", {"mode": "a11y"}, result_dict)
        assert result_dict["ok"] is False
