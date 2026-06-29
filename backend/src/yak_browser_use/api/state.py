"""Engine runtime state singleton for the FastAPI server."""

from __future__ import annotations

import asyncio
from typing import Any, TYPE_CHECKING

from yak_browser_use.cdp.playwright_bridge import PlaywrightBridge
from yak_browser_use.utils.logging import get_logger

if TYPE_CHECKING:
    from yak_browser_use.engine.state import RunContext

logger = get_logger(__name__)


class _EngineState:
    """Hold engine runtime state for the FastAPI server.

    Attributes
    ----------
    current_state : str
        One of ``idle``, ``connecting``, ``connected``, ``running``.
    bridge : PlaywrightBridge | None
        The active PlaywrightBridge instance for browser operations.
    _running_pipeline : RunContext | None
        Context for the currently executing pipeline, if any.
    ws_clients : list[asyncio.Queue]
        Queues for broadcasting events to WebSocket clients.
    """

    def __init__(self) -> None:
        self.current_state: str = "idle"
        self.bridge: PlaywrightBridge | None = None
        self._running_pipeline: RunContext | None = None
        self.ws_clients: list[asyncio.Queue] = []
        self._service: object | None = None
        self._service_lock = asyncio.Lock()
        self._connect_lock = asyncio.Lock()
        self.pipeline_lock = asyncio.Lock()

    # ── Chrome connection  ──────────────────────────────────────────

    async def connect_chrome(self, ws_url: str | None = None, pipeline_name: str = "__chat__") -> str:
        """Connect to Chrome via PlaywrightBridge (CDP).

        Parameters
        ----------
        ws_url:
            Optional explicit WebSocket URL. If omitted, auto-discovers.
        pipeline_name:
            Pipeline name for per-pipeline download isolation.

        Returns
        -------
        The connected CDP URL (truncated for logging).
        """
        async with self._connect_lock:
            if self._running_pipeline is not None:
                raise RuntimeError("A pipeline is currently running — cannot reconnect Chrome")

            if self.bridge is not None:
                logger.warning("Chrome already connected — disconnecting old bridge first")
                old_bridge = self.bridge
                self.bridge = None
                self.current_state = "idle"
                try:
                    await old_bridge.stop()
                except Exception:
                    logger.debug("Failed to stop old bridge", exc_info=True)

            self.current_state = "connecting"

            if ws_url is None:
                from yak_browser_use.cdp.discover import discover_ws_url
                ws_url = await discover_ws_url()

            if ws_url is None:
                raise RuntimeError("Cannot discover Chrome debug URL — is Chrome running with --remote-debugging-port?")

            bridge = PlaywrightBridge(ws_url, pipeline_name=pipeline_name)
            await bridge.start()
            bridge.start_health_check()

            bridge_id = id(bridge)
            async def _on_bridge_disconnected() -> None:
                """Bridge-specific disconnect callback — only clears state if this bridge is still current."""
                if self.bridge is None or id(self.bridge) != bridge_id:
                    return
                logger.info("EngineState: processing bridge disconnect (bridge_id=%s)", bridge_id)
                self.bridge = None
                self.current_state = "idle"
                await self.broadcast_event({
                    "type": "chrome_disconnected",
                    "reason": "browser_closed",
                })

            bridge._on_disconnect_cb = _on_bridge_disconnected

            self.bridge = bridge
            self.current_state = "connected"
            logger.info("Chrome connected via %s ...", ws_url[:60])
            return ws_url

    async def disconnect_chrome(self) -> None:
        """Disconnect from Chrome and reset state."""
        if self._running_pipeline is not None:
            raise RuntimeError("A pipeline is currently running")

        if self.bridge:
            await self.bridge.stop()
        self.bridge = None
        self.current_state = "idle"
        logger.info("Chrome disconnected")

    @property
    def chrome_connected(self) -> bool:
        """Return True if bridge is active."""
        return self.bridge is not None

    # ── Pipeline lifecycle  ─────────────────────────────────────────

    @property
    def running_pipeline(self) -> RunContext | None:
        return self._running_pipeline

    @running_pipeline.setter
    def running_pipeline(self, ctx: RunContext | None) -> None:
        self._running_pipeline = ctx
        if ctx is not None:
            self.current_state = "running"
        elif self.bridge is not None:
            self.current_state = "connected"
        else:
            self.current_state = "idle"

    # ── Event broadcasting  ─────────────────────────────────────────

    async def broadcast_event(self, event: dict) -> None:
        """Push a structured event to all registered WebSocket queues."""
        dead: list[asyncio.Queue] = []
        for q in self.ws_clients:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
            except Exception:
                dead.append(q)
        for q in dead:
            try:
                self.ws_clients.remove(q)
            except ValueError:
                pass

    # ── Cleanup  ────────────────────────────────────────────────────

    async def cleanup(self) -> None:
        """Gracefully shut down everything: bridge, pipeline, WS clients."""
        logger.info("EngineState: cleaning up …")

        if self.bridge:
            await self.bridge.stop()
            self.bridge = None

        self._running_pipeline = None
        self.ws_clients.clear()
        self.current_state = "idle"
        self._service = None

        from yak_browser_use.cdp.launcher import cleanup_isolated
        await cleanup_isolated()

        logger.info("EngineState: cleanup complete")


# Module-level singleton
engine_state = _EngineState()
