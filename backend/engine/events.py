"""Event system — publishes pipeline events to files, WS clients, and logs."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from utils.logging import get_logger

logger = get_logger(__name__)


class EventSink:
    """Writes structured events to a JSONL file and optionally broadcasts to WS clients."""

    def __init__(self, run_dir: Path, ws_clients: list | None = None):
        self._run_dir = run_dir
        self._ws_clients = ws_clients or []
        self._event_log = run_dir / "_events.jsonl"
        self._event_log.parent.mkdir(parents=True, exist_ok=True)

    def _emit(self, event: dict) -> None:
        event["_ts"] = time.time()
        line = json.dumps(event, ensure_ascii=False)
        try:
            with open(self._event_log, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass
        for ws in self._ws_clients:
            try:
                ws.put_nowait(event)
            except Exception:
                pass

    def emit_run_start(self, pipeline_name: str, run_id: str, version: str) -> None:
        self._emit({"type": "run_start", "pipeline": pipeline_name, "run_id": run_id, "version": version})

    def emit_run_end(self, status: str, duration_ms: int) -> None:
        self._emit({"type": "run_end", "status": status, "duration_ms": duration_ms})

    def emit_step_start(self, step_name: str, step_type: str) -> None:
        self._emit({"type": "step_start", "step": step_name, "step_type": step_type})

    def emit_step_end(self, step_name: str, step_type: str, status: str, duration_ms: int,
                      input_files: Any = None, output_files: Any = None) -> None:
        self._emit({
            "type": "step_end", "step": step_name, "step_type": step_type,
            "status": status, "duration_ms": duration_ms,
            "input_files": input_files, "output_files": output_files,
        })

    def emit_error(self, step: str, code: str, message: str, stack: str = "") -> None:
        self._emit({"type": "error", "step": step, "code": code, "message": message, "stack": stack})

    def emit_log(self, step: str, message: str, level: str = "INFO") -> None:
        self._emit({"type": "log", "step": step, "message": message, "level": level})

    def close(self) -> None:
        pass  # No cleanup needed currently
