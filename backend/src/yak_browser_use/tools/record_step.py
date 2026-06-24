"""record_step tool — LLM calls this to append a step to pipeline.yaml.

Each call appends one step to the pipeline. On first call, creates the
pipeline file. Pushes a pipeline.edit WebSocket event for diff review.
"""

from __future__ import annotations

from pathlib import Path

from yak_browser_use.workspace.manager import WORKSPACES_ROOT

from yak_browser_use.engine._harness.pipeline_events import push_pipeline_edit_event

from yak_browser_use.utils.helpers import sanitize_pipeline_name
from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)

_WORKSPACES_DIR = WORKSPACES_ROOT

_pipeline_edit_id: dict[str, str] = {}


async def record_step(
    pipeline_name: str,
    step_name: str,
    description: str,
    op_type: str | None = None,
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
            When omitted, creates an outline placeholder step with only name + description.
        op_args: Arguments passed to the operation.
        explanation: Why this step is needed.

    Returns:
        Status message.
    """
    import yaml

    try:
        safe_name = sanitize_pipeline_name(pipeline_name)
    except ValueError:
        return f"Invalid pipeline name: {pipeline_name}"

    pipeline_path = _WORKSPACES_DIR / safe_name / "pipeline.yaml"
    pipeline_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing pipeline or create new
    if pipeline_path.exists():
        try:
            data = yaml.safe_load(pipeline_path.read_text(encoding="utf-8")) or {}
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

    if op_type is not None:
        if op_type == "goal_run":
            if op_args:
                step_entry["goal_description"] = op_args.get("description", description)
            else:
                step_entry["goal_description"] = description
        else:
            browser_op: dict
            if op_args and "value" in op_args and len(op_args) == 1:
                browser_op = {op_type: op_args["value"]}
            else:
                browser_op = {op_type: op_args or {}}
            step_entry["browser_ops"] = [browser_op]

    # Append or update step
    existing_idx = next((i for i, s in enumerate(steps) if s.get("name") == step_name), None)
    if existing_idx is not None:
        steps[existing_idx] = step_entry
    else:
        steps.append(step_entry)
        logger.debug("Recording step %s%s", step_name, f": {op_type}" if op_type else "")

    # Save checkpoint before writing
    original = pipeline_path.read_text(encoding="utf-8") if pipeline_path.exists() else ""

    # Write back
    new_content = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    pipeline_path.write_text(new_content, encoding="utf-8")

    # Push pipeline.edit event for review
    from yak_browser_use.api.state import engine_state
    from yak_browser_use.tools.edit_pipeline import get_checkpoint_path, get_edit_status, register_edit

    existing_edit_id = _pipeline_edit_id.get(safe_name)

    if existing_edit_id and get_edit_status(existing_edit_id) == "pending":
        edit_id = existing_edit_id
        cp = get_checkpoint_path(edit_id)
        if cp and cp.exists():
            original = cp.read_text(encoding="utf-8")
    else:
        edit_id = f"rec_{safe_name}_{int(time.time() * 1000)}"
        checkpoint_path = _WORKSPACES_DIR / safe_name / f"{edit_id}.orig"
        checkpoint_path.write_text(original, encoding="utf-8")
        logger.debug("Saved checkpoint: %s", checkpoint_path)
        register_edit(edit_id, checkpoint_path, safe_name)
        _pipeline_edit_id[safe_name] = edit_id

    await push_pipeline_edit_event(
        engine_state,
        edit_id=edit_id,
        original=original,
        modified=new_content,
        explanation=explanation or f"Recorded step: {step_name}",
    )

    return f"Step '{step_name}' recorded: {description}"
