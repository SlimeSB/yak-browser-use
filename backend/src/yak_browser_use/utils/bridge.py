"""Bridge-level helpers — extract_bridge, CircuitBreakerMixin."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_bridge(cdp_helpers: object | None) -> Any:
    """Extract *PlaywrightBridge* from *cdp_helpers*, falling back through known attribute names.

    Returns ``None`` when *cdp_helpers* is ``None`` or has no bridge-like attribute.
    """
    if cdp_helpers is None:
        return None
    bridge = getattr(cdp_helpers, "bridge", None)
    if bridge is not None:
        return bridge
    bridge = getattr(cdp_helpers, "_bridge", None)
    if bridge is not None:
        return bridge
    return None


class CircuitBreakerMixin:
    """Mixin that provides a circuit-breaker guard for browser operations.

    Subclasses must set ``_fail_count`` and ``_max_fails`` (defaults provided).

    Usage::

        class MyOps(CircuitBreakerMixin):
            async def click(self, ...):
                self._check_failures()
                try:
                    result = await self._bridge.click(...)
                    self._fail_count = 0
                    return result
                except Exception:
                    self._fail_count += 1
                    raise
    """

    _fail_count: int = 0
    _max_fails: int = 3

    def _check_failures(self) -> None:
        """Raise ``RuntimeError`` if *max_fails* consecutive failures have been reached."""
        if self._fail_count >= self._max_fails:
            raise RuntimeError(
                f"circuit breaker: {self._max_fails} consecutive failures"
            )

    async def _run_breaker(self, coro_fn, *args, **kwargs) -> Any:
        """Execute *coro_fn* with circuit-breaker guard.

        On success resets the failure count; on failure increments it.
        """
        self._check_failures()
        try:
            result = await coro_fn(*args, **kwargs)
            self._fail_count = 0
            return result
        except Exception:
            self._fail_count += 1
            raise
