"""Tests for Agent (conversation_loop) — pure unit tests with mock LLM and mock bridge."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yak_browser_use.engine._harness.conversation_loop import Agent, ConversationResult
from yak_browser_use.engine._harness.iteration_budget import IterationBudget
from yak_browser_use.engine._harness.tool_executor import UnrecoverableError


# ── Helpers ──────────────────────────────────────────────────────


def _make_llm_response(*, content: str | None = None, tool_calls: list | None = None):
    """Build a minimal LLM response object."""
    resp = MagicMock()
    resp.content = content
    resp.reasoning = None
    resp.thinking = None
    if tool_calls is not None:
        resp.tool_calls = tool_calls
    else:
        resp.tool_calls = []
        del resp.tool_calls  # hasattr returns False
    return resp


def _make_tool_call(name: str, args: dict, tc_id: str = "tc_1") -> dict:
    return {
        "id": tc_id,
        "function": {"name": name, "arguments": args},
    }


# ── Layer 1: Agent.run() — text response ─────────────────────────


class TestAgentTextResponse:
    """Agent stops when LLM returns plain text (no tool_calls)."""

    @pytest.mark.asyncio
    async def test_single_turn_text_response(self):
        llm = AsyncMock(return_value=_make_llm_response(content="Hello!"))
        agent = Agent(
            llm_call=llm,
            system_prompt="You are a helper.",
            messages=[{"role": "user", "content": "Hi"}],
            tools=[],
        )
        result = await agent.run()

        assert result.final_response == "Hello!"
        assert result.interrupted is False
        assert result.turn_count == 1

    @pytest.mark.asyncio
    async def test_empty_fallback_to_last_content_with_tools(self):
        """When final text is empty, fall back to last_content_with_tools."""
        first_resp = _make_llm_response(content="Let me check...")
        first_resp.tool_calls = [_make_tool_call("browser_goto", {"url": "https://x.com"})]
        # remove the del from helper
        second_resp = MagicMock()
        second_resp.content = ""
        second_resp.reasoning = None
        second_resp.thinking = None
        second_resp.tool_calls = []

        llm = AsyncMock(side_effect=[first_resp, second_resp])
        agent = Agent(
            llm_call=llm,
            system_prompt="sys",
            messages=[{"role": "user", "content": "go"}],
            tools=[],
        )
        result = await agent.run()

        assert result.final_response == "Let me check..."

    @pytest.mark.asyncio
    async def test_none_tool_calls_attribute(self):
        """LLM response with no tool_calls attribute at all."""
        resp = MagicMock(spec=["content"])
        resp.content = "Done"
        llm = AsyncMock(return_value=resp)

        agent = Agent(
            llm_call=llm,
            system_prompt="sys",
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
        )
        result = await agent.run()
        assert result.final_response == "Done"


# ── Layer 1: Agent.run() — tool calls → loop continues ───────────


class TestAgentWithToolCalls:
    """Agent loops when LLM returns tool_calls, stops when text follows."""

    @pytest.mark.asyncio
    async def test_tool_then_text(self):
        """First turn: tool call, second turn: text → stop."""
        tool_resp = _make_llm_response(content="Navigating...")
        tool_resp.tool_calls = [_make_tool_call("browser_goto", {"url": "https://x.com"})]

        text_resp = _make_llm_response(content="Done!")

        llm = AsyncMock(side_effect=[tool_resp, text_resp])

        tool_exec = AsyncMock()

        agent = Agent(
            llm_call=llm,
            system_prompt="sys",
            messages=[{"role": "user", "content": "go to x.com"}],
            tools=[],
        )
        with patch(
            "yak_browser_use.engine._harness.conversation_loop.execute_tool_calls_sequential",
            tool_exec,
        ):
            result = await agent.run()

        assert result.final_response == "Done!"
        assert result.turn_count == 2
        assert tool_exec.call_count == 1

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_in_one_turn(self):
        """Multiple tool_calls in a single turn all get executed."""
        tool_resp = _make_llm_response()
        tool_resp.tool_calls = [
            _make_tool_call("browser_goto", {"url": "https://x.com"}, tc_id="tc_1"),
            _make_tool_call("browser_fill", {"selector": "#q", "text": "test"}, tc_id="tc_2"),
        ]
        text_resp = _make_llm_response(content="Done")

        llm = AsyncMock(side_effect=[tool_resp, text_resp])
        tool_exec = AsyncMock()

        agent = Agent(
            llm_call=llm,
            system_prompt="sys",
            messages=[{"role": "user", "content": "search"}],
            tools=[],
        )
        with patch(
            "yak_browser_use.engine._harness.conversation_loop.execute_tool_calls_sequential",
            tool_exec,
        ):
            await agent.run()

        # tool_exec called once with all tool_calls
        assert tool_exec.call_count == 1
        passed_tool_calls = tool_exec.call_args.kwargs.get("tool_calls") or tool_exec.call_args[0][1]
        assert len(passed_tool_calls) == 2


# ── Layer 1: preset_mode ─────────────────────────────────────────


class TestPresetMode:
    """preset_mode skips guardrail creation and config."""

    @pytest.mark.asyncio
    async def test_preset_mode_skips_guardrail_config(self):
        llm = AsyncMock(return_value=_make_llm_response(content="ok"))
        with patch(
            "yak_browser_use.engine._harness.conversation_loop.create_chat_guardrail_config",
        ) as mock_cfg:
            agent = Agent(
                llm_call=llm,
                system_prompt="sys",
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
                preset_mode=True,
            )
            await agent.run()
            mock_cfg.assert_not_called()

    @pytest.mark.asyncio
    async def test_chat_mode_creates_guardrail_config(self):
        llm = AsyncMock(return_value=_make_llm_response(content="ok"))
        with patch(
            "yak_browser_use.engine._harness.conversation_loop.create_chat_guardrail_config",
        ) as mock_cfg:
            agent = Agent(
                llm_call=llm,
                system_prompt="sys",
                messages=[{"role": "user", "content": "hi"}],
                tools=[],
            )
            await agent.run()
            mock_cfg.assert_called_once()

    @pytest.mark.asyncio
    async def test_preset_mode_no_last_content_with_tools(self):
        """In preset_mode, last_content_with_tools is NOT saved."""
        tool_resp = _make_llm_response(content="Processing...")
        tool_resp.tool_calls = [_make_tool_call("browser_goto", {"url": "https://x.com"})]
        text_resp = MagicMock(spec=["content"])
        text_resp.content = ""
        text_resp.reasoning = None
        text_resp.thinking = None

        llm = AsyncMock(side_effect=[tool_resp, text_resp])

        agent = Agent(
            llm_call=llm,
            system_prompt="sys",
            messages=[{"role": "user", "content": "go"}],
            tools=[],
            preset_mode=True,
        )
        with patch(
            "yak_browser_use.engine._harness.conversation_loop.execute_tool_calls_sequential",
            AsyncMock(),
        ):
            result = await agent.run()

        # In preset mode, empty final with no fallback content → empty string
        assert result.final_response == ""


# ── Layer 1: exit conditions ─────────────────────────────────────


class TestExitConditions:
    """_check_exit triggers on various conditions."""

    @pytest.mark.asyncio
    async def test_budget_exhausted(self):
        """Agent stops after max_total turns with tool calls."""
        tool_resp = _make_llm_response()
        tool_resp.tool_calls = [_make_tool_call("browser_goto", {"url": "https://x.com"})]

        llm = AsyncMock(return_value=tool_resp)
        budget = IterationBudget(max_total=12)

        agent = Agent(
            llm_call=llm,
            system_prompt="sys",
            messages=[{"role": "user", "content": "loop"}],
            tools=[],
            budget=budget,
        )
        with patch(
            "yak_browser_use.engine._harness.conversation_loop.execute_tool_calls_sequential",
            AsyncMock(),
        ):
            result = await agent.run()

        assert result.turn_count == 12
        assert result.budget.is_exhausted is True
        assert result.final_response is None

    @pytest.mark.asyncio
    async def test_interrupt_check(self):
        """interrupt_check returns True → immediate stop."""
        llm = AsyncMock(return_value=_make_llm_response(content="should not be called"))

        interrupt = MagicMock(return_value=True)

        agent = Agent(
            llm_call=llm,
            system_prompt="sys",
            messages=[{"role": "user", "content": "stop"}],
            tools=[],
            interrupt_check=interrupt,
        )
        result = await agent.run()

        assert result.interrupted is True
        llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_unrecoverable_error_stops(self):
        """UnrecoverableError during tool execution stops the loop."""
        tool_resp = _make_llm_response()
        tool_resp.tool_calls = [_make_tool_call("browser_goto", {"url": "https://x.com"})]

        llm = AsyncMock(return_value=tool_resp)

        tool_exec = AsyncMock(side_effect=UnrecoverableError("fatal"))

        agent = Agent(
            llm_call=llm,
            system_prompt="sys",
            messages=[{"role": "user", "content": "go"}],
            tools=[],
        )
        with patch(
            "yak_browser_use.engine._harness.conversation_loop.execute_tool_calls_sequential",
            tool_exec,
        ):
            result = await agent.run()

        assert result.interrupted is True
        assert result.turn_count == 1


# ── Layer 1: LLM failure handling ────────────────────────────────


class TestLLMFailureHandling:
    """Consecutive LLM failures and retries."""

    @pytest.mark.asyncio
    async def test_consecutive_llm_failures_stop(self):
        """After _MAX_CONSECUTIVE_LLM_FAILURES failures, agent stops."""
        llm = AsyncMock(side_effect=ConnectionError("API down"))

        agent = Agent(
            llm_call=llm,
            system_prompt="sys",
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            budget=IterationBudget(max_total=20),
        )
        result = await agent.run()

        assert result.interrupted is True
        # 5 consecutive failures × 3 retries each = 15 total LLM calls
        assert llm.call_count == 15

    @pytest.mark.asyncio
    async def test_transient_failure_recovers(self):
        """Agent continues after a single transient failure if later calls succeed."""
        fail_resp = ConnectionError("timeout")
        ok_resp = _make_llm_response(content="ok")

        llm = AsyncMock(side_effect=[fail_resp, ok_resp])

        agent = Agent(
            llm_call=llm,
            system_prompt="sys",
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
        )
        result = await agent.run()

        assert result.final_response == "ok"
        assert result.turn_count == 1
        assert llm.call_count == 2


# ── Layer 1: stream_callback ────────────────────────────────────


class TestStreamCallback:
    """Event stream emits correct events."""

    @pytest.mark.asyncio
    async def test_events_emitted_in_order(self):
        tool_resp = _make_llm_response(content="thinking...")
        tool_resp.tool_calls = [_make_tool_call("browser_goto", {"url": "https://x.com"})]
        text_resp = _make_llm_response(content="Done!")

        llm = AsyncMock(side_effect=[tool_resp, text_resp])
        events = []

        agent = Agent(
            llm_call=llm,
            system_prompt="sys",
            messages=[{"role": "user", "content": "go"}],
            tools=[],
            stream_callback=events.append,
        )
        with patch(
            "yak_browser_use.engine._harness.conversation_loop.execute_tool_calls_sequential",
            AsyncMock(),
        ):
            await agent.run()

        turn_starts = [e for e in events if e["type"] == "turn_start"]
        llm_turns = [e for e in events if e["type"] == "llm_turn"]
        assert len(turn_starts) == 2
        assert len(llm_turns) == 2
        assert turn_starts[0]["turn"] == 1
        assert turn_starts[1]["turn"] == 2


# ── Layer 1: LLM retry with backoff (via _call_llm_with_retry) ──


class TestLLMRetry:
    """LLM retry logic for non-fatal errors."""

    @pytest.mark.asyncio
    async def test_non_retryable_error_returns_none(self):
        """Non-retryable API error → _call_llm_with_retry returns None."""
        from yak_browser_use.engine._harness.conversation_loop import _call_llm_with_retry

        # AuthenticationError maps to AUTH_ERROR, retryable=False
        class AuthenticationError(Exception):
            pass

        llm = AsyncMock(side_effect=AuthenticationError("invalid API key"))
        from yak_browser_use.engine._harness.turn_context import TurnContext

        turn_ctx = TurnContext()

        result = await _call_llm_with_retry(llm, [], [], turn_ctx)

        assert result is None
        # Non-retryable → called once
        assert llm.call_count == 1


# ── Layer 2: execute_tool_calls_sequential ────────────────────────


class TestExecuteToolCallsSequential:
    """Sequential tool call execution with mock registry."""

    @pytest.mark.asyncio
    async def test_single_tool_call_appends_result(self):
        """A single tool call result is appended to messages."""
        from yak_browser_use.engine._harness.tool_executor import execute_tool_calls_sequential

        messages = []
        tool_calls = [{"id": "tc_1", "function": {"name": "browser_goto", "arguments": '{"url": "https://x.com"}'}}]

        mock_registry = AsyncMock()
        mock_registry.dispatch = AsyncMock(return_value={"ok": True, "result": "navigated"})

        with patch("yak_browser_use.tools.registry.registry", mock_registry):
            await execute_tool_calls_sequential(
                messages=messages,
                tool_calls=tool_calls,
            )

        assert len(messages) == 1
        assert messages[0]["role"] == "tool"
        assert messages[0]["tool_call_id"] == "tc_1"
        assert messages[0]["ok"] is True

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_sequential_order(self):
        """Multiple tool calls execute in order."""
        from yak_browser_use.engine._harness.tool_executor import execute_tool_calls_sequential

        messages = []
        tool_calls = [
            {"id": "tc_1", "function": {"name": "browser_goto", "arguments": '{"url": "https://x.com"}'}},
            {"id": "tc_2", "function": {"name": "browser_fill", "arguments": '{"selector": "#q", "text": "hi"}'}},
        ]

        call_order = []

        async def mock_dispatch(name, args, ctx):
            call_order.append(name)
            return {"ok": True, "result": f"done_{name}"}

        mock_registry = MagicMock()
        mock_registry.dispatch = mock_dispatch

        with patch("yak_browser_use.tools.registry.registry", mock_registry):
            await execute_tool_calls_sequential(
                messages=messages,
                tool_calls=tool_calls,
            )

        assert call_order == ["browser_goto", "browser_fill"]
        assert len(messages) == 2
        assert messages[0]["tool_call_id"] == "tc_1"
        assert messages[1]["tool_call_id"] == "tc_2"

    @pytest.mark.asyncio
    async def test_failed_tool_appends_error(self):
        """Failed tool call gets ok=False in messages."""
        from yak_browser_use.engine._harness.tool_executor import execute_tool_calls_sequential

        messages = []
        tool_calls = [{"id": "tc_1", "function": {"name": "browser_goto", "arguments": '{"url": "bad"}'}}]

        mock_registry = AsyncMock()
        mock_registry.dispatch = AsyncMock(return_value={"ok": False, "error": "invalid URL"})

        with patch("yak_browser_use.tools.registry.registry", mock_registry):
            await execute_tool_calls_sequential(
                messages=messages,
                tool_calls=tool_calls,
            )

        assert len(messages) == 1
        assert messages[0]["ok"] is False
        assert "Error" in messages[0]["content"]

    @pytest.mark.asyncio
    async def test_interrupt_stops_remaining_calls(self):
        """Interrupt check stops execution of remaining tool calls."""
        from yak_browser_use.engine._harness.tool_executor import execute_tool_calls_sequential

        messages = []
        tool_calls = [
            {"id": "tc_1", "function": {"name": "browser_goto", "arguments": "{}"}},
            {"id": "tc_2", "function": {"name": "browser_fill", "arguments": "{}"}},
        ]

        call_count = 0

        async def mock_dispatch(name, args, ctx):
            nonlocal call_count
            call_count += 1
            return {"ok": True, "result": "ok"}

        mock_registry = MagicMock()
        mock_registry.dispatch = mock_dispatch

        # Return False first, then True → interrupt after first call
        interrupt_checks = [False, True]
        interrupt_mock = MagicMock(side_effect=interrupt_checks)

        with patch("yak_browser_use.tools.registry.registry", mock_registry):
            await execute_tool_calls_sequential(
                messages=messages,
                tool_calls=tool_calls,
                interrupt_check=interrupt_mock,
            )

        assert call_count == 1
        assert len(messages) == 1

    @pytest.mark.asyncio
    async def test_unrecoverable_error_propagates(self):
        """UnrecoverableError is re-raised."""
        from yak_browser_use.engine._harness.tool_executor import (
            execute_tool_calls_sequential,
            UnrecoverableError,
        )

        messages = []
        tool_calls = [{"id": "tc_1", "function": {"name": "browser_goto", "arguments": "{}"}}]

        async def mock_dispatch(name, args, ctx):
            raise UnrecoverableError("chrome crashed")

        mock_registry = MagicMock()
        mock_registry.dispatch = mock_dispatch

        with patch("yak_browser_use.tools.registry.registry", mock_registry):
            with pytest.raises(UnrecoverableError, match="chrome crashed"):
                await execute_tool_calls_sequential(
                    messages=messages,
                    tool_calls=tool_calls,
                )

    @pytest.mark.asyncio
    async def test_generic_exception_becomes_error_result(self):
        """Non-unrecoverable exception → error result in messages, not propagated."""
        from yak_browser_use.engine._harness.tool_executor import execute_tool_calls_sequential

        messages = []
        tool_calls = [{"id": "tc_1", "function": {"name": "browser_goto", "arguments": "{}"}}]

        async def mock_dispatch(name, args, ctx):
            raise RuntimeError("something went wrong")

        mock_registry = MagicMock()
        mock_registry.dispatch = mock_dispatch

        with patch("yak_browser_use.tools.registry.registry", mock_registry):
            await execute_tool_calls_sequential(
                messages=messages,
                tool_calls=tool_calls,
            )

        assert len(messages) == 1
        assert messages[0]["ok"] is False
        assert "something went wrong" in messages[0]["content"]

    @pytest.mark.asyncio
    async def test_stream_callback_emits_tool_start_end(self):
        """Stream callback receives tool_start and tool_end events."""
        from yak_browser_use.engine._harness.tool_executor import execute_tool_calls_sequential

        messages = []
        tool_calls = [{"id": "tc_1", "function": {"name": "browser_goto", "arguments": '{"url": "x.com"}'}}]
        events = []

        mock_registry = AsyncMock()
        mock_registry.dispatch = AsyncMock(return_value={"ok": True, "result": "ok", "duration_ms": 5})

        with patch("yak_browser_use.tools.registry.registry", mock_registry):
            await execute_tool_calls_sequential(
                messages=messages,
                tool_calls=tool_calls,
                stream_callback=events.append,
            )

        tool_starts = [e for e in events if e["type"] == "chat.tool_start"]
        tool_ends = [e for e in events if e["type"] == "chat.tool_end"]
        assert len(tool_starts) == 1
        assert len(tool_ends) == 1
        assert tool_starts[0]["tool_name"] == "browser_goto"
        assert tool_ends[0]["ok"] is True

    @pytest.mark.asyncio
    async def test_heavy_data_filter_on_snapshot(self):
        """browser_snapshot results go through _apply_heavy_data_filter."""
        from yak_browser_use.engine._harness.tool_executor import execute_tool_calls_sequential

        messages = []
        tool_calls = [{"id": "tc_1", "function": {"name": "browser_snapshot", "arguments": '{"mode": "progressive"}'}}]

        # Full snapshot result that should be filtered
        raw_result = {
            "ok": True,
            "result": {
                "elements": [{"ref": "@e1", "role": "button", "name": "Submit"}],
                "url": "https://x.com",
                "title": "X",
            },
            "duration_ms": 10,
        }

        mock_registry = AsyncMock()
        mock_registry.dispatch = AsyncMock(return_value=raw_result)

        with patch("yak_browser_use.tools.registry.registry", mock_registry):
            await execute_tool_calls_sequential(
                messages=messages,
                tool_calls=tool_calls,
            )

        assert len(messages) == 1
        assert messages[0]["ok"] is True
        # Content is a formatted result string (the filter transforms dict to summary)
        content = messages[0]["content"]
        assert isinstance(content, str)

    @pytest.mark.asyncio
    async def test_guardrail_blocks_tool_call(self):
        """Guardrail before_call returning non-True blocks execution."""
        from yak_browser_use.engine._harness.tool_executor import execute_tool_calls_sequential
        from yak_browser_use.engine._harness.tool_guardrails import ToolCallGuardrailState

        messages = []
        tool_calls = [{"id": "tc_1", "function": {"name": "browser_goto", "arguments": "{}"}}]

        guardrail = ToolCallGuardrailState()
        guardrail.config = MagicMock()
        # before_call returns a string → blocked
        guardrail.before_call = MagicMock(return_value="tool not allowed in this context")

        mock_registry = AsyncMock()

        with patch("yak_browser_use.tools.registry.registry", mock_registry):
            with patch(
                "yak_browser_use.engine._harness.tool_executor.load_prompt",
                return_value="[Blocked]",
            ):
                await execute_tool_calls_sequential(
                    messages=messages,
                    tool_calls=tool_calls,
                    guardrail_state=guardrail,
                )

        # Registry dispatch NOT called → blocked
        mock_registry.dispatch.assert_not_called()
        assert len(messages) == 1
        assert messages[0]["ok"] is False
        assert "Blocked" in messages[0]["content"]

    @pytest.mark.asyncio
    async def test_pipeline_finish_stops_loop(self):
        """_pipeline_flag in result stops further tool execution."""
        from yak_browser_use.engine._harness.tool_executor import execute_tool_calls_sequential

        messages = []
        tool_calls = [
            {"id": "tc_1", "function": {"name": "browser_goto", "arguments": "{}"}},
            {"id": "tc_2", "function": {"name": "browser_fill", "arguments": "{}"}},
        ]

        call_count = 0

        async def mock_dispatch(name, args, ctx):
            nonlocal call_count
            call_count += 1
            # First call signals pipeline finish
            if call_count == 1:
                return {"ok": True, "_pipeline_finish": True, "status": "completed", "summary": "done"}
            return {"ok": True, "result": "ok"}

        mock_registry = MagicMock()
        mock_registry.dispatch = mock_dispatch

        with patch("yak_browser_use.tools.registry.registry", mock_registry):
            await execute_tool_calls_sequential(
                messages=messages,
                tool_calls=tool_calls,
            )

        assert call_count == 1
        assert len(messages) == 1
