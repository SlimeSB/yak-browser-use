"""Shared path validation for file I/O and format conversion tools."""

from pathlib import Path

from yak_browser_use.workspace.manager import WORKSPACES_ROOT


def validate_path(path: str, pipeline: str | None = None) -> Path:
    """Validate and resolve a file path, rejecting traversal and absolute paths.

    When *path* starts with ``downloads/`` and *pipeline* is provided, the
    path is resolved relative to ``WORKSPACES_ROOT / pipeline / downloads/``.

    Returns the resolved Path relative to the current working directory.
    """
    if not path or not path.strip():
        raise ValueError(f"路径不能为空")
    p = Path(path)
    if p.is_absolute():
        raise ValueError(f"绝对路径不被允许: {path}")
    normalized = path.replace("\\", "/")
    parts = normalized.split("/")
    if ".." in parts:
        raise ValueError(f"路径穿越被拒绝: {path}")

    if path.startswith("downloads/") and pipeline:
        return (WORKSPACES_ROOT / pipeline / path).resolve()

    return p.resolve()
