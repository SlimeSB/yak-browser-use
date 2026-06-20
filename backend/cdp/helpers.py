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

    async def capture_snapshot_interactive(self, query: str = "", in_viewport: bool = False) -> dict:
        try:
            result = await self._bridge.simplify_dom(query=query, in_viewport=in_viewport)
            elements = result.get("elements", [])

            for el in elements:
                ref = el.get("ref", "")
                if ref:
                    if ref in self._ref_map:
                        self._ref_map[ref].update({
                            "x": el.get("x", 0), "y": el.get("y", 0),
                            "width": el.get("width", 0), "height": el.get("height", 0),
                        })
                    else:
                        self._ref_map[ref] = _build_element_info(el)

            try:
                await self.add_dom_highlights(elements)
            except Exception:
                logger.warning("auto-highlight after interactive snapshot failed", exc_info=True)

            return result
        except Exception:
            logger.info("interactive snapshot degraded to full")
            full = await self.capture_snapshot()
            return {"elements": [], "mode": "interactive", "degraded": True, **full}

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
            return {"summary": "", "lists": [], "tables": [], "mode": "simplified", "degraded": True, **full}

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
            "(function(){"
            "function _ybu_run(){"
            "if(!document.body)return;"
            "var oldC=document.getElementById('ybu-highlights');"
            "if(oldC){"
            "if(oldC._ybu_scrollFn)window.removeEventListener('scroll',oldC._ybu_scrollFn);"
            "if(oldC._ybu_resizeFn)window.removeEventListener('resize',oldC._ybu_resizeFn);"
            "if(oldC._ybu_mo)oldC._ybu_mo.disconnect();"
            "oldC.remove();"
            "}"
            "var outlined=document.querySelectorAll('[data-ybu-outlined]');"
            "for(var i=0;i<outlined.length;i++){outlined[i].style.outline='';outlined[i].removeAttribute('data-ybu-outlined');}"
            "var container=document.createElement('div');"
            "container.id='ybu-highlights';"
            "container.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:2147483646;';"
            "document.body.appendChild(container);"
            "var elements=" + elements_json + ";"
            "var selIdx={};"
            "for(var i=0;i<elements.length;i++){"
            "var el=elements[i];"
            "if(el.selector){"
            "try{"
            "var si=selIdx[el.selector]||0;selIdx[el.selector]=si+1;"
            "var all=document.querySelectorAll(el.selector);"
            "if(all.length>si){"
            "var target=all[si];"
            "target.style.outline='2px dashed #3b82f6';target.style.outlineOffset='0px';"
            "target.setAttribute('data-ybu-outlined',el.ref);"
            "var rect=target.getBoundingClientRect();"
            "var badgeDiv=document.createElement('div');"
            "badgeDiv.setAttribute('data-ybu-badge',el.ref);"
            "badgeDiv.style.cssText='position:fixed;left:'+rect.left+'px;top:'+Math.max(0,rect.top-14)+'px;pointer-events:none;';"
            "var badge=document.createElement('span');"
            "badge.textContent=el.ref;"
            "badge.style.cssText='background:#3b82f6;color:#fff;font-size:10px;font-family:Arial,sans-serif;padding:1px 4px;border-radius:2px;line-height:1.2;white-space:nowrap;';"
            "badgeDiv.appendChild(badge);"
            "container.appendChild(badgeDiv);"
            "continue;"
            "}"
            "}catch(e){}"
            "}"
            "var div=document.createElement('div');"
            "div.setAttribute('data-ybu-highlight',el.ref);"
            "div.style.cssText='position:absolute;left:'+el.x+'px;top:'+el.y+'px;width:'+el.width+'px;height:'+el.height+'px;border:2px dashed #3b82f6;border-radius:2px;pointer-events:none;';"
            "var fb=document.createElement('span');"
            "fb.textContent=el.ref;"
            "fb.style.cssText='position:absolute;top:-12px;left:-2px;background:#3b82f6;color:#fff;font-size:10px;font-family:Arial,sans-serif;padding:1px 4px;border-radius:2px;line-height:1.2;white-space:nowrap;pointer-events:none;';"
            "div.appendChild(fb);"
            "container.appendChild(div);"
            "}"
            "function _ybu_updateBadges(){"
            "var o=document.querySelectorAll('[data-ybu-outlined]');"
            "for(var j=0;j<o.length;j++){"
            "var t=o[j];"
            "var ref=t.getAttribute('data-ybu-outlined');"
            "var bd=container.querySelector('[data-ybu-badge=\"'+ref.replace(/\"/g,'\\\\\"')+'\"]');"
            "if(bd){"
            "var r=t.getBoundingClientRect();"
            "bd.style.left=r.left+'px';"
            "bd.style.top=Math.max(0,r.top-14)+'px';"
            "}"
            "}"
            "}"
            "window.addEventListener('scroll',_ybu_updateBadges,{passive:true});"
            "window.addEventListener('resize',_ybu_updateBadges,{passive:true});"
            "container._ybu_scrollFn=_ybu_updateBadges;"
            "container._ybu_resizeFn=_ybu_updateBadges;"
            "var _ybu_moTimer=null;"
            "if(window.MutationObserver){"
            "container._ybu_mo=new MutationObserver(function(){"
            "if(_ybu_moTimer)clearTimeout(_ybu_moTimer);"
            "_ybu_moTimer=setTimeout(_ybu_run,300);"
            "});"
            "container._ybu_mo.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['style','class','hidden','aria-hidden']});"
            "}"
            "}"
            "if(document.readyState==='loading'){"
            "document.addEventListener('DOMContentLoaded',_ybu_run);"
            "}else{"
            "_ybu_run();"
            "}"
            "})()"
        )
        try:
            await self.js(js_code)
        except Exception as e:
            logger.error("add_dom_highlights: js injection failed: %s", e)
        return {"ok": True, "count": len(highlight_elements), "element_map": dict(self._ref_map)}

    async def remove_dom_highlights(self) -> None:
        js = (
            "(function(){"
            "var o=document.querySelectorAll('[data-ybu-outlined]');"
            "for(var i=0;i<o.length;i++){o[i].style.outline='';o[i].removeAttribute('data-ybu-outlined');}"
            "var c=document.getElementById('ybu-highlights');"
            "if(c){"
            "if(c._ybu_scrollFn)window.removeEventListener('scroll',c._ybu_scrollFn);"
            "if(c._ybu_resizeFn)window.removeEventListener('resize',c._ybu_resizeFn);"
            "if(c._ybu_mo)c._ybu_mo.disconnect();"
            "c.remove();"
            "}"
            "})()"
        )
        await self.js(js)

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
