"""Tests for browser_extract_list/table/details chat tools."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from yak_browser_use.tools.extract_fields import (
    _build_list_selector_js_with_attr,
    _build_details_container_js,
    _safe_selector,
)
from yak_browser_use.tools.registry import (
    LIST_TRUNC_LIMIT,
    TABLE_TRUNC_LIMIT,
    ToolContext,
    build_registry,
    registry,
)


@pytest.fixture(autouse=True)
def _ensure_registry():
    build_registry()
    yield


def _make_ctx(shared_store: dict | None = None) -> ToolContext:
    bridge = MagicMock()
    bridge.evaluate = AsyncMock()
    cdp = MagicMock()
    cdp.bridge = bridge
    return ToolContext(cdp_helpers=cdp, shared_store=shared_store or {})


class TestBrowserExtractList:
    @pytest.mark.asyncio
    async def test_generic_list_extraction(self):
        ctx = _make_ctx()
        ctx.cdp_helpers.bridge.evaluate.return_value = [
            {"text": "Item 1", "href": "https://example.com/1"},
            {"text": "Item 2", "href": "https://example.com/2"},
        ]
        result = await registry.dispatch("browser_extract_list", {}, ctx)
        assert result["ok"] is True
        assert len(result["result"]["items"]) == 2
        assert result["result"]["items"][0]["text"] == "Item 1"

    @pytest.mark.asyncio
    async def test_custom_selector(self):
        ctx = _make_ctx()
        ctx.cdp_helpers.bridge.evaluate.return_value = [
            {"text": "Card 1", "href": ""},
        ]
        result = await registry.dispatch(
            "browser_extract_list", {"selector": ".bili-video-card"}, ctx
        )
        assert result["ok"] is True
        assert len(result["result"]["items"]) == 1
        # Verify the JS contains the escaped selector
        call_js = ctx.cdp_helpers.bridge.evaluate.call_args[0][0]
        assert ".bili-video-card" in call_js

    @pytest.mark.asyncio
    async def test_fields_mapping(self):
        ctx = _make_ctx()
        ctx.cdp_helpers.bridge.evaluate.return_value = [
            {"title": "Title 1", "link": "https://example.com/1"},
        ]
        result = await registry.dispatch(
            "browser_extract_list",
            {"selector": ".item", "fields": {"title": "h3", "link": "@href"}},
            ctx,
        )
        assert result["ok"] is True
        assert result["result"]["items"][0]["title"] == "Title 1"
        assert result["result"]["items"][0]["link"] == "https://example.com/1"

    @pytest.mark.asyncio
    async def test_fields_without_selector_returns_error(self):
        ctx = _make_ctx()
        result = await registry.dispatch(
            "browser_extract_list",
            {"fields": {"title": "h3"}},
            ctx,
        )
        assert result["ok"] is False
        assert "selector" in result["error"]

    @pytest.mark.asyncio
    async def test_fields_type_error_returns_error(self):
        ctx = _make_ctx()
        result = await registry.dispatch(
            "browser_extract_list",
            {"selector": ".item", "fields": "h3"},
            ctx,
        )
        assert result["ok"] is False
        assert "object" in result["error"]

    @pytest.mark.asyncio
    async def test_fields_with_output_to(self):
        ctx = _make_ctx()
        items = [{"title": f"T{i}"} for i in range(60)]
        ctx.cdp_helpers.bridge.evaluate.return_value = items
        result = await registry.dispatch(
            "browser_extract_list",
            {"selector": ".item", "fields": {"title": "h3"}, "output_to": "data"},
            ctx,
        )
        assert result["ok"] is True
        assert result["_output_to"] == "data"
        assert len(ctx.shared_store["data"]) == 60
        assert len(result["result"]["items"]) == 50
        # New output_to enrichments
        assert result["key"] == "data"
        assert result["count"] == 60
        assert result["fields"] == ["title"]

    @pytest.mark.asyncio
    async def test_evaluate_returns_null(self):
        ctx = _make_ctx()
        ctx.cdp_helpers.bridge.evaluate.return_value = None
        result = await registry.dispatch("browser_extract_list", {}, ctx)
        assert result["ok"] is True
        assert result["result"]["items"] == []
        assert result["result"]["count"] == 0

    @pytest.mark.asyncio
    async def test_output_to_stores_full_data(self):
        ctx = _make_ctx()
        items = [{"text": f"Item {i}", "href": ""} for i in range(60)]
        ctx.cdp_helpers.bridge.evaluate.return_value = items
        result = await registry.dispatch(
            "browser_extract_list", {"output_to": "videos"}, ctx
        )
        assert result["ok"] is True
        assert result["_output_to"] == "videos"
        assert ctx.shared_store["videos"] == items
        assert len(ctx.shared_store["videos"]) == 60

    @pytest.mark.asyncio
    async def test_truncation_with_output_to(self):
        ctx = _make_ctx()
        items = [{"text": f"Item {i}", "href": ""} for i in range(60)]
        ctx.cdp_helpers.bridge.evaluate.return_value = items
        result = await registry.dispatch(
            "browser_extract_list", {"output_to": "videos"}, ctx
        )
        assert result["ok"] is True
        assert result["_truncated"] is True
        assert result["total"] == 60
        assert result["count"] == 60  # top-level count (full data) when output_to is set
        assert result["key"] == "videos"
        assert len(result["result"]["items"]) == 50

    @pytest.mark.asyncio
    async def test_truncation_without_output_to(self):
        ctx = _make_ctx()
        items = [{"text": f"Item {i}", "href": ""} for i in range(60)]
        ctx.cdp_helpers.bridge.evaluate.return_value = items
        result = await registry.dispatch("browser_extract_list", {}, ctx)
        assert result["ok"] is True
        assert result["_truncated"] is True
        assert result["total"] == 60
        assert len(result["result"]["items"]) == 50

    @pytest.mark.asyncio
    async def test_selector_with_single_quote_escaped(self):
        ctx = _make_ctx()
        ctx.cdp_helpers.bridge.evaluate.return_value = []
        result = await registry.dispatch(
            "browser_extract_list", {"selector": "div[data-name='test']"}, ctx
        )
        assert result["ok"] is True
        call_js = ctx.cdp_helpers.bridge.evaluate.call_args[0][0]
        assert "data-name=\\'test\\'" in call_js

    @pytest.mark.asyncio
    async def test_no_browser_returns_error(self):
        ctx = ToolContext()
        result = await registry.dispatch("browser_extract_list", {}, ctx)
        assert result["ok"] is False
        assert "浏览器" in result["error"]


class TestBrowserExtractTable:
    @pytest.mark.asyncio
    async def test_generic_table_extraction(self):
        ctx = _make_ctx()
        ctx.cdp_helpers.bridge.evaluate.return_value = {
            "headers": ["Name", "Age"],
            "rows": [["Alice", "30"], ["Bob", "25"]],
        }
        result = await registry.dispatch("browser_extract_table", {}, ctx)
        assert result["ok"] is True
        assert result["headers"] == ["Name", "Age"]
        assert len(result["rows"]) == 2

    @pytest.mark.asyncio
    async def test_custom_selector(self):
        ctx = _make_ctx()
        ctx.cdp_helpers.bridge.evaluate.return_value = {
            "headers": ["Col1"],
            "rows": [["Val1"]],
        }
        result = await registry.dispatch(
            "browser_extract_table", {"selector": ".data-table"}, ctx
        )
        assert result["ok"] is True
        call_js = ctx.cdp_helpers.bridge.evaluate.call_args[0][0]
        assert ".data-table" in call_js

    @pytest.mark.asyncio
    async def test_output_to_stores_full_data(self):
        ctx = _make_ctx()
        rows = [[f"Row {i}"] for i in range(150)]
        ctx.cdp_helpers.bridge.evaluate.return_value = {
            "headers": ["Col1"],
            "rows": rows,
        }
        result = await registry.dispatch(
            "browser_extract_table", {"output_to": "my_table"}, ctx
        )
        assert result["ok"] is True
        assert result["_output_to"] == "my_table"
        assert len(ctx.shared_store["my_table"]["rows"]) == 150

    @pytest.mark.asyncio
    async def test_truncation(self):
        ctx = _make_ctx()
        rows = [[f"Row {i}"] for i in range(150)]
        ctx.cdp_helpers.bridge.evaluate.return_value = {
            "headers": ["Col1"],
            "rows": rows,
        }
        result = await registry.dispatch("browser_extract_table", {}, ctx)
        assert result["ok"] is True
        assert result["_truncated"] is True
        assert result["total_rows"] == 150
        assert len(result["rows"]) == 100

    @pytest.mark.asyncio
    async def test_evaluate_returns_null(self):
        ctx = _make_ctx()
        ctx.cdp_helpers.bridge.evaluate.return_value = None
        result = await registry.dispatch("browser_extract_table", {}, ctx)
        assert result["ok"] is True
        assert result["headers"] == []
        assert result["rows"] == []

    @pytest.mark.asyncio
    async def test_no_browser_returns_error(self):
        ctx = ToolContext()
        result = await registry.dispatch("browser_extract_table", {}, ctx)
        assert result["ok"] is False
        assert "浏览器" in result["error"]


class TestBrowserExtractDetails:
    @pytest.mark.asyncio
    async def test_generic_details_extraction(self):
        ctx = _make_ctx()
        ctx.cdp_helpers.bridge.evaluate.return_value = {
            "text": "Product page text",
            "details": [{"label": "Brand", "value": "Acme"}],
        }
        result = await registry.dispatch("browser_extract_details", {}, ctx)
        assert result["ok"] is True
        assert result["text"] == "Product page text"
        assert len(result["details"]) == 1

    @pytest.mark.asyncio
    async def test_custom_selector(self):
        ctx = _make_ctx()
        ctx.cdp_helpers.bridge.evaluate.return_value = {
            "text": "Details text",
            "details": [{"label": "SKU", "value": "123"}],
        }
        result = await registry.dispatch(
            "browser_extract_details", {"selector": "#product-details"}, ctx
        )
        assert result["ok"] is True
        call_js = ctx.cdp_helpers.bridge.evaluate.call_args[0][0]
        assert "#product-details" in call_js

    @pytest.mark.asyncio
    async def test_output_to_stores_full_data(self):
        ctx = _make_ctx()
        full = {"text": "Page", "details": [{"label": "Key", "value": "Val"}]}
        ctx.cdp_helpers.bridge.evaluate.return_value = full
        result = await registry.dispatch(
            "browser_extract_details", {"output_to": "product_info"}, ctx
        )
        assert result["ok"] is True
        assert result["_output_to"] == "product_info"
        assert ctx.shared_store["product_info"] == full

    @pytest.mark.asyncio
    async def test_evaluate_returns_null(self):
        ctx = _make_ctx()
        ctx.cdp_helpers.bridge.evaluate.return_value = None
        result = await registry.dispatch("browser_extract_details", {}, ctx)
        assert result["ok"] is True
        assert result["text"] == ""
        assert result["details"] == []

    @pytest.mark.asyncio
    async def test_no_browser_returns_error(self):
        ctx = ToolContext()
        result = await registry.dispatch("browser_extract_details", {}, ctx)
        assert result["ok"] is False
        assert "浏览器" in result["error"]


class TestTruncationLimits:
    def test_limits_are_module_constants(self):
        assert LIST_TRUNC_LIMIT == 50
        assert TABLE_TRUNC_LIMIT == 100


class TestSharedBuilders:
    def test_build_list_selector_js_with_attr_no_attr(self):
        js = _build_list_selector_js_with_attr(".item")
        assert ".item" in js
        assert "querySelector" in js
        assert "getAttribute" not in js or "href" in js

    def test_build_list_selector_js_with_attr_has_attr(self):
        js = _build_list_selector_js_with_attr(".item", "data-id")
        assert "data-id" in js

    def test_build_details_container_js(self):
        js = _build_details_container_js("#product")
        assert "#product" in js
        assert "querySelectorAll('tr')" in js

    def test_safe_selector_escapes_single_quote(self):
        assert _safe_selector("div[data-name='test']") == "div[data-name=\\'test\\']"
