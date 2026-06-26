"""Shared path utilities — single source of truth for project root."""
from __future__ import annotations

from pathlib import Path

# backend/src/yak_browser_use/utils/ → 5 levels up = project root
_PROJECT_ROOT: Path | None = None
_TEMP_ROOT: Path | None = None


def project_root() -> Path:
    global _PROJECT_ROOT
    if _PROJECT_ROOT is None:
        _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
    return _PROJECT_ROOT


def temp_root() -> Path:
    """Return a per-project temp directory under userdata/temp."""
    global _TEMP_ROOT
    if _TEMP_ROOT is None:
        _TEMP_ROOT = project_root() / "userdata" / "temp"
        _TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    return _TEMP_ROOT
