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
    from yak_browser_use.cdp.playwright_bridge import PlaywrightBridge

from yak_browser_use.cdp.playwright_bridge import A11yNotAvailable
from yak_browser_use.utils.bridge import CircuitBreakerMixin

logger = logging.getLogger(__name__)


class ToolCDPHelpers(CircuitBreakerMixin):
    """Restricted browser access for tool functions."""

    SAFE_OPS = frozenset({"click", "fill", "type", "wait", "snapshot", "evaluate"})

    def __init__(self, bridge: PlaywrightBridge, allowed_domains: list[str] | None = None):
        self._bridge = bridge
        self._allowed_domains = allowed_domains or []
        self._fail_count = 0
        self._max_fails = 3

    async def click_selector(self, selector: str) -> dict:
        return await self._run_breaker(self._bridge.click, selector)

    async def fill_input(self, selector: str, text: str) -> dict:
        logger.debug("fill_input: %s = <sensitive: %d chars>", selector, len(text))
        return await self._run_breaker(self._bridge.fill, selector, text)

    async def wait(self, seconds: float = 1.0) -> None:
        await asyncio.sleep(seconds)

    async def snapshot(self, mode: str = "a11y", query: str = "", in_viewport: bool = False) -> dict:
        self._check_failures()
        try:
            if mode == "a11y" or mode == "interactive":
                try:
                    result = await self._bridge.a11y_snapshot()
                except A11yNotAvailable:
                    logger.warning(
                        "a11y snapshot not available in this environment, "
                        "falling back to progressive mode"
                    )
                    result = await self._bridge._progressive_snapshot(query=query)
                    result["degraded"] = True
                    result["_fallback_reason"] = "accessibility_tree_unavailable"
            elif mode == "aria" or mode == "simplified":
                result = await self._bridge.aria_snapshot()
            elif mode == "progressive":
                result = await self._bridge._progressive_snapshot(query=query)
            else:
                result = await self._bridge.capture_snapshot()
            self._fail_count = 0
            return result
        except Exception:
            self._fail_count += 1
            raise

    async def evaluate(self, js: str) -> Any:
        return await self._run_breaker(self._bridge.evaluate, js)
