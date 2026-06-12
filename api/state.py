"""Engine runtime state singleton for the FastAPI server."""

from __future__ import annotations

import asyncio
from typing import Any

from cdp.daemon import CDPDaemon
from engine.state import RunContext
from utils.logging import get_logger

logger = get_logger(__name__)


class _EngineState:
    """Hold engine runtime state for the FastAPI server.

    Attributes
    ----------
    current_state : str
        One of ``idle``, ``connecting``, ``connected``, ``running``.
    chrome_daemon : CDPDaemon | None
        The active Chrome DevTools Protocol daemon instance.
    _running_pipeline : RunContext | None
        Context for the currently executing pipeline, if any.
    ws_clients : list[asyncio.Queue]
        Queues for broadcasting events to WebSocket clients.
    """

    def __init__(self) -> None:
        self.current_state: str = "idle"
        self.chrome_daemon: CDPDaemon | None = None
        self._running_pipeline: RunContext | None = None
        self.ws_clients: list[asyncio.Queue] = []

    # ── Chrome connection  ──────────────────────────────────────────

    async def connect_chrome(self, ws_url: str | None = None) -> str:
        """Connect to Chrome via CDP WebSocket.

        Parameters
        ----------
        ws_url:
            Optional explicit WebSocket URL. If omitted, auto-discovers.

        Returns
        -------
        The connected WebSocket URL (truncated for logging).
        """
        if self.chrome_daemon and self.chrome_daemon.is_running:
            raise RuntimeError("Chrome is already connected")

        self.current_state = "connecting"

        if ws_url is None:
            from cdp.discover import discover_ws_url
            ws_url = await discover_ws_url()

        daemon = CDPDaemon(ws_url)
        await daemon.start()
        await daemon.attach_first_page()
        await daemon.enable_default_domains()

        self.chrome_daemon = daemon
        self.current_state = "connected"
        logger.info("Chrome connected via %s ...", ws_url[:60])
        return ws_url

    async def disconnect_chrome(self) -> None:
        """Disconnect from Chrome and reset state."""
        if self._running_pipeline is not None:
            raise RuntimeError("A pipeline is currently running")

        if self.chrome_daemon:
            await self.chrome_daemon.stop()
        self.chrome_daemon = None
        self.current_state = "idle"
        logger.info("Chrome disconnected")

    @property
    def chrome_connected(self) -> bool:
        """Return True if Chrome daemon is active and running."""
        return self.chrome_daemon is not None and self.chrome_daemon.is_running

    # ── Pipeline lifecycle  ─────────────────────────────────────────

    @property
    def running_pipeline(self) -> RunContext | None:
        return self._running_pipeline

    @running_pipeline.setter
    def running_pipeline(self, ctx: RunContext | None) -> None:
        self._running_pipeline = ctx
        if ctx is not None:
            self.current_state = "running"
        elif self.chrome_daemon and self.chrome_daemon.is_running:
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
            if q in self.ws_clients:
                self.ws_clients.remove(q)

    # ── Cleanup  ────────────────────────────────────────────────────

    async def cleanup(self) -> None:
        """Gracefully shut down everything: daemon, pipeline, WS clients."""
        logger.info("EngineState: cleaning up …")

        if self.chrome_daemon:
            await self.chrome_daemon.stop()
            self.chrome_daemon = None

        self._running_pipeline = None
        self.ws_clients.clear()
        self.current_state = "idle"

        from cdp.launcher import cleanup_isolated
        await cleanup_isolated()

        logger.info("EngineState: cleanup complete")


# Module-level singleton
engine_state = _EngineState()
