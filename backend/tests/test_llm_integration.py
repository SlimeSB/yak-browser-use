"""Integration tests for LLM call chain — Agent → conversation_loop → tool_executor.

Mocks LLMClient at the conversation_loop boundary to verify the full
call chain without making real API calls or CDP connections.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yak_browser_use.engine._harness.conversation_loop import Agent, ConversationResult
from yak_browser_use.engine._harness.tool_executor import execute_tool_calls_sequential
from yak_browser_use.engine._harness.iteration_budget import IterationBudget

_MIN_BUDGET = 10


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_response(content: str = "", tool_calls: list | None = None) -> SimpleNamespace:
    """Create a minimal LLM response object."""
    return SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
        reasoning=None,
    )


def _make_tool_call(name: str, args: dict) -> dict:
    """Create a tool call dict in OpenAI format."""
    return {
        "id": f"tc_{name}_1",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(args),
        },
    }


# ── Agent.run() — text-only response ─────────────────────────────────────


class TestAgentTextResponse:
    """Agent returns a plain text response without tool calls."""

    @pytest.mark.asyncio
    async def test_single_turn_text_response(self):
        llm_call = AsyncMock(return_value=_make_response(content="Hello! How can I help?"))
        budget = IterationBudget(max_total=_MIN_BUDGET)

        agent = Agent(
            llm_call=llm_call,
            system_prompt="You are a test assistant.",
            messages=[{"role": "user", "content": "Hi"}],
            tools=[],
            budget=budget,
        )

        result = await agent.run()

        assert result.final_response == "Hello! How can I help?"
        assert result.turn_count == 1
        assert result.interrupted is False
        llm_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_content_exits_immediately(self):
        """LLM returns empty content — exits after 1 turn (final_response='' is not None)."""
        call_count = 0

        async def _llm(messages, tools):
            nonlocal call_count
            call_count += 1
            return _make_response(content="")

        budget = IterationBudget(max_total=_MIN_BUDGET)

        agent = Agent(
            llm_call=_llm,
            system_prompt="Test",
            messages=[{"role": "user", "content": "hello"}],
            tools=[],
            budget=budget,
        )

        result = await agent.run()

        assert call_count == 1
        assert result.final_response == ""


# ── Agent.run() — tool call response ────────────────────────────────────


class TestAgentToolCallResponse:
    """Agent handles tool call responses and executes them."""

    @pytest.mark.asyncio
    async def test_tool_call_executed_sequential(self):
        """LLM returns a tool call → tool is executed → loop continues."""
        tool_call = _make_tool_call("browser_goto", {"url": "https://example.com"})
        events = []

        def _stream_cb(event):
            events.append(event["type"])

        async def _llm_call(messages, tools):
            return _make_response(content="Navigating...", tool_calls=[tool_call])

        budget = IterationBudget(max_total=_MIN_BUDGET)

        agent = Agent(
            llm_call=_llm_call,
            system_prompt="Test",
            messages=[{"role": "user", "content": "go to example.com"}],
            tools=[{"type": "function", "function": {"name": "browser_goto", "parameters": {}}}],
            cdp_helpers=None,
            tools_dir=Path("nonexistent"),
            budget=budget,
            stream_callback=_stream_cb,
        )

        result = await agent.run()

        assert result.turn_count >= 1
        turn_events = [e for e in events if e == "turn_start"]
        assert len(turn_events) >= 1

    @pytest.mark.asyncio
    async def test_budget_exhaustion_stops_loop(self):
        """Agent stops when budget is exhausted."""
        async def _llm_call(messages, tools):
            return _make_response(content="partial", tool_calls=[
                _make_tool_call("browser_goto", {"url": "https://example.com"}),
            ])

        budget = IterationBudget(max_total=_MIN_BUDGET)

        agent = Agent(
            llm_call=_llm_call,
            system_prompt="Test",
            messages=[{"role": "user", "content": "loop forever"}],
            tools=[],
            cdp_helpers=None,
            tools_dir=Path("nonexistent"),
            budget=budget,
        )

        result = await agent.run()

        assert result.turn_count <= _MIN_BUDGET


# ── execute_tool_calls_sequential ───────────────────────────────────────


class TestExecuteToolCalls:
    """execute_tool_calls_sequential routes and executes tool calls."""

    @pytest.mark.asyncio
    async def test_single_tool_call_executed(self):
        messages = []
        tool_calls = [_make_tool_call("browser_goto", {"url": "https://test.com"})]

        await execute_tool_calls_sequential(
            messages=messages,
            tool_calls=tool_calls,
            cdp_helpers=None,
            tools_dir=Path("nonexistent"),
        )

        assert len(messages) == 1
        assert messages[0]["role"] == "tool"
        assert messages[0]["name"] == "browser_goto"

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_executed_in_order(self):
        messages = []
        tool_calls = [
            _make_tool_call("browser_goto", {"url": "https://a.com"}),
            _make_tool_call("browser_click", {"selector": "#btn"}),
        ]

        await execute_tool_calls_sequential(
            messages=messages,
            tool_calls=tool_calls,
            cdp_helpers=None,
            tools_dir=Path("nonexistent"),
        )

        assert len(messages) == 2
        assert messages[0]["name"] == "browser_goto"
        assert messages[1]["name"] == "browser_click"

    @pytest.mark.asyncio
    async def test_empty_tool_calls_list(self):
        messages = []
        await execute_tool_calls_sequential(
            messages=messages,
            tool_calls=[],
        )
        assert len(messages) == 0

    @pytest.mark.asyncio
    async def test_interrupt_stops_remaining_calls(self):
        messages = []
        tool_calls = [
            _make_tool_call("browser_goto", {"url": "https://a.com"}),
            _make_tool_call("browser_click", {"selector": "#btn"}),
        ]

        await execute_tool_calls_sequential(
            messages=messages,
            tool_calls=tool_calls,
            cdp_helpers=None,
            tools_dir=Path("nonexistent"),
            interrupt_check=lambda: True,
        )

        assert len(messages) == 0


# ── LLM retry with error classification ─────────────────────────────────


class TestLLMRetry:
    """_call_llm_with_retry handles transient errors correctly."""

    @pytest.mark.asyncio
    async def test_retryable_error_retries(self):
        from yak_browser_use.engine._harness.conversation_loop import _call_llm_with_retry
        from yak_browser_use.engine._harness.turn_context import TurnContext

        call_count = 0

        async def _flaky_llm(messages, tools):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Network timeout")
            return _make_response(content="Recovered!")

        turn_ctx = TurnContext()
        result = await _call_llm_with_retry(
            llm_call=_flaky_llm,
            messages=[],
            tools=[],
            turn_ctx=turn_ctx,
        )

        assert call_count == 2
        assert result is not None
        assert result.content == "Recovered!"

    @pytest.mark.asyncio
    async def test_non_retryable_error_returns_none(self):
        from yak_browser_use.engine._harness.conversation_loop import _call_llm_with_retry
        from yak_browser_use.engine._harness.turn_context import TurnContext

        async def _auth_error_llm(messages, tools):
            raise PermissionError("Invalid API key — auth failed")

        turn_ctx = TurnContext()
        result = await _call_llm_with_retry(
            llm_call=_auth_error_llm,
            messages=[],
            tools=[],
            turn_ctx=turn_ctx,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_max_retries_exhausted_returns_none(self):
        from yak_browser_use.engine._harness.conversation_loop import _call_llm_with_retry
        from yak_browser_use.engine._harness.turn_context import TurnContext

        async def _always_fail(messages, tools):
            raise ConnectionError("Network unreachable")

        turn_ctx = TurnContext()
        turn_ctx.max_api_retries = 2
        result = await _call_llm_with_retry(
            llm_call=_always_fail,
            messages=[],
            tools=[],
            turn_ctx=turn_ctx,
        )

        assert result is None
