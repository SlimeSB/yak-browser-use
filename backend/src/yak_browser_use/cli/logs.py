"""Unified log viewer for yak-browser-use.

Reads log files from the ``logs/`` directory or a specific run:

  logs/backend.log           — Python backend (timed rotating, daily)
  logs/electron.log          — Electron main process
  logs/llm/*.jsonl           — LLM response records
  userdata/workspaces/<pipeline>/runs/<run_id>/  — run-specific logs

Usage:
  ybu logs                         # last 50 lines from all sources
  ybu logs -f                      # tail live
  ybu logs --source backend        # only backend logs
  ybu logs -n 100                  # last 100 lines
  ybu logs --run <run_id>          # logs for a specific run
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from yak_browser_use.utils.logging import get_logger
from yak_browser_use.utils._path import project_root

logger = get_logger(__name__)

_LOG_DIR = (project_root() / "logs").resolve()
_WORKSPACES_ROOT = project_root() / "userdata" / "workspaces"


def _find_run_dir(run_id: str) -> Path | None:
    """Search workspace directories for a run directory matching run_id."""
    if not _WORKSPACES_ROOT.exists():
        return None
    for pipeline_dir in _WORKSPACES_ROOT.iterdir():
        if not pipeline_dir.is_dir():
            continue
        run_dir = pipeline_dir / "runs" / run_id
        if run_dir.is_dir():
            return run_dir
    return None


def _find_log_files(source: str, run_dir: Path | None = None) -> list[Path]:
    """Yield existing log file paths matching the source filter."""
    if run_dir:
        # Run-specific logs: look for .log files in the run directory
        files: list[Path] = []
        for p in sorted(run_dir.glob("*.log")):
            files.append(p)
        for p in sorted(run_dir.glob("*.jsonl")):
            files.append(p)
        # Also include _run.json metadata
        meta = run_dir / "_run.json"
        if meta.exists():
            files.append(meta)
        return files

    files: list[Path] = []
    if source in ("all", "backend"):
        backend_log = _LOG_DIR / "backend.log"
        if backend_log.exists():
            files.append(backend_log)
    if source in ("all", "electron"):
        electron_log = _LOG_DIR / "electron.log"
        if electron_log.exists():
            files.append(electron_log)
    if source in ("all", "llm"):
        llm_dir = _LOG_DIR / "llm"
        if llm_dir.is_dir():
            for p in sorted(llm_dir.glob("*.jsonl")):
                files.append(p)
    return files


def _tail_file(path: Path, lines: int) -> list[str]:
    """Return the last *lines* of *path*, with source label prefix."""
    prefix = _label(path)
    try:
        raw = path.read_text(encoding="utf-8")
        all_lines = [line.rstrip("\n") for line in raw.splitlines() if line.strip()]
        return [f"{prefix} {line}" for line in all_lines[-lines:]]
    except Exception:
        return [f"{prefix} [read error]"]


def _label(path: Path) -> str:
    parent = path.parent
    if parent.name == "logs" or parent.parent.name == "logs":
        if path.name == "backend.log":
            return "[backend]"
        if path.name == "electron.log":
            return "[electron]"
        if path.suffix == ".jsonl":
            return f"[llm:{path.stem}]"
    # Run-specific logs — path looks like workspaces/<pipeline>/runs/<run_id>/*
    if path.parent.parent.name == "runs" and path.parent.parent.parent.parent.name == "workspaces":
        return f"[run:{path.parent.name}]"
    if path.name == "_run.json":
        return "[run:meta]"
    return f"[{path.stem}]"


async def _cmd_logs(source: str = "all", lines: int = 50, follow: bool = False, run: str | None = None) -> None:
    """View unified logs."""

    # Resolve run directory if --run was given
    run_dir = _find_run_dir(run) if run else None
    if run and not run_dir:
        print(f"Run '{run}' not found in any workspace")
        return

    log_files = _find_log_files(source, run_dir)

    if not log_files:
        if run_dir:
            print(f"No log files found in {run_dir}")
        else:
            print(f"No log files found in {_LOG_DIR}")
            if not _LOG_DIR.exists():
                print("  (directory does not exist yet — run the app first)")
        return

    if follow:
        await _tail_follow(log_files, source, lines)
    else:
        for path in log_files:
            for line in _tail_file(path, lines):
                print(line)


async def _tail_follow(paths: list[Path], source: str, head_lines: int) -> None:
    """Print recent lines then watch for new content in real time."""
    file_positions: dict[Path, int] = {}
    for path in paths:
        try:
            content = path.read_text(encoding="utf-8")
            all_lines = [l.rstrip("\n") for l in content.splitlines() if l.strip()]
            for line in all_lines[-head_lines:]:
                print(f"{_label(path)} {line}")
            file_positions[path] = path.stat().st_size
        except Exception:
            file_positions[path] = 0

    if not file_positions:
        return

    print("\n--- live tail (Ctrl+C to stop) ---")
    try:
        while True:
            current = paths  # don't auto-refresh file list for run-specific
            for path in current:
                if path not in file_positions:
                    try:
                        file_positions[path] = path.stat().st_size
                    except Exception:
                        continue

            for path, prev_size in list(file_positions.items()):
                try:
                    if not path.exists():
                        del file_positions[path]
                        continue
                    new_size = path.stat().st_size
                    if new_size > prev_size:
                        with open(path, "r", encoding="utf-8") as f:
                            f.seek(prev_size)
                            chunk = f.read(new_size - prev_size)
                            for line in chunk.splitlines():
                                line = line.rstrip("\n").rstrip("\r")
                                if line.strip():
                                    print(f"{_label(path)} {line}")
                        file_positions[path] = new_size
                except Exception:
                    logger.warning("tail_follow: error reading log chunk", exc_info=True)
            await asyncio.sleep(0.5)
    except KeyboardInterrupt:
        print("\n--- tail stopped ---")
