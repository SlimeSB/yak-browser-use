"""EventBus — centralized event dispatch for chat and pipeline events.

Routes events to:
- Registered callbacks (e.g. WebSocket manager)
- Engine state WS client queues
- (Pipeline events also go through EventSink, which is separate)
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)


class EventBus:
    """Pushes structured events to callbacks and engine-state WS clients.

    Tracks a ``chat_streaming`` flag so ``chat.message`` events can be
    suppressed during streaming (the delta chunks are sent via individual
    streaming callbacks, so the full message event is redundant).
    """

    def __init__(self, engine_state: Any | None = None):
        self._engine_state = engine_state
        self._event_callbacks: list[Callable[[dict], None]] = []
        self.chat_streaming: bool = False

    def on_event(self, callback: Callable[[dict], None]) -> None:
        """Register a callback for event streaming."""
        self._event_callbacks.append(callback)

    def push(self, event: dict) -> None:
        """Push an event to all registered callbacks AND engine-state WS clients.

        ``chat.message`` events are silently dropped while
        ``chat_streaming`` is active to avoid duplicating the delta stream.
        """
        if event.get("type") == "chat.message" and self.chat_streaming:
            return
        event["_ts"] = time.time()
        for cb in self._event_callbacks:
            try:
                cb(event)
            except Exception:
                logger.warning("Event callback failed for type=%s", event.get("type"), exc_info=True)
        if self._engine_state and hasattr(self._engine_state, "ws_clients"):
            dead: list[asyncio.Queue] = []
            for q in self._engine_state.ws_clients:
                try:
                    q.put_nowait(event)
                except Exception:
                    dead.append(q)
            for q in dead:
                try:
                    self._engine_state.ws_clients.remove(q)
                except ValueError:
                    pass
