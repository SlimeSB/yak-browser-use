"""Tests for engine._harness.turn_context — per-turn execution state."""

from __future__ import annotations

import pytest

from yak_browser_use.engine._harness.turn_context import (
    TurnContext,
    InterruptState,
    build_turn_context,
    save_interrupt_state,
)
from yak_browser_use.engine._harness.iteration_budget import IterationBudget
from yak_browser_use.engine._harness.tool_guardrails import ToolCallGuardrailState


class TestTurnContext:
    def test_defaults(self):
        ctx = TurnContext()
        assert ctx.tool_retries == 0
        assert ctx.json_retries == 0
        assert ctx.empty_content_retries == 0
        assert ctx.api_retries == 0
        assert ctx.max_tool_retries == 3
        assert ctx.max_json_retries == 2
        assert ctx.max_empty_content_retries == 2
        assert ctx.max_api_retries == 3
        assert ctx.turn_messages_snapshot == []

    def test_reset_all_counters(self):
        ctx = TurnContext()
        ctx.tool_retries = 5
        ctx.json_retries = 3
        ctx.empty_content_retries = 1
        ctx.api_retries = 2
        ctx.turn_messages_snapshot = [{"role": "user", "content": "hi"}]

        ctx.reset()
        assert ctx.tool_retries == 0
        assert ctx.json_retries == 0
        assert ctx.empty_content_retries == 0
        assert ctx.api_retries == 0
        assert ctx.turn_messages_snapshot == []

    def test_snapshot_saves_messages(self):
        ctx = TurnContext()
        msgs = [{"role": "user", "content": "hello"}]
        ctx.snapshot(msgs)
        assert ctx.turn_messages_snapshot == msgs
        # Snapshot should be a copy, not a reference
        msgs.append({"role": "assistant", "content": "hi"})
        assert len(ctx.turn_messages_snapshot) == 1

    def test_custom_max_retries(self):
        ctx = TurnContext(
            max_tool_retries=5,
            max_json_retries=3,
            max_empty_content_retries=4,
            max_api_retries=6,
        )
        assert ctx.max_tool_retries == 5
        assert ctx.max_json_retries == 3
        assert ctx.max_empty_content_retries == 4
        assert ctx.max_api_retries == 6


class TestInterruptState:
    def test_defaults(self):
        state = InterruptState()
        assert state.messages == []
        assert state.budget is None
        assert state.error_info is None
        assert state.last_tool_result is None

    def test_with_values(self):
        state = InterruptState(
            messages=[{"role": "user", "content": "hello"}],
            budget={"max_total": 50, "used": 10},
            error_info={"code": "TIMEOUT"},
            last_tool_result={"ok": False, "error": "timeout"},
        )
        assert len(state.messages) == 1
        assert state.budget["max_total"] == 50
        assert state.error_info["code"] == "TIMEOUT"
        assert state.last_tool_result["ok"] is False

    def test_to_dict_full(self):
        state = InterruptState(
            messages=[{"role": "user", "content": "hi"}],
            budget={"max_total": 50},
            error_info={"code": "error"},
            last_tool_result={"ok": True},
        )
        d = state.to_dict()
        assert d["messages"] == [{"role": "user", "content": "hi"}]
        assert d["budget"] == {"max_total": 50}
        assert d["error_info"] == {"code": "error"}
        assert d["last_tool_result"] == {"ok": True}

    def test_to_dict_minimal(self):
        state = InterruptState()
        d = state.to_dict()
        assert d["messages"] == []
        assert d["budget"] is None
        assert d["error_info"] is None
        assert d["last_tool_result"] is None

    def test_from_dict_full(self):
        d = {
            "messages": [{"role": "user", "content": "hi"}],
            "budget": {"max_total": 30, "used": 5},
            "error_info": None,
            "last_tool_result": {"ok": True},
        }
        state = InterruptState.from_dict(d)
        assert len(state.messages) == 1
        assert state.budget["max_total"] == 30
        assert state.error_info is None
        assert state.last_tool_result == {"ok": True}

    def test_from_dict_empty(self):
        state = InterruptState.from_dict({})
        assert state.messages == []
        assert state.budget is None
        assert state.error_info is None
        assert state.last_tool_result is None


class TestBuildTurnContext:
    def test_fresh_context(self):
        ctx = build_turn_context()
        assert isinstance(ctx, TurnContext)
        assert ctx.tool_retries == 0

    def test_with_guardrail_reset(self):
        guardrail = ToolCallGuardrailState()
        guardrail._exact_failures["test"] = 10
        ctx = build_turn_context(guardrail_state=guardrail)
        assert len(guardrail._exact_failures) == 0  # reset by build_turn_context

    def test_without_guardrail(self):
        ctx = build_turn_context()
        assert isinstance(ctx, TurnContext)


class TestSaveInterruptState:
    def test_saves_full_state(self):
        budget = IterationBudget(max_total=50)
        budget.consume(10)
        state = save_interrupt_state(
            messages=[{"role": "user", "content": "hello"}],
            budget=budget,
            error_info={"code": "timeout"},
            last_tool_result={"ok": False, "error": "timeout"},
        )
        assert isinstance(state, InterruptState)
        assert len(state.messages) == 1
        assert state.budget["remaining"] == 40
        assert state.error_info == {"code": "timeout"}
        assert state.last_tool_result == {"ok": False, "error": "timeout"}

    def test_minimal_state(self):
        budget = IterationBudget(max_total=20)
        state = save_interrupt_state(messages=[], budget=budget)
        assert state.messages == []
        assert state.budget["max_total"] == 20
        assert state.error_info is None
        assert state.last_tool_result is None

    def test_messages_copied(self):
        budget = IterationBudget(max_total=10)
        msgs = [{"role": "user", "content": "original"}]
        state = save_interrupt_state(messages=msgs, budget=budget)
        msgs.append({"role": "assistant", "content": "extra"})
        assert len(state.messages) == 1  # copy, not reference
