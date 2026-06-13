"""CDPHelpers — high-level browser operation wrappers.

All CDP operations go through this class (or its restricted ToolCDPHelpers variant).
"""
from __future__ import annotations

import base64
import json as _json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SIMPLIFY_DOM_JS: str | None = None


def _load_simplify_dom_js() -> str | None:
    global _SIMPLIFY_DOM_JS
    if _SIMPLIFY_DOM_JS is not None:
        return _SIMPLIFY_DOM_JS
    script_path = Path(__file__).resolve().parent.parent / "assets" / "simplify-dom.js"
    try:
        _SIMPLIFY_DOM_JS = script_path.read_text(encoding="utf-8")
        return _SIMPLIFY_DOM_JS
    except Exception:
        logger.warning("simplify-dom.js not found at %s", script_path)
        return None


class CDPHelpers:
    """Wraps a CDPDaemon for common browser operations."""

    def __init__(self, daemon: object):
        self._daemon = daemon
        self._element_map: dict[str, dict] = {}

    async def _cdp(self, method: str, params: dict | None = None, _sensitive: bool = False) -> Any:
        if _sensitive and params:
            masked = {k: f"<sensitive: {len(v)} chars>" if isinstance(v, str) and v else v
                      for k, v in params.items()}
            logger.debug("browser_op: %s %s", method, masked)
        else:
            logger.debug("browser_op: %s %s", method, params)
        return await self._daemon._send(method, params)

    async def goto_url(self, url: str) -> dict:
        return await self._cdp("Page.navigate", {"url": url})

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
        """Capture screenshot + page HTML."""
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
        return result

    async def get_page_html(self) -> str:
        result = await self._cdp("Runtime.evaluate", {
            "expression": "document.documentElement.outerHTML",
        })
        return result.get("result", {}).get("value", "")

    async def wait_for_network_idle(self, timeout: int = 5000) -> None:
        import asyncio
        await asyncio.sleep(0.5)  # Simple approach; CDP Network.enable tracking would be more precise

    async def js(self, code: str) -> Any:
        result = await self._cdp("Runtime.evaluate", {"expression": code})
        return result.get("result", {}).get("value")

    async def _inject_simplify_js(self, mode: str) -> Any:
        script = _load_simplify_dom_js()
        if script is None:
            return None
        safe_mode = _json.dumps(mode)
        expression = f"{script}\nsimplifyDom({{mode: {safe_mode}}})"
        try:
            result = await self.js(expression)
            return result
        except Exception:
            logger.warning("simplify-dom.js execution failed for mode=%s", mode)
            return None

    async def capture_snapshot_interactive(self) -> dict:
        js_result = await self._inject_simplify_js("interactive")
        if js_result and isinstance(js_result, dict) and js_result.get("elements") is not None:
            result = {"elements": js_result.get("elements", []), "mode": "interactive"}
            if js_result.get("truncated"):
                result["truncated"] = True
                result["total_found"] = js_result.get("total_found", 0)
            return result
        logger.info("interactive snapshot degraded to full")
        full = await self.capture_snapshot()
        return {"elements": [], "mode": "interactive", "degraded": True, **full}

    async def capture_snapshot_simplified(self) -> dict:
        js_result = await self._inject_simplify_js("simplified")
        if js_result and isinstance(js_result, dict) and js_result.get("summary") is not None:
            return {
                "summary": js_result.get("summary", ""),
                "lists": js_result.get("lists", []),
                "tables": js_result.get("tables", []),
                "mode": "simplified",
            }
        logger.info("simplified snapshot degraded to full")
        full = await self.capture_snapshot()
        return {"summary": "", "lists": [], "tables": [], "mode": "simplified", "degraded": True, **full}

    async def add_dom_highlights(self, elements: list[dict] | None = None) -> dict:
        """Inject interactive element highlight badges into the page.

        Args:
            elements: Optional pre-scanned element list. If None, scans via
                      ``_inject_simplify_js("interactive")``.

        Returns:
            ``{ok, count, element_map}``.
        """
        if elements is None:
            js_result = await self._inject_simplify_js("interactive")
            if not js_result or not isinstance(js_result, dict):
                return {"ok": True, "count": 0, "element_map": {}}
            elements = js_result.get("elements", [])

        if not elements:
            self._element_map = {}
            return {"ok": True, "count": 0, "element_map": {}}

        self._element_map = {}
        for el in elements:
            ref = el.get("ref", "")
            if ref:
                self._element_map[ref] = {
                    "ref": ref,
                    "tag": el.get("tag", ""),
                    "type": el.get("type", ""),
                    "text": el.get("text", ""),
                    "selector": el.get("selector", ""),
                    "value": el.get("value", ""),
                    "x": el.get("x", 0),
                    "y": el.get("y", 0),
                    "width": el.get("width", 0),
                    "height": el.get("height", 0),
                }

        elements_json = _json.dumps(elements)
        js_code = (
            "(function(){"
            "var old=document.getElementById('ybu-highlights');"
            "if(old)old.remove();"
            "var container=document.createElement('div');"
            "container.id='ybu-highlights';"
            "container.style.cssText='position:absolute;top:0;left:0;width:100%;pointer-events:none;z-index:2147483646;';"
            "document.body.appendChild(container);"
            "var elements=" + elements_json + ";"
            "var sx=window.scrollX||window.pageXOffset||0;"
            "var sy=window.scrollY||window.pageYOffset||0;"
            "for(var i=0;i<elements.length;i++){"
            "var el=elements[i];"
            "var div=document.createElement('div');"
            "div.setAttribute('data-ybu-highlight',el.ref);"
            "div.style.cssText='position:absolute;"
            "left:'+(el.x+sx)+'px;top:'+(el.y+sy)+'px;"
            "width:'+el.width+'px;height:'+el.height+'px;"
            "border:2px dashed #3b82f6;border-radius:2px;pointer-events:none;';"
            "var badge=document.createElement('span');"
            "badge.textContent=el.ref;"
            "badge.style.cssText='position:absolute;top:-12px;left:-2px;"
            "background:#3b82f6;color:#fff;font-size:10px;font-family:Arial,sans-serif;"
            "padding:1px 4px;border-radius:2px;line-height:1.2;white-space:nowrap;pointer-events:none;';"
            "div.appendChild(badge);"
            "container.appendChild(div);"
            "}"
            "})()"
        )
        await self.js(js_code)
        return {"ok": True, "count": len(elements), "element_map": dict(self._element_map)}

    async def remove_dom_highlights(self) -> None:
        """Remove all highlight overlays from the page and clear the element map."""
        await self.js("var el=document.getElementById('ybu-highlights');if(el)el.remove();")
        self._element_map = {}

    def get_element_by_index(self, ref: str) -> dict:
        """Look up an element by its @eN reference.

        Args:
            ref: Reference string like ``"@e3"``, ``"e3"``, or ``"3"``.

        Returns:
            Dict with element info or ``{ref, error}`` on failure.
        """
        if not self._element_map:
            return {"ref": ref, "error": "no highlights injected"}

        normalized = ref.strip()
        if not normalized.startswith("@"):
            normalized = "@e" + normalized if not normalized.startswith("e") else "@" + normalized

        el = self._element_map.get(normalized)
        if el is None:
            return {"ref": normalized, "error": "not found"}

        return {
            "ref": el["ref"],
            "tag": el["tag"],
            "type": el.get("type", ""),
            "text": el["text"],
            "selector": el["selector"],
            "bounds": {"x": el["x"], "y": el["y"], "w": el["width"], "h": el["height"]},
        }
