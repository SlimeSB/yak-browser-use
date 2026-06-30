"""SessionManager — chat session lifecycle and persistence."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from yak_browser_use.api.errors import APIError
from yak_browser_use.tools.todo_store import TodoStore
from yak_browser_use.workspace.session_store import (
    SessionStore,
    read_last_active,
    write_last_active,
)
from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_PIPELINE = "__chat__"


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


class SessionManager:
    """Manages in-memory session state and persistence to disk."""

    def __init__(self):
        self._sessions: dict[str, SessionState] = {}
        self._active_pipeline: str = _DEFAULT_PIPELINE
        self._on_event: Callable[[dict], None] | None = None

    def set_event_pusher(self, pusher: Callable[[dict], None]) -> None:
        self._on_event = pusher

    # ── Normalization ───────────────────────────────────────────────

    @staticmethod
    def normalize_pipeline(name: str) -> str:
        return _DEFAULT_PIPELINE if not name or name == "chat" else name

    @property
    def active_pipeline(self) -> str:
        return self._active_pipeline

    @active_pipeline.setter
    def active_pipeline(self, name: str) -> None:
        self._active_pipeline = name

    # ── CRUD ────────────────────────────────────────────────────────

    def create_session(self, pipeline_name: str = "") -> SessionState:
        """Create a new chat session for a pipeline. Rejects if one is running."""
        normalized = self.normalize_pipeline(pipeline_name)
        existing = self._sessions.get(normalized)
        if existing and existing.status == "running":
            raise APIError("当前有任务正在执行，请先结束或取消")
        session_id = f"session_{int(time.time() * 1000)}"
        session = SessionState(session_id=session_id, pipeline_name=normalized)
        self._sessions[normalized] = session
        self._active_pipeline = normalized
        logger.info("Session created: %s (pipeline=%s)", session_id, normalized)
        if self._on_event:
            self._on_event({"type": "session.state", "status": "idle", "session_id": session_id})
        return session

    def get_session(self, pipeline_name: str | None = None) -> SessionState | None:
        """Get the active session for a pipeline.

        If pipeline_name is None, uses the current active pipeline.
        Falls back to disk restore if not found in memory.
        """
        name = self.normalize_pipeline(pipeline_name) if pipeline_name is not None else self._active_pipeline
        session = self._sessions.get(name)
        if session is not None:
            return session
        return self._restore_from_disk(name)

    def reset_session(self) -> SessionState:
        """Cancel current session, save history, start new."""
        current = self._sessions.get(self._active_pipeline)
        if current:
            self._persist_session(current)
        return self.create_session(self._active_pipeline)

    def cancel_session(self) -> SessionState | None:
        """Cancel the active session."""
        session = self._sessions.get(self._active_pipeline)
        if session:
            session.status = "cancelled"
            if self._on_event:
                self._on_event({
                    "type": "session.state",
                    "status": "cancelled",
                    "session_id": session.session_id,
                })
        return session

    def switch_session(self, pipeline_name: str) -> list[dict]:
        """Switch active pipeline: save current session, load target workspace.

        Returns the target workspace's session list.
        """
        target = self.normalize_pipeline(pipeline_name)

        current = self._sessions.get(self._active_pipeline)
        if current:
            self._persist_session(current)

        self._active_pipeline = target
        write_last_active(target)

        store = SessionStore(target)
        store.ensure_session_dir()
        sessions = store.list_sessions()

        logger.info("Switched to pipeline %s (%d sessions)", target, len(sessions))
        return sessions

    def archive_session(self, pipeline_name: str, session_id: str) -> bool:
        """Archive a session for the given pipeline."""
        normalized = self.normalize_pipeline(pipeline_name)
        store = SessionStore(normalized)
        ok = store.archive_session(session_id)
        if ok:
            logger.info("SessionManager: archived session %s in pipeline %s", session_id, normalized)
        return ok

    def new_session(self, pipeline_name: str) -> dict:
        """Create a new persisted session for the given pipeline."""
        normalized = self.normalize_pipeline(pipeline_name)
        store = SessionStore(normalized)
        store.ensure_session_dir()
        session_id = store.new_session()

        session = SessionState(session_id=session_id, pipeline_name=normalized)
        self._sessions[normalized] = session
        self._active_pipeline = normalized

        logger.info("new_session: %s for pipeline %s", session_id, normalized)
        return {
            "session_id": session_id,
            "created_at": session.created_at,
            "pipeline_name": normalized,
        }

    # ── Migration ───────────────────────────────────────────────────

    def migrate_session(self, from_pipeline: str, to_pipeline: str) -> SessionState | None:
        session = self._sessions.get(from_pipeline)
        if session is None:
            return None
        session.pipeline_name = to_pipeline
        self._persist_session(session)
        self._sessions[to_pipeline] = session
        self._sessions.pop(from_pipeline, None)
        self._active_pipeline = to_pipeline
        write_last_active(to_pipeline)
        logger.info(
            "Session %s migrated from %s to %s",
            session.session_id, from_pipeline, to_pipeline,
        )
        return session

    # ── Persistence ─────────────────────────────────────────────────

    def persist_session(self, session: SessionState, context: str = "history") -> None:
        """Persist session to workspace session dir, catching errors.

        Public so callers (e.g. chat processing) can trigger save
        without accessing SessionStore directly.
        """
        self._persist_session(session, context)

    def _persist_session(self, session: SessionState, context: str = "history") -> None:
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
            logger.warning("Failed to save session %s: %s", context, e)

    def _restore_from_disk(self, pipeline_name: str) -> SessionState | None:
        """Try to load the latest session for *pipeline_name* from disk.

        Returns None if nothing is persisted.
        """
        store = SessionStore(pipeline_name)
        store.ensure_session_dir()
        sessions = store.list_sessions()
        if not sessions:
            return None

        latest = sessions[0]
        session_id = latest.get("session_id", "")
        if not session_id:
            return None

        data = store.load_session(session_id)
        if data is None:
            return None

        session = SessionState(
            session_id=data.get("session_id", session_id),
            pipeline_name=data.get("pipeline_name", pipeline_name),
            status=data.get("status", "idle"),
            created_at=data.get("created_at", time.time()),
            messages=data.get("messages", []),
            budget_snapshot=data.get("budget_snapshot"),
        )
        self._sessions[pipeline_name] = session
        self._active_pipeline = pipeline_name
        logger.info("Session restored from disk: %s (pipeline=%s, %d messages)",
                     session.session_id, pipeline_name, len(session.messages))
        return session
