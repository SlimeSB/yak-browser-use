"""Tests for API service — process_chat_message."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yak_browser_use.api.service import Service
from yak_browser_use.api.session_manager import SessionState


@pytest.fixture
def svc():
    """Return a fresh Service with disk-backed operations mocked."""
    s = Service()
    s.sessions.persist_session = MagicMock()
    s.sessions._restore_from_disk = MagicMock(return_value=None)
    return s


@pytest.fixture
def mock_loop_result():
    """Return a factory for mock ConversationResult."""

    def _make(**overrides):
        r = MagicMock()
        r.final_response = overrides.get("final_response", "Hello!")
        r.interrupted = overrides.get("interrupted", False)
        r.messages = overrides.get("messages", [{"role": "user", "content": "hi"}])
        r.budget.to_dict.return_value = overrides.get("budget", {"max_total": 50, "used": 1})
        r.turn_count = overrides.get("turn_count", 1)
        r.duration_ms = overrides.get("duration_ms", 100)
        return r

    return _make


# ── Basic success ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_basic_success(svc, mock_loop_result):
    """process_chat_message returns ok with response."""
    with (
        patch("yak_browser_use.engine._harness.conversation_loop.run_conversation_loop") as mock_loop,
        patch("yak_browser_use.engine._harness.tools.get_all_tools", return_value=[]),
        patch("yak_browser_use.prompts._loader.build_system_prompt", return_value="sys"),
        patch("yak_browser_use.tools.todo_store.current_store") as mock_store,
    ):
        mock_store.set.return_value = "token"
        mock_store.reset = MagicMock()
        mock_loop.return_value = mock_loop_result()

        result = await svc.process_chat_message("hello", cdp_helpers=MagicMock())

    assert result["ok"] is True
    assert result["response"] == "Hello!"
    assert result["status"] == "completed"
    assert result["turn_count"] == 1
    assert result["duration_ms"] == 100


# ── Session reuse ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_session_reuse_messages_accumulate(svc, mock_loop_result):
    """Second message appends to the same session; same messages list passed to loop."""
    with (
        patch("yak_browser_use.engine._harness.conversation_loop.run_conversation_loop") as mock_loop,
        patch("yak_browser_use.engine._harness.tools.get_all_tools", return_value=[]),
        patch("yak_browser_use.prompts._loader.build_system_prompt", return_value="sys"),
        patch("yak_browser_use.tools.todo_store.current_store") as mock_store,
    ):
        mock_store.set.return_value = "token"
        mock_store.reset = MagicMock()
        mock_loop.return_value = mock_loop_result()

        await svc.process_chat_message("first", cdp_helpers=MagicMock())
        await svc.process_chat_message("second", cdp_helpers=MagicMock())

    session = svc.sessions._sessions.get("__chat__")
    assert session is not None
    assert len(session.messages) == 2
    assert session.messages[0] == {"role": "user", "content": "first"}
    assert session.messages[1] == {"role": "user", "content": "second"}

    # Both calls pass the same session.messages list to the loop
    _, kwargs = mock_loop.call_args
    assert kwargs["messages"] is session.messages


# ── Interrupted status ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_interrupted_returns_cancelled(svc, mock_loop_result):
    """When loop is interrupted, status is cancelled."""
    with (
        patch("yak_browser_use.engine._harness.conversation_loop.run_conversation_loop") as mock_loop,
        patch("yak_browser_use.engine._harness.tools.get_all_tools", return_value=[]),
        patch("yak_browser_use.prompts._loader.build_system_prompt", return_value="sys"),
        patch("yak_browser_use.tools.todo_store.current_store") as mock_store,
    ):
        mock_store.set.return_value = "token"
        mock_store.reset = MagicMock()
        mock_loop.return_value = mock_loop_result(interrupted=True)

        result = await svc.process_chat_message("hello", cdp_helpers=MagicMock())

    assert result["ok"] is True
    assert result["status"] == "cancelled"


# ── Error handling ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_error_returns_false(svc):
    """Exception during loop returns ok: False."""
    with (
        patch("yak_browser_use.engine._harness.conversation_loop.run_conversation_loop") as mock_loop,
        patch("yak_browser_use.engine._harness.tools.get_all_tools", return_value=[]),
        patch("yak_browser_use.prompts._loader.build_system_prompt", return_value="sys"),
        patch("yak_browser_use.tools.todo_store.current_store") as mock_store,
    ):
        mock_store.set.return_value = "token"
        mock_store.reset = MagicMock()
        mock_loop.side_effect = RuntimeError("LLM down")

        result = await svc.process_chat_message("hello", cdp_helpers=MagicMock())

    assert result["ok"] is False
    assert "LLM down" in result["error"]


# ── Streaming callback ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_callback_injects_session_id(svc, mock_loop_result):
    """Stream callback appends session_id to events pushed to EventBus."""
    svc.events.push = MagicMock()

    with (
        patch("yak_browser_use.engine._harness.conversation_loop.run_conversation_loop") as mock_loop,
        patch("yak_browser_use.engine._harness.tools.get_all_tools", return_value=[]),
        patch("yak_browser_use.prompts._loader.build_system_prompt", return_value="sys"),
        patch("yak_browser_use.tools.todo_store.current_store") as mock_store,
    ):
        mock_store.set.return_value = "token"
        mock_store.reset = MagicMock()

        def _sim_stream(*, stream_callback, **kwargs):
            stream_callback({"type": "turn_start", "turn": 1})
            stream_callback({"type": "llm_turn", "content": "Hi"})
            return mock_loop_result()

        mock_loop.side_effect = _sim_stream

        await svc.process_chat_message("hello", cdp_helpers=MagicMock())

    assert svc.events.push.call_count >= 2
    session = svc.sessions._sessions.get("__chat__")
    for call in svc.events.push.call_args_list:
        event = call[0][0]
        assert event.get("session_id") == session.session_id


# ── Pipeline context injection ───────────────────────────────────


@pytest.mark.asyncio
async def test_non_default_pipeline_injects_context(svc, mock_loop_result):
    """Non-__chat__ pipeline appends pipeline context to system_prompt."""
    with (
        patch("yak_browser_use.engine._harness.conversation_loop.run_conversation_loop") as mock_loop,
        patch("yak_browser_use.engine._harness.tools.get_all_tools", return_value=[]),
        patch("yak_browser_use.prompts._loader.build_system_prompt", return_value="base sys"),
        patch("yak_browser_use.tools.todo_store.current_store") as mock_store,
        patch("yak_browser_use.api.service._build_pipeline_context") as mock_ctx,
    ):
        mock_store.set.return_value = "token"
        mock_store.reset = MagicMock()
        mock_loop.return_value = mock_loop_result()
        mock_ctx.return_value = "## Pipeline: mypipe\n目标: test"

        await svc.process_chat_message("hello", pipeline_name="mypipe", cdp_helpers=MagicMock())

    _, kwargs = mock_loop.call_args
    assert "base sys" in kwargs["system_prompt"]
    assert "## Pipeline: mypipe" in kwargs["system_prompt"]
    mock_ctx.assert_called_once_with("mypipe")


# ── Default pipeline does not inject context ─────────────────────


@pytest.mark.asyncio
async def test_default_pipeline_no_context(svc, mock_loop_result):
    """Default __chat__ pipeline does NOT inject pipeline context."""
    with (
        patch("yak_browser_use.engine._harness.conversation_loop.run_conversation_loop") as mock_loop,
        patch("yak_browser_use.engine._harness.tools.get_all_tools", return_value=[]),
        patch("yak_browser_use.prompts._loader.build_system_prompt", return_value="base sys"),
        patch("yak_browser_use.tools.todo_store.current_store") as mock_store,
        patch("yak_browser_use.api.service._build_pipeline_context") as mock_ctx,
    ):
        mock_store.set.return_value = "token"
        mock_store.reset = MagicMock()
        mock_loop.return_value = mock_loop_result()

        await svc.process_chat_message("hello", cdp_helpers=MagicMock())

    mock_ctx.assert_not_called()


# ── Session is persisted on turn complete ────────────────────────


@pytest.mark.asyncio
async def test_session_persisted(svc, mock_loop_result):
    """persist_session is called via on_turn_complete callback."""
    with (
        patch("yak_browser_use.engine._harness.conversation_loop.run_conversation_loop") as mock_loop,
        patch("yak_browser_use.engine._harness.tools.get_all_tools", return_value=[]),
        patch("yak_browser_use.prompts._loader.build_system_prompt", return_value="sys"),
        patch("yak_browser_use.tools.todo_store.current_store") as mock_store,
    ):
        mock_store.set.return_value = "token"
        mock_store.reset = MagicMock()

        def _sim(*, on_turn_complete, **kwargs):
            on_turn_complete()
            return mock_loop_result()

        mock_loop.side_effect = _sim

        await svc.process_chat_message("hello", cdp_helpers=MagicMock())

    svc.sessions.persist_session.assert_called()
