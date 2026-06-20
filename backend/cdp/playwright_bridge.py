"""PlaywrightBridge — unified browser driver via playwright.chromium.connect_over_cdp().

Replaces CDPDaemon's raw WebSocket path. All browser operations (interaction,
navigation, snapshot, highlight, clipboard) go through Playwright's Page API,
which provides auto-wait, auto-scroll, and auto-retry.

Usage::

    bridge = PlaywrightBridge(cdp_url="http://127.0.0.1:9222")
    await bridge.start()
    await bridge.goto("https://example.com")
    await bridge.click("#btn")
    await bridge.stop()
"""

from __future__ import annotations

import asyncio
import base64
import json as _json
import logging
import uuid
from typing import Any

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Interactive element detection heuristics
# ---------------------------------------------------------------------------

_INTERACTIVE_TAGS = frozenset({
    "a", "button", "input", "select", "textarea", "details", "summary",
    "option", "optgroup", "label", "datalist", "output", "fieldset",
    "video", "audio",
})
_INTERACTIVE_ROLES = frozenset({
    "button", "link", "checkbox", "radio", "switch", "tab",
    "menuitem", "menuitemcheckbox", "menuitemradio", "option",
    "combobox", "listbox", "textbox", "searchbox", "slider",
    "spinbutton", "treeitem",
})


def _is_interactive(tag: str, attrs: dict[str, str]) -> bool:
    if tag in _INTERACTIVE_TAGS:
        if tag == "a" and not attrs.get("href"):
            return False
        if tag == "input" and attrs.get("type", "").lower() == "hidden":
            return False
        return True
    if attrs.get("role", "").lower() in _INTERACTIVE_ROLES:
        return True
    if attrs.get("tabindex") is not None:
        return True
    if attrs.get("onclick"):
        return True
    cedit = attrs.get("contenteditable")
    if cedit is not None and cedit.lower() in ("true", ""):
        return True
    if tag in ("div", "span", "li") and any(k.startswith("data-v-") or k.startswith("data-react-") for k in attrs):
        return True
    return False


def _is_tentative(tag: str, attrs: dict[str, str]) -> bool:
    if tag in _INTERACTIVE_TAGS:
        return False
    if attrs.get("role", "").lower() in _INTERACTIVE_ROLES:
        return False
    if attrs.get("tabindex") is not None:
        return False
    if attrs.get("onclick"):
        return False
    cedit = attrs.get("contenteditable")
    if cedit is not None and cedit.lower() in ("true", ""):
        return False
    return True


def _build_selector_from_node(tag: str, attrs: dict[str, str]) -> str:
    node_id = attrs.get("id")
    if node_id:
        return f"#{node_id}"

    parts = [tag]
    cls = attrs.get("class", "")
    for c in cls.split():
        if c:
            parts.append(f".{c}")

    for attr_name in ("name", "type", "role", "aria-label", "href", "placeholder", "title", "target"):
        val = attrs.get(attr_name)
        if val and '"' not in val:
            parts.append(f'[{attr_name}="{val}"]')

    return "".join(parts)


# ---------------------------------------------------------------------------
# highlight JS — injected into every new page so @eN badges are always visible
# ---------------------------------------------------------------------------

_HIGHLIGHT_BOOTSTRAP = """
(function() {
    if (window.__ybu_highlight_ready) return;
    window.__ybu_highlight_ready = true;

    function _ybu_run() {
        if (!document.body) return;
        var oldC = document.getElementById('ybu-highlights');
        if (oldC) {
            if (oldC._ybu_scrollFn) window.removeEventListener('scroll', oldC._ybu_scrollFn);
            if (oldC._ybu_resizeFn) window.removeEventListener('resize', oldC._ybu_resizeFn);
            if (oldC._ybu_mo) oldC._ybu_mo.disconnect();
            oldC.remove();
        }
        var outlined = document.querySelectorAll('[data-ybu-outlined]');
        for (var i = 0; i < outlined.length; i++) {
            outlined[i].style.outline = '';
            outlined[i].removeAttribute('data-ybu-outlined');
        }
        var container = document.createElement('div');
        container.id = 'ybu-highlights';
        container.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:2147483646;';
        document.body.appendChild(container);

        var elements = window.__ybu_last_elements || [];
        var selIdx = {};
        for (var i = 0; i < elements.length; i++) {
            var el = elements[i];
            if (el.selector) {
                try {
                    var si = selIdx[el.selector] || 0;
                    selIdx[el.selector] = si + 1;
                    var all = document.querySelectorAll(el.selector);
                    if (all.length > si) {
                        var target = all[si];
                        target.style.outline = '2px dashed #3b82f6';
                        target.style.outlineOffset = '0px';
                        target.setAttribute('data-ybu-outlined', el.ref);
                        var rect = target.getBoundingClientRect();
                        var badgeDiv = document.createElement('div');
                        badgeDiv.setAttribute('data-ybu-badge', el.ref);
                        badgeDiv.style.cssText = 'position:fixed;left:' + rect.left + 'px;top:' + Math.max(0, rect.top - 14) + 'px;pointer-events:none;';
                        var badge = document.createElement('span');
                        badge.textContent = el.ref;
                        badge.style.cssText = 'background:#3b82f6;color:#fff;font-size:10px;font-family:Arial,sans-serif;padding:1px 4px;border-radius:2px;line-height:1.2;white-space:nowrap;';
                        badgeDiv.appendChild(badge);
                        container.appendChild(badgeDiv);
                        continue;
                    }
                } catch (e) {}
            }
            var div = document.createElement('div');
            div.setAttribute('data-ybu-highlight', el.ref);
            div.style.cssText = 'position:absolute;left:' + el.x + 'px;top:' + el.y + 'px;width:' + el.width + 'px;height:' + el.height + 'px;border:2px dashed #3b82f6;border-radius:2px;pointer-events:none;';
            var fb = document.createElement('span');
            fb.textContent = el.ref;
            fb.style.cssText = 'position:absolute;top:-12px;left:-2px;background:#3b82f6;color:#fff;font-size:10px;font-family:Arial,sans-serif;padding:1px 4px;border-radius:2px;line-height:1.2;white-space:nowrap;pointer-events:none;';
            div.appendChild(fb);
            container.appendChild(div);
        }

        function _ybu_updateBadges() {
            var o = document.querySelectorAll('[data-ybu-outlined]');
            for (var j = 0; j < o.length; j++) {
                var t = o[j];
                var ref = t.getAttribute('data-ybu-outlined');
                var bd = container.querySelector('[data-ybu-badge="' + ref.replace(/"/g, '\\"') + '"]');
                if (bd) {
                    var r = t.getBoundingClientRect();
                    bd.style.left = r.left + 'px';
                    bd.style.top = Math.max(0, r.top - 14) + 'px';
                }
            }
        }
        window.__ybu_run = _ybu_run;
        window.addEventListener('scroll', _ybu_updateBadges, {passive: true});
        window.addEventListener('resize', _ybu_updateBadges, {passive: true});
        container._ybu_scrollFn = _ybu_updateBadges;
        container._ybu_resizeFn = _ybu_updateBadges;
        var _ybu_moTimer = null;
        if (window.MutationObserver) {
            container._ybu_mo = new MutationObserver(function() {
                if (_ybu_moTimer) clearTimeout(_ybu_moTimer);
                _ybu_moTimer = setTimeout(_ybu_run, 300);
            });
            container._ybu_mo.observe(document.body, {childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'class', 'hidden', 'aria-hidden']});
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', _ybu_run);
    } else {
        _ybu_run();
    }
})();
"""

_SIMPLIFIED_SNAPSHOT_JS = """
(function() {
    var r = {title: document.title, h: [], l: [], lists: [], tables: []};
    var seen = {};
    document.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach(function(h) {
        var t = (h.textContent || '').trim();
        if (t) r.h.push({l: h.tagName.toLowerCase(), t: t});
    });
    document.querySelectorAll('a[href]').forEach(function(a) {
        var t = (a.textContent || '').trim();
        var hr = a.getAttribute('href');
        if (t && hr && !seen[hr + '|' + t]) {
            seen[hr + '|' + t] = 1;
            r.l.push({t: t, h: hr});
        }
    });
    document.querySelectorAll('ul,ol').forEach(function(lst) {
        var items = [];
        lst.querySelectorAll('li').forEach(function(li) {
            var t = (li.textContent || '').trim();
            if (t) items.push(t);
        });
        if (items.length) {
            var sel = '';
            if (lst.id) sel = '#' + lst.id;
            else {
                sel = lst.tagName.toLowerCase();
                var c = lst.className;
                if (c) sel += '.' + c.split(/\\s+/).filter(Boolean).join('.');
            }
            r.lists.push({
                selector: sel,
                tag: lst.tagName.toLowerCase(),
                item_count: items.length,
                sample_items: items.slice(0, 5)
            });
        }
    });
    document.querySelectorAll('table').forEach(function(tbl) {
        var rows = [], headers = [];
        tbl.querySelectorAll('tr').forEach(function(tr, i) {
            var cells = [];
            tr.querySelectorAll('th,td').forEach(function(c) {
                cells.push((c.textContent || '').trim());
            });
            if (cells.length) {
                if (i === 0) headers = cells.slice();
                rows.push(cells);
            }
        });
        if (rows.length) r.tables.push({
            row_count: rows.length,
            col_count: headers.length,
            headers: headers
        });
    });
    var body = document.body;
    r.text = body ? body.innerText.substring(0, 2000) : '';
    return JSON.stringify(r);
})()
"""


class PlaywrightBridge:
    """Unified browser driver via ``playwright.chromium.connect_over_cdp()``.

    All ops go through this class:
    - Interaction / navigation / tabs → Playwright Page API
    - Snapshot / highlight / eval → ``page.evaluate()`` / ``page.screenshot()``
    - Clipboard → ``page.evaluate()``
    """

    def __init__(self, cdp_url: str = "http://127.0.0.1:9222") -> None:
        self._cdp_url = cdp_url
        self._playwright: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._ref_map: dict[str, dict] = {}
        self._element_map: dict[str, Any] = {}
        self._last_highlight_elements: list[dict] = []
        self._highlight_guard_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @staticmethod
    def _schedule(coro):
        task = asyncio.ensure_future(coro)
        task.add_done_callback(lambda t: t.exception() and logger.debug("_schedule: background task failed", exc_info=t.exception()))
        return task

    async def start(self) -> None:
        """Connect to Chrome via CDP and grab the active page."""
        logger.info("PlaywrightBridge connecting to %s", self._cdp_url)
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.connect_over_cdp(self._cdp_url)
        self._context = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()

        pages = self._context.pages
        if pages:
            self._page = pages[0]
        else:
            self._page = await self._context.new_page()

        self._context.on("page", self._on_new_page)
        for p in self._context.pages:
            p.on("load", lambda pg=p: self._schedule(self._on_page_load(pg)))
            p.on("close", lambda pg=p: self._schedule(self._on_page_closed(pg)))
            p.on("framenavigated", lambda f, pg=p: self._schedule(self._on_frame_navigated(f, pg)))
        await self.ensure_highlights()
        # 给其他标签页也注入 bootstrap 框架（但不扫描，等切到时再扫）
        for p in self._context.pages:
            if p is not self._page:
                await self.ensure_highlights(p)
        # 自动扫描当前页面，让开局就有高亮（不依赖 chat tool call）
        try:
            await self.simplify_dom()
            logger.info("initial DOM scan complete: %d interactive elements", len(self._last_highlight_elements))
        except Exception:
            logger.warning("initial DOM scan failed, will retry via guard", exc_info=True)
        self._start_highlight_guard()
        logger.info("PlaywrightBridge connected (pages: %d)", len(self._context.pages))

    async def stop(self) -> None:
        """Release Playwright resources. Does NOT close Chrome."""
        logger.info("PlaywrightBridge stopping")
        if self._highlight_guard_task is not None:
            self._highlight_guard_task.cancel()
            self._highlight_guard_task = None
        try:
            if self._context:
                try:
                    self._context.remove_listener("page", self._on_new_page)
                except Exception:
                    pass
        except Exception:
            pass
        if self._playwright:
            await self._playwright.stop()
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    @property
    def page(self) -> Page | None:
        """The currently active Playwright Page."""
        return self._page

    # ------------------------------------------------------------------
    # New-page highlight auto-injection
    # ------------------------------------------------------------------

    async def _on_new_page(self, page: Page) -> None:
        """Auto-inject highlight JS and page ID when a new tab/page opens."""
        page.on("load", lambda pg=page: self._schedule(self._on_page_load(pg)))
        page.on("framenavigated", lambda f, pg=page: self._schedule(self._on_frame_navigated(f, pg)))
        page.on("close", lambda: self._schedule(self._on_page_closed(page)))
        try:
            page_id = str(uuid.uuid4())[:8]
            await page.evaluate(f"window.__ybu_page_id = '{page_id}';")
            await page.wait_for_load_state("domcontentloaded")
            if self._last_highlight_elements:
                elements_json = _json.dumps(self._last_highlight_elements)
                await page.evaluate(
                    f"window.__ybu_last_elements = {elements_json};"
                )
            await page.evaluate(_HIGHLIGHT_BOOTSTRAP)
        except Exception:
            logger.debug("_on_new_page highlight injection failed", exc_info=True)
        # 新标签页自动设为活动页并扫描（让用户点链接后马上看到高亮）
        self._page = page
        try:
            await self.simplify_dom()
        except Exception:
            logger.debug("_on_new_page: auto-scan failed", exc_info=True)

    async def _on_page_closed(self, page: Page) -> None:
        """当页面被关闭时自动切换到其他可用页面。"""
        if self._page is not page:
            return
        logger.info("current page closed, switching to another tab")
        if self._context and self._context.pages:
            self._page = self._context.pages[0]
            await self.ensure_highlights()
        else:
            self._page = None

    async def ensure_highlights(self, page: Page | None = None) -> None:
        """Inject highlight bootstrap and push element data into the page.

        For the active page (pg is self._page), pushes fresh element data and
        renders highlights.  For inactive pages, only ensures the bootstrap
        framework is present — never writes stale element data so highlights
        on other tabs stay clean.
        """
        pg = page or self._page
        if not pg:
            return
        try:
            is_active = pg is self._page
            if is_active:
                await pg.evaluate(
                    f"window.__ybu_last_elements = {_json.dumps(self._last_highlight_elements)};"
                )
            await pg.evaluate(_HIGHLIGHT_BOOTSTRAP)
            if is_active:
                await pg.evaluate("window.__ybu_run && window.__ybu_run();")
        except Exception:
            logger.warning("ensure_highlights failed for %s", pg.url[:60] if pg.url else "(no url)", exc_info=True)

    async def _on_page_load(self, page: Page) -> None:
        """Page load / reload 后自动重注高亮 + 扫描新元素。"""
        await self.ensure_highlights(page)
        # 页面的 load 事件说明内容变了，自动扫描刷新高亮
        if page is self._page:
            try:
                await self.simplify_dom()
            except Exception:
                logger.debug("_on_page_load: auto-scan failed", exc_info=True)

    async def _on_frame_navigated(self, frame, page: Page | None = None) -> None:
        """SPA pushState / replaceState — re-inject highlights + auto-scan."""
        pg = page or self._page
        if not pg or frame != pg.main_frame:
            return
        await self.ensure_highlights(pg)
        if pg is self._page:
            try:
                await self.simplify_dom()
            except Exception:
                logger.debug("_on_frame_navigated: auto-scan failed", exc_info=True)

    # ------------------------------------------------------------------
    # Highlight guard — periodic safety-net refresh (every 2 s)
    # ------------------------------------------------------------------

    def _start_highlight_guard(self) -> None:
        """Background task: periodically re-inject highlights every ~2 s.

        Replicates the safety-net refresh that used to live in
        ``routes._highlight_guard`` before the Playwright migration.
        Covers async DOM mutations, injected scripts that clear the
        overlay, and other events the event-driven path misses.
        """

        async def _guard() -> None:
            while self._page is not None:
                await asyncio.sleep(2.0)
                try:
                    # 如果当前页已被用户关闭，自动切到其他页
                    if self._context and self._page not in self._context.pages:
                        if self._context.pages:
                            self._page = self._context.pages[0]
                            await self.simplify_dom()
                        else:
                            self._page = None
                            return
                    await self.ensure_highlights()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass

        self._highlight_guard_task = asyncio.ensure_future(_guard())
        self._highlight_guard_task.add_done_callback(
            lambda t: logger.debug(
                "_highlight_guard: task ended (cancelled=%s)",
                t.cancelled(),
            )
        )

    # ------------------------------------------------------------------
    # Interaction ops
    # ------------------------------------------------------------------

    async def goto(self, url: str) -> dict:
        # SSRF guard: only allow http/https
        if not url.startswith(("http://", "https://")):
            return {"ok": False, "error": f"URL scheme not allowed: {url.split(':')[0]}:// (only http/https)"}
        await self._page.goto(url, wait_until="domcontentloaded")
        # 导航后扫描新页面，自动刷新高亮
        try:
            await self.simplify_dom()
        except Exception:
            logger.debug("goto: auto-scan failed", exc_info=True)
        return {"url": url}

    async def click(self, selector: str, click_count: int = 1) -> dict:
        locator = self._page.locator(selector)
        if click_count > 1:
            await locator.dblclick()
        else:
            await locator.click()
        return {"selector": selector}

    async def fill(self, selector: str, text: str) -> dict:
        await self._page.locator(selector).fill(text)
        return {"selector": selector}

    async def scroll(self, direction: str = "down", amount: int = 300) -> dict:
        if direction == "down":
            js = f"window.scrollBy(0, {amount});"
        elif direction == "up":
            js = f"window.scrollBy(0, -{amount});"
        elif direction == "left":
            js = f"window.scrollBy(-{amount}, 0);"
        elif direction == "right":
            js = f"window.scrollBy({amount}, 0);"
        else:
            js = f"window.scrollBy(0, {amount});"
        await self._page.evaluate(js)
        return {"direction": direction, "amount": amount}

    async def source(self) -> str:
        return await self._page.content()

    async def evaluate(self, js: str) -> Any:
        return await self._page.evaluate(js)

    # ------------------------------------------------------------------
    # New ops
    # ------------------------------------------------------------------

    async def hover(self, selector: str) -> dict:
        await self._page.locator(selector).hover()
        return {"selector": selector}

    async def unhover(self, selector: str) -> dict:
        """Move mouse to (0,0) to unhover. ``selector`` is informational only."""
        await self._page.mouse.move(0, 0)
        return {"selector": selector}

    async def focus(self, selector: str) -> dict:
        await self._page.locator(selector).focus()
        return {"selector": selector}

    async def select(self, selector: str, value: str, mode: str = "value") -> dict:
        locator = self._page.locator(selector)
        if mode == "label":
            await locator.select_option(label=value)
        elif mode == "index":
            await locator.select_option(index=int(value))
        else:
            await locator.select_option(value=value)
        return {"selector": selector}

    async def clear(self, selector: str, mode: str = "js") -> dict:
        if mode == "pw":
            await self._page.locator(selector).clear()
        else:
            await self._page.evaluate(
                f"(function() {{ var el = document.querySelector({_json.dumps(selector)}); if (el) el.value = ''; }})()"
            )
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
        try:
            await self.simplify_dom()
        except Exception:
            logger.debug("navigate: auto-scan failed", exc_info=True)
        return {"action": action}

    async def wait(self, mode: str = "time", **kwargs: Any) -> dict:
        if mode == "time":
            duration = kwargs.get("duration", 1000)
            await asyncio.sleep(duration / 1000.0)
        elif mode == "selector":
            selector = kwargs.get("selector", "")
            await self._page.wait_for_selector(selector)
        elif mode == "load":
            state = kwargs.get("state", "load")
            await self._page.wait_for_load_state(state)
        return {"mode": mode}

    # ------------------------------------------------------------------
    # Tab management
    # ------------------------------------------------------------------

    async def tab_new(self, url: str = "about:blank") -> dict:
        new_page = await self._context.new_page()
        page_id = str(uuid.uuid4())[:8]
        await new_page.evaluate(f"window.__ybu_page_id = '{page_id}';")
        if url and url != "about:blank":
            await new_page.goto(url, wait_until="domcontentloaded")
        self._page = new_page
        return {"targetId": page_id, "url": new_page.url}

    async def tab_switch(self, target_id: str) -> dict:
        for p in self._context.pages:
            pid = await p.evaluate("() => window.__ybu_page_id || ''")
            if pid == target_id:
                await p.bring_to_front()
                self._page = p
                await self.ensure_highlights()
                try:
                    await self.simplify_dom()
                except Exception:
                    logger.debug("tab_switch: auto-scan failed", exc_info=True)
                return {"targetId": target_id, "url": p.url}
        raise ValueError(f"Tab not found: {target_id}")

    async def tab_close(self, target_id: str) -> dict:
        for p in self._context.pages:
            pid = await p.evaluate("() => window.__ybu_page_id || ''")
            if pid == target_id:
                await p.close()
                if self._page == p:
                    remaining = self._context.pages
                    if remaining:
                        self._page = remaining[0]
                    else:
                        self._page = await self._context.new_page()
                return {"targetId": target_id, "closed": True}
        raise ValueError(f"Tab not found: {target_id}")

    async def tab_list(self) -> list[dict]:
        result = []
        for i, p in enumerate(self._context.pages):
            try:
                url = p.url
                title = await p.title()
                pid = await p.evaluate("() => window.__ybu_page_id || ''")
            except Exception:
                url = ""
                title = ""
                pid = ""
            result.append({
                "index": i,
                "targetId": pid or f"tab_{i}",
                "url": url,
                "title": title,
            })
        return result

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------

    async def copy_to_clipboard(self, selector: str) -> dict:
        text = await self._page.evaluate(
            f"(function() {{ var el = document.querySelector({_json.dumps(selector)}); return el ? (el.textContent || el.innerText || '') : ''; }})()"
        )
        return {"text": text, "selector": selector}

    async def paste_from_clipboard(self, selector: str, index: int = -1) -> dict:
        """Paste clipboard content into an input element.

        Note: navigator.clipboard.readText() requires a user gesture (click/keydown)
        or the "clipboard-read" permission. In headless/automated contexts this
        will often return an empty string.
        """
        text = await self._page.evaluate("() => navigator.clipboard?.readText() || ''")
        js = (
            f"(function() {{"
            f"var el = document.querySelector({_json.dumps(selector)});"
            f"if (!el) return;"
            f"var t = {_json.dumps(text)};"
            f"if ({index} < 0) {{ el.value = (el.value || '') + t; }}"
            f"else {{ var v = el.value || ''; el.value = v.slice(0, {index}) + t + v.slice({index}); }}"
            f"el.dispatchEvent(new Event('input', {{bubbles: true}}));"
            f"}})()"
        )
        await self._page.evaluate(js)
        return {"selector": selector, "text": text}

    # ------------------------------------------------------------------
    # Wait helpers
    # ------------------------------------------------------------------

    async def wait_for_network_idle(self) -> None:
        await self._page.wait_for_load_state("networkidle")

    async def wait_for_page_load(self) -> None:
        await self._page.wait_for_load_state("load")

    # ------------------------------------------------------------------
    # Page HTML (with optional cache)
    # ------------------------------------------------------------------

    async def get_page_html(self, cached: bool = False) -> str:
        if cached and "raw_html" in self._element_map:
            return self._element_map.get("raw_html", "")
        html = await self._page.content()
        self._element_map["raw_html"] = html
        return html

    # ------------------------------------------------------------------
    # Snapshot / Highlight
    # ------------------------------------------------------------------

    async def screenshot(self) -> str:
        data = await self._page.screenshot(type="png", full_page=False)
        return base64.b64encode(data).decode("utf-8")

    async def simplify_dom(self, query: str = "", in_viewport: bool = False) -> dict:
        cdp = await self._context.new_cdp_session(self._page)
        try:
            doc = await cdp.send("DOM.getDocument", {"depth": -1, "pierce": True})
        finally:
            await cdp.detach()
        elements: list[dict] = []

        def walk(node: dict) -> None:
            if node.get("nodeType") != 1:
                for child in node.get("children", []):
                    walk(child)
                return

            attrs_list = node.get("attributes", [])
            attrs: dict[str, str] = {}
            for i in range(0, len(attrs_list), 2):
                if i + 1 < len(attrs_list):
                    attrs[attrs_list[i]] = attrs_list[i + 1]

            tag = node["nodeName"].lower()
            bid = node["backendNodeId"]

            if not _is_interactive(tag, attrs):
                for child in node.get("children", []):
                    walk(child)
                return

            selector = _build_selector_from_node(tag, attrs)
            ref = f"@e_{bid}"

            elem_type = attrs.get("type", "text") if tag == "input" else ""
            elements.append({
                "ref": ref,
                "selector": selector,
                "tag": tag,
                "type": elem_type,
                "text": "",
                "value": attrs.get("value", ""),
                "role": attrs.get("role", ""),
                "tentative": _is_tentative(tag, attrs),
                "x": 0, "y": 0, "width": 0, "height": 0,
            })

            for child in node.get("children", []):
                walk(child)

        walk(doc.get("root", {}))
        logger.debug("simplify_dom: found %d interactive elements from DOM.getDocument", len(elements))

        if elements:
            sels = [e["selector"] for e in elements]
            js = (
                "(function(){"
                "var sels=" + _json.dumps(sels) + ";"
                "var selIdx={};"
                "var out=[];"
                "for(var i=0;i<sels.length;i++){"
                "var si=selIdx[sels[i]]||0;selIdx[sels[i]]=si+1;"
                "try{"
                "var all=document.querySelectorAll(sels[i]);"
                "if(all.length>si){"
                "var el=all[si];"
                "var r=el.getBoundingClientRect();"
                "var t=el.textContent||el.innerText||'';"
                "var cs=getComputedStyle(el);"
                "out.push({x:r.left,y:r.top,w:r.width,h:r.height,t:t.trim().substring(0,100),c:cs.cursor==='pointer'});"
                "}else{out.push({x:0,y:0,w:0,h:0,t:'',c:false});}"
                "}catch(e){out.push({x:0,y:0,w:0,h:0,t:'',c:false});}"
                "}"
                "return JSON.stringify(out);"
                "})()"
            )
            try:
                raw = await self._page.evaluate(js)
                if raw:
                    data = _json.loads(raw)
                    for el, d in zip(elements, data):
                        if isinstance(d, dict):
                            el["x"] = d.get("x", 0)
                            el["y"] = d.get("y", 0)
                            el["width"] = d.get("w", 0)
                            el["height"] = d.get("h", 0)
                            el["text"] = d.get("t", "")
                            el["clickable"] = d.get("c", False)
            except Exception:
                logger.debug("simplify_dom: position enrichment failed", exc_info=True)

        elements = [el for el in elements if not el.get("tentative") or el.get("clickable")]

        for el in elements:
            ref = el.get("ref", "")
            if ref:
                self._ref_map[ref] = {
                    "ref": ref,
                    "tag": el.get("tag", ""),
                    "type": el.get("type", ""),
                    "text": el.get("text", ""),
                    "selector": el.get("selector", ""),
                    "value": el.get("value", ""),
                    "role": el.get("role", ""),
                    "x": el.get("x", 0),
                    "y": el.get("y", 0),
                    "width": el.get("width", 0),
                    "height": el.get("height", 0),
                }

        if in_viewport:
            vp_w = await self._page.evaluate("window.innerWidth") or 1920
            vp_h = await self._page.evaluate("window.innerHeight") or 1080
            elements = [
                el for el in elements
                if el.get("y", 0) + el.get("height", 0) > 0
                and el.get("y", 0) < vp_h
                and el.get("x", 0) + el.get("width", 0) > 0
                and el.get("x", 0) < vp_w
            ]

        if query:
            q = query.lower()
            if q.startswith("#") or q.startswith("."):
                elements = [el for el in elements if q in el.get("selector", "").lower()]
            else:
                elements = [
                    el for el in elements
                    if q in el.get("text", "").lower()
                    or q in el.get("tag", "").lower()
                    or q in el.get("type", "").lower()
                    or q in el.get("role", "").lower()
                ]

        self._last_highlight_elements = list(elements)
        await self.ensure_highlights()

        result: dict = {"elements": elements, "mode": "interactive"}
        try:
            meta_raw = await self._page.evaluate(
                "JSON.stringify({url: window.location.href, title: document.title})"
            )
            meta = _json.loads(meta_raw)
            result["url"] = meta.get("url", "")
            result["title"] = meta.get("title", "")
        except Exception:
            pass
        return result

    async def simplified_snapshot(self) -> dict:
        raw = await self._page.evaluate(_SIMPLIFIED_SNAPSHOT_JS)
        data = _json.loads(raw) if isinstance(raw, str) else raw
        lines = []
        if data.get("title"):
            lines.append(f"Title: {data['title']}")
        for h in data.get("h", []):
            lines.append(f"{h['l'].upper()}: {h['t']}")
        links = data.get("l", [])
        if links:
            lines.append("")
            lines.append("Links:")
            for link in links[:20]:
                lines.append(f"  - {link['t']} ({link['h'][:60]})")
            if len(links) > 20:
                lines.append(f"  ... and {len(links) - 20} more")
        text = data.get("text", "")
        if text:
            lines.append("")
            lines.append(text[:1500])
        return {
            "summary": "\n".join(lines),
            "lists": data.get("lists", []),
            "tables": data.get("tables", []),
            "mode": "simplified",
        }

    async def capture_snapshot(self) -> dict:
        result: dict = {}
        try:
            result["screenshot_base64"] = await self.screenshot()
        except Exception:
            logger.debug("capture_snapshot: screenshot failed", exc_info=True)
        try:
            result["html"] = await self._page.evaluate("document.documentElement.outerHTML")
        except Exception:
            logger.debug("capture_snapshot: html extraction failed", exc_info=True)
        try:
            meta_raw = await self._page.evaluate(
                "JSON.stringify({url: window.location.href, title: document.title})"
            )
            meta = _json.loads(meta_raw)
            result["url"] = meta.get("url", "")
            result["title"] = meta.get("title", "")
        except Exception:
            logger.debug("capture_snapshot: meta extraction failed", exc_info=True)
        return result

    # ------------------------------------------------------------------
    # Element mapping
    # ------------------------------------------------------------------

    def reset_ref_map(self) -> None:
        self._ref_map = {}
        self._element_map = {}
        self._last_highlight_elements = []

    def get_element_by_index(self, ref: str) -> dict:
        if not self._ref_map:
            return {"ref": ref, "error": "no highlights injected"}

        raw = ref.strip()
        if raw.startswith("@"):
            if raw.startswith("@e") and not raw.startswith("@e_") and raw[2:].isdigit():
                normalized = "@e_" + raw[2:]
            else:
                normalized = raw
        elif raw.startswith("e_"):
            normalized = "@" + raw
        elif raw.startswith("e") and raw[1:].isdigit():
            normalized = "@e_" + raw[1:]
        else:
            normalized = "@e_" + raw

        el = self._ref_map.get(normalized)
        if el is None:
            return {"ref": normalized, "error": "not found"}

        return {
            "ref": el.get("ref", normalized),
            "tag": el.get("tag", ""),
            "type": el.get("type", ""),
            "text": el.get("text", ""),
            "selector": el.get("selector", ""),
            "bounds": {
                "x": el.get("x", 0),
                "y": el.get("y", 0),
                "w": el.get("width", 0),
                "h": el.get("height", 0),
            },
        }
