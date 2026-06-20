"""API service layer — session/chat/pipeline business logic.

Bridges the API routes to the engine: session management,
chat message processing, pipeline compilation, and event pushing.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from utils.logging import get_logger

from api.errors import APIError
from tools.todo_store import TodoStore

logger = get_logger(__name__)

# Default session directory
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "userdata"
_SESSIONS_DIR = _DATA_DIR / "sessions"
_PRESETS_DIR = _DATA_DIR / "presets"


@dataclass
class SessionState:
    """State for a single chat session."""

    session_id: str
    pipeline_name: str = ""
    status: str = "idle"  # idle, running, paused, completed, cancelled
    created_at: float = field(default_factory=time.time)
    messages: list[dict] = field(default_factory=list)
    error_info: dict | None = None
    budget_snapshot: dict | None = None
    todo_store: TodoStore = field(default_factory=TodoStore)


class Service:
    """Business logic service for the YBU API."""

    def __init__(self, engine_state: object | None = None):
        self._engine_state = engine_state
        self._active_session: SessionState | None = None
        self._event_callbacks: list[Callable[[dict], None]] = []
        self._chat_lock = asyncio.Lock()
        self._chat_streaming = False

    # ── Session management ──────────────────────────────────────────

    def create_session(self, pipeline_name: str = "") -> SessionState:
        """Create a new chat session. Rejects if one is already active."""
        if self._active_session and self._active_session.status == "running":
            raise APIError("当前有任务正在执行，请先结束或取消")
        session_id = f"session_{int(time.time() * 1000)}"
        session = SessionState(session_id=session_id, pipeline_name=pipeline_name)
        self._active_session = session
        logger.info("Session created: %s (pipeline=%s)", session_id, pipeline_name or "chat")
        self._push_event({"type": "session.state", "status": "idle", "session_id": session_id})
        return session

    def get_session(self) -> SessionState | None:
        """Get the current active session."""
        return self._active_session

    def reset_session(self) -> SessionState:
        """Cancel current session, save history, start new."""
        if self._active_session:
            self._save_session_history(self._active_session)
        self._active_session = None
        return self.create_session()

    def cancel_session(self) -> None:
        """Cancel the active session."""
        if self._active_session:
            self._active_session.status = "cancelled"
            self._push_event({
                "type": "session.state",
                "status": "cancelled",
                "session_id": self._active_session.session_id,
            })

    # ── Chat message processing ─────────────────────────────────────

    async def process_chat_message(
        self,
        message: str,
        *,
        cdp_helpers: object | None = None,
        tools_dir: Path | None = None,
        pipeline_name: str = "",
        llm_call: Callable | None = None,
    ) -> dict:
        """Process a chat message through conversation_loop.

        Args:
            message: User's text message.
            cdp_helpers: CDP helpers instance.
            tools_dir: Directory for tool modules.
            pipeline_name: Pipeline name.
            llm_call: Async callable for LLM API calls.

        Returns:
            Result dict with response and status.
        """
        async with self._chat_lock:
            from engine._harness.conversation_loop import run_conversation_loop, ConversationResult
            from engine._harness.tools import get_all_tools
            from prompts._loader import build_system_prompt
            from tools.todo_store import current_store

            if self._active_session is None:
                self.create_session(pipeline_name)

            session = self._active_session
            if session is None:
                return {"ok": False, "error": "No active session"}
            logger.info("Session created: %s", session.session_id)

            logger.info("Chat [%s] user: %s", session.session_id, message[:120])

            session.status = "running"
            self._push_event({
                "type": "session.state",
                "status": "running",
                "session_id": session.session_id,
            })

            session.messages.append({"role": "user", "content": message})

            system_prompt = build_system_prompt()

            def _stream_cb(event: dict) -> None:
                event["session_id"] = session.session_id
                self._push_event(event)

            def _interrupt_check() -> bool:
                return session.status in ("cancelled",)

            _todo_token = current_store.set(session.todo_store)
            self._chat_streaming = True
            try:
                result: ConversationResult = await run_conversation_loop(
                    llm_call=llm_call,
                    system_prompt=system_prompt,
                    messages=session.messages,
                    tools=get_all_tools(),
                    cdp_helpers=cdp_helpers,
                    tools_dir=tools_dir,
                    pipeline_name=pipeline_name,
                    interrupt_check=_interrupt_check,
                    stream_callback=_stream_cb,
                )

                session.status = "completed" if not result.interrupted else "cancelled"
                session.budget_snapshot = result.budget.to_dict()

                resp_preview = (result.final_response or "")[:120]
                logger.info("Chat [%s] done: status=%s turns=%d duration=%dms response: %s",
                            session.session_id, session.status,
                            result.turn_count, result.duration_ms, resp_preview)

                return {
                    "ok": True,
                    "response": result.final_response,
                    "status": session.status,
                    "turn_count": result.turn_count,
                    "duration_ms": result.duration_ms,
                }

            except Exception as e:
                logger.error("Chat processing error: %s", e)
                session.status = "cancelled"
                session.error_info = {"message": str(e)}
                return {"ok": False, "error": str(e)}

            finally:
                self._chat_streaming = False
                self._push_event({
                    "type": "session.state",
                    "status": session.status,
                    "session_id": session.session_id,
                })
                current_store.reset(_todo_token)

    # ── Pipeline management ─────────────────────────────────────────

    def compile_pipeline(self, pipeline_text: str) -> dict:
        """Compile pipeline.yaml text into step definitions."""
        try:
            from compiler.parser import parse_pipeline
            from compiler.resolver import resolve
            parsed = parse_pipeline(pipeline_text)
            return resolve(parsed)
        except Exception as e:
            raise APIError(f"Failed to compile pipeline.yaml: {e}")

    def list_presets(self) -> list[dict]:
        """List saved preset pipelines."""
        presets_dir = _PRESETS_DIR
        if not presets_dir.exists():
            return []
        presets: list[dict] = []
        for f in sorted(presets_dir.glob("*.pipeline.yaml"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                name = f.stem.replace(".pipeline", "")
                presets.append({
                    "name": name,
                    "path": str(f),
                    "modified": f.stat().st_mtime,
                })
            except Exception:
                logger.warning("Failed to stat preset file for %s", f, exc_info=True)
        return presets

    # ── Events ──────────────────────────────────────────────────────

    def on_event(self, callback: Callable[[dict], None]) -> None:
        """Register a callback for event streaming."""
        self._event_callbacks.append(callback)

    def _push_event(self, event: dict) -> None:
        """Push an event to all registered callbacks AND engine_state WS clients."""
        if event.get("type") == "chat.message" and self._chat_streaming:
            return
        event["_ts"] = time.time()
        for cb in self._event_callbacks:
            try:
                cb(event)
            except Exception:
                logger.warning("Event callback failed for type=%s", event.get("type"), exc_info=True)
        if self._engine_state and hasattr(self._engine_state, "ws_clients"):
            for q in self._engine_state.ws_clients:
                try:
                    q.put_nowait(event)
                except Exception:  # expected: queue full
                    pass

    # ── Internal helpers ────────────────────────────────────────────

    def _save_session_history(self, session: SessionState) -> None:
        """Persist session history to disk."""
        try:
            _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
            path = _SESSIONS_DIR / f"{session.session_id}.json"
            data = {
                "session_id": session.session_id,
                "pipeline_name": session.pipeline_name,
                "status": session.status,
                "created_at": session.created_at,
                "messages": session.messages,
                "budget_snapshot": session.budget_snapshot,
            }
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to save session history: %s", e)

    def _push_auto_record_review(self, pipeline_name: str, pipeline_text: str, session_id: str) -> None:
        """Push auto-recorded pipeline for review, same flow as edit_pipeline."""
        import difflib
        import os
        import time

        presets_dir = _PRESETS_DIR
        preset_path = presets_dir / f"{pipeline_name}.pipeline.yaml"

        edit_id = f"auto_{session_id}"
        original = preset_path.read_text(encoding="utf-8") if preset_path.exists() else ""

        if original.strip() == pipeline_text.strip():
            return

        # Save checkpoint
        checkpoint_path = presets_dir / f"{pipeline_name}.pipeline.yaml.{edit_id}.orig"
        presets_dir.mkdir(parents=True, exist_ok=True)
        if preset_path.exists():
            checkpoint_path.write_text(original, encoding="utf-8")
        else:
            checkpoint_path.write_text("", encoding="utf-8")

        # Write new content
        preset_path.write_text(pipeline_text, encoding="utf-8")

        # Compute diff
        diff_lines = list(difflib.unified_diff(
            original.splitlines(keepends=True),
            pipeline_text.splitlines(keepends=True),
            fromfile="original", tofile="modified", lineterm="",
        ))

        event = {
            "type": "pipeline.edit",
            "edit_id": edit_id,
            "original": original,
            "modified": pipeline_text,
            "diff_lines": [l for l in diff_lines if not l.startswith("---") and not l.startswith("+++")],
            "explanation": f"Auto-recorded from session {session_id}",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        if self._engine_state and hasattr(self._engine_state, "ws_clients"):
            for q in self._engine_state.ws_clients:
                try:
                    q.put_nowait(event)
                except Exception:  # expected: no ws client
                    pass

        # Register edit for confirm/revert
        from tools.edit_pipeline import register_edit
        register_edit(edit_id, checkpoint_path, pipeline_name, status="pending")
