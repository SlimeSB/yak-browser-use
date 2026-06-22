"""Tests for engine.runner — chat mode runner and browser lifecycle."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── run_chat_loop ──────────────────────────────────────────────────


class TestRunChatLoop:
    @pytest.mark.asyncio
    async def test_default_messages_list(self):
        """When messages is None, should default to empty list."""
        from engine.runner import run_chat_loop

        mock_llm = MagicMock()

        with (
            patch("engine._harness.conversation_loop.run_conversation_loop") as mock_loop,
            patch("engine._harness.tools.get_all_tools", return_value=[]),
            patch("prompts._loader.build_system_prompt", return_value="sys prompt"),
        ):
            mock_result = MagicMock()
            mock_result.final_response = "Hello!"
            mock_result.interrupted = False
            mock_result.messages = [{"role": "user", "content": "hi"}]
            mock_result.budget.to_dict.return_value = {"max_total": 50, "used": 1}
            mock_result.turn_count = 1
            mock_result.duration_ms = 100
            mock_loop.return_value = mock_result

            result = await run_chat_loop(llm_call=mock_llm, cdp_helpers=MagicMock())

        assert result["response"] == "Hello!"
        assert result["status"] == "completed"
        assert result["turn_count"] == 1
        assert result["duration_ms"] == 100
        assert result["budget"]["max_total"] == 50
        assert len(result["messages"]) == 1

    @pytest.mark.asyncio
    async def test_interrupted_status(self):
        from engine.runner import run_chat_loop

        mock_llm = MagicMock()

        with (
            patch("engine._harness.conversation_loop.run_conversation_loop") as mock_loop,
            patch("engine._harness.tools.get_all_tools", return_value=[]),
            patch("prompts._loader.build_system_prompt", return_value="sys"),
        ):
            mock_result = MagicMock()
            mock_result.interrupted = True
            mock_result.final_response = "Cancelled"
            mock_result.messages = []
            mock_result.budget.to_dict.return_value = {}
            mock_result.turn_count = 2
            mock_result.duration_ms = 500
            mock_loop.return_value = mock_result

            result = await run_chat_loop(llm_call=mock_llm, cdp_helpers=MagicMock())

        assert result["status"] == "cancelled"
        assert result["response"] == "Cancelled"

    @pytest.mark.asyncio
    async def test_custom_system_prompt_passed_through(self):
        from engine.runner import run_chat_loop

        mock_llm = MagicMock()
        custom_prompt = "You are a custom assistant."

        with (
            patch("engine._harness.conversation_loop.run_conversation_loop") as mock_loop,
            patch("engine._harness.tools.get_all_tools", return_value=[]),
        ):
            mock_result = MagicMock()
            mock_result.final_response = "OK"
            mock_result.interrupted = False
            mock_result.messages = []
            mock_result.budget.to_dict.return_value = {}
            mock_result.turn_count = 0
            mock_result.duration_ms = 0
            mock_loop.return_value = mock_result

            await run_chat_loop(
                llm_call=mock_llm,
                cdp_helpers=MagicMock(),
                system_prompt=custom_prompt,
            )

            _, kwargs = mock_loop.call_args
            assert kwargs["system_prompt"] == custom_prompt

    @pytest.mark.asyncio
    async def test_empty_system_prompt_loads_default(self):
        """When system_prompt is empty, should call build_system_prompt()."""
        from engine.runner import run_chat_loop

        mock_llm = MagicMock()

        with (
            patch("engine._harness.conversation_loop.run_conversation_loop") as mock_loop,
            patch("engine._harness.tools.get_all_tools", return_value=[]),
            patch("prompts._loader.build_system_prompt", return_value="default prompt") as mock_build,
        ):
            mock_result = MagicMock()
            mock_result.final_response = "OK"
            mock_result.interrupted = False
            mock_result.messages = []
            mock_result.budget.to_dict.return_value = {}
            mock_result.turn_count = 0
            mock_result.duration_ms = 0
            mock_loop.return_value = mock_result

            await run_chat_loop(llm_call=mock_llm, cdp_helpers=MagicMock())

            mock_build.assert_called_once()

    @pytest.mark.asyncio
    async def test_provided_messages_passed_through(self):
        from engine.runner import run_chat_loop

        mock_llm = MagicMock()
        msgs = [{"role": "system", "content": "be helpful"}]

        with (
            patch("engine._harness.conversation_loop.run_conversation_loop") as mock_loop,
            patch("engine._harness.tools.get_all_tools", return_value=[]),
            patch("prompts._loader.build_system_prompt", return_value="sys"),
        ):
            mock_result = MagicMock()
            mock_result.final_response = "OK"
            mock_result.interrupted = False
            mock_result.messages = msgs
            mock_result.budget.to_dict.return_value = {}
            mock_result.turn_count = 1
            mock_result.duration_ms = 0
            mock_loop.return_value = mock_result

            await run_chat_loop(llm_call=mock_llm, messages=msgs, cdp_helpers=MagicMock())

            _, kwargs = mock_loop.call_args
            assert kwargs["messages"] is msgs


# ---------------------------------------------------------------------------
# _ensure_browser_connected is tested indirectly via run_chat_loop.
# Direct testing requires importing cdp submodules which have heavy
# dependencies (Playwright, browser discovery) — covered by integration tests.
# ---------------------------------------------------------------------------
