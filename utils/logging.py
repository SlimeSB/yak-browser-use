"""Shared logger setup for learning-browser-use."""
from __future__ import annotations

import logging
import sys

_initialized = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def setup_logging(level: str | None = None) -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)

    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(level or "DEBUG")
