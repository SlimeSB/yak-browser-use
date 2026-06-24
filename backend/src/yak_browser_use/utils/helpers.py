"""Miscellaneous shared helpers — validation, result formatting."""

from __future__ import annotations

import os


def sanitize_pipeline_name(pipeline_name: str) -> str:
    """Validate and sanitize *pipeline_name*, returning the safe basename.

    Raises ``ValueError`` if the name contains path separators or is empty.
    """
    safe = os.path.basename(pipeline_name.replace("\\", "/"))
    if not safe or safe != pipeline_name.replace("\\", "/"):
        raise ValueError(f"Invalid pipeline name: {pipeline_name}")
    return safe


def prepend_resolve_errors(result: dict, resolve_errors: list[str]) -> None:
    """Prepend parameter-template resolve errors to a tool *result* dict, mutating in-place.

    When *resolve_errors* is empty the call is a no-op.
    """
    if not resolve_errors:
        return
    warning = f"\u26a0\ufe0f \u53c2\u6570\u6a21\u677f\u89e3\u6790\u5931\u8d25: {resolve_errors}"
    if result.get("ok"):
        existing = result.get("result", "")
        if isinstance(existing, str):
            result["result"] = warning + "\n\n" + existing
        else:
            result["result"] = warning
    else:
        existing = result.get("error", "")
        result["error"] = warning + "\n\n" + existing
