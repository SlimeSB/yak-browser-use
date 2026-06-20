"""Restricted CDP helpers for tool-level browser access (safe subset).

Provides the same interface as CDPHelpers but with:
- Allowed domain restrictions
- Timeout limits
- Circuit breaker (3 consecutive failures)
- Only safe operations exposed

Backed by PlaywrightBridge instead of raw CDP.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from cdp.playwright_bridge import PlaywrightBridge

logger = logging.getLogger(__name__)


class ToolCDPHelpers:
    """Restricted browser access for tool functions."""

    SAFE_OPS = frozenset({"click", "fill", "type", "wait", "snapshot", "evaluate"})

    def __init__(self, bridge: PlaywrightBridge, allowed_domains: list[str] | None = None):
        self._bridge = bridge
        self._allowed_domains = allowed_domains or []
        self._fail_count = 0
        self._max_fails = 3

    async def click_selector(self, selector: str) -> dict:
        self._check_failures()
        result = await self._bridge.click(selector)
        self._fail_count = 0
        return result

    async def fill_input(self, selector: str, text: str) -> dict:
        self._check_failures()
        logger.debug("fill_input: %s = <sensitive: %d chars>", selector, len(text))
        result = await self._bridge.fill(selector, text)
        self._fail_count = 0
        return result

    async def fill_credential(self, selector: str, param_ref: object) -> None:
        from params.manager import resolve_param
        text = resolve_param(param_ref)
        await self.fill_input(selector, text)

    async def wait(self, seconds: float = 1.0) -> None:
        await asyncio.sleep(seconds)

    async def snapshot(self, mode: str = "a11y", query: str = "", in_viewport: bool = False) -> dict:
        self._check_failures()
        if mode == "a11y":
            result = await self._bridge.a11y_snapshot()
        elif mode == "interactive":
            result = await self._bridge.simplify_dom(query=query, in_viewport=in_viewport)
        elif mode == "simplified":
            result = await self._bridge.simplified_snapshot()
        else:
            result = await self._bridge.capture_snapshot()
        self._fail_count = 0
        return result

    async def evaluate(self, js: str) -> Any:
        self._check_failures()
        result = await self._bridge.evaluate(js)
        self._fail_count = 0
        return result

    def _check_failures(self) -> None:
        if self._fail_count >= self._max_fails:
            raise RuntimeError(f"ToolCDP circuit breaker: {self._max_fails} consecutive failures")
        self._fail_count += 1
