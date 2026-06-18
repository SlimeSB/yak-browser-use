"""CDPDaemon — WebSocket connection manager for Chrome DevTools Protocol.

.. deprecated::
    Use :class:`cdp.playwright_bridge.PlaywrightBridge` instead.
    CDPDaemon is kept for backward compatibility only and will be removed
    in a future release.
"""

from __future__ import annotations

import asyncio
import json
import os
import warnings
from typing import Any

import websockets

from utils.logging import get_logger

logger = get_logger(__name__)

# Module-level session store (simple dict, no SessionManager class).
_sessions: dict[str, dict[str, Any]] = {}


class CDPDaemon:
    """Manages a WebSocket connection to Chrome's DevTools Protocol endpoint.

    Provides ``_send(method, params)`` as the interface that
    :class:`cdp.helpers.CDPHelpers` depends on.

    Parameters
    ----------
    ws_url:
        The ``ws://`` or ``wss://`` CDP WebSocket URL.
    """

    def __init__(self, ws_url: str = "") -> None:
        self.ws_url = ws_url
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._msg_id: int = 0
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._session_id: str | None = None
        self._target_id: str | None = None
        self._running = False
        self._listen_task: asyncio.Task | None = None
        self._stopped_intentional = False
        self._reconnect_attempts = 0
        self._max_reconnect = 3
        self._reconnect_delays = [1, 2, 4]

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Connect to the CDP WebSocket endpoint and start listening."""
        logger.info("CDPDaemon connecting to %s", self.ws_url[:60])
        self._ws = await websockets.connect(
            self.ws_url,
            max_size=100 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=10,
        )
        self._running = True
        self._listen_task = asyncio.create_task(self._listen())
        logger.info("CDPDaemon connected")

    async def stop(self) -> None:
        """Close the CDP connection."""
        self._stopped_intentional = True
        logger.info("CDPDaemon stopping")
        self._running = False

        if self._ws:
            await self._ws.close()
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except (asyncio.CancelledError, Exception):
                pass

    @property
    def is_running(self) -> bool:
        """Return True if the daemon has an active WebSocket connection."""
        return self._running and self._ws is not None

    def set_running(self, val: bool) -> None:
        """Allow external code to update the running flag (e.g. after IPC)."""
        self._running = val

    # ------------------------------------------------------------------
    # CDP command / send
    # ------------------------------------------------------------------

    async def _send(self, method: str, params: dict | None = None, *, session_id: str | None = None) -> Any:
        """Send a CDP command and wait for its result.

        This is the interface that :class:`cdp.helpers.CDPHelpers` calls.
        Pass *session_id* to target a specific tab (auto-attach mode).
        """
        logger.debug("CDP send: %s", method)

        self._msg_id += 1
        msg_id = self._msg_id
        payload: dict[str, Any] = {"id": msg_id, "method": method}
        if params:
            payload["params"] = params
        sid = session_id if session_id is not None else self._session_id
        if sid:
            payload["sessionId"] = sid

        future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future

        await self._ws.send(json.dumps(payload))  # type: ignore[reportOptionalMemberAccess]
        return await asyncio.wait_for(future, timeout=30.0)

    async def drain_events(self) -> list[dict]:
        """Drain all buffered CDP events from the internal queue."""
        events: list[dict] = []
        while not self._event_queue.empty():
            try:
                events.append(self._event_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return events

    # ------------------------------------------------------------------
    # Listen loop
    # ------------------------------------------------------------------

    async def _listen(self) -> None:
        """Background task that reads messages from the WS connection."""
        logger.debug("CDP listener started")
        try:
            async for message in self._ws:  # type: ignore[reportOptionalIterable]
                try:
                    data = json.loads(message)
                    msg_id = data.get("id")
                    if msg_id is not None and msg_id in self._pending:
                        future = self._pending.pop(msg_id)
                        if "error" in data:
                            future.set_exception(
                                RuntimeError(json.dumps(data["error"]))
                            )
                        else:
                            future.set_result(data.get("result", {}))
                    else:
                        await self._event_queue.put(data)
                except json.JSONDecodeError:
                    pass
        except websockets.exceptions.ConnectionClosed:
            self._running = False
            if not self._stopped_intentional:
                await self._auto_reconnect()

    async def _auto_reconnect(self) -> None:
        """Exponential-backoff reconnection with up to *max_reconnect* attempts."""
        self._reconnect_attempts = 0
        while self._reconnect_attempts < self._max_reconnect:
            if not self._running or self._stopped_intentional:
                return

            self._reconnect_attempts += 1
            delay = self._reconnect_delays[self._reconnect_attempts - 1]

            logger.info(
                "CDPDaemon reconnect attempt %d/%d in %ds",
                self._reconnect_attempts,
                self._max_reconnect,
                delay,
            )
            await asyncio.sleep(delay)

            if self._stopped_intentional:
                return

            try:
                self._ws = await websockets.connect(
                    self.ws_url,
                    max_size=100 * 1024 * 1024,
                    ping_interval=20,
                    ping_timeout=10,
                )
                self._session_id = None
                self._target_id = None
                self._running = True
                await self.attach_first_page()
                await self.enable_default_domains()

                self._listen_task = asyncio.create_task(self._listen())

                logger.info(
                    "CDPDaemon reconnected after %d attempts",
                    self._reconnect_attempts,
                )
                self._reconnect_attempts = 0
                return
            except Exception as e:
                logger.warning(
                    "CDPDaemon reconnect attempt %d failed: %s",
                    self._reconnect_attempts,
                    e,
                )

        logger.error("CDPDaemon: all reconnect attempts failed")

    # ------------------------------------------------------------------
    # Page attachment & domains
    # ------------------------------------------------------------------

    async def attach_first_page(self) -> None:
        """Attach to the first available page tab, or create a blank one."""
        logger.debug("Attaching to first page")
        targets = await self._send("Target.getTargets")
        pages = [
            t
            for t in targets.get("targetInfos", [])
            if t.get("type") == "page"
        ]

        if pages:
            target_id = pages[0]["targetId"]
            session = await self._send(
                "Target.attachToTarget",
                {"targetId": target_id, "flatten": True},
            )
            self._target_id = target_id
            self._session_id = session.get("sessionId")
        else:
            result = await self._send("Target.createTarget", {"url": "about:blank"})
            target_id = result.get("targetId")
            self._target_id = target_id
            session = await self._send(
                "Target.attachToTarget",
                {"targetId": target_id, "flatten": True},
            )
            self._session_id = session.get("sessionId")

    async def enable_default_domains(self) -> None:
        """Enable Page, DOM, Runtime, Network CDP domains and auto-attach to all targets."""
        logger.debug("Enabling default CDP domains")
        await self._send("Page.enable")
        await self._send("DOM.enable")
        await self._send("Runtime.enable")
        await self._send("Network.enable")
        await self._send("Target.setAutoAttach", {
            "autoAttach": True,
            "waitForDebuggerOnStart": False,
            "flatten": True,
        }, session_id="")

    # ------------------------------------------------------------------
    # IPC handler (for daemon-server mode)
    # ------------------------------------------------------------------

    async def handle_ipc(self, req: dict) -> dict:
        """Handle an IPC (JSON) request on this daemon.

        Requests without ``"meta"`` are forwarded as CDP commands.
        Meta-requests handle internal operations such as ping, event
        draining, and session info.
        """
        req_id = req.get("id", "unknown")

        if "meta" in req:
            return await self._handle_meta(req_id, req["meta"], req)

        method = req.get("method")
        params = req.get("params", {})
        if not method:
            return {"id": req_id, "error": "missing method"}

        try:
            result = await self._send(method, params)
            return {"id": req_id, "result": result}
        except Exception as e:
            return {"id": req_id, "error": str(e)}

    async def _handle_meta(self, req_id: str, meta: str, req: dict) -> dict:
        if meta == "ping":
            return {"id": req_id, "pong": True, "pid": os.getpid()}
        elif meta == "drain_events":
            events = await self.drain_events()
            return {"id": req_id, "events": events}
        elif meta == "session":
            return {
                "id": req_id,
                "session_id": self._session_id,
                "target_id": self._target_id,
            }
        elif meta == "close_tab":
            await self._send("Target.closeTarget", {"targetId": self._target_id})
            return {"id": req_id, "closed": True}
        else:
            return {"id": req_id, "error": f"unknown meta: {meta}"}


# ---------------------------------------------------------------------------
# Module-level factory
# ---------------------------------------------------------------------------


async def ensure_daemon(name: str = "yak-browser-use") -> CDPDaemon:
    """Return a running CDPDaemon, creating one if necessary.

    .. deprecated::
        Use :class:`cdp.playwright_bridge.PlaywrightBridge` instead.

    Checks the module-level session dict for an existing daemon with
    the same *name*; if none exists, it discovers a WS URL, starts a
    new daemon, attaches the first page, and enables default domains.

    The resulting daemon is *not* cached — callers that need to reuse a
    daemon should hold a reference or coordinate via the session dict
    themselves.
    """
    warnings.warn(
        "ensure_daemon is deprecated; use PlaywrightBridge instead",
        DeprecationWarning,
        stacklevel=2,
    )
    # Check if a session already exists
    existing = _sessions.get(name)
    if existing and existing.get("ws_url"):
        daemon = CDPDaemon(existing["ws_url"])
        await daemon.start()
        await daemon.attach_first_page()
        await daemon.enable_default_domains()
        return daemon

    from .discover import discover_ws_url

    ws_url = await discover_ws_url()
    daemon = CDPDaemon(ws_url)
    await daemon.start()
    await daemon.attach_first_page()
    await daemon.enable_default_domains()

    _sessions[name] = {"ws_url": ws_url}
    return daemon
