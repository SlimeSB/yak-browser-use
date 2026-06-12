"""Tests for turn_context module."""

from engine._harness.turn_context import (
    TurnContext,
    InterruptState,
    build_turn_context,
    save_interrupt_state,
)
from engine._harness.iteration_budget import IterationBudget
from engine._harness.tool_guardrails import ToolCallGuardrailState


def test_turn_context_defaults():
    ctx = TurnContext()
    assert ctx.tool_retries == 0
    assert ctx.json_retries == 0
    assert ctx.empty_content_retries == 0
    assert ctx.api_retries == 0
    assert ctx.max_tool_retries == 3
    assert ctx.max_json_retries == 2
    assert ctx.max_api_retries == 3


def test_build_turn_context_resets_guardrails():
    gs = ToolCallGuardrailState()
    gs._exact_failures["x"] = 5
    ctx = build_turn_context(guardrail_state=gs)
    assert ctx.tool_retries == 0
    assert len(gs._exact_failures) == 0


def test_build_turn_context_no_guardrail():
    ctx = build_turn_context(guardrail_state=None)
    assert ctx.tool_retries == 0


def test_interrupt_state_to_from_dict():
    budget = IterationBudget(max_total=50)
    budget.consume(5)

    state = save_interrupt_state(
        messages=[{"role": "user", "content": "hello"}],
        budget=budget,
        error_info={"code": "timeout"},
    )

    d = state.to_dict()
    assert len(d["messages"]) == 1
    assert d["budget"]["used"] == 5
    assert d["error_info"]["code"] == "timeout"

    restored = InterruptState.from_dict(d)
    assert restored.messages[0]["content"] == "hello"
    assert restored.budget["used"] == 5
    assert restored.error_info["code"] == "timeout"
