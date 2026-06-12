"""API service layer — session/chat/pipeline business logic.

Bridges the API routes to the engine: session management,
chat message processing, pipeline compilation, and event pushing.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from utils.logging import get_logger

from api.errors import APIError

logger = get_logger(__name__)

# Default session directory
_SESSIONS_DIR = Path.home() / ".lbu" / "sessions"


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


class Service:
    """Business logic service for the LBU API."""

    def __init__(self, engine_state: object | None = None):
        self._engine_state = engine_state
        self._active_session: SessionState | None = None
        self._event_callbacks: list[Callable[[dict], None]] = []

    # ── Session management ──────────────────────────────────────────

    def create_session(self, pipeline_name: str = "") -> SessionState:
        """Create a new chat session. Rejects if one is already active."""
        if self._active_session and self._active_session.status == "running":
            raise APIError("当前有任务正在执行，请先结束或取消")
        session_id = f"session_{int(time.time() * 1000)}"
        session = SessionState(session_id=session_id, pipeline_name=pipeline_name)
        self._active_session = session
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
        from engine._harness.conversation_loop import run_conversation_loop, ConversationResult
        from engine._harness.tools import get_all_tools
        from prompts._loader import load_prompt

        if self._active_session is None:
            self.create_session(pipeline_name)

        session = self._active_session
        if session is None:
            return {"ok": False, "error": "No active session"}

        session.status = "running"
        self._push_event({
            "type": "session.state",
            "status": "running",
            "session_id": session.session_id,
        })

        session.messages.append({"role": "user", "content": message})

        system_prompt = load_prompt("chat/system")

        def _stream_cb(event: dict) -> None:
            event["session_id"] = session.session_id
            self._push_event(event)

        def _interrupt_check() -> bool:
            return session.status in ("cancelled",)

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
            self._push_event({
                "type": "session.state",
                "status": session.status,
                "session_id": session.session_id,
            })

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
        presets_dir = _SESSIONS_DIR / "presets"
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
                pass
        return presets

    def save_preset(self, name: str, pipeline_text: str) -> Path:
        """Save conversation history as a preset pipeline.yaml file."""
        presets_dir = _SESSIONS_DIR / "presets"
        presets_dir.mkdir(parents=True, exist_ok=True)
        path = presets_dir / f"{name}.pipeline.yaml"
        path.write_text(pipeline_text, encoding="utf-8")
        return path

    def compile_session_to_preset(self, session: SessionState) -> str:
        """Compile a session's conversation history into pipeline.yaml format.

        Builds a PipelineYaml object from session tool-call messages
        and dumps to YAML text.
        """
        import yaml
        from compiler.schema import PipelineYaml, StepYaml

        pipeline_name = session.pipeline_name or "chat-preset"
        steps: list[StepYaml] = []

        step_index = 1
        for msg in session.messages:
            role = msg.get("role", "")
            if role == "tool":
                tool_name = msg.get("name", "")
                content = str(msg.get("content", ""))[:200]

                if tool_name.startswith("browser_"):
                    op_type = tool_name.replace("browser_", "")
                    step_yaml = StepYaml(
                        name=f"step_{step_index}",
                        description=f"{op_type}: {content[:80]}",
                        browser_ops=[{op_type: content[:80]}],
                    )
                else:
                    step_yaml = StepYaml(
                        name=f"step_{step_index}",
                        description=f"tool {tool_name}: {content[:80]}",
                        tool_name=tool_name,
                    )
                steps.append(step_yaml)
                step_index += 1

        if not steps:
            steps.append(StepYaml(
                name="step_1",
                description="Empty compiled session",
                goal_description=session.messages[0].get("content", "")[:200] if session.messages else "",
            ))

        pipeline = PipelineYaml(
            name=pipeline_name,
            description=f"Compiled from session {session.session_id}",
            steps=steps,
        )

        data = pipeline.model_dump(exclude_none=True)
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # ── Events ──────────────────────────────────────────────────────

    def on_event(self, callback: Callable[[dict], None]) -> None:
        """Register a callback for event streaming."""
        self._event_callbacks.append(callback)

    def _push_event(self, event: dict) -> None:
        """Push an event to all registered callbacks AND engine_state WS clients."""
        event["_ts"] = time.time()
        for cb in self._event_callbacks:
            try:
                cb(event)
            except Exception:
                pass
        if self._engine_state and hasattr(self._engine_state, "ws_clients"):
            for q in self._engine_state.ws_clients:
                try:
                    q.put_nowait(event)
                except Exception:
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
