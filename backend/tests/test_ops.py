"""Unit tests for ToolContext (engine.ops)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.ops import ToolContext


class MockBridge:
    """Minimal mock of PlaywrightBridge for testing ToolContext."""

    def __init__(self):
        self.page = MagicMock()
        self.page.url = "https://example.com/page"

    async def evaluate(self, js: str):
        return {"title": "test"}

    async def click(self, selector: str, click_count: int = 1):
        return {"selector": selector}

    async def fill(self, selector: str, text: str):
        return {"selector": selector}

    async def capture_snapshot(self):
        return {"html": "<html></html>"}

    async def simplified_snapshot(self):
        return {"summary": "simplified"}

    async def simplify_dom(self, query: str = "", in_viewport: bool = False):
        return {"elements": []}

    async def screenshot(self):
        return "base64string"

    async def source(self):
        return "<html></html>"


@pytest.fixture
def bridge():
    return MockBridge()


@pytest.fixture
def ctx(bridge):
    return ToolContext(bridge=bridge)


# ── Browser ops ──


@pytest.mark.asyncio
async def test_wait(ctx):
    import asyncio
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await ctx.wait(1.5)
        mock_sleep.assert_called_once_with(1.5)


@pytest.mark.asyncio
async def test_eval(ctx, bridge):
    result = await ctx.eval("document.title")
    assert result == {"title": "test"}
    assert ctx._fail_count == 0


@pytest.mark.asyncio
async def test_click(ctx, bridge):
    result = await ctx.click("#btn")
    assert result == {"selector": "#btn"}
    assert ctx._fail_count == 0


@pytest.mark.asyncio
async def test_click_double(ctx, bridge):
    bridge.click = AsyncMock(return_value={"selector": "#btn"})
    await ctx.click("#btn", click_count=2)
    bridge.click.assert_called_once_with("#btn", click_count=2)


@pytest.mark.asyncio
async def test_type(ctx, bridge):
    result = await ctx.type("#input", "hello")
    assert result == {"selector": "#input"}
    assert ctx._fail_count == 0


@pytest.mark.asyncio
async def test_snapshot_full(ctx, bridge):
    result = await ctx.snapshot(mode="full")
    assert result == {"html": "<html></html>"}


@pytest.mark.asyncio
async def test_snapshot_simplified(ctx, bridge):
    result = await ctx.snapshot(mode="simplified")
    assert result == {"summary": "simplified"}


@pytest.mark.asyncio
async def test_snapshot_interactive(ctx, bridge):
    result = await ctx.snapshot(mode="interactive", query="div", in_viewport=True)
    assert result == {"elements": []}


@pytest.mark.asyncio
async def test_screenshot(ctx, bridge):
    result = await ctx.screenshot()
    assert result == "base64string"


@pytest.mark.asyncio
async def test_source(ctx, bridge):
    result = await ctx.source()
    assert result == "<html></html>"


# ── Circuit breaker ──


@pytest.mark.asyncio
async def test_circuit_breaker_triggers(ctx, bridge):
    bridge.evaluate = AsyncMock(side_effect=RuntimeError("fail"))
    for _ in range(3):
        with pytest.raises(RuntimeError, match="fail"):
            await ctx.eval("x")
    with pytest.raises(RuntimeError, match="circuit breaker"):
        await ctx.eval("x")


@pytest.mark.asyncio
async def test_circuit_breaker_resets_on_success(ctx, bridge):
    bridge.evaluate = AsyncMock(side_effect=[RuntimeError("fail"), RuntimeError("fail"), {"ok": True}])
    with pytest.raises(RuntimeError):
        await ctx.eval("x")
    with pytest.raises(RuntimeError):
        await ctx.eval("x")
    result = await ctx.eval("x")
    assert result == {"ok": True}
    assert ctx._fail_count == 0


# ── Domain whitelist ──


@pytest.mark.asyncio
async def test_domain_whitelist_allows(ctx, bridge):
    bridge.page.url = "https://example.com/page"
    ctx_dom = ToolContext(bridge=bridge, allowed_domains=["example.com"])
    result = await ctx_dom.eval("x")
    assert result == {"title": "test"}


@pytest.mark.asyncio
async def test_domain_whitelist_blocks(ctx, bridge):
    bridge.page.url = "https://evil.com/page"
    ctx_dom = ToolContext(bridge=bridge, allowed_domains=["example.com"])
    with pytest.raises(RuntimeError, match="not in allowed_domains"):
        await ctx_dom.eval("x")


@pytest.mark.asyncio
async def test_domain_whitelist_none_allows_all(ctx, bridge):
    bridge.page.url = "https://any.com/page"
    ctx_dom = ToolContext(bridge=bridge, allowed_domains=None)
    result = await ctx_dom.eval("x")
    assert result == {"title": "test"}
