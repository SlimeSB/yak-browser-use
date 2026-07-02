"""SessionStore — per-workspace session persistence.

Manages session metadata index and individual session message files
under <workspace>/session/ directory.

Directory layout:
  workspaces/{pipeline_name}/
    sessions.json          # {session_id: metadata} dict
    {session_id}.json      # full session data (messages + meta)
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from yak_browser_use.utils.logging import get_logger
from yak_browser_use.utils._path import project_root

logger = get_logger(__name__)

_WORKSPACES_ROOT = project_root() / "userdata" / "workspaces"



def _normalize_pipeline(name: str) -> str:
    """Normalize pipeline name: empty or 'chat' -> '__chat__'."""
    if not name or name == "chat":
        return "__chat__"
    return name


def _generate_session_id() -> str:
    """Generate YYYYMMDD_HHMMSS_hex session ID."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:6]
    return f"{timestamp}_{short_uuid}"


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically via temp file + rename."""
    tmp_path = path.with_suffix(".json.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(str(tmp_path), str(path))
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def _read_json(path: Path) -> dict:
    """Read JSON file, return empty dict if missing."""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _last_active_path() -> Path:
    return _WORKSPACES_ROOT / ".last_active"


def read_last_active() -> str | None:
    """Read last active pipeline name from marker file."""
    path = _last_active_path()
    if path.exists():
        return path.read_text(encoding="utf-8").strip() or None
    return None


def write_last_active(pipeline_name: str) -> None:
    """Write last active pipeline name to marker file."""
    _WORKSPACES_ROOT.mkdir(parents=True, exist_ok=True)
    _last_active_path().write_text(pipeline_name, encoding="utf-8")


class SessionStore:
    """Per-workspace session persistence backed by the workspace directory."""

    def __init__(self, pipeline_name: str):
        self.pipeline_name = _normalize_pipeline(pipeline_name)
        self.session_dir = _WORKSPACES_ROOT / self.pipeline_name / "session"

    # ── directory ──

    def ensure_session_dir(self) -> Path:
        """Create session directory if it doesn't exist."""
        self.session_dir.mkdir(parents=True, exist_ok=True)
        return self.session_dir

    # ── index ──

    def _index_path(self) -> Path:
        return self.session_dir / "sessions.json"

    def _read_index(self) -> dict:
        return _read_json(self._index_path())

    def _write_index(self, data: dict) -> None:
        self.ensure_session_dir()
        _atomic_write_json(self._index_path(), data)

    # ── session CRUD ──

    def new_session(self) -> dict:
        """Create a new session ID and register it in the index.

        Also creates a corresponding run directory (``create_run("agent")``)
        for download isolation. Returns ``{"session_id": ..., "run_id": ...}``.
        """
        session_id = _generate_session_id()
        index = self._read_index()
        if session_id not in index:
            index[session_id] = {
                "session_id": session_id,
                "display_name": None,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "message_count": 0,
                "status": "idle",
            }
            self._write_index(index)
            # Create corresponding run directory for download isolation
            from yak_browser_use.workspace.manager import WorkspaceManager
            wm = WorkspaceManager(self.pipeline_name)
            run_dir = wm.create_run("agent")
            run_id = run_dir.name
            index[session_id]["run_id"] = run_id
            self._write_index(index)
            logger.info("session_store: new session %s (run %s) in %s", session_id, run_id, self.pipeline_name)
        else:
            run_id = index[session_id].get("run_id", "")
        return {"session_id": session_id, "run_id": run_id}

    def save_session(self, session_id: str, session_dict: dict) -> None:
        """Save full session data to {session_id}.json and update index."""
        self.ensure_session_dir()
        path = self.session_dir / f"{session_id}.json"
        _atomic_write_json(path, session_dict)

        # Update index metadata
        index = self._read_index()
        if session_id in index:
            index[session_id]["updated_at"] = datetime.now().isoformat()
            index[session_id]["message_count"] = len(session_dict.get("messages", []))
            index[session_id]["status"] = session_dict.get("status", "idle")
        else:
            index[session_id] = {
                "session_id": session_id,
                "display_name": None,
                "created_at": session_dict.get("created_at", datetime.now().isoformat()),
                "updated_at": datetime.now().isoformat(),
                "message_count": len(session_dict.get("messages", [])),
                "status": session_dict.get("status", "idle"),
            }
        self._write_index(index)

    def load_session(self, session_id: str) -> dict | None:
        """Load full session data from {session_id}.json."""
        path = self.session_dir / f"{session_id}.json"
        if not path.exists():
            logger.warning("session_store: session %s not found in %s", session_id, self.pipeline_name)
            return None
        return _read_json(path)

    def list_sessions(self, include_archived: bool = False) -> list[dict]:
        """Return all session metadata, sorted by creation time descending."""
        index = self._read_index()
        sessions = list(index.values())
        if not include_archived:
            sessions = [s for s in sessions if not s.get("archived")]
        def _created_at_key(s: dict):
            v = s.get("created_at", 0)
            if isinstance(v, (int, float)):
                return (0, v)
            return (1, str(v))
        sessions.sort(key=_created_at_key, reverse=True)
        return sessions

    def archive_session(self, session_id: str) -> bool:
        """Mark a session as archived (soft-delete)."""
        index = self._read_index()
        if session_id not in index:
            return False
        index[session_id]["archived"] = True
        index[session_id]["updated_at"] = datetime.now().isoformat()
        self._write_index(index)
        logger.info("session_store: archived session %s in %s", session_id, self.pipeline_name)
        return True

    def unarchive_session(self, session_id: str) -> bool:
        """Remove archived flag from a session."""
        index = self._read_index()
        if session_id not in index:
            return False
        index[session_id].pop("archived", None)
        index[session_id]["updated_at"] = datetime.now().isoformat()
        self._write_index(index)
        logger.info("session_store: unarchived session %s in %s", session_id, self.pipeline_name)
        return True

    def delete_session_files(self, session_id: str) -> None:
        """Remove session files and index entry."""
        path = self.session_dir / f"{session_id}.json"
        if path.exists():
            path.unlink(missing_ok=True)
        index = self._read_index()
        index.pop(session_id, None)
        self._write_index(index)
