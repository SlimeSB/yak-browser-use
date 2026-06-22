"""Pipeline tools — CRUD operations for pipeline files.

Provides load, list, update_step, add_step, remove_step, and create
functions. Read operations return structured summaries. Write operations
reuse tools/edit_pipeline.py for checkpoint + diff + WebSocket safety.

All storage is under workspaces/<name>/ so the pipeline YAML lives
alongside its runs, versions, tools, and checkpoints.
"""

from __future__ import annotations

import json
import time
from pathlib import PurePosixPath

from workspace.manager import WORKSPACES_ROOT

from engine._harness.pipeline_events import push_pipeline_edit_event

import yaml

from compiler.schema import PipelineYaml, StepYaml
from utils.logging import get_logger

logger = get_logger(__name__)

_WORKSPACES_DIR = WORKSPACES_ROOT

_VALID_UPDATE_KEYS = frozenset({
    "browser_ops", "tool_name", "goal_description", "description", "depends_on", "params",
})


def _resolve_pipeline_path(pipeline_name: str) -> Path:
    safe_name = PurePosixPath(pipeline_name).name
    if not safe_name or safe_name != pipeline_name.replace("\\", "/"):
        raise ValueError(f"Invalid pipeline name: {pipeline_name}")
    return _WORKSPACES_DIR / safe_name / "pipeline.yaml"


def _load_pipeline_yaml(pipeline_name: str) -> PipelineYaml:
    path = _resolve_pipeline_path(pipeline_name)
    if not path.exists():
        raise FileNotFoundError(f"Pipeline '{pipeline_name}' not found")
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


async def pipeline_load(pipeline_name: str, **kwargs) -> dict:
    if not pipeline_name:
        return {"ok": False, "error": "pipeline_name is required"}

    try:
        validated = _load_pipeline_yaml(pipeline_name)
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Failed to load pipeline: {e}"}

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

    return {
        "ok": True,
        "name": validated.name,
        "description": validated.description,
        "step_count": len(validated.steps),
        "required_params": validated.required_params,
        "steps": steps,
    }


from compiler.step_type import infer_step_type as _step_type


async def pipeline_list(**kwargs) -> dict:
    if not _WORKSPACES_DIR.exists():
        return {"ok": True, "presets": []}

    presets = []
    for d in sorted(_WORKSPACES_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        pipe_path = d / "pipeline.yaml"
        if not pipe_path.exists():
            continue
        name = d.name
        try:
            raw = yaml.safe_load(pipe_path.read_text(encoding="utf-8")) or {}
            if not isinstance(raw, dict):
                raise ValueError("not a mapping")
            desc = raw.get("description", "")
            steps = raw.get("steps", [])
            step_count = len(steps) if isinstance(steps, list) else 0
        except Exception:
            logger.warning("pipeline_list: failed to parse %s", pipe_path, exc_info=True)
            desc = "(parse error)"
            step_count = 0
        presets.append({
            "name": name,
            "description": desc,
            "step_count": step_count,
        })

    return {"ok": True, "presets": presets}


async def pipeline_update_step(
    pipeline_name: str,
    step_name: str,
    updates: dict,
    explanation: str = "",
    **kwargs,
) -> dict:
    if not updates:
        return {"ok": False, "error": "updates must not be empty"}

    unknown_keys = set(updates) - _VALID_UPDATE_KEYS
    if unknown_keys:
        return {
            "ok": False,
            "error": f"Unknown update keys: {', '.join(sorted(unknown_keys))}. "
                     f"Allowed keys: {', '.join(sorted(_VALID_UPDATE_KEYS))}",
        }

    try:
        validated = _load_pipeline_yaml(pipeline_name)
    except (FileNotFoundError, ValueError) as e:
        return {"ok": False, "error": str(e)}

    target_idx = None
    for i, s in enumerate(validated.steps):
        if s.name == step_name:
            target_idx = i
            break

    if target_idx is None:
        return {"ok": False, "error": f"Step '{step_name}' not found in pipeline '{pipeline_name}'"}

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
    if "params" in updates:
        step_dict["params"] = updates["params"]

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
        return {"ok": False, "error": f"Validation failed: {e}"}

    validated.steps[target_idx] = new_step

    try:
        PipelineYaml.model_validate(validated.model_dump())
    except Exception as e:
        return {"ok": False, "error": f"Pipeline validation failed: {e}"}

    await _write_via_edit_pipeline(pipeline_name, validated, explanation)
    return {"ok": True, "result": f"Step '{step_name}' updated in pipeline '{pipeline_name}'"}


async def pipeline_add_step(
    pipeline_name: str,
    step_name: str,
    description: str,
    browser_ops: list | None = None,
    tool_name: str | None = None,
    goal_description: str | None = None,
    depends_on: list | None = None,
    after: str | None = None,
    heading: bool = False,
    explanation: str = "",
    **kwargs,
) -> dict:
    try:
        validated = _load_pipeline_yaml(pipeline_name)
    except (FileNotFoundError, ValueError) as e:
        return {"ok": False, "error": str(e)}

    for s in validated.steps:
        if s.name == step_name:
            return {
                "ok": False,
                "error": f"Step '{step_name}' already exists in pipeline '{pipeline_name}'",
            }

    step_dict: dict = {
        "name": step_name,
        "description": description,
    }
    if not heading:
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
        return {"ok": False, "error": f"Step validation failed: {e}"}

    if after is not None:
        insert_idx = None
        for i, s in enumerate(validated.steps):
            if s.name == after:
                insert_idx = i + 1
                break
        if insert_idx is None:
            return {"ok": False, "error": f"Anchor step '{after}' not found in pipeline '{pipeline_name}'"}
        validated.steps.insert(insert_idx, new_step)
    else:
        validated.steps.append(new_step)

    try:
        PipelineYaml.model_validate(validated.model_dump())
    except Exception as e:
        return {"ok": False, "error": f"Pipeline validation failed: {e}"}

    await _write_via_edit_pipeline(pipeline_name, validated, explanation)
    return {"ok": True, "result": f"Step '{step_name}' added to pipeline '{pipeline_name}'"}


async def pipeline_remove_step(
    pipeline_name: str,
    step_name: str,
    explanation: str = "",
    **kwargs,
) -> dict:
    try:
        validated = _load_pipeline_yaml(pipeline_name)
    except (FileNotFoundError, ValueError) as e:
        return {"ok": False, "error": str(e)}

    target_idx = None
    for i, s in enumerate(validated.steps):
        if s.name == step_name:
            target_idx = i
            break

    if target_idx is None:
        return {"ok": False, "error": f"Step '{step_name}' not found in pipeline '{pipeline_name}'"}

    validated.steps.pop(target_idx)

    for s in validated.steps:
        if step_name in s.depends_on:
            s.depends_on = [d for d in s.depends_on if d != step_name]

    try:
        PipelineYaml.model_validate(validated.model_dump())
    except Exception as e:
        return {"ok": False, "error": f"Pipeline validation failed: {e}"}

    await _write_via_edit_pipeline(pipeline_name, validated, explanation)
    return {"ok": True, "result": f"Step '{step_name}' removed from pipeline '{pipeline_name}'"}


async def pipeline_create(
    pipeline_name: str,
    description: str,
    steps: list,
    explanation: str = "",
    **kwargs,
) -> dict:
    try:
        path = _resolve_pipeline_path(pipeline_name)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    safe_name = path.parent.name

    step_models = []
    for s in steps:
        try:
            step_models.append(StepYaml.model_validate(s))
        except Exception as e:
            return {"ok": False, "error": f"Step validation failed: {e}"}

    try:
        pipeline = PipelineYaml(
            name=safe_name,
            description=description,
            steps=step_models,
        )
    except Exception as e:
        return {"ok": False, "error": f"Pipeline validation failed: {e}"}

    path.parent.mkdir(parents=True, exist_ok=True)
    content = _dump_pipeline_yaml(pipeline)

    try:
        with open(path, "x", encoding="utf-8") as f:
            f.write(content)
    except FileExistsError:
        return {"ok": False, "error": f"Pipeline '{safe_name}' already exists"}

    from api.state import engine_state

    await push_pipeline_edit_event(
        engine_state,
        edit_id=f"pipe_{int(time.time() * 1000)}",
        original="",
        modified=content,
        explanation=explanation,
    )

    return {"ok": True, "result": f"Pipeline '{safe_name}' created successfully"}


async def pipeline_compile(
    pipeline_name: str,
    explanation: str = "",
    **kwargs,
) -> dict:
    try:
        path = _resolve_pipeline_path(pipeline_name)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    safe_name = path.parent.name

    from api.state import engine_state

    service = getattr(engine_state, "_service", None)
    if service is None:
        return {"ok": False, "error": "No active service"}

    session = getattr(service, "_active_session", None)
    if session is None:
        return {"ok": False, "error": "No active session"}

    messages = getattr(session, "messages", []) or []

    tool_results: dict[str, dict] = {}
    for msg in messages:
        if msg.get("role") == "tool":
            tc_id = msg.get("tool_call_id")
            if tc_id:
                tool_results[tc_id] = msg

    steps: list[dict] = []
    step_index = 1
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        tool_calls = msg.get("tool_calls", [])
        if not tool_calls:
            continue
        for tc in tool_calls:
            fn = tc.get("function", {})
            tool_name = fn.get("name", "")
            args = _parse_tool_args(fn.get("arguments"))
            tc_id = tc.get("id", "")
            tr = tool_results.get(tc_id, {}) if tc_id else {}
            result_text = str(tr.get("content", ""))[:200]

            if tool_name in ("edit_pipeline", "todo", "pipeline_compile", "pipeline_load",
                             "pipeline_list", "pipeline_create", "pipeline_update_step",
                             "pipeline_add_step", "pipeline_remove_step", "pipeline_finish",
                             "record_step"):
                continue

            if tool_name.startswith("browser_"):
                op_type = tool_name.replace("browser_", "")
                steps.append({
                    "name": f"step_{step_index}",
                    "description": f"{op_type}: {_fmt_args(args)}",
                    "browser_ops": [{op_type: _first_arg(args)}],
                })
            elif tool_name == "goal_run":
                steps.append({
                    "name": f"step_{step_index}",
                    "description": args.get("description", "") or result_text[:80],
                    "goal_description": args.get("description", "") or result_text[:200],
                })
            else:
                params = {k: v for k, v in args.items() if k not in ("image_bytes", "background_bytes")}
                steps.append({
                    "name": f"step_{step_index}",
                    "description": f"{tool_name}: {_fmt_args(args)}",
                    "tool_name": tool_name,
                    "params": params or None,
                })
            step_index += 1

    if not steps:
        return {"ok": False, "error": "No browser operations found in session"}

    return {
        "ok": True,
        "pipeline_name": safe_name,
        "step_count": len(steps),
        "steps": steps,
        "hint": (
            "Review the steps above. Add 'check' fields, refine descriptions, "
            "adjust browser_ops as needed, then use pipeline_create to save "
            "(or edit_pipeline if the pipeline already exists)."
        ),
    }


def _parse_tool_args(raw_args) -> dict:
    if isinstance(raw_args, dict):
        return raw_args
    if isinstance(raw_args, str) and raw_args.strip():
        try:
            return json.loads(raw_args)
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def _fmt_args(args: dict) -> str:
    if not args:
        return ""
    items = []
    for k, v in args.items():
        s = str(v)
        if len(s) > 60:
            s = s[:57] + "..."
        items.append(f"{k}={s}")
    return ", ".join(items)


def _first_arg(args: dict) -> str:
    if not args:
        return ""
    first = next(iter(args.values()), "")
    return str(first)[:200]


