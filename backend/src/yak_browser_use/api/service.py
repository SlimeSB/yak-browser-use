"""API service layer — session/chat/pipeline business logic.

Bridges the API routes to the engine: session management,
chat message processing, pipeline compilation, and event pushing.

Delegates to :class:`SessionManager` and :class:`EventBus` for the
respective sub-domains; Service itself handles chat orchestration
and pipeline utilities.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable

from yak_browser_use.utils.logging import get_logger

from yak_browser_use.api.errors import APIError
from yak_browser_use.api.event_bus import EventBus
from yak_browser_use.api.session_manager import SessionManager, SessionState, _DEFAULT_PIPELINE
from yak_browser_use.workspace.manager import WORKSPACES_ROOT
from yak_browser_use.tools.todo_store import current_store

logger = get_logger(__name__)

_WORKSPACES_DIR = WORKSPACES_ROOT


def _build_pipeline_context(pipeline_name: str) -> str | None:
    """Build a markdown snippet describing the currently selected pipeline."""
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


class Service:
    """Business logic service for the YBU API.

    Composes :class:`SessionManager` and :class:`EventBus` and
    exposes the combined interface used by the route layer.
    """

    def __init__(self, engine_state: object | None = None):
        self.sessions = SessionManager()
        self.events = EventBus(engine_state)
        self.sessions.set_event_pusher(self.events.push)
        self._chat_lock = asyncio.Lock()

    # ── Session management (delegated) ──────────────────────────────

    def create_session(self, pipeline_name: str = "") -> SessionState:
        return self.sessions.create_session(pipeline_name)

    def get_session(self, pipeline_name: str | None = None) -> SessionState | None:
        return self.sessions.get_session(pipeline_name)

    def reset_session(self) -> SessionState:
        return self.sessions.reset_session()

    def cancel_session(self) -> SessionState | None:
        return self.sessions.cancel_session()

    def switch_session(self, pipeline_name: str) -> list[dict]:
        return self.sessions.switch_session(pipeline_name)

    def archive_session(self, pipeline_name: str, session_id: str) -> bool:
        return self.sessions.archive_session(pipeline_name, session_id)

    def new_session(self, pipeline_name: str) -> dict:
        return self.sessions.new_session(pipeline_name)

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
        """Process a chat message through conversation_loop."""
        async with self._chat_lock:
            from yak_browser_use.engine._harness.conversation_loop import (
                run_conversation_loop,
                ConversationResult,
            )
            from yak_browser_use.engine._harness.tools import get_all_tools
            from yak_browser_use.prompts._loader import build_system_prompt

            session = self.sessions.get_session(pipeline_name)
            if session is None:
                session = self.sessions.create_session(pipeline_name)

            logger.info("Chat [%s] user: %s", session.session_id, message[:120])

            session.status = "running"
            self.events.push({
                "type": "session.state",
                "status": "running",
                "session_id": session.session_id,
            })

            session.messages.append({"role": "user", "content": message})
            self.sessions.persist_session(session, context="user_msg")

            system_prompt = build_system_prompt()

            normalized = self.sessions.normalize_pipeline(pipeline_name)
            self.sessions.active_pipeline = normalized
            if normalized != _DEFAULT_PIPELINE:
                pipeline_ctx = _build_pipeline_context(normalized)
                if pipeline_ctx:
                    system_prompt += "\n\n" + pipeline_ctx

            def _stream_cb(event: dict) -> None:
                event["session_id"] = session.session_id
                self.events.push(event)

            def _interrupt_check() -> bool:
                return session.status in ("cancelled",)

            _todo_token = current_store.set(session.todo_store)
            self.events.chat_streaming = True

            def _on_turn_complete() -> None:
                self.sessions.persist_session(session)

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

                self.sessions.persist_session(session)

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
                self.events.chat_streaming = False
                self.events.push({
                    "type": "session.state",
                    "status": session.status,
                    "session_id": session.session_id,
                })
                current_store.reset(_todo_token)

    # ── Pipeline management ─────────────────────────────────────────

    def compile_pipeline(self, pipeline_text: str) -> dict:
        """Compile pipeline.yaml text into step definitions."""
        try:
            from yak_browser_use.compiler.parser import parse_pipeline
            from yak_browser_use.compiler.resolver import resolve
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

    # ── Events (delegated) ─────────────────────────────────────────

    def on_event(self, callback: Callable[[dict], None]) -> None:
        """Register a callback for event streaming."""
        self.events.on_event(callback)


