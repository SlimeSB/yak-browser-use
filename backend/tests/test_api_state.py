"""Tests for api.state — _EngineState reset_for_test()."""

from __future__ import annotations

from unittest.mock import MagicMock

from yak_browser_use.api.state import _EngineState


class TestResetForTest:
    def test_resets_all_fields_to_initial(self):
        state = _EngineState()
        state.bridge = MagicMock()
        state._running_pipeline = MagicMock()
        state.ws_clients = [MagicMock(), MagicMock()]
        state.current_state = "running"

        state.reset_for_test()

        assert state.current_state == "idle"
        assert state.bridge is None
        assert state._running_pipeline is None
        assert state.ws_clients == []

    def test_twice_does_not_raise(self):
        state = _EngineState()
        state.reset_for_test()
        state.reset_for_test()

        assert state.current_state == "idle"
        assert state.bridge is None
        assert state._running_pipeline is None
        assert state.ws_clients == []
