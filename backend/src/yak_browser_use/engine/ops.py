"""ToolContext — unified browser SDK wrapping PlaywrightBridge.

Provides a safe subset of browser operations with domain whitelisting
and a circuit breaker. Used by both preset tools and LLM-generated tools.

Usage::

    async def my_tool(ctx: ToolContext) -> dict:
        await ctx.wait(1.0)
        title = await ctx.eval("document.title")
        return {"ok": True, "title": title}
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from yak_browser_use.cdp.playwright_bridge import PlaywrightBridge

logger = logging.getLogger(__name__)


def _extract_bridge(cdp_helpers: object | None):
    """Extract PlaywrightBridge from helpers, falling back through known attribute names."""
    if cdp_helpers is None:
        return None
    bridge = getattr(cdp_helpers, "bridge", None)
    if bridge is not None:
        return bridge
    bridge = getattr(cdp_helpers, "_bridge", None)
    if bridge is not None:
        return bridge
    return None


def build_tool_kwargs(
    func,
    cdp_helpers: object | None,
    allowed_domains: list[str] | None = None,
) -> dict:
    """Build kwargs dict for a tool function based on its signature.

    Inspects the function's parameters and injects:
    - ``ctx``: ToolContext (if the function accepts it and cdp_helpers is available)
    - ``cdp_helpers``: ToolCDPHelpers for legacy tools (if no ``ctx`` param)

    Returns a dict ready for ``func(**kwargs)``.
    """
    sig = inspect.signature(func)
    param_names = set(sig.parameters.keys())

    kwargs: dict = {}
    bridge = _extract_bridge(cdp_helpers)
    if "ctx" in param_names and bridge is not None:
        kwargs["ctx"] = ToolContext(bridge=bridge, allowed_domains=allowed_domains)
    elif "cdp_helpers" in param_names and bridge is not None:
        from yak_browser_use.utils.tool_cdp import ToolCDPHelpers

        kwargs["cdp_helpers"] = ToolCDPHelpers(bridge)

    return kwargs


class ToolContext:
    """Controlled browser API for tool functions.

    Wraps PlaywrightBridge via composition (not inheritance) to expose a
    safe subset of browser operations with domain whitelisting and a
    circuit breaker.
    """

    def __init__(
        self,
        bridge: PlaywrightBridge,
        allowed_domains: list[str] | None = None,
    ) -> None:
        self._bridge = bridge
        self._allowed_domains = allowed_domains or []
        self._fail_count = 0
        self._max_fails = 3

    # ------------------------------------------------------------------
    # Browser ops
    # ------------------------------------------------------------------

    async def wait(self, seconds: float) -> None:
        """Wait for *seconds* (direct ``asyncio.sleep``, not through bridge).

        Does NOT participate in the circuit breaker.
        """
        await asyncio.sleep(seconds)

    async def eval(self, js: str) -> Any:
        """Execute JavaScript in the page and return the result."""
        self._check_domain()
        self._check_failures()
        try:
            result = await self._bridge.evaluate(js)
            self._fail_count = 0
            return result
        except Exception:
            self._fail_count += 1
            raise

    async def click(self, selector: str, click_count: int = 1) -> dict:
        """Click an element matching *selector*. ``click_count=2`` for double-click."""
        self._check_domain()
        self._check_failures()
        try:
            result = await self._bridge.click(selector, click_count=click_count)
            self._fail_count = 0
            return result
        except Exception:
            self._fail_count += 1
            raise

    async def type(self, selector: str, text: str) -> dict:
        """Type *text* into an input matching *selector*."""
        self._check_domain()
        self._check_failures()
        try:
            result = await self._bridge.fill(selector, text)
            self._fail_count = 0
            return result
        except Exception:
            self._fail_count += 1
            raise

    async def snapshot(
        self,
        mode: str = "aria",
        query: str = "",
        in_viewport: bool = False,
    ) -> dict:
        """Capture a page snapshot.

        *mode* values:
          - ``aria`` (default) — Playwright aria_snapshot(mode="ai"), YAML 语义树.
            LLM 友好的页面快照：展示所有可交互元素的 role/name 层级结构。
            token 最少，适合"先看一眼这页有什么"。
          - ``a11y`` — CDP Accessibility.getFullAXTree, 结构化元素列表.
            每个元素带 ref/role/name/nth/selector。
            LLM 可以拿着 ref 直接 click/fill/hover（如点击 @a_3）。
          - ``progressive`` — CDP DOM 深度扫描 + 密度自适应折叠.
            最多 200 元素，密集容器自动折叠为 folded_containers，可用 expand_branch 展开。
            适合超长列表/复杂页面。
          - ``full`` — screenshot + HTML 全量转储.
        """
        self._check_domain()
        self._check_failures()
        try:
            if mode == "a11y" or mode == "interactive":
                result = await self._bridge.a11y_snapshot()
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

    async def expand_branch(self, key: str, limit: int = 30, offset: int = 0) -> dict:
        """Expand a folded container from progressive snapshot (pure in-memory, no CDP)."""
        self._check_domain()
        self._check_failures()
        try:
            result = await self._bridge.expand_branch(key, limit=limit, offset=offset)
            self._fail_count = 0
            return result
        except Exception:
            self._fail_count += 1
            raise

    async def screenshot(self) -> str:
        """Capture the current viewport as a base64-encoded PNG string."""
        self._check_domain()
        self._check_failures()
        try:
            result = await self._bridge.screenshot()
            self._fail_count = 0
            return result
        except Exception:
            self._fail_count += 1
            raise

    async def source(self) -> str:
        """Return the full serialized HTML of the current page."""
        self._check_domain()
        self._check_failures()
        try:
            result = await self._bridge.source()
            self._fail_count = 0
            return result
        except Exception:
            self._fail_count += 1
            raise

    # ------------------------------------------------------------------
    # Safety internals
    # ------------------------------------------------------------------

    def _check_domain(self) -> None:
        """Raise if the current page domain is not in the allowed list."""
        if not self._allowed_domains:
            return

        page = self._bridge.page
        if page is None:
            return

        from urllib.parse import urlparse

        current_url = page.url
        if not current_url:
            return
        hostname = urlparse(current_url).hostname or ""
        if hostname not in self._allowed_domains:
            raise RuntimeError(
                f"ToolContext: domain '{hostname}' not in allowed_domains {self._allowed_domains}"
            )

    def _check_failures(self) -> None:
        if self._fail_count >= self._max_fails:
            raise RuntimeError(f"ToolContext circuit breaker: {self._max_fails} consecutive failures")
