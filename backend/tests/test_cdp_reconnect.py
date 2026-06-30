"""Integration tests for CDP disconnect detection and reconnect logic."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yak_browser_use.engine._harness.tool_executor import (
    _is_cdp_disconnect,
    _CDP_RECONNECT_MAX,
    _CDP_RECONNECT_DELAYS,
    execute_tool_calls_sequential,
)
from yak_browser_use.engine._harness.iteration_budget import IterationBudget

import yak_browser_use.tools.registry as reg_mod


def _mock_cdp():
    """Create a CDPHelpers mock with async bridge methods."""
    helpers = MagicMock()
    helpers.bridge.stop = AsyncMock()
    helpers.bridge.start = AsyncMock()
    helpers.bridge.wait_for_page_scan = AsyncMock()
    return helpers


# ── _is_cdp_disconnect classification ───────────────────────────────────


class TestIsCdpDisconnect:

    def test_target_closed_exception(self):
        class TargetClosedError(Exception):
            pass
        assert _is_cdp_disconnect(TargetClosedError("x")) is True

    def test_browser_closed_exception(self):
        class BrowserClosedException(Exception):
            pass
        assert _is_cdp_disconnect(BrowserClosedException("x")) is True

    def test_websocket_exception(self):
        class WebSocketError(Exception):
            pass
        assert _is_cdp_disconnect(WebSocketError("x")) is True

    def test_target_closed_message(self):
        assert _is_cdp_disconnect(RuntimeError("target closed")) is True

    def test_browser_closed_message(self):
        assert _is_cdp_disconnect(RuntimeError("browser has been closed")) is True

    def test_browser_closed_short(self):
        assert _is_cdp_disconnect(RuntimeError("browser closed")) is True

    def test_connection_closed_reading(self):
        assert _is_cdp_disconnect(ConnectionError("connection closed while reading from socket")) is True

    def test_protocol_error(self):
        assert _is_cdp_disconnect(RuntimeError("protocol error: session not found")) is True

    def test_normal_error_not_cdp(self):
        assert _is_cdp_disconnect(ValueError("invalid selector")) is False

    def test_timeout_not_cdp(self):
        assert _is_cdp_disconnect(TimeoutError("timed out")) is False

    def test_generic_not_cdp(self):
        assert _is_cdp_disconnect(Exception("something went wrong")) is False


# ── Reconnect constants ─────────────────────────────────────────────────


class TestReconnectConstants:

    def test_delays_non_decreasing(self):
        for i in range(len(_CDP_RECONNECT_DELAYS) - 1):
            assert _CDP_RECONNECT_DELAYS[i + 1] >= _CDP_RECONNECT_DELAYS[i]

    def test_max_positive(self):
        assert isinstance(_CDP_RECONNECT_MAX, int) and _CDP_RECONNECT_MAX >= 1

    def test_delays_length_matches_max(self):
        assert len(_CDP_RECONNECT_DELAYS) == _CDP_RECONNECT_MAX


# ── tool_executor reconnect behavior ────────────────────────────────────


class TestReconnectBehavior:

    @pytest.mark.asyncio
    async def test_cdp_disconnect_triggers_bridge_restart(self):
        messages = []
        tool_calls = [{
            "id": "tc_1",
            "type": "function",
            "function": {"name": "browser_goto", "arguments": '{"url": "https://example.com"}'},
        }]
        call_count = 0

        async def _dispatch(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("protocol error: session not found")
            return {"ok": True, "result": "ok", "duration_ms": 100}

        mock_helpers = _mock_cdp()
        budget = IterationBudget(max_total=10)

        with patch.object(reg_mod.registry, "dispatch", new=_dispatch):
            await execute_tool_calls_sequential(
                messages=messages, tool_calls=tool_calls,
                cdp_helpers=mock_helpers, budget=budget,
            )

        mock_helpers.bridge.stop.assert_called_once()
        mock_helpers.bridge.start.assert_called_once()
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_non_cdp_error_no_restart(self):
        messages = []
        tool_calls = [{
            "id": "tc_1",
            "type": "function",
            "function": {"name": "browser_goto", "arguments": '{"url": "https://x.com"}'},
        }]

        async def _dispatch(*a, **kw):
            raise ValueError("invalid argument")

        mock_helpers = _mock_cdp()

        with patch.object(reg_mod.registry, "dispatch", new=_dispatch):
            await execute_tool_calls_sequential(
                messages=messages, tool_calls=tool_calls,
                cdp_helpers=mock_helpers,
            )

        mock_helpers.bridge.stop.assert_not_called()
        mock_helpers.bridge.start.assert_not_called()
        assert len(messages) == 1
        assert "Error" in messages[0]["content"]

    @pytest.mark.asyncio
    async def test_all_retries_fail(self):
        messages = []
        tool_calls = [{
            "id": "tc_1",
            "type": "function",
            "function": {"name": "browser_goto", "arguments": '{"url": "https://x.com"}'},
        }]

        async def _dispatch(*a, **kw):
            raise ConnectionError("protocol error: transport closed")

        mock_helpers = _mock_cdp()
        mock_helpers.bridge.start.side_effect = ConnectionError("cannot restart")

        with patch.object(reg_mod.registry, "dispatch", new=_dispatch):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await execute_tool_calls_sequential(
                    messages=messages, tool_calls=tool_calls,
                    cdp_helpers=mock_helpers,
                )

        assert mock_helpers.bridge.stop.call_count == _CDP_RECONNECT_MAX
        assert mock_helpers.bridge.start.call_count == _CDP_RECONNECT_MAX

    @pytest.mark.asyncio
    async def test_budget_resumed_after_reconnect(self):
        messages = []
        tool_calls = [{
            "id": "tc_1",
            "type": "function",
            "function": {"name": "browser_goto", "arguments": '{"url": "https://x.com"}'},
        }]
        call_count = 0

        async def _dispatch(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("protocol error")
            return {"ok": True, "result": "ok", "duration_ms": 10}

        mock_helpers = _mock_cdp()
        budget = IterationBudget(max_total=10)

        with patch.object(reg_mod.registry, "dispatch", new=_dispatch):
            await execute_tool_calls_sequential(
                messages=messages, tool_calls=tool_calls,
                cdp_helpers=mock_helpers, budget=budget,
            )

        assert budget.is_paused is False

    @pytest.mark.asyncio
    async def test_stream_error_after_max_retries(self):
        messages = []
        tool_calls = [{
            "id": "tc_1",
            "type": "function",
            "function": {"name": "browser_goto", "arguments": '{"url": "https://x.com"}'},
        }]
        events = []

        async def _dispatch(*a, **kw):
            raise ConnectionError("protocol error")

        mock_helpers = _mock_cdp()
        mock_helpers.bridge.start.side_effect = ConnectionError("cannot restart")

        with patch.object(reg_mod.registry, "dispatch", new=_dispatch):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await execute_tool_calls_sequential(
                    messages=messages, tool_calls=tool_calls,
                    cdp_helpers=mock_helpers,
                    stream_callback=lambda e: events.append(e),
                )

        error_events = [e for e in events if "error" in e.get("type", "").lower()]
        assert len(error_events) >= 1


# ── EngineState disconnect callback ─────────────────────────────────────


class TestEngineStateDisconnect:

    @pytest.mark.asyncio
    async def test_disconnect_via_callback(self):
        """Register a disconnect callback and verify it fires + clears state."""
        from yak_browser_use.api.state import engine_state

        engine_state.reset_for_test()
        mock_bridge = MagicMock()
        mock_bridge_id = id(mock_bridge)
        engine_state.bridge = mock_bridge
        engine_state.current_state = "connected"

        captured = {}

        async def _on_disconnect():
            captured["called"] = True
            engine_state.bridge = None
            engine_state.current_state = "idle"

        mock_bridge._on_disconnect_cb = _on_disconnect
        await mock_bridge._on_disconnect_cb()

        assert captured["called"] is True
        assert engine_state.bridge is None
        assert engine_state.current_state == "idle"

    @pytest.mark.asyncio
    async def test_disconnect_broadcasts_to_clients(self):
        """Verify broadcast_event sends disconnect event to all WS clients."""
        from yak_browser_use.api.state import _EngineState

        state = _EngineState()
        q = asyncio.Queue()
        state.ws_clients = [q]
        state.current_state = "connected"

        await state.broadcast_event({"type": "chrome_disconnected", "reason": "browser_closed"})

        event = q.get_nowait()
        assert event["type"] == "chrome_disconnected"

    @pytest.mark.asyncio
    async def test_chrome_connected_property(self):
        """chrome_connected returns True only when bridge is set."""
        from yak_browser_use.api.state import _EngineState

        state = _EngineState()
        assert state.chrome_connected is False

        state.bridge = MagicMock()
        assert state.chrome_connected is True

        state.bridge = None
        assert state.chrome_connected is False
