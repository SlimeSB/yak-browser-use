"""CDPHelpers — high-level browser operation wrappers.

All CDP operations go through this class (or its restricted ToolCDPHelpers variant).
"""
from __future__ import annotations

import json as _json
import logging
from typing import Any

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
    """True if the element is only interactive due to heuristics (not tag/role/onclick)."""
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


class CDPHelpers:
    """Wraps a CDPDaemon for common browser operations."""

    def __init__(self, daemon: object, *, session_id: str | None = None):
        self._daemon = daemon
        self._session_id = session_id
        self._ref_map: dict[str, dict] = {}

    def target_session(self, sid: str | None) -> None:
        """Set the CDP session for subsequent calls (multi-tab targeting)."""
        self._session_id = sid

    async def _cdp(self, method: str, params: dict | None = None, _sensitive: bool = False) -> Any:
        if _sensitive and params:
            masked = {k: f"<sensitive: {len(v)} chars>" if isinstance(v, str) and v else v
                      for k, v in params.items()}
            logger.debug("browser_op: %s %s", method, masked)
        else:
            logger.debug("browser_op: %s %s", method, params)
        return await self._daemon._send(method, params, session_id=self._session_id)

    async def goto_url(self, url: str) -> dict:
        return await self._cdp("Page.navigate", {"url": url})

    def reset_ref_map(self) -> None:
        self._ref_map = {}

    async def click_at_xy(self, x: float, y: float) -> dict:
        await self._cdp("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1,
        })
        return await self._cdp("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1,
        })

    async def click_selector(self, selector: str) -> dict:
        node_result = await self._cdp("DOM.getDocument")
        root = node_result.get("root", {})
        query_result = await self._cdp("DOM.querySelector", {
            "nodeId": root.get("nodeId"), "selector": selector,
        })
        node_id = query_result.get("nodeId")
        if not node_id or node_id == 0:
            raise ValueError(f"Element not found: {selector}")
        box = await self._cdp("DOM.getBoxModel", {"nodeId": node_id})
        model = box.get("model", {})
        content = model.get("content", [])
        if len(content) >= 4:
            x = (content[0] + content[2]) / 2
            y = (content[1] + content[3]) / 2
            return await self.click_at_xy(x, y)
        raise ValueError(f"Cannot get box model for element: {selector}")

    async def fill_input(self, selector: str, text: str, _sensitive: bool = False) -> dict:
        if _sensitive:
            logger.debug("fill_input: %s = <sensitive: %d chars>", selector, len(text))
        else:
            logger.debug("fill_input: %s = %s", selector, text[:30])
        node_result = await self._cdp("DOM.getDocument")
        root = node_result.get("root", {})
        query_result = await self._cdp("DOM.querySelector", {
            "nodeId": root.get("nodeId"), "selector": selector,
        })
        node_id = query_result.get("nodeId")
        if not node_id or node_id == 0:
            raise ValueError(f"Input element not found: {selector}")
        await self._cdp("DOM.focus", {"nodeId": node_id})
        await self._cdp("Input.insertText", {"text": text})
        return {"nodeId": node_id}

    async def capture_snapshot(self) -> dict:
        """Capture screenshot + page HTML + url + title."""
        result = {}
        try:
            screenshot = await self._cdp("Page.captureScreenshot", {"format": "png", "fromSurface": True})
            result["screenshot_base64"] = screenshot.get("data", "")
        except Exception:
            pass
        try:
            html = await self._cdp("Runtime.evaluate", {
                "expression": "document.documentElement.outerHTML",
            })
            result["html"] = html.get("result", {}).get("value", "")
        except Exception:
            pass
        try:
            meta = await self._cdp("Runtime.evaluate", {
                "expression": "JSON.stringify({url: window.location.href, title: document.title})",
            })
            meta_val = (meta.get("result", {}).get("value") or "{}")
            meta_dict = _json.loads(meta_val)
            result["url"] = meta_dict.get("url", "")
            result["title"] = meta_dict.get("title", "")
        except Exception:
            pass
        return result

    async def get_page_html(self) -> str:
        result = await self._cdp("Runtime.evaluate", {
            "expression": "document.documentElement.outerHTML",
        })
        return result.get("result", {}).get("value", "")

    async def wait_for_network_idle(self) -> None:
        import asyncio
        await asyncio.sleep(0.5)

    async def js(self, code: str) -> Any:
        result = await self._cdp("Runtime.evaluate", {"expression": code, "returnByValue": True})
        return result.get("result", {}).get("value")

    async def _discover_all_interactive(self) -> list[dict]:
        """Discover ALL interactive elements from the full DOM tree.

        Uses a single ``DOM.getDocument(depth=-1)`` call, then filters
        element nodes by tag/role/attributes.  Returns a list of
        ``{ref, selector, tag, type}`` — no position data (positions are
        retrieved JS-side via ``getBoundingClientRect()`` in the highlight
        injection).
        """
        doc = await self._cdp("DOM.getDocument", {"depth": -1, "pierce": True})
        results: list[dict] = []

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
            results.append({
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
        logger.debug("_discover_all_interactive: found %d interactive elements from full tree",
                     len(results))
        return results

    async def _get_element_positions(self, elements: list[dict]) -> list[dict]:
        """Enrich elements with bounding rects, text, and clickable flag via a single JS call."""
        if not elements:
            return elements
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
            raw = await self.js(js)
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
            logger.debug("_get_element_positions failed", exc_info=True)
        return elements

    async def capture_snapshot_interactive(self, query: str = "", in_viewport: bool = False) -> dict:
        try:
            elements = await self._discover_all_interactive()
            enriched = await self._get_element_positions(elements)

            enriched = [el for el in enriched if not el.get("tentative") or el.get("clickable")]

            if in_viewport:
                vp_w = await self.js("window.innerWidth") or 1920
                vp_h = await self.js("window.innerHeight") or 1080
                enriched = [
                    el for el in enriched
                    if el["y"] + el["height"] > 0 and el["y"] < vp_h
                    and el["x"] + el["width"] > 0 and el["x"] < vp_w
                ]

            if query:
                q = query.lower()
                if q.startswith("#") or q.startswith("."):
                    enriched = [el for el in enriched if q in el.get("selector", "").lower()]
                else:
                    enriched = [
                        el for el in enriched
                        if q in el.get("text", "").lower()
                        or q in el.get("tag", "").lower()
                        or q in el.get("type", "").lower()
                        or q in el.get("role", "").lower()
                    ]

            for el in enriched:
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
                await self.add_dom_highlights(enriched)
            except Exception:
                logger.warning("auto-highlight after interactive snapshot failed", exc_info=True)
            result = {"elements": enriched, "mode": "interactive"}
            try:
                meta = await self._cdp("Runtime.evaluate", {
                    "expression": "JSON.stringify({url: window.location.href, title: document.title})",
                })
                meta_val = (meta.get("result", {}).get("value") or "{}")
                meta_dict = _json.loads(meta_val)
                result["url"] = meta_dict.get("url", "")
                result["title"] = meta_dict.get("title", "")
            except Exception:
                pass
            return result
        except Exception:
            logger.info("interactive snapshot degraded to full")
            full = await self.capture_snapshot()
            return {"elements": [], "mode": "interactive", "degraded": True, **full}

    async def capture_snapshot_simplified(self) -> dict:
        """Simplified page summary (headings, links, lists, tables) for LLM consumption."""
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

        # Build summary text
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
        """Inject interactive element highlight badges into the page.

        Scans the full DOM tree via ``DOM.getDocument``, then injects
        outlines + scroll-aware badge overlays.

        Args:
            elements: Optional pre-scanned element list. If None (typical),
                      scans via ``_discover_all_interactive()``.

        Returns:
            ``{ok, count, element_map}``.
        """
        highlight_elements: list[dict] | None = None
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

        try:
            highlight_elements = await self._discover_all_interactive()
        except Exception:
            logger.warning("_discover_all_interactive failed, using snapshot elements", exc_info=True)
            highlight_elements = elements

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
        """Remove all highlight overlays and element outlines from the page."""
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
        """Look up an element by its @e_XXXXX reference.

        Args:
            ref: Reference string like ``"@e_12345"``, ``"e_12345"``,
                 ``"12345"``, or the old-style ``"@e3"`` / ``"e3"``.

        Returns:
            Dict with element info or ``{ref, error}`` on failure.
        """
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
