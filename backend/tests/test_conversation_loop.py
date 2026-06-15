"""Tests for conversation_loop module (unit-level, no LLM/CDP)."""

from engine._harness.conversation_loop import (
    _prepare_messages,
    ConversationResult,
    resume_conversation,
)
from engine._harness.iteration_budget import IterationBudget
from engine._harness.turn_context import InterruptState, save_interrupt_state


def test_prepare_messages_with_system():
    messages = [{"role": "user", "content": "hello"}]
    result = _prepare_messages(messages, "system prompt")
    assert len(result) == 2
    assert result[0]["role"] == "system"
    assert result[0]["content"] == "system prompt"
    assert result[1]["role"] == "user"


def test_prepare_messages_empty_system():
    messages = [{"role": "user", "content": "hello"}]
    result = _prepare_messages(messages, "")
    assert len(result) == 1
    assert result[0]["role"] == "user"


def test_conversation_result_defaults():
    budget = IterationBudget(max_total=20)
    result = ConversationResult(
        final_response="done",
        messages=[{"role": "assistant", "content": "done"}],
        budget=budget,
    )
    assert result.final_response == "done"
    assert result.interrupted is False
    assert result.turn_count == 0


def test_resume_conversation():
    budget = IterationBudget(max_total=50)
    budget.consume(5)
    state = save_interrupt_state(
        messages=[{"role": "user", "content": "hello"}],
        budget=budget,
        error_info={"code": "timeout"},
    )
    msgs, restored_budget, error_info = resume_conversation(state, "system prompt")
    assert len(msgs) == 1
    assert msgs[0]["content"] == "hello"
    assert restored_budget is not None
    assert restored_budget.remaining == 45
    assert error_info["code"] == "timeout"


def test_resume_conversation_no_budget():
    state = InterruptState(
        messages=[{"role": "user", "content": "hi"}],
        budget=None,
        error_info=None,
    )
    msgs, budget, error_info = resume_conversation(state, "")
    assert len(msgs) == 1
    assert budget is None
    assert error_info is None
