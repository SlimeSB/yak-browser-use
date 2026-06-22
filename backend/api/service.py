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
from workspace.manager import WORKSPACES_ROOT
from workspace.session_store import SessionStore, read_last_active, write_last_active

logger = get_logger(__name__)

_WORKSPACES_DIR = WORKSPACES_ROOT

_DEFAULT_PIPELINE = "__chat__"


def _build_pipeline_context(pipeline_name: str) -> str | None:
    """Build a markdown snippet describing the currently selected pipeline.

    Injects pipeline name, goal, and step names so the agent knows
    which YAML the user is viewing and can operate on it by default.
    """
    import yaml

    pipe_path = _WORKSPACES_DIR / pipeline_name / "pipeline.yaml"
    if not pipe_path.exists():
        logger.info("Pipeline %s not found for context injection", pipeline_name)
        return None

    try:
        content = pipe_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
        if not isinstance(data, dict):
            return None

        name = data.get("name", pipeline_name)
        goal = data.get("goal", data.get("description", ""))
        steps = data.get("steps", [])

        lines = [f"## 当前选中的 Pipeline: {name}"]
        if goal:
            lines.append(f"目标: {goal}")
        if steps:
            lines.append("")
            lines.append("### 步骤列表")
            for i, step in enumerate(steps):
                step_name = step.get("name") if isinstance(step, dict) else str(step)
                lines.append(f"- {step_name or f'step_{i}'}")
        lines.append("")
        lines.append("你可以使用 pipeline_* 工具对此 pipeline 进行操作。")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("Failed to load pipeline %s context: %s", pipeline_name, exc)
        return None


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
        self._sessions: dict[str, SessionState] = {}
        self._active_pipeline: str = _DEFAULT_PIPELINE
        self._event_callbacks: list[Callable[[dict], None]] = []
        self._chat_lock = asyncio.Lock()
        self._chat_streaming = False

    # ── Session management ──────────────────────────────────────────

    def _normalize_pipeline(self, name: str) -> str:
        return _DEFAULT_PIPELINE if not name or name == "chat" else name

    def create_session(self, pipeline_name: str = "") -> SessionState:
        """Create a new chat session for a pipeline. Rejects if one is running."""
        normalized = self._normalize_pipeline(pipeline_name)
        existing = self._sessions.get(normalized)
        if existing and existing.status == "running":
            raise APIError("当前有任务正在执行，请先结束或取消")
        session_id = f"session_{int(time.time() * 1000)}"
        session = SessionState(session_id=session_id, pipeline_name=normalized)
        self._sessions[normalized] = session
        self._active_pipeline = normalized
        logger.info("Session created: %s (pipeline=%s)", session_id, normalized)
        self._push_event({"type": "session.state", "status": "idle", "session_id": session_id})
        return session

    def get_session(self, pipeline_name: str | None = None) -> SessionState | None:
        """Get the active session for a pipeline.

        If pipeline_name is None, uses the current active pipeline.
        """
        name = self._normalize_pipeline(pipeline_name) if pipeline_name is not None else self._active_pipeline
        return self._sessions.get(name)

    def reset_session(self) -> SessionState:
        """Cancel current session, save history, start new."""
        current = self._sessions.get(self._active_pipeline)
        if current:
            self._save_session_history(current)
        return self.create_session(self._active_pipeline)

    def cancel_session(self) -> None:
        """Cancel the active session."""
        session = self._sessions.get(self._active_pipeline)
        if session:
            session.status = "cancelled"
            self._push_event({
                "type": "session.state",
                "status": "cancelled",
                "session_id": session.session_id,
            })

    def switch_session(self, pipeline_name: str) -> list[dict]:
        """Switch active pipeline: save current session, load target workspace.

        Returns the target workspace's session list.
        """
        target = self._normalize_pipeline(pipeline_name)

        # Save current session if dirty
        current = self._sessions.get(self._active_pipeline)
        if current:
            self._save_session_history(current)

        self._active_pipeline = target
        write_last_active(target)

        # Load sessions from workspace
        store = SessionStore(target)
        store.ensure_session_dir()
        sessions = store.list_sessions()

        logger.info("Switched to pipeline %s (%d sessions)", target, len(sessions))
        return sessions

    def new_session(self, pipeline_name: str) -> dict:
        """Create a new persisted session for the given pipeline."""
        normalized = self._normalize_pipeline(pipeline_name)
        store = SessionStore(normalized)
        store.ensure_session_dir()
        session_id = store.new_session()

        # Create in-memory state
        session = SessionState(session_id=session_id, pipeline_name=normalized)
        self._sessions[normalized] = session
        self._active_pipeline = normalized

        logger.info("new_session: %s for pipeline %s", session_id, normalized)
        return {
            "session_id": session_id,
            "created_at": session.created_at,
            "pipeline_name": normalized,
        }

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

            normalized = self._normalize_pipeline(pipeline_name)
            self._active_pipeline = normalized

            session = self._sessions.get(normalized)
            if session is None:
                session = SessionState(
                    session_id=f"session_{int(time.time() * 1000)}",
                    pipeline_name=normalized,
                )
                self._sessions[normalized] = session

            logger.info("Chat [%s] user: %s", session.session_id, message[:120])

            session.status = "running"
            self._push_event({
                "type": "session.state",
                "status": "running",
                "session_id": session.session_id,
            })

            session.messages.append({"role": "user", "content": message})

            system_prompt = build_system_prompt()

            if normalized != _DEFAULT_PIPELINE:
                pipeline_ctx = _build_pipeline_context(normalized)
                if pipeline_ctx:
                    system_prompt += "\n\n" + pipeline_ctx

            def _stream_cb(event: dict) -> None:
                event["session_id"] = session.session_id
                self._push_event(event)

            def _interrupt_check() -> bool:
                return session.status in ("cancelled",)

            _todo_token = current_store.set(session.todo_store)
            self._chat_streaming = True

            def _on_turn_complete() -> None:
                self._async_save_session(session)

            try:
                result: ConversationResult = await run_conversation_loop(
                    llm_call=llm_call,
                    system_prompt=system_prompt,
                    messages=session.messages,
                    tools=get_all_tools(),
                    cdp_helpers=cdp_helpers,
                    tools_dir=tools_dir,
                    pipeline_name=normalized,
                    interrupt_check=_interrupt_check,
                    stream_callback=_stream_cb,
                    on_turn_complete=_on_turn_complete,
                )

                session.status = "completed" if not result.interrupted else "cancelled"
                session.budget_snapshot = result.budget.to_dict()

                # Final save after conversation completes
                self._async_save_session(session)

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
        """List saved pipelines from workspaces/."""
        if not _WORKSPACES_DIR.exists():
            return []
        presets: list[dict] = []
        for d in sorted(_WORKSPACES_DIR.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            pipe_path = d / "pipeline.yaml"
            if not pipe_path.exists():
                continue
            try:
                presets.append({
                    "name": d.name,
                    "path": str(pipe_path),
                    "modified": pipe_path.stat().st_mtime,
                })
            except Exception:
                logger.warning("Failed to stat pipeline in %s", d, exc_info=True)
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
        """Persist session history to workspace session dir."""
        try:
            store = SessionStore(session.pipeline_name)
            store.ensure_session_dir()
            data = {
                "session_id": session.session_id,
                "pipeline_name": session.pipeline_name,
                "status": session.status,
                "created_at": session.created_at,
                "messages": session.messages,
                "budget_snapshot": session.budget_snapshot,
            }
            store.save_session(session.session_id, data)
        except Exception as e:
            logger.warning("Failed to save session history: %s", e)

    def _async_save_session(self, session: SessionState) -> None:
        """Save session async (fire-and-forget with error catch)."""
        try:
            store = SessionStore(session.pipeline_name)
            store.ensure_session_dir()
            data = {
                "session_id": session.session_id,
                "pipeline_name": session.pipeline_name,
                "status": session.status,
                "created_at": session.created_at,
                "messages": session.messages,
                "budget_snapshot": session.budget_snapshot,
            }
            store.save_session(session.session_id, data)
        except Exception as e:
            logger.warning("Failed to async save session %s: %s", session.session_id, e)


