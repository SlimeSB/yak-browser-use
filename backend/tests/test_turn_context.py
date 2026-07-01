"""Tests for engine._harness.turn_context — per-turn execution state."""

from __future__ import annotations

from yak_browser_use.engine._harness.turn_context import (
    TurnContext,
    build_turn_context,
)
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
