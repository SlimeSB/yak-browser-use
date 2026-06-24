"""Shared path validation for file I/O and format conversion tools."""

from pathlib import Path


def validate_path(path: str) -> Path:
    """Validate and resolve a file path, rejecting traversal and absolute paths.

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
    return p.resolve()
