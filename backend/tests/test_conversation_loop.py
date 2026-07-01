"""Tests for conversation_loop module (unit-level, no LLM/CDP)."""

from yak_browser_use.engine._harness.conversation_loop import (
    _prepare_messages,
    ConversationResult,
)
from yak_browser_use.engine._harness.iteration_budget import IterationBudget


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
