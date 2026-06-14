"""Tests for run_check — programmatic step verification."""

from __future__ import annotations

import pytest
from engine.executor import run_check


class MockCDPHelpers:
    """Mock CDP helpers for testing run_check without browser."""

    def __init__(self, url="https://www.example.com/search?q=test", body_text="搜索结果: 10条记录", elements_present=None, elements_visible=None):
        self._url = url
        self._body_text = body_text
        self._elements_present = elements_present or {}
        self._elements_visible = elements_visible or {}

    async def js(self, expression):
        if "window.location.href" in expression:
            return self._url
        if "document.querySelector" in expression:
            selector = _extract_selector(expression)
            if "getComputedStyle" in expression or "offsetWidth" in expression:
                return self._elements_visible.get(selector, False)
            return self._elements_present.get(selector, False)
        if "document.body.innerText" in expression:
            return self._body_text
        return None


def _extract_selector(js):
    """Simple extractor for the selector from a JS expression."""
    import re
    m = re.search(r"""querySelector\((['"])(.+?)\1\)""", js)
    if m:
        return m.group(2)
    return ""


class TestRunCheckUrlContains:
    @pytest.mark.asyncio
    async def test_pass(self):
        cdp = MockCDPHelpers(url="https://x.com/wd=机械键盘")
        result = await run_check({"url_contains": "wd=机械键盘"}, cdp)
        assert result["ok"] is True
        assert "通过" in result["result"]

    @pytest.mark.asyncio
    async def test_fail(self):
        cdp = MockCDPHelpers(url="https://x.com/other")
        result = await run_check({"url_contains": "wd=机械键盘"}, cdp)
        assert result["ok"] is False
        assert "url_contains" in result["result"]

    @pytest.mark.asyncio
    async def test_includes_current_url(self):
        cdp = MockCDPHelpers(url="https://x.com/path")
        result = await run_check({"url_contains": "path"}, cdp)
        assert "current_url" in result
        assert result["current_url"] == "https://x.com/path"


class TestRunCheckElementExists:
    @pytest.mark.asyncio
    async def test_pass(self):
        cdp = MockCDPHelpers(elements_present={"#search": True})
        result = await run_check({"element_exists": "#search"}, cdp)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_fail(self):
        cdp = MockCDPHelpers(elements_present={"#search": False})
        result = await run_check({"element_exists": "#search"}, cdp)
        assert result["ok"] is False
        assert "element_exists" in result["result"]


class TestRunCheckTextContains:
    @pytest.mark.asyncio
    async def test_pass(self):
        cdp = MockCDPHelpers(body_text="页面包含搜索结果")
        result = await run_check({"text_contains": "搜索结果"}, cdp)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_fail(self):
        cdp = MockCDPHelpers(body_text="页面无相关内容")
        result = await run_check({"text_contains": "搜索结果"}, cdp)
        assert result["ok"] is False


class TestRunCheckElementVisible:
    @pytest.mark.asyncio
    async def test_pass(self):
        cdp = MockCDPHelpers(elements_visible={".result-list": True})
        result = await run_check({"element_visible": ".result-list"}, cdp)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_fail(self):
        cdp = MockCDPHelpers(elements_visible={".result-list": False})
        result = await run_check({"element_visible": ".result-list"}, cdp)
        assert result["ok"] is False


class TestRunCheckEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_check_def(self):
        result = await run_check({}, None)
        assert result["ok"] is True
        assert "默认通过" in result["result"]

    @pytest.mark.asyncio
    async def test_none_check_def(self):
        result = await run_check(None, None)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_empty_string_value_rejected(self):
        cdp = MockCDPHelpers()
        result = await run_check({"url_contains": ""}, cdp)
        assert result["ok"] is False
        assert "无效参数" in result["result"]

    @pytest.mark.asyncio
    async def test_none_value_rejected(self):
        cdp = MockCDPHelpers()
        result = await run_check({"text_contains": None}, cdp)
        assert result["ok"] is False
        assert "无效参数" in result["result"]

    @pytest.mark.asyncio
    async def test_multiple_conditions_all_pass(self):
        cdp = MockCDPHelpers(
            url="https://x.com/search?q=test",
            body_text="搜索结果",
            elements_present={"#search": True}
        )
        result = await run_check({
            "url_contains": "search",
            "text_contains": "搜索结果",
            "element_exists": "#search",
        }, cdp)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_multiple_conditions_first_fails(self):
        cdp = MockCDPHelpers(url="https://x.com/other")
        result = await run_check({
            "url_contains": "search",
            "text_contains": "搜索结果",
        }, cdp)
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_always_returns_current_url(self):
        cdp = MockCDPHelpers(url="https://x.com")
        result = await run_check({"element_exists": ".x"}, cdp)
        assert "current_url" in result
        assert result["current_url"] == "https://x.com"
