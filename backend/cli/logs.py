"""Unified log viewer for yak-browser-use.

Reads log files from the ``logs/`` directory:

  logs/backend.log   — Python backend (timed rotating, daily)
  logs/electron.log  — Electron main process
  logs/llm/*.jsonl   — LLM response records

Usage:
  yak logs                     # last 50 lines from all sources
  yak logs -f                  # tail live
  yak logs --source backend    # only backend logs
  yak logs -n 100              # last 100 lines
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)

_LOG_DIR = (Path(__file__).resolve().parent.parent.parent / "logs").resolve()


def _find_log_files(source: str) -> list[Path]:
    """Yield existing log file paths matching the source filter."""
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
    if path.name == "backend.log":
        return "[backend]"
    if path.name == "electron.log":
        return "[electron]"
    if path.suffix == ".jsonl":
        return f"[llm:{path.stem}]"
    return f"[{path.stem}]"


async def _cmd_logs(source: str = "all", lines: int = 50, follow: bool = False) -> None:
    """View unified logs."""
    log_files = _find_log_files(source)

    if not log_files:
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
    # Print recent lines first
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

    # Poll for new content
    print("\n--- live tail (Ctrl+C to stop) ---")
    try:
        while True:
            # Refresh file list in case new files appear
            current = _find_log_files(source)
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
                    pass
            await asyncio.sleep(0.5)
    except KeyboardInterrupt:
        print("\n--- tail stopped ---")
