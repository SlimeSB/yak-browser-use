"""Tests for run_check — programmatic step verification."""

from __future__ import annotations

from pathlib import Path

import pytest
from yak_browser_use.engine.executor import run_check


class MockPage:
    def __init__(self, url: str = ""):
        self.url = url


class MockBridge:
    """Mock PlaywrightBridge for testing run_check without browser."""

    def __init__(self, url="https://www.example.com/search?q=test", body_text="搜索结果: 10条记录", elements_present=None, elements_visible=None):
        self.page = MockPage(url)
        self._body_text = body_text
        self._elements_present = elements_present or {}
        self._elements_visible = elements_visible or {}

    async def evaluate(self, expression):
        if "document.querySelector" in expression:
            selector = _extract_selector(expression)
            if "getComputedStyle" in expression or "offsetWidth" in expression:
                return self._elements_visible.get(selector, False)
            return self._elements_present.get(selector, False)
        if "document.body.innerText" in expression:
            return self._body_text
        if "window.location.href" in expression:
            return self.page.url
        if expression == "return true":
            return True
        if expression == "return false":
            return False
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
        bridge = MockBridge(url="https://x.com/wd=机械键盘")
        result = await run_check({"url_contains": "wd=机械键盘"}, bridge)
        assert result["ok"] is True
        assert "通过" in result["result"]

    @pytest.mark.asyncio
    async def test_fail(self):
        bridge = MockBridge(url="https://x.com/other")
        result = await run_check({"url_contains": "wd=机械键盘"}, bridge)
        assert result["ok"] is False
        assert "url_contains" in result["result"]

    @pytest.mark.asyncio
    async def test_includes_current_url(self):
        bridge = MockBridge(url="https://x.com/path")
        result = await run_check({"url_contains": "path"}, bridge)
        assert "current_url" in result
        assert result["current_url"] == "https://x.com/path"


class TestRunCheckElementExists:
    @pytest.mark.asyncio
    async def test_pass(self):
        bridge = MockBridge(elements_present={"#search": True})
        result = await run_check({"element_exists": "#search"}, bridge)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_fail(self):
        bridge = MockBridge(elements_present={"#search": False})
        result = await run_check({"element_exists": "#search"}, bridge)
        assert result["ok"] is False
        assert "element_exists" in result["result"]


class TestRunCheckTextContains:
    @pytest.mark.asyncio
    async def test_pass(self):
        bridge = MockBridge(body_text="页面包含搜索结果")
        result = await run_check({"text_contains": "搜索结果"}, bridge)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_fail(self):
        bridge = MockBridge(body_text="页面无相关内容")
        result = await run_check({"text_contains": "搜索结果"}, bridge)
        assert result["ok"] is False


class TestRunCheckElementVisible:
    @pytest.mark.asyncio
    async def test_pass(self):
        bridge = MockBridge(elements_visible={".result-list": True})
        result = await run_check({"element_visible": ".result-list"}, bridge)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_fail(self):
        bridge = MockBridge(elements_visible={".result-list": False})
        result = await run_check({"element_visible": ".result-list"}, bridge)
        assert result["ok"] is False


class TestRunCheckEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_check_def(self):
        result = await run_check({}, None)
        assert result["ok"] is False
        assert "不能为空" in result["error"]

    @pytest.mark.asyncio
    async def test_none_check_def(self):
        result = await run_check(None, None)
        assert result["ok"] is False
        assert "不能为 None" in result["error"]

    @pytest.mark.asyncio
    async def test_empty_string_value_rejected(self):
        bridge = MockBridge()
        result = await run_check({"url_contains": ""}, bridge)
        assert result["ok"] is False
        assert "无效参数" in result["result"]

    @pytest.mark.asyncio
    async def test_none_value_rejected(self):
        bridge = MockBridge()
        result = await run_check({"text_contains": None}, bridge)
        assert result["ok"] is False
        assert "无效参数" in result["result"]

    @pytest.mark.asyncio
    async def test_multiple_conditions_all_pass(self):
        bridge = MockBridge(
            url="https://x.com/search?q=test",
            body_text="搜索结果",
            elements_present={"#search": True}
        )
        result = await run_check({
            "url_contains": "search",
            "text_contains": "搜索结果",
            "element_exists": "#search",
        }, bridge)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_multiple_conditions_first_fails(self):
        bridge = MockBridge(url="https://x.com/other")
        result = await run_check({
            "url_contains": "search",
            "text_contains": "搜索结果",
        }, bridge)
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_always_returns_current_url(self):
        bridge = MockBridge(url="https://x.com")
        result = await run_check({"element_exists": ".x"}, bridge)
        assert "current_url" in result
        assert result["current_url"] == "https://x.com"

    @pytest.mark.asyncio
    async def test_unknown_key_rejected(self):
        result = await run_check({"foo": "bar"}, None)
        assert result["ok"] is False
        assert "不支持的 check key" in result["error"]


class TestRunCheckIgnore:
    @pytest.mark.asyncio
    async def test_ignore_returns_ok(self):
        result = await run_check({"ignore": True}, None)
        assert result["ok"] is True
        assert "显式跳过" in result["result"]

    @pytest.mark.asyncio
    async def test_ignore_no_resources_needed(self):
        result = await run_check({"ignore": True}, None, step_dir=None, shared_store=None)
        assert result["ok"] is True


class TestRunCheckOutputExists:
    @pytest.mark.asyncio
    async def test_pass(self, tmp_path):
        (tmp_path / "out.csv").write_text("a,b,c", encoding="utf-8")
        result = await run_check({"output_exists": "out.csv"}, None, step_dir=tmp_path)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_fail(self, tmp_path):
        result = await run_check({"output_exists": "nope.csv"}, None, step_dir=tmp_path)
        assert result["ok"] is False
        assert "输出文件不存在" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_step_dir(self):
        result = await run_check({"output_exists": "out.csv"}, None)
        assert result["ok"] is False
        assert "需要 step_dir" in result["error"]


class TestRunCheckFileContains:
    @pytest.mark.asyncio
    async def test_pass(self, tmp_path):
        (tmp_path / "out.csv").write_text("title,BV123,date", encoding="utf-8")
        result = await run_check({"file_contains": {"path": "out.csv", "text": "BV123"}}, None, step_dir=tmp_path)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_fail(self, tmp_path):
        (tmp_path / "out.csv").write_text("title,date", encoding="utf-8")
        result = await run_check({"file_contains": {"path": "out.csv", "text": "BV"}}, None, step_dir=tmp_path)
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_file_missing(self, tmp_path):
        result = await run_check({"file_contains": {"path": "nope.csv", "text": "x"}}, None, step_dir=tmp_path)
        assert result["ok"] is False
        assert "文件不存在" in result["error"]


class TestRunCheckJsonFieldExists:
    @pytest.mark.asyncio
    async def test_pass(self):
        shared_store = {"step_2": {"data": {"bili_videos_data": [{"title": "v1"}]}}}
        result = await run_check(
            {"json_field_exists": {"step": "step_2", "field": "bili_videos_data"}},
            None, shared_store=shared_store,
        )
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_field_missing(self):
        shared_store = {"step_2": {"data": {}}}
        result = await run_check(
            {"json_field_exists": {"step": "step_2", "field": "missing"}},
            None, shared_store=shared_store,
        )
        assert result["ok"] is False
        assert "字段不存在" in result["error"]

    @pytest.mark.asyncio
    async def test_nested_path(self):
        shared_store = {"s1": {"data": {"a": {"b": {"c": "value"}}}}}
        result = await run_check(
            {"json_field_exists": {"step": "s1", "field": "a.b.c"}},
            None, shared_store=shared_store,
        )
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_missing_shared_store(self):
        result = await run_check({"json_field_exists": {"step": "s1", "field": "x"}}, None)
        assert result["ok"] is False
        assert "需要 shared_store" in result["error"]


class TestRunCheckJsExpression:
    @pytest.mark.asyncio
    async def test_pass(self):
        bridge = MockBridge()
        result = await run_check({"js_expression": "return true"}, bridge)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_fail(self):
        bridge = MockBridge()
        result = await run_check({"js_expression": "return false"}, bridge)
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_missing_bridge(self):
        result = await run_check({"js_expression": "return true"}, None)
        assert result["ok"] is False
        assert "需要浏览器环境" in result["error"]


class TestRunCheckNonStringValues:
    @pytest.mark.asyncio
    async def test_file_contains_dict_not_misidentified(self, tmp_path):
        (tmp_path / "data.txt").write_text("hello", encoding="utf-8")
        result = await run_check({"file_contains": {"path": "data.txt", "text": "hello"}}, None, step_dir=tmp_path)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_ignore_bool_not_misidentified(self):
        result = await run_check({"ignore": True}, None)
        assert result["ok"] is True
