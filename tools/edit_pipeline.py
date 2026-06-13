"""edit_pipeline tool — LLM can invoke this to modify pipeline.yaml files.

Saves a checkpoint on first call and pushes a pipeline.edit WebSocket event
so the frontend can show an inline diff for user review.
"""

from __future__ import annotations

import asyncio
import difflib
import os
import time
from pathlib import Path


PRESETS_DIR = Path.home() / ".ybu" / "sessions" / "presets"

_checkpoints: dict[str, Path] = {}
_processed_edits: set[str] = set()
_edit_status: dict[str, str] = {}  # 'pending' | 'confirmed' | 'reverted'


async def edit_pipeline(
    pipeline_name: str,
    content: str,
    explanation: str = "",
    **kwargs,
) -> str:
    """Modify a pipeline.yaml preset file.

    On first call for an edit_id, saves an original checkpoint.
    After writing, reads checkpoint + new content and pushes
    a pipeline.edit WebSocket event for frontend diff review.

    Args:
        pipeline_name: Name of the pipeline preset to edit.
        content: Full YAML content to write to the pipeline file.
        explanation: Human-readable description of what was changed.

    Returns:
        Status message string.
    """
    from api.state import engine_state

    safe_name = os.path.basename(pipeline_name.replace("\\", "/"))
    if not safe_name or safe_name != pipeline_name.replace("\\", "/"):
        return f"Invalid pipeline name: {pipeline_name}"

    preset_path = PRESETS_DIR / f"{safe_name}.pipeline.yaml"

    if not preset_path.exists():
        return f"Pipeline preset '{safe_name}' not found"

    edit_id = kwargs.get("edit_id", f"edit_{int(time.time() * 1000)}")
    safe_edit_id = os.path.basename(edit_id.replace("\\", "/"))
    if not safe_edit_id or safe_edit_id != edit_id.replace("\\", "/"):
        return f"Invalid edit_id: {edit_id}"
    edit_id = safe_edit_id
    is_first = edit_id not in _processed_edits

    if is_first:
        checkpoint_path = PRESETS_DIR / f"{safe_name}.pipeline.yaml.{edit_id}.orig"
        checkpoint_path.write_text(preset_path.read_text(encoding="utf-8"), encoding="utf-8")
        _checkpoints[edit_id] = checkpoint_path
        _processed_edits.add(edit_id)
        _edit_status[edit_id] = "pending"

    preset_path.write_text(content, encoding="utf-8")

    checkpoint_path = _checkpoints.get(edit_id)
    if checkpoint_path and checkpoint_path.exists():
        original = checkpoint_path.read_text(encoding="utf-8")
    else:
        original = content

    modified = content

    diff_lines = _compute_diff(original, modified)

    event = {
        "type": "pipeline.edit",
        "edit_id": edit_id,
        "original": original,
        "modified": modified,
        "diff_lines": diff_lines,
        "explanation": explanation,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    if hasattr(engine_state, "ws_clients"):
        for q in engine_state.ws_clients:
            try:
                q.put_nowait(event)
            except Exception:
                pass

    return (
        f"Pipeline '{safe_name}' updated successfully. "
        f"Changes pushed for review (edit_id: {edit_id})."
    )


def _compute_diff(original: str, modified: str) -> list[dict]:
    """Compute a line-level diff between original and modified text."""
    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)

    diff = list(difflib.unified_diff(
        orig_lines, mod_lines,
        fromfile="original", tofile="modified",
        lineterm="",
    ))

    result: list[dict] = []
    old_num = 0
    new_num = 0

    for line in diff:
        if line.startswith("@@"):
            continue
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("-"):
            old_num += 1
            result.append({"type": "del", "line": line[1:], "oldLineNum": old_num})
        elif line.startswith("+"):
            new_num += 1
            result.append({"type": "add", "line": line[1:], "newLineNum": new_num})
        else:
            old_num += 1
            new_num += 1
            result.append({"type": "ctx", "line": line[1:] if line.startswith(" ") else line})

    return result


def get_checkpoint_path(edit_id: str) -> Path | None:
    """Get the checkpoint file path for an edit_id, or None."""
    return _checkpoints.get(edit_id)


def get_edit_status(edit_id: str) -> str:
    """Get the status of an edit: 'pending', 'confirmed', 'reverted', or 'unknown'."""
    return _edit_status.get(edit_id, "unknown")


def set_edit_status(edit_id: str, status: str) -> None:
    """Set the status of an edit."""
    _edit_status[edit_id] = status


def delete_checkpoint(edit_id: str) -> bool:
    """Delete the checkpoint file and tracking for an edit_id."""
    cp = _checkpoints.pop(edit_id, None)
    if cp and cp.exists():
        os.remove(str(cp))
        return True
    return False
