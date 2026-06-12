"""CDPHelpers — high-level browser operation wrappers.

All CDP operations go through this class (or its restricted ToolCDPHelpers variant).
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CDPHelpers:
    """Wraps a CDPDaemon for common browser operations."""

    def __init__(self, daemon: object):
        self._daemon = daemon

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
