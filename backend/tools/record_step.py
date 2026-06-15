"""record_step tool — LLM calls this to append a step to pipeline.yaml.

Each call appends one step to the pipeline. On first call, creates the
pipeline file. Pushes a pipeline.edit WebSocket event for diff review.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)

PRESETS_DIR = Path(__file__).resolve().parent.parent.parent / "userdata" / "presets"

_pipeline_edit_id: dict[str, str] = {}


async def record_step(
    pipeline_name: str,
    step_name: str,
    description: str,
    op_type: str,
    op_args: dict | None = None,
    explanation: str = "",
    **kwargs,
) -> str:
    """Record a browser operation as a step in pipeline.yaml.

    Args:
        pipeline_name: Name of the pipeline preset.
        step_name: Unique step name (e.g. 'step_1').
        description: Human-readable description.
        op_type: Operation type (goto, click, fill, scroll, snapshot, source, eval, goal_run).
        op_args: Arguments passed to the operation.
        explanation: Why this step is needed.

    Returns:
        Status message.
    """
    import yaml

    safe_name = os.path.basename(pipeline_name.replace("\\", "/"))
    if not safe_name or safe_name != pipeline_name.replace("\\", "/"):
        return f"Invalid pipeline name: {pipeline_name}"

    preset_path = PRESETS_DIR / f"{safe_name}.pipeline.yaml"
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing pipeline or create new
    if preset_path.exists():
        try:
            data = yaml.safe_load(preset_path.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
    else:
        data = {}
        logger.info("Creating new pipeline: %s", safe_name)

    if not isinstance(data, dict):
        data = {}

    data.setdefault("name", safe_name)
    data.setdefault("description", f"Recorded pipeline: {safe_name}")
    steps = data.setdefault("steps", [])
    if not isinstance(steps, list):
        steps = []
        data["steps"] = steps

    # Build step entry
    step_entry: dict = {
        "name": step_name,
        "description": description,
    }

    if op_type == "goal_run":
        step_entry["goal_description"] = op_args.get("description", description) if op_args else description
    else:
        browser_op: dict = {op_type: op_args.get("value", "") if op_args and "value" in op_args else (op_args or {})}
        step_entry["browser_ops"] = [browser_op]

    # Append or update step
    existing_idx = next((i for i, s in enumerate(steps) if s.get("name") == step_name), None)
    if existing_idx is not None:
        steps[existing_idx] = step_entry
    else:
        steps.append(step_entry)
        logger.debug("Recording step %s: %s", step_name, op_type)

    # Save checkpoint before writing
    original = preset_path.read_text(encoding="utf-8") if preset_path.exists() else ""

    # Write back
    new_content = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    preset_path.write_text(new_content, encoding="utf-8")

    # Push pipeline.edit event for review
    _push_edit_event(safe_name, original, new_content, step_name, explanation or f"Recorded step: {step_name}")

    return f"Step '{step_name}' recorded: {description}"


def _push_edit_event(pipeline_name: str, original: str, modified: str, step_name: str, explanation: str) -> None:
    """Push a pipeline.edit event to WebSocket clients. Reuses edit_id across
    multiple record_step calls so the frontend accumulates diffs as a batch."""
    import difflib

    from api.state import engine_state
    from tools.edit_pipeline import _checkpoints, _processed_edits, _edit_status

    existing_edit_id = _pipeline_edit_id.get(pipeline_name)

    if existing_edit_id and _edit_status.get(existing_edit_id) == "pending":
        edit_id = existing_edit_id
        cp = _checkpoints.get(edit_id)
        if cp and cp.exists():
            original = cp.read_text(encoding="utf-8")
    else:
        edit_id = f"rec_{pipeline_name}_{int(time.time() * 1000)}"
        checkpoint_path = PRESETS_DIR / f"{pipeline_name}.pipeline.yaml.{edit_id}.orig"
        checkpoint_path.write_text(original, encoding="utf-8")
        logger.debug("Saved checkpoint: %s", checkpoint_path)
        _checkpoints[edit_id] = checkpoint_path
        _processed_edits.add(edit_id)
        _edit_status[edit_id] = "pending"
        _pipeline_edit_id[pipeline_name] = edit_id

    diff_lines = list(difflib.unified_diff(
        original.splitlines(keepends=True),
        modified.splitlines(keepends=True),
        fromfile="original", tofile="modified", lineterm="",
    ))

    event = {
        "type": "pipeline.edit",
        "edit_id": edit_id,
        "original": original,
        "modified": modified,
        "diff_lines": [l for l in diff_lines if not l.startswith("---") and not l.startswith("+++")],
        "explanation": explanation,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    if hasattr(engine_state, "ws_clients"):
        for q in engine_state.ws_clients:
            try:
                q.put_nowait(event)
            except Exception:
                pass
