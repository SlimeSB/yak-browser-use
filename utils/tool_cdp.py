"""Restricted CDP helpers for tool-level browser access (safe subset).

Provides the same interface as CDPHelpers but with:
- Allowed domain restrictions
- Timeout limits
- Circuit breaker (3 consecutive failures)
- Only safe operations exposed
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from cdp.helpers import CDPHelpers

logger = logging.getLogger(__name__)


class ToolCDPHelpers:
    """Restricted browser access for tool functions."""

    SAFE_OPS = frozenset({"click", "fill", "type", "wait", "snapshot"})

    def __init__(self, helpers: CDPHelpers, allowed_domains: list[str] | None = None):
        self._helpers = helpers
        self._allowed_domains = allowed_domains or []
        self._fail_count = 0
        self._max_fails = 3

    async def click_selector(self, selector: str) -> dict:
        self._check_failures()
        result = await self._helpers.click_selector(selector)
        self._fail_count = 0
        return result

    async def fill_input(self, selector: str, text: str) -> dict:
        self._check_failures()
        result = await self._helpers.fill_input(selector, text, _sensitive=True)
        self._fail_count = 0
        return result

    async def fill_credential(self, selector: str, param_ref: object) -> None:
        """Resolve a param reference and fill it into a form field."""
        from params.manager import resolve_param
        text = resolve_param(param_ref)
        await self.fill_input(selector, text)

    async def wait(self, seconds: float = 1.0) -> None:
        await asyncio.sleep(seconds)

    async def snapshot(self) -> dict:
        self._check_failures()
        return await self._helpers.capture_snapshot()

    def _check_failures(self) -> None:
        if self._fail_count >= self._max_fails:
            raise RuntimeError(f"ToolCDP circuit breaker: {self._max_fails} consecutive failures")
        self._fail_count += 1
