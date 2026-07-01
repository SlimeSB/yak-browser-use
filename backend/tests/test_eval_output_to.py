"""Tests for browser_eval_js output_to and return_format features."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yak_browser_use.tools.registry import (
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


@pytest.mark.asyncio
async def test_output_to_stores_in_shared_store():
    ctx = _make_ctx()
    ctx.cdp_helpers.bridge.evaluate.return_value = 42
    result = await registry.dispatch("browser_eval_js", {"code": "1+1", "output_to": "my_var"}, ctx)
    assert result["ok"] is True
    assert ctx.shared_store["my_var"] == 42


@pytest.mark.asyncio
async def test_output_to_not_provided_does_not_modify_store():
    ctx = _make_ctx({"existing": "val"})
    ctx.cdp_helpers.bridge.evaluate.return_value = 99
    result = await registry.dispatch("browser_eval_js", {"code": "1+1"}, ctx)
    assert result["ok"] is True
    assert "existing" in ctx.shared_store
    assert "my_var" not in ctx.shared_store


@pytest.mark.asyncio
async def test_return_format_raw():
    ctx = _make_ctx()
    ctx.cdp_helpers.bridge.evaluate.return_value = 42
    result = await registry.dispatch("browser_eval_js", {"code": "1+1", "return_format": "raw"}, ctx)
    assert result["ok"] is True
    assert result["result"] == 42


@pytest.mark.asyncio
async def test_return_format_json():
    ctx = _make_ctx()
    ctx.cdp_helpers.bridge.evaluate.return_value = [1, 2, 3]
    result = await registry.dispatch("browser_eval_js", {"code": "[1,2,3]", "return_format": "json"}, ctx)
    assert result["ok"] is True
    assert result["result"] == "[1, 2, 3]"


@pytest.mark.asyncio
async def test_return_format_csv_array_of_dicts():
    ctx = _make_ctx()
    ctx.cdp_helpers.bridge.evaluate.return_value = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
    result = await registry.dispatch("browser_eval_js", {"code": "data", "return_format": "csv"}, ctx)
    assert result["ok"] is True
    csv_text = result["result"]
    assert "name,age" in csv_text or "age,name" in csv_text
    assert "Alice" in csv_text
    assert "Bob" in csv_text


@pytest.mark.asyncio
async def test_return_format_csv_non_array_fallback():
    ctx = _make_ctx()
    ctx.cdp_helpers.bridge.evaluate.return_value = "hello"
    result = await registry.dispatch("browser_eval_js", {"code": "'hello'", "return_format": "csv"}, ctx)
    assert result["ok"] is True
    assert "requires array" in result["result"]


@pytest.mark.asyncio
async def test_output_to_and_return_format_together():
    ctx = _make_ctx()
    ctx.cdp_helpers.bridge.evaluate.return_value = [{"x": 1}]
    result = await registry.dispatch(
        "browser_eval_js",
        {"code": "data", "output_to": "my_data", "return_format": "csv"},
        ctx,
    )
    assert result["ok"] is True
    assert "my_data" in ctx.shared_store
    assert ctx.shared_store["my_data"] == [{"x": 1}]
