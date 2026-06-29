"""Integration tests for the agent-architecture-reform data flow.

Tests cross-layer paths that unit tests can't reach:
- snapshot full lifecycle through filter → scratchpad → message
- run_check integration with step verification
- goal execution via todo + browser_*
- element lookup dual-path selection
- compiler check field round-trip
"""
from __future__ import annotations

import pytest

from yak_browser_use.engine.scratchpad import (
    _scratchpads,
    clear,
    clear_all,
    get as get_scratchpad,
    store as store_scratchpad,
    store_raw_html,
)
from yak_browser_use.engine._harness.tool_executor import (
    _apply_heavy_data_filter,
)
from yak_browser_use.engine.executor import run_check
from yak_browser_use.compiler.schema import StepYaml, PipelineYaml
from yak_browser_use.compiler.models import StepDef, PipelineDef


class MockPage:
    def __init__(self, url: str = ""):
        self.url = url


class MockBridge:
    """Mock PlaywrightBridge for integration tests."""

    def __init__(self, *, url="https://example.com/page", title="Example Page",
                 elements=None, screenshot_base64="", html="",
                 body_text="Some page text"):
        self.page = MockPage(url)
        self._title = title
        self._elements = elements or []
        self._screenshot = screenshot_base64
        self._html = html
        self._body_text = body_text

    async def evaluate(self, expression):
        if "window.location.href" in expression:
            return self.page.url
        if "document.querySelector" in expression:
            return self._selectors_match(expression)
        if "document.body.innerText" in expression:
            return self._body_text
        if "getComputedStyle" in expression:
            return self._selectors_match(expression)
        return None

    def _selectors_match(self, js):
        for el in self._elements:
            sel = el.get("selector", "")
            if sel and (sel in js or f'"{sel}"' in js or f"'{sel}'" in js):
                return el.get("visible", True)
        return False

    async def capture_snapshot_progressive(self, query: str = "", in_viewport: bool = False):
        return {
            "elements": self._elements,
            "url": self._url,
            "title": self._title,
            "mode": "progressive",
        }

    async def capture_snapshot(self):
        return {
            "screenshot_base64": self._screenshot,
            "html": self._html,
            "url": self._url,
            "title": self._title,
        }


# ── Snapshot full lifecycle integration ──

class TestSnapshotInteractiveLifecycle:
    """CDP response → executor → filter → scratchpad → message summary."""

    def setup_method(self):
        clear_all()

    def test_full_flow_stores_to_scratchpad(self):
        elements = [
            {"ref": "@e1", "tag": "button", "type": "submit", "text": "Search",
             "selector": "button#search"},
            {"ref": "@e2", "tag": "input", "type": "text", "text": "",
             "selector": "input[name='q']"},
        ]
        result_dict = {
            "ok": True,
            "result": {
                "elements": elements,
                "url": "https://example.com/search",
                "title": "Search Page",
                "mode": "interactive",
            },
        }
        _apply_heavy_data_filter("browser_snapshot", {"mode": "interactive"}, result_dict)

        sp = get_scratchpad()
        assert sp.url == "https://example.com/search"
        assert sp.title == "Search Page"
        assert sp.element_map == {"@e1": "button#search", "@e2": "input[name='q']"}
        assert "Search Page" in sp.summary
        assert "2个可交互元素" in sp.summary

    def test_message_receives_summary_not_raw_data(self):
        elements = [{"ref": "@e1", "selector": "button", "tag": "button", "text": "OK"}]
        result_dict = {
            "ok": True,
            "result": {
                "elements": elements,
                "url": "https://x.com",
                "title": "X",
                "mode": "interactive",
            },
        }
        _apply_heavy_data_filter("browser_snapshot", {"mode": "interactive"}, result_dict)

        result_text = result_dict["result"]
        assert isinstance(result_text, str)
        assert "X" in result_text
        assert "1个可交互元素" in result_text
        assert "@e1" in result_text  # element refs now included in summary

class TestSnapshotFullLifecycle:
    def setup_method(self):
        clear_all()

    def test_full_mode_strips_heavy_data(self):
        result_dict = {
            "ok": True,
            "result": {"url": "https://x.com", "title": "X"},
            "screenshot_base64": "iVBORw0KGgoAAAA...",
            "html": "<html><body>very long html content</body></html>",
        }
        _apply_heavy_data_filter("browser_snapshot", {"mode": "full"}, result_dict)

        assert "screenshot_base64" not in result_dict
        assert "html" not in result_dict
        assert "完整快照" in result_dict["result"]

    def test_full_mode_stores_html_to_scratchpad(self):
        html = "<html><body>test body</body></html>"
        result_dict = {
            "ok": True,
            "result": {"url": "https://x.com", "title": "X"},
            "html": html,
        }
        _apply_heavy_data_filter("browser_snapshot", {"mode": "full"}, result_dict)

        assert get_scratchpad().raw_html == html


class TestSnapshotSimplifiedDegradedLifecycle:
    def setup_method(self):
        clear_all()

    def test_simplified_degraded_strips_heavy_data(self):
        result_dict = {
            "ok": True,
            "result": {
                "mode": "simplified",
                "degraded": True,
                "summary": "",
                "lists": [],
                "tables": [],
                "screenshot_base64": "aaaa...",
                "html": "<html><body>content</body></html>",
                "url": "https://x.com",
                "title": "X",
            },
        }
        _apply_heavy_data_filter("browser_snapshot", {"mode": "simplified"}, result_dict)

        result_payload = result_dict["result"]
        assert isinstance(result_payload, str)
        assert "降级" in result_payload
        assert "screenshot_base64" not in result_dict.get("result", {})
        assert get_scratchpad().url == "https://x.com"

    def test_simplified_normal_no_filter(self):
        result_dict = {"ok": True, "result": "页面文本摘要"}
        _apply_heavy_data_filter("browser_snapshot", {"mode": "simplified"}, result_dict)
        assert result_dict["result"] == "页面文本摘要"

    def test_interactive_degraded_strips_nested_heavy_data(self):
        result_dict = {
            "ok": True,
            "result": {
                "elements": [{"ref": "@e1", "selector": "btn", "tag": "button", "text": "Go"}],
                "url": "https://x.com",
                "title": "X",
                "mode": "interactive",
                "degraded": True,
                "screenshot_base64": "bbbb...",
                "html": "<html>fallback</html>",
            },
        }
        _apply_heavy_data_filter("browser_snapshot", {"mode": "interactive"}, result_dict)

        result_payload = result_dict.get("result", {})
        assert "screenshot_base64" not in result_payload
        assert "html" not in result_payload
        assert "降级" in result_dict["result"]


# ── browser_source integration ──

class TestBrowserSourceLifecycle:
    def setup_method(self):
        clear_all()

    def test_source_caches_and_strips_html(self):
        result_dict = {
            "ok": True,
            "result": {},
            "html": "<html><body>page source</body></html>",
        }
        _apply_heavy_data_filter("browser_source", {}, result_dict)

        assert "html" not in result_dict
        assert result_dict["result"]["length"] == len("<html><body>page source</body></html>")

    def test_source_cached_true_hit(self):
        store_raw_html("<html>cached</html>")
        result_dict = {
            "ok": True,
            "result": {"length": 17, "cached": True},
            "html": "<html>cached</html>",
        }
        _apply_heavy_data_filter("browser_source", {"cached": True}, result_dict)

        assert result_dict["result"]["cached"] is True
        assert "note" not in result_dict["result"]

    def test_source_cached_true_miss_then_fallback(self):
        result_dict = {
            "ok": True,
            "result": {},
            "html": "<html>fresh</html>",
        }
        _apply_heavy_data_filter("browser_source", {"cached": True}, result_dict)

        assert result_dict["result"]["cached"] is False
        assert "无缓存" in result_dict["result"]["note"]

# ── run_check integration ──

class TestRunCheckIntegration:
    @pytest.mark.asyncio
    async def test_url_contains_pass_with_fixture(self):
        bridge = MockBridge(url="https://search.com/results?q=test")
        result = await run_check({"url_contains": "results"}, bridge)
        assert result["ok"] is True
        assert "current_url" in result

    @pytest.mark.asyncio
    async def test_element_exists_pass(self):
        bridge = MockBridge(elements=[{"selector": "#submit", "ref": "@e1"}])
        result = await run_check({"element_exists": "#submit"}, bridge)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_element_exists_fail_missing(self):
        bridge = MockBridge(elements=[{"selector": "#other", "ref": "@e1"}])
        result = await run_check({"element_exists": "#submit"}, bridge)
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_text_contains_pass(self):
        bridge = MockBridge(body_text="这里有搜索结果 10 条")
        result = await run_check({"text_contains": "搜索结果"}, bridge)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_text_contains_fail(self):
        bridge = MockBridge(body_text="页面无内容")
        result = await run_check({"text_contains": "搜索结果"}, bridge)
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_element_visible_pass(self):
        bridge = MockBridge(elements=[{"selector": ".modal", "ref": "@e1", "visible": True}])
        result = await run_check({"element_visible": ".modal"}, bridge)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_element_visible_fail_hidden(self):
        bridge = MockBridge(elements=[{"selector": ".modal", "ref": "@e1", "visible": False}])
        result = await run_check({"element_visible": ".modal"}, bridge)
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_all_conditions_pass(self):
        bridge = MockBridge(
            url="https://x.com/search?q=test",
            body_text="搜索完成",
            elements=[{"selector": "#results", "ref": "@e1", "visible": True}],
        )
        result = await run_check({
            "url_contains": "search",
            "text_contains": "搜索",
            "element_exists": "#results",
            "element_visible": "#results",
        }, bridge)
        assert result["ok"] is True
        assert "current_url" in result

    @pytest.mark.asyncio
    async def test_none_check_passes(self):
        result = await run_check(None, None)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_bad_value_rejected(self):
        bridge = MockBridge()
        result = await run_check({"url_contains": None}, bridge)
        assert result["ok"] is False
        assert "无效参数" in result["result"]


# ── Compiler check field round-trip ──

class TestCheckFieldRoundTrip:
    def test_step_yaml_with_check_to_step_def(self):
        step = StepYaml.model_validate({
            "name": "verify",
            "browser_ops": [{"goto": "https://x.com"}],
            "check": {"url_contains": "x.com", "element_exists": "#header"},
        })
        sd = step.to_step_def()
        assert sd.check == {"url_contains": "x.com", "element_exists": "#header"}

    def test_step_def_to_runtime_passes_check(self):
        step = StepYaml.model_validate({
            "name": "verify",
            "browser_ops": [{"goto": "https://x.com"}],
            "check": {"url_contains": "x.com"},
        })
        sd = step.to_step_def()
        runtime = sd.to_runtime_dict()
        assert runtime["check"] == {"url_contains": "x.com"}

    def test_step_without_check_is_none(self):
        step = StepYaml.model_validate({
            "name": "simple",
            "browser_ops": [{"goto": "https://x.com"}],
        })
        sd = step.to_step_def()
        assert sd.check is None
        runtime = sd.to_runtime_dict()
        assert runtime["check"] is None

    def test_full_pipeline_with_check_steps(self):
        pipeline = PipelineYaml.model_validate({
            "name": "test_check",
            "steps": [
                {"name": "step1", "browser_ops": [{"goto": "https://x.com"}],
                 "check": {"url_contains": "x.com"}},
                {"name": "step2", "tool_name": "extract",
                 "check": {"text_contains": "result"}},
                {"name": "step3", "goal_description": "do something"},
            ],
        })
        pd = pipeline.to_pipeline_def()
        assert pd.steps[0].check == {"url_contains": "x.com"}
        assert pd.steps[1].check == {"text_contains": "result"}
        assert pd.steps[2].check is None

    def test_check_field_round_trip(self):
        """check survives: YAML dict → StepYaml → StepDef → runtime_dict."""
        step = StepYaml.model_validate({
            "name": "rtt",
            "browser_ops": [{"click": "#go"}],
            "check": {"element_exists": "#go", "element_visible": "#go"},
        })
        runtime = step.to_step_def().to_runtime_dict()
        assert runtime["check"]["element_exists"] == "#go"
        assert runtime["check"]["element_visible"] == "#go"


# ── Scratchpad lifecycle (memory) ──

class TestScratchpadLifecycle:
    def setup_method(self):
        clear_all()

    def test_clear_removes_session(self):
        store_scratchpad({
            "elements": [{"ref": "@e1", "selector": "btn"}],
            "url": "https://x.com",
            "title": "X",
        }, session_id="run-1")
        assert len(_scratchpads) == 1

        clear("run-1")
        assert len(_scratchpads) == 0

    def test_clear_all_removes_everything(self):
        store_scratchpad({"elements": [], "url": "", "title": ""}, "a")
        store_scratchpad({"elements": [], "url": "", "title": ""}, "b")
        store_scratchpad({"elements": [], "url": "", "title": ""}, "c")
        assert len(_scratchpads) == 3

        clear_all()
        assert len(_scratchpads) == 0

    def test_overwrite_does_not_leak_new_keys(self):
        store_scratchpad({"elements": [{"ref": "@e1", "selector": "old"}], "url": "old.com", "title": "Old"})
        get_scratchpad().raw_html = "<html>custom</html>"

        store_scratchpad({"elements": [], "url": "new.com", "title": "New"})
        sp = get_scratchpad()
        assert sp.url == "new.com"
        assert sp.title == "New"
        assert sp.element_map == {}
        assert sp.elements == []
        assert sp.raw_html == "<html>custom</html>"  # preserved by design


# ── Filter unknown modes ──

class TestFilterUnknownMode:
    def setup_method(self):
        clear_all()

    def test_unknown_mode_uses_fallback(self):
        result_dict = {
            "ok": True,
            "result": {"some": "data"},
        }
        _apply_heavy_data_filter("browser_snapshot", {"mode": "minimal"}, result_dict)
        assert "无摘要" in result_dict["result"]

    def test_non_snapshot_tool_passes_through(self):
        result_dict = {"ok": True, "result": {"url": "https://x.com"}}
        _apply_heavy_data_filter("browser_goto", {"url": "https://x.com"}, result_dict)
        assert result_dict["result"]["url"] == "https://x.com"

    def test_error_tool_passes_through(self):
        result_dict = {"ok": False, "error": "timeout", "result": "..."}
        _apply_heavy_data_filter("browser_snapshot", {"mode": "interactive"}, result_dict)
        assert result_dict["ok"] is False
        assert result_dict["result"] == "..."
