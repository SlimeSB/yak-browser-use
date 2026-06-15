"""WorkspaceManager — manages the workspace directory layout, run lifecycle, and cleanup.

Root: <project>/workspaces/<pipeline_name>/
Run dirs: runs/<datetime>/
Version snapshots: versions/
Tool dir: tools/
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_MAX_RUNS = 20
VALID_STATUSES = frozenset({"running", "completed", "failed", "paused", "cancelled", "crashed"})

_WORKSPACES_ROOT = Path(__file__).resolve().parent.parent.parent / "userdata" / "workspaces"


class WorkspaceManager:
    """Manages the workspace directory layout, run lifecycle, and cleanup."""

    def __init__(self, pipeline_name: str):
        self.pipeline_name = pipeline_name
        self.root = (_WORKSPACES_ROOT / pipeline_name).resolve()
        self.runs_dir = self.root / "runs"
        self.versions_dir = self.root / "versions"
        self.tools_dir = self.root / "tools"

    # ── directory creation ──

    def ensure_workspace(self) -> Path:
        """Create the workspace root and required subdirectories."""
        self.root.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(exist_ok=True)
        self.versions_dir.mkdir(exist_ok=True)
        self.tools_dir.mkdir(exist_ok=True)
        return self.root

    def create_run(self) -> Path:
        """Create a new run directory with metadata."""
        self.ensure_workspace()
        run_id = _generate_run_id(self.runs_dir)
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "final").mkdir(exist_ok=True)

        meta = {
            "pipeline": self.pipeline_name,
            "run_id": run_id,
            "status": "pending",
            "version": _read_latest_version(self.versions_dir),
            "created_at": _now_iso(),
            "completed_at": None,
            "crashed_detected_at": None,
        }
        _write_json(run_dir / "_run.json", meta)

        logger.info("workspace: created run %s/%s", self.pipeline_name, run_id)
        return run_dir

    # ── run lifecycle ──

    def set_status(self, run_dir: Path, status: str, current_step: str | None = None) -> None:
        """Set the status of a run."""
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{status}'. Must be one of {sorted(VALID_STATUSES)}")

        meta = _read_json(run_dir / "_run.json")
        meta["status"] = status
        if current_step is not None:
            meta["current_step"] = current_step
        if status in ("completed", "failed", "crashed", "cancelled"):
            meta["completed_at"] = _now_iso()
        if status == "crashed":
            meta["crashed_detected_at"] = _now_iso()
        _write_json(run_dir / "_run.json", meta)

    def get_status(self, run_dir: Path) -> str | None:
        """Get the status of a run."""
        run_json = run_dir / "_run.json"
        if run_json.exists():
            meta = _read_json(run_json)
            return meta.get("status")
        return None

    def list_runs(self) -> list[dict]:
        """List all runs with their metadata, sorted by creation time descending."""
        if not self.runs_dir.exists():
            return []

        run_dirs = sorted(
            [d for d in self.runs_dir.iterdir() if d.is_dir() and _looks_like_run_id(d.name)],
            key=lambda p: p.name,
            reverse=True,
        )
        result = []
        for d in run_dirs:
            meta_path = d / "_run.json"
            if meta_path.exists():
                result.append(_read_json(meta_path))
        return result

    # ── crash detection ──

    def detect_crashed_runs(self) -> list[Path]:
        """Find runs still marked as 'running' and mark them as 'crashed'."""
        runs = sorted(self.runs_dir.glob("*"), key=lambda p: p.name)
        crashed = []
        for run_dir in runs:
            if not run_dir.is_dir():
                continue
            run_json = run_dir / "_run.json"
            if run_json.exists():
                meta = _read_json(run_json)
                if meta.get("status") == "running":
                    meta["status"] = "crashed"
                    meta["crashed_detected_at"] = _now_iso()
                    meta["completed_at"] = _now_iso()
                    _write_json(run_json, meta)
                    crashed.append(run_dir)
        return crashed

    # ── cleanup ──

    def cleanup_old_runs(self, max_runs: int = DEFAULT_MAX_RUNS) -> int:
        """Remove oldest runs beyond max_runs."""
        if not self.runs_dir.exists():
            return 0
        run_dirs = sorted(
            [d for d in self.runs_dir.iterdir() if d.is_dir() and _looks_like_run_id(d.name)],
            key=lambda p: p.name,
        )
        removed = 0
        while len(run_dirs) > max_runs:
            oldest = run_dirs.pop(0)
            shutil.rmtree(oldest, ignore_errors=True)
            removed += 1
            logger.info("workspace: cleaned run %s/%s", self.pipeline_name, oldest.name)
        return removed

    # ── exports / final ──

    def fill_final(self, run_dir: Path, last_step_dir: Path) -> None:
        """Copy content from last_step_dir into run_dir/final."""
        final_dir = run_dir / "final"
        if last_step_dir.exists():
            for f in last_step_dir.iterdir():
                dest = final_dir / f.name
                if f.is_file():
                    shutil.copy2(f, dest)
                elif f.is_dir():
                    shutil.copytree(f, dest, dirs_exist_ok=True)


# ── helpers ──

def _generate_run_id(runs_dir: Path) -> str:
    base = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = base
    n = 2
    while (runs_dir / candidate).exists():
        candidate = f"{base}_{n}"
        n += 1
    return candidate


def _looks_like_run_id(name: str) -> bool:
    return bool(re.match(r"^\d{8}_\d{6}(_\d+)?$", name))


def _read_latest_version(versions_dir: Path) -> str | None:
    latest_file = versions_dir / "LATEST"
    if latest_file.exists():
        return latest_file.read_text(encoding="utf-8").strip()
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
