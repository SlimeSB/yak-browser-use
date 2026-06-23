"""Shared logger setup for yak-browser-use."""

from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from yak_browser_use.utils._path import project_root

_initialized = False

# Resolve the project root directory (two levels above this file)
_LOG_DIR = (project_root() / "logs").resolve()


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def _ensure_log_dir() -> Path:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    return _LOG_DIR


def setup_logging(level: str | None = None) -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    fmt = logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(levelname)-5s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Console output
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)

    # Timed rotating file (daily, 7-day retention)
    log_dir = _ensure_log_dir()
    file_handler = TimedRotatingFileHandler(
        filename=str(log_dir / "backend.log"),
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.addHandler(console)
    root.addHandler(file_handler)
    root.setLevel(level or "DEBUG")
