"""Unit tests for ToolContext (engine.ops)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.ops import ToolContext


class MockBridge:
    """Minimal mock of PlaywrightBridge for testing ToolContext."""

    def __init__(self):
        self.page = MagicMock()
        self.page.url = "https://example.com/page"
        self._context = MagicMock()

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
    return ToolContext(
        bridge=bridge,
        input_files={"input": "/path/to/input.json"},
        output_dir="/tmp/output",
        params={"key": "value"},
    )


# ── Browser ops ──


@pytest.mark.asyncio
async def test_wait(ctx):
    import asyncio
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await ctx.wait(1.5)
        mock_sleep.assert_called_once_with(1.5)


@pytest.mark.asyncio
async def test_evaluate(ctx, bridge):
    result = await ctx.evaluate("document.title")
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
async def test_fill(ctx, bridge):
    result = await ctx.fill("#input", "hello")
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


# ── CDP escape hatch ──


@pytest.mark.asyncio
async def test_cdp(ctx, bridge):
    mock_session = AsyncMock()
    mock_session.send = AsyncMock(return_value={"result": "ok"})
    bridge._context.new_cdp_session = AsyncMock(return_value=mock_session)

    result = await ctx.cdp("Page.captureScreenshot", {"format": "png"})
    assert result == {"result": "ok"}
    mock_session.detach.assert_called_once()


@pytest.mark.asyncio
async def test_cdp_page_none(bridge):
    bridge.page = None
    ctx_no_page = ToolContext(bridge, {}, "/tmp", {})
    with pytest.raises(RuntimeError, match="bridge.page is None"):
        await ctx_no_page.cdp("Page.captureScreenshot", {})


# ── Data ops ──


@pytest.mark.asyncio
async def test_save_json(ctx, tmp_path):
    ctx.output_dir = str(tmp_path)
    path = await ctx.save_json({"a": 1}, "test.json")
    assert Path(path).exists()
    data = json.loads(Path(path).read_text())
    assert data == {"a": 1}


@pytest.mark.asyncio
async def test_load_json(ctx, tmp_path):
    p = tmp_path / "input.json"
    p.write_text(json.dumps({"x": 42}))
    ctx.input_files = {"data": str(p)}
    result = await ctx.load_json("data")
    assert result == {"x": 42}


@pytest.mark.asyncio
async def test_load_json_missing(ctx):
    with pytest.raises(FileNotFoundError):
        await ctx.load_json("nonexistent")


@pytest.mark.asyncio
async def test_save_csv(ctx, tmp_path):
    ctx.output_dir = str(tmp_path)
    path = await ctx.save_csv([{"a": "1", "b": "2"}], "test.csv")
    assert Path(path).exists()
    content = Path(path).read_text(encoding="utf-8-sig")
    assert "a,b" in content


@pytest.mark.asyncio
async def test_load_csv(ctx, tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("a,b\n1,2\n3,4", encoding="utf-8-sig")
    ctx.input_files = {"data": str(p)}
    result = await ctx.load_csv("data")
    assert len(result) == 2
    assert result[0]["a"] == "1"


@pytest.mark.asyncio
async def test_save_bytes(ctx, tmp_path):
    ctx.output_dir = str(tmp_path)
    path = await ctx.save_bytes(b"hello", "test.bin")
    assert Path(path).read_bytes() == b"hello"


# ── Circuit breaker ──


@pytest.mark.asyncio
async def test_circuit_breaker_triggers(ctx, bridge):
    bridge.evaluate = AsyncMock(side_effect=RuntimeError("fail"))
    for _ in range(3):
        with pytest.raises(RuntimeError, match="fail"):
            await ctx.evaluate("x")
    with pytest.raises(RuntimeError, match="circuit breaker"):
        await ctx.evaluate("x")


@pytest.mark.asyncio
async def test_circuit_breaker_resets_on_success(ctx, bridge):
    bridge.evaluate = AsyncMock(side_effect=[RuntimeError("fail"), RuntimeError("fail"), {"ok": True}])
    with pytest.raises(RuntimeError):
        await ctx.evaluate("x")
    with pytest.raises(RuntimeError):
        await ctx.evaluate("x")
    result = await ctx.evaluate("x")
    assert result == {"ok": True}
    assert ctx._fail_count == 0


# ── Domain whitelist ──


@pytest.mark.asyncio
async def test_domain_whitelist_allows(ctx, bridge):
    bridge.page.url = "https://example.com/page"
    ctx_dom = ToolContext(bridge, {}, "/tmp", {}, allowed_domains=["example.com"])
    result = await ctx_dom.evaluate("x")
    assert result == {"title": "test"}


@pytest.mark.asyncio
async def test_domain_whitelist_blocks(ctx, bridge):
    bridge.page.url = "https://evil.com/page"
    ctx_dom = ToolContext(bridge, {}, "/tmp", {}, allowed_domains=["example.com"])
    with pytest.raises(RuntimeError, match="not in allowed_domains"):
        await ctx_dom.evaluate("x")


@pytest.mark.asyncio
async def test_domain_whitelist_none_allows_all(ctx, bridge):
    bridge.page.url = "https://any.com/page"
    ctx_dom = ToolContext(bridge, {}, "/tmp", {}, allowed_domains=None)
    result = await ctx_dom.evaluate("x")
    assert result == {"title": "test"}


# ── DANGEROUS_MODULES ──


def test_dangerous_modules_is_frozenset():
    assert isinstance(ToolContext.DANGEROUS_MODULES, frozenset)


def test_dangerous_modules_contains_expected():
    assert "os" in ToolContext.DANGEROUS_MODULES
    assert "subprocess" in ToolContext.DANGEROUS_MODULES
    assert "sys" in ToolContext.DANGEROUS_MODULES
    assert "shutil" in ToolContext.DANGEROUS_MODULES
    assert "socket" in ToolContext.DANGEROUS_MODULES
    assert "ctypes" in ToolContext.DANGEROUS_MODULES
    assert "signal" in ToolContext.DANGEROUS_MODULES
    assert "multiprocessing" in ToolContext.DANGEROUS_MODULES
    assert "threading" in ToolContext.DANGEROUS_MODULES
    assert "importlib" in ToolContext.DANGEROUS_MODULES
