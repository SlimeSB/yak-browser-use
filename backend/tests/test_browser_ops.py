"""Layer 3: execute_browser_op integration tests.

Uses real headless Chromium via Playwright, loading local HTML fixtures
with file:// URLs — zero network dependency.

Uses subprocess-per-test isolation to fully decouple from pytest-asyncio's
event loop management.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from urllib.request import pathname2url

import pytest
from playwright.async_api import async_playwright, Page

from yak_browser_use.engine.executor import execute_browser_op

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _file_url(html_name: str) -> str:
    """Convert a fixture filename to a file:// URL."""
    path = FIXTURES_DIR / html_name
    return "file://" + pathname2url(str(path.absolute()))


class PlaywrightBridgeAdapter:
    """Adapter: Playwright Page → BrowserBridge protocol.

    Implements just enough of the BrowserBridge interface for execute_browser_op.
    """

    def __init__(self, page: Page):
        self._page = page

    async def goto(self, url: str) -> dict:
        await self._page.goto(url)
        return {"url": url}

    async def reset_ref_map(self) -> None:
        pass

    async def click(self, selector: str, click_count: int = 1) -> dict:
        await self._page.click(selector, click_count=click_count)
        return {"selector": selector}

    async def fill(self, selector: str, text: str) -> dict:
        await self._page.fill(selector, text)
        return {"selector": selector}

    async def a11y_snapshot(self, query: str = "") -> dict:
        return await self._page.accessibility.snapshot() or {}

    async def aria_snapshot(self) -> dict:
        return {}

    async def _progressive_snapshot(self, query: str = "") -> dict:
        # Use page content as a basic progressive snapshot
        elements = await self._page.evaluate("""() => {
            const result = [];
            document.querySelectorAll('button, a, input, select, [role]').forEach((el, i) => {
                result.push({
                    ref: '@e' + i,
                    role: el.getAttribute('role') || el.tagName.toLowerCase(),
                    name: el.textContent?.trim()?.slice(0, 50) || el.getAttribute('aria-label') || '',
                    selector: el.tagName.toLowerCase() + (el.id ? '#' + el.id : ''),
                    visible: el.offsetParent !== null
                });
            });
            return result;
        }""")
        return {
            "elements": elements or [],
            "url": self._page.url,
            "title": await self._page.title(),
        }

    async def capture_snapshot(self) -> dict:
        return {
            "screenshot_base64": "",
            "html": await self._page.content(),
            "url": self._page.url,
            "title": await self._page.title(),
        }

    async def evaluate(self, js: str) -> Any:
        return await self._page.evaluate(js)

    async def get_page_html(self, cached: bool = False) -> str:
        return await self._page.content()

    async def source(self, strip_styles: bool = False, only_body: bool = False) -> str:
        html = await self._page.content()
        if only_body:
            import re
            match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
            html = match.group(1) if match else html
        return html

    async def expand_branch(self, key: str, limit: int = 30, offset: int = 0) -> dict:
        return {"elements": []}

    def get_element_by_index(self, ref: str) -> dict:
        return {"ref": ref, "error": "not supported in test adapter"}

    async def hover(self, selector: str) -> dict:
        await self._page.hover(selector)
        return {"selector": selector}

    async def unhover(self, selector: str) -> dict:
        return {"selector": selector}

    async def focus(self, selector: str) -> dict:
        await self._page.focus(selector)
        return {"selector": selector}

    async def select(self, selector: str, value: str, mode: str = "value") -> dict:
        if mode == "value":
            await self._page.select_option(selector, value=value)
        else:
            await self._page.select_option(selector, label=value)
        return {"selector": selector}

    async def clear(self, selector: str, mode: str = "js") -> dict:
        if mode == "pw":
            el = await self._page.query_selector(selector)
            if el:
                await el.fill("")
        else:
            await self._page.evaluate(f"document.querySelector('{selector}').value = ''")
        return {"selector": selector}

    async def keyboard_press(self, key: str) -> dict:
        await self._page.keyboard.press(key)
        return {"key": key}

    async def keyboard_type(self, text: str) -> dict:
        await self._page.keyboard.type(text)
        return {"text": text}

    async def navigate(self, action: str, hard: bool = False) -> dict:
        if action == "back":
            await self._page.go_back()
        elif action == "forward":
            await self._page.go_forward()
        elif action == "reload":
            await self._page.reload()
        return {"action": action}

    async def wait(self, mode: str = "time", **kwargs: Any) -> dict:
        if mode == "time":
            duration = kwargs.get("duration", 1000)
            await self._page.wait_for_timeout(duration)
        elif mode == "selector":
            selector = kwargs.get("selector", "")
            await self._page.wait_for_selector(selector)
        elif mode == "load":
            await self._page.wait_for_load_state(kwargs.get("state", "load"))
        return {"mode": mode}

    async def tab_new(self, url: str = "about:blank") -> dict:
        ctx = self._page.context
        new_page = await ctx.new_page()
        await new_page.goto(url)
        return {"target_id": str(id(new_page))}

    async def tab_switch(self, target_id: str) -> dict:
        return {"target_id": target_id}

    async def tab_close(self, target_id: str) -> dict:
        return {"target_id": target_id}

    async def tab_list(self) -> list[dict]:
        ctx = self._page.context
        return [{"target_id": str(id(p)), "url": p.url} for p in ctx.pages]

    async def copy_to_clipboard(self, selector: str) -> dict:
        return {"copied": False}

    async def paste_from_clipboard(self, selector: str, index: int = -1) -> dict:
        return {"pasted": False}

    @property
    def page(self) -> Any:
        return self._page


class _TestContext:  # noqa: pytest won't collect (underscore prefix)
    """Manages a Playwright browser+page for testing execute_browser_op."""

    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._pw = None
        self._browser = None
        self._page = None
        self._bridge = None

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    def start(self):
        async def _do():
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=True)
            self._page = await self._browser.new_page()
            self._bridge = PlaywrightBridgeAdapter(self._page)
        self._run(_do())

    def goto(self, url: str):
        self._run(self._page.goto(url))

    def inner_text(self, sel: str) -> str:
        return self._run(self._page.inner_text(sel))

    def input_value(self, sel: str) -> str:
        return self._run(self._page.input_value(sel))

    def is_visible(self, sel: str) -> bool:
        return self._run(self._page.is_visible(sel))

    def fill(self, sel: str, text: str):
        self._run(self._page.fill(sel, text))

    def click(self, sel: str):
        self._run(self._page.click(sel))

    def set_viewport(self, w: int, h: int):
        self._run(self._page.set_viewport_size({"width": w, "height": h}))

    def wait_timeout(self, ms: int):
        self._run(self._page.wait_for_timeout(ms))

    def call_op(self, op_type: str, params: dict) -> dict:
        return self._run(execute_browser_op(op_type, params, self._bridge))

    def close(self):
        if self._page:
            self._run(self._page.close())
        if self._browser:
            self._run(self._browser.close())
        if self._pw:
            self._run(self._pw.stop())
        self._loop.close()


@pytest.fixture
def ctx() -> _TestContext:
    """Fresh browser context per test (full isolation)."""
    ctx = _TestContext()
    ctx.start()
    yield ctx
    ctx.close()


# ── goto ─────────────────────────────────────────────────────────


class TestGoto:
    def test_goto_file_url(self, ctx: _TestContext):
        url = _file_url("search.html")
        result = ctx.call_op("goto", {"url": url})
        assert result["ok"] is True
        assert result["result"]["url"] == url


# ── fill ─────────────────────────────────────────────────────────


class TestFill:
    def test_fill_input(self, ctx: PageCtx):
        url = _file_url("search.html")
        ctx.goto(url)

        result = ctx.call_op("fill", {
            "selector": "#search-input",
            "text": "测试关键词",
        })

        assert result["ok"] is True
        value = ctx.input_value("#search-input")
        assert value == "测试关键词"


# ── click ────────────────────────────────────────────────────────


class TestClick:
    def test_click_submit_form(self, ctx: PageCtx):
        url = _file_url("search.html")
        ctx.goto(url)

        ctx.fill("#search-input", "hello")
        result = ctx.call_op("click", {"selector": "#search-btn"})

        assert result["ok"] is True
        ctx.wait_timeout(500)
        output_text = ctx.inner_text("#output")
        assert "搜索完成" in output_text


# ── snapshot ─────────────────────────────────────────────────────


class TestSnapshot:
    def test_snapshot_progressive(self, ctx: PageCtx):
        url = _file_url("search.html")
        ctx.goto(url)

        result = ctx.call_op("snapshot", {"mode": "progressive"})

        assert result["ok"] is True
        snap = result["result"]
        assert isinstance(snap, dict)
        assert "elements" in snap


# ── scroll ───────────────────────────────────────────────────────


class TestScroll:
    def test_scroll_down(self, ctx: PageCtx):
        url = _file_url("search.html")
        ctx.goto(url)
        ctx.set_viewport(800, 600)

        result = ctx.call_op("scroll", {"direction": "down", "amount": 300})
        assert result["ok"] is True


# ── source ───────────────────────────────────────────────────────


class TestSource:
    def test_source_full_html(self, ctx: PageCtx):
        url = _file_url("search.html")
        ctx.goto(url)

        result = ctx.call_op("source", {})

        assert result["ok"] is True
        html = result.get("html", "")
        assert "搜索测试页面" in html

    def test_source_with_selector(self, ctx: PageCtx):
        url = _file_url("search.html")
        ctx.goto(url)

        result = ctx.call_op("source", {"selector": "#intro-text"})

        assert result["ok"] is True
        html = result.get("html", "")
        assert "欢迎使用搜索功能" in html


# ── select ───────────────────────────────────────────────────────


class TestSelect:
    def test_select_dropdown(self, ctx: PageCtx):
        url = _file_url("search.html")
        ctx.goto(url)

        result = ctx.call_op("select", {"selector": "#category-select", "value": "news"})

        assert result["ok"] is True
        value = ctx.input_value("#category-select")
        assert value == "news"


# ── keyboard ─────────────────────────────────────────────────────


class TestKeyboard:
    def test_keyboard_type(self, ctx: PageCtx):
        url = _file_url("search.html")
        ctx.goto(url)

        ctx.click("#search-input")
        result = ctx.call_op("keyboard", {"mode": "text", "text": "typed text"})

        assert result["ok"] is True
        value = ctx.input_value("#search-input")
        assert value == "typed text"


# ── hover ────────────────────────────────────────────────────────


class TestHover:
    def test_hover_shows_tooltip(self, ctx: PageCtx):
        url = _file_url("search.html")
        ctx.goto(url)

        result = ctx.call_op("hover", {"selector": "#hover-target"})
        assert result["ok"] is True

        ctx.wait_timeout(200)
        tooltip_visible = ctx.is_visible("#tooltip")
        assert tooltip_visible is True


# ── wait ─────────────────────────────────────────────────────────


class TestWait:
    def test_wait_time(self, ctx: PageCtx):
        url = _file_url("search.html")
        ctx.goto(url)

        result = ctx.call_op("wait", {"mode": "time", "duration": 200})
        assert result["ok"] is True


# ── navigate ─────────────────────────────────────────────────────


class TestNavigate:
    def test_navigate_back(self, ctx: PageCtx):
        url1 = _file_url("search.html")
        url2 = _file_url("a11y_test.html")

        ctx.goto(url1)
        ctx.goto(url2)

        result = ctx.call_op("navigate", {"action": "back"})
        assert result["ok"] is True
        ctx.wait_timeout(500)


# ── clear ────────────────────────────────────────────────────────


class TestClear:
    def test_clear_input(self, ctx: PageCtx):
        url = _file_url("search.html")
        ctx.goto(url)

        ctx.fill("#search-input", "some text")
        result = ctx.call_op("clear", {"selector": "#search-input"})

        assert result["ok"] is True
        value = ctx.input_value("#search-input")
        assert value == ""


# ── error handling ───────────────────────────────────────────────


class TestErrorHandling:
    def test_unknown_op_type(self, ctx: PageCtx):
        url = _file_url("search.html")
        ctx.goto(url)

        result = ctx.call_op("nonexistent_op", {})
        assert result["ok"] is False
        assert "Unknown" in result["error"]

    def test_click_missing_selector(self, ctx: PageCtx):
        url = _file_url("search.html")
        ctx.goto(url)

        result = ctx.call_op("click", {})
        assert result["ok"] is False

    def test_fill_missing_selector(self, ctx: PageCtx):
        url = _file_url("search.html")
        ctx.goto(url)

        result = ctx.call_op("fill", {"text": "test"})
        assert result["ok"] is False
