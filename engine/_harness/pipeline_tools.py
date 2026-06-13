"""Pipeline tools — CRUD operations for pipeline preset files.

Provides load, list, update_step, add_step, remove_step, and create
functions. Read operations return structured summaries. Write operations
reuse tools/edit_pipeline.py for checkpoint + diff + WebSocket safety.

All public functions are async to match the dispatch pattern in
tool_executor.py, even though they perform synchronous I/O internally.
"""

from __future__ import annotations

import json
import time
from pathlib import Path, PurePosixPath

import yaml

from compiler.schema import PipelineYaml, StepYaml
from utils.logging import get_logger

logger = get_logger(__name__)

PRESETS_DIR = Path.home() / ".ybu" / "sessions" / "presets"

_VALID_UPDATE_KEYS = frozenset({
    "browser_ops", "tool_name", "goal_description", "description", "depends_on",
})


def _resolve_pipeline_path(pipeline_name: str) -> Path:
    safe_name = PurePosixPath(pipeline_name).name
    if not safe_name or safe_name != pipeline_name.replace("\\", "/"):
        raise ValueError(f"Invalid pipeline name: {pipeline_name}")
    return PRESETS_DIR / f"{safe_name}.pipeline.yaml"


def _load_pipeline_yaml(pipeline_name: str) -> PipelineYaml:
    path = _resolve_pipeline_path(pipeline_name)
    if not path.exists():
        raise FileNotFoundError(f"Pipeline preset '{pipeline_name}' not found")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Pipeline '{pipeline_name}' is not a valid YAML mapping")
    return PipelineYaml.model_validate(raw)


def _dump_pipeline_yaml(pipeline: PipelineYaml) -> str:
    return yaml.dump(
        pipeline.model_dump(exclude_defaults=True),
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )


async def _write_via_edit_pipeline(
    pipeline_name: str,
    pipeline: PipelineYaml,
    explanation: str,
) -> str:
    from tools.edit_pipeline import edit_pipeline

    content = _dump_pipeline_yaml(pipeline)
    result = await edit_pipeline(
        pipeline_name=pipeline_name,
        content=content,
        explanation=explanation,
    )
    return result


async def pipeline_load(pipeline_name: str, **kwargs) -> str:
    if not pipeline_name:
        return json.dumps({"ok": False, "error": "pipeline_name is required"})

    try:
        validated = _load_pipeline_yaml(pipeline_name)
    except FileNotFoundError as e:
        return json.dumps({"ok": False, "error": str(e)})
    except Exception as e:
        return json.dumps({"ok": False, "error": f"Failed to load pipeline: {e}"})

    steps = []
    for s in validated.steps:
        step_info: dict = {
            "name": s.name,
            "type": _step_type(s),
            "description": s.description,
            "depends_on": s.depends_on,
        }
        if s.tool_name:
            step_info["tool_name"] = s.tool_name
        if s.browser_ops is not None:
            step_info["browser_op_count"] = len(s.browser_ops)
        steps.append(step_info)

    return json.dumps({
        "ok": True,
        "name": validated.name,
        "description": validated.description,
        "step_count": len(validated.steps),
        "required_params": validated.required_params,
        "steps": steps,
    }, ensure_ascii=False)


def _step_type(step: StepYaml) -> str:
    if step.browser_ops is not None:
        return "browser"
    if step.tool_name is not None:
        return "tool"
    return "goal"


async def pipeline_list(**kwargs) -> str:
    if not PRESETS_DIR.exists():
        return json.dumps({"ok": True, "presets": []})

    presets = []
    for f in sorted(PRESETS_DIR.glob("*.pipeline.yaml")):
        name = f.stem.removesuffix(".pipeline")
        try:
            raw = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            if not isinstance(raw, dict):
                raise ValueError("not a mapping")
            desc = raw.get("description", "")
            steps = raw.get("steps", [])
            step_count = len(steps) if isinstance(steps, list) else 0
        except Exception:
            logger.warning("pipeline_list: failed to parse %s", f, exc_info=True)
            desc = "(parse error)"
            step_count = 0
        presets.append({
            "name": name,
            "description": desc,
            "step_count": step_count,
        })

    return json.dumps({"ok": True, "presets": presets}, ensure_ascii=False)


async def pipeline_update_step(
    pipeline_name: str,
    step_name: str,
    updates: dict,
    explanation: str = "",
    **kwargs,
) -> str:
    if not updates:
        return json.dumps({"ok": False, "error": "updates must not be empty"})

    unknown_keys = set(updates) - _VALID_UPDATE_KEYS
    if unknown_keys:
        return json.dumps({
            "ok": False,
            "error": f"Unknown update keys: {', '.join(sorted(unknown_keys))}. "
                     f"Allowed keys: {', '.join(sorted(_VALID_UPDATE_KEYS))}",
        })

    try:
        validated = _load_pipeline_yaml(pipeline_name)
    except (FileNotFoundError, ValueError) as e:
        return json.dumps({"ok": False, "error": str(e)})

    target_idx = None
    for i, s in enumerate(validated.steps):
        if s.name == step_name:
            target_idx = i
            break

    if target_idx is None:
        return json.dumps({"ok": False, "error": f"Step '{step_name}' not found in pipeline '{pipeline_name}'"})

    step = validated.steps[target_idx]
    step_dict = step.model_dump()

    type_fields_in_updates = [
        k for k in ("browser_ops", "tool_name", "goal_description") if k in updates
    ]

    if "browser_ops" in updates:
        step_dict["browser_ops"] = updates["browser_ops"]
    if "tool_name" in updates:
        step_dict["tool_name"] = updates["tool_name"]
    if "goal_description" in updates:
        step_dict["goal_description"] = updates["goal_description"]

    if len(type_fields_in_updates) == 1:
        for other in ("browser_ops", "tool_name", "goal_description"):
            if other not in updates:
                step_dict[other] = None

    if "description" in updates:
        step_dict["description"] = updates["description"]
    if "depends_on" in updates:
        step_dict["depends_on"] = updates["depends_on"]

    try:
        new_step = StepYaml.model_validate(step_dict)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"Validation failed: {e}"})

    validated.steps[target_idx] = new_step

    try:
        PipelineYaml.model_validate(validated.model_dump())
    except Exception as e:
        return json.dumps({"ok": False, "error": f"Pipeline validation failed: {e}"})

    await _write_via_edit_pipeline(pipeline_name, validated, explanation)
    return json.dumps({"ok": True, "result": f"Step '{step_name}' updated in pipeline '{pipeline_name}'"})


async def pipeline_add_step(
    pipeline_name: str,
    step_name: str,
    description: str,
    browser_ops: list | None = None,
    tool_name: str | None = None,
    goal_description: str | None = None,
    depends_on: list | None = None,
    after: str | None = None,
    explanation: str = "",
    **kwargs,
) -> str:
    try:
        validated = _load_pipeline_yaml(pipeline_name)
    except (FileNotFoundError, ValueError) as e:
        return json.dumps({"ok": False, "error": str(e)})

    for s in validated.steps:
        if s.name == step_name:
            return json.dumps({
                "ok": False,
                "error": f"Step '{step_name}' already exists in pipeline '{pipeline_name}'",
            })

    step_dict: dict = {
        "name": step_name,
        "description": description,
    }
    if browser_ops is not None:
        step_dict["browser_ops"] = browser_ops
    if tool_name is not None:
        step_dict["tool_name"] = tool_name
    if goal_description is not None:
        step_dict["goal_description"] = goal_description
    if depends_on is not None:
        step_dict["depends_on"] = depends_on

    try:
        new_step = StepYaml.model_validate(step_dict)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"Step validation failed: {e}"})

    if after is not None:
        insert_idx = None
        for i, s in enumerate(validated.steps):
            if s.name == after:
                insert_idx = i + 1
                break
        if insert_idx is None:
            return json.dumps({"ok": False, "error": f"Anchor step '{after}' not found in pipeline '{pipeline_name}'"})
        validated.steps.insert(insert_idx, new_step)
    else:
        validated.steps.append(new_step)

    try:
        PipelineYaml.model_validate(validated.model_dump())
    except Exception as e:
        return json.dumps({"ok": False, "error": f"Pipeline validation failed: {e}"})

    await _write_via_edit_pipeline(pipeline_name, validated, explanation)
    return json.dumps({"ok": True, "result": f"Step '{step_name}' added to pipeline '{pipeline_name}'"})


async def pipeline_remove_step(
    pipeline_name: str,
    step_name: str,
    explanation: str = "",
    **kwargs,
) -> str:
    try:
        validated = _load_pipeline_yaml(pipeline_name)
    except (FileNotFoundError, ValueError) as e:
        return json.dumps({"ok": False, "error": str(e)})

    target_idx = None
    for i, s in enumerate(validated.steps):
        if s.name == step_name:
            target_idx = i
            break

    if target_idx is None:
        return json.dumps({"ok": False, "error": f"Step '{step_name}' not found in pipeline '{pipeline_name}'"})

    validated.steps.pop(target_idx)

    for s in validated.steps:
        if step_name in s.depends_on:
            s.depends_on = [d for d in s.depends_on if d != step_name]

    try:
        PipelineYaml.model_validate(validated.model_dump())
    except Exception as e:
        return json.dumps({"ok": False, "error": f"Pipeline validation failed: {e}"})

    await _write_via_edit_pipeline(pipeline_name, validated, explanation)
    return json.dumps({"ok": True, "result": f"Step '{step_name}' removed from pipeline '{pipeline_name}'"})


async def pipeline_create(
    pipeline_name: str,
    description: str,
    steps: list,
    explanation: str = "",
    **kwargs,
) -> str:
    try:
        path = _resolve_pipeline_path(pipeline_name)
    except ValueError as e:
        return json.dumps({"ok": False, "error": str(e)})

    safe_name = path.stem.removesuffix(".pipeline")

    step_models = []
    for s in steps:
        try:
            step_models.append(StepYaml.model_validate(s))
        except Exception as e:
            return json.dumps({"ok": False, "error": f"Step validation failed: {e}"})

    try:
        pipeline = PipelineYaml(
            name=safe_name,
            description=description,
            steps=step_models,
        )
    except Exception as e:
        return json.dumps({"ok": False, "error": f"Pipeline validation failed: {e}"})

    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    content = _dump_pipeline_yaml(pipeline)

    try:
        with open(path, "x", encoding="utf-8") as f:
            f.write(content)
    except FileExistsError:
        return json.dumps({"ok": False, "error": f"Pipeline '{safe_name}' already exists"})

    _push_ws_event(safe_name, "", content, explanation)

    return json.dumps({"ok": True, "result": f"Pipeline '{safe_name}' created successfully"})


def _push_ws_event(pipeline_name: str, original: str, modified: str, explanation: str) -> None:
    import difflib

    from api.state import engine_state

    edit_id = f"pipe_{int(time.time() * 1000)}"

    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        orig_lines, mod_lines,
        fromfile="original", tofile="modified", lineterm="",
    ))

    diff_lines: list[dict] = []
    old_num = 0
    new_num = 0
    for line in diff:
        if line.startswith("@@") or line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("-"):
            old_num += 1
            diff_lines.append({"type": "del", "line": line[1:], "oldLineNum": old_num})
        elif line.startswith("+"):
            new_num += 1
            diff_lines.append({"type": "add", "line": line[1:], "newLineNum": new_num})
        else:
            old_num += 1
            new_num += 1
            diff_lines.append({"type": "ctx", "line": line[1:] if line.startswith(" ") else line})

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
                logger.warning("_push_ws_event: failed to push event to a WS client", exc_info=True)
