"""CDPHelpers — high-level browser operation wrappers.

All browser operations go through this class (or its restricted ToolCDPHelpers variant).
Backed by PlaywrightBridge instead of raw CDP WebSocket.
"""

from __future__ import annotations

import json as _json
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from cdp.playwright_bridge import PlaywrightBridge

logger = logging.getLogger(__name__)


def _build_element_info(el: dict) -> dict:
    return {
        "ref": el.get("ref", ""),
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


class CDPHelpers:
    """Wraps a PlaywrightBridge for common browser operations."""

    def __init__(self, bridge: PlaywrightBridge):
        self._bridge = bridge
        self._ref_map: dict[str, dict] = {}

    @property
    def bridge(self):
        """Public accessor for the underlying PlaywrightBridge."""
        return self._bridge

    # ------------------------------------------------------------------
    # Existing methods — rewritten to call PlaywrightBridge
    # ------------------------------------------------------------------

    async def goto_url(self, url: str) -> dict:
        return await self._bridge.goto(url)

    def reset_ref_map(self) -> None:
        self._bridge.reset_ref_map()
        self._ref_map = {}

    async def click_selector(self, selector: str, click_count: int = 1) -> dict:
        return await self._bridge.click(selector, click_count)

    async def fill_input(self, selector: str, text: str, _sensitive: bool = False) -> dict:
        logger.debug("fill_input: %s = <text: %d chars>", selector, len(text))
        return await self._bridge.fill(selector, text)

    async def capture_snapshot(self) -> dict:
        return await self._bridge.capture_snapshot()

    async def get_page_html(self) -> str:
        return await self._bridge.source()

    async def wait_for_network_idle(self) -> None:
        await self._bridge.wait_for_network_idle()

    async def wait_for_page_load(self) -> None:
        await self._bridge.wait_for_page_load()

    async def js(self, code: str) -> Any:
        return await self._bridge.evaluate(code)

    async def capture_snapshot_simplified(self) -> dict:
        try:
            raw = await self.js((
                "(function(){"
                "var r={title:document.title,h:[],l:[],lists:[],tables:[]};"
                "document.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach(function(h){"
                "var t=(h.textContent||'').trim();if(t)r.h.push({l:h.tagName.toLowerCase(),t:t});"
                "});"
                "var seen={};"
                "document.querySelectorAll('a[href]').forEach(function(a){"
                "var t=(a.textContent||'').trim();var hr=a.getAttribute('href');"
                "if(t&&hr&&!seen[hr+'|'+t]){seen[hr+'|'+t]=1;r.l.push({t:t,h:hr});}"
                "});"
                "document.querySelectorAll('ul,ol').forEach(function(lst){"
                "var items=[];"
                "lst.querySelectorAll('li').forEach(function(li){var t=(li.textContent||'').trim();if(t)items.push(t);});"
                "if(items.length){"
                "var sel='';"
                "if(lst.id)sel='#'+lst.id;"
                "else{sel=lst.tagName.toLowerCase();var c=lst.className;if(c)sel+='.'+c.split(/\\s+/).filter(Boolean).join('.');}"
                "r.lists.push({selector:sel,tag:lst.tagName.toLowerCase(),item_count:items.length,sample_items:items.slice(0,5)});"
                "}"
                "});"
                "document.querySelectorAll('table').forEach(function(tbl){"
                "var rows=[];var headers=[];"
                "tbl.querySelectorAll('tr').forEach(function(tr,i){"
                "var cells=[];"
                "tr.querySelectorAll('th,td').forEach(function(c){cells.push((c.textContent||'').trim());});"
                "if(cells.length){"
                "if(i===0)headers=cells.slice();"
                "rows.push(cells);"
                "}"
                "});"
                "if(rows.length)r.tables.push({row_count:rows.length,col_count:headers.length,headers:headers});"
                "});"
                "var body=document.body;"
                "r.text=body?body.innerText.substring(0,2000):'';"
                "return JSON.stringify(r);"
                "})()"
            ))
            if not raw:
                raise ValueError("empty JS result")
            data = _json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            logger.info("simplified snapshot degraded to full")
            full = await self.capture_snapshot()
            return {"summary": "", "lists": [], "tables": [], "mode": "simplified", **full}

        lines = []
        if data.get("title"):
            lines.append(f"Title: {data['title']}")
        headings = data.get("h", [])
        for h in headings:
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

        try:
            await self.add_dom_highlights()
        except Exception:
            logger.warning("auto-highlight after simplified snapshot failed", exc_info=True)

        return {
            "summary": "\n".join(lines),
            "lists": data.get("lists", []),
            "tables": data.get("tables", []),
            "mode": "simplified",
        }

    async def add_dom_highlights(self, elements: list[dict] | None = None) -> dict:
        """Push element data to the browser's bootstrap highlight renderer.

        ⚠️🚫 不要在下面注 JS。再注死妈。
        再写一套内联 JS 就会跟 playwright_bridge.py 的 _HIGHLIGHT_BOOTSTRAP
        抢容器、抢事件、抢 MutationObserver——两个系统互拆互建，滚动卡死。
        之前的 83 行内联 JS 就是这么死的。删了就好了。

        正确做法：设 window.__ybu_last_elements + 调 _ybu_render()。
        滚动有 RAF 节流 + transform 合成层定位，MO 只轻量重绘不拆容器。
        所有高亮逻辑只在这一条路径里。
        """
        highlight_elements = elements or []

        if elements:
            for el in elements:
                ref = el.get("ref", "")
                if ref:
                    if ref in self._ref_map:
                        self._ref_map[ref].update({
                            "x": el.get("x", 0),
                            "y": el.get("y", 0),
                            "width": el.get("width", 0),
                            "height": el.get("height", 0),
                        })
                    else:
                        self._ref_map[ref] = _build_element_info(el)

        if not highlight_elements:
            return {"ok": True, "count": 0, "element_map": dict(self._ref_map)}

        elements_json = _json.dumps(highlight_elements)
        js_code = (
            f"window.__ybu_last_elements = {elements_json};"
            "window.__ybu_render && window.__ybu_render();"
        )
        try:
            await self.js(js_code)
        except Exception as e:
            logger.error("add_dom_highlights: js injection failed: %s", e)
        return {"ok": True, "count": len(highlight_elements), "element_map": dict(self._ref_map)}

    async def remove_dom_highlights(self) -> None:
        await self.js("window.__ybu_last_elements = []; window.__ybu_render && window.__ybu_render();")

    def get_element_by_index(self, ref: str) -> dict:
        return self._bridge.get_element_by_index(ref)

    # ------------------------------------------------------------------
    # New methods — transparent proxy to PlaywrightBridge
    # ------------------------------------------------------------------

    async def hover(self, selector: str) -> dict:
        return await self._bridge.hover(selector)

    async def unhover(self, selector: str) -> dict:
        return await self._bridge.unhover(selector)

    async def focus_selector(self, selector: str) -> dict:
        return await self._bridge.focus(selector)

    async def select_option(self, selector: str, value: str, mode: str = "value") -> dict:
        return await self._bridge.select(selector, value, mode)

    async def clear_input(self, selector: str, mode: str = "js") -> dict:
        return await self._bridge.clear(selector, mode)

    async def keyboard_key(self, key: str) -> dict:
        return await self._bridge.keyboard_press(key)

    async def keyboard_text(self, text: str) -> dict:
        return await self._bridge.keyboard_type(text)

    async def navigate(self, action: str, hard: bool = False) -> dict:
        return await self._bridge.navigate(action, hard)

    async def wait(self, mode: str = "time", **kwargs: Any) -> dict:
        return await self._bridge.wait(mode, **kwargs)

    async def tab_new(self, url: str = "about:blank") -> dict:
        return await self._bridge.tab_new(url)

    async def tab_switch(self, target_id: str) -> dict:
        return await self._bridge.tab_switch(target_id)

    async def tab_close(self, target_id: str) -> dict:
        return await self._bridge.tab_close(target_id)

    async def tab_list(self) -> list[dict]:
        return await self._bridge.tab_list()

    async def copy_to_clipboard(self, selector: str) -> dict:
        return await self._bridge.copy_to_clipboard(selector)

    async def paste_from_clipboard(self, selector: str, index: int = -1) -> dict:
        return await self._bridge.paste_from_clipboard(selector, index)
