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

from yak_browser_use.workspace.manager import WORKSPACES_ROOT

from yak_browser_use.engine._harness.pipeline_events import push_pipeline_edit_event

from yak_browser_use.compiler.pipeline_store import PipelineMeta, PipelineStore
from yak_browser_use.compiler.schema import PipelineYaml, StepYaml
from yak_browser_use.utils.helpers import sanitize_pipeline_name
from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)

_WORKSPACES_DIR = WORKSPACES_ROOT

def _get_store() -> PipelineStore:
    return PipelineStore(workspaces_root=_WORKSPACES_DIR)

_VALID_UPDATE_KEYS = None  # None = no restriction (deep-path keys allowed)


def _resolve_pipeline_path(pipeline_name: str) -> Path:
    safe_name = sanitize_pipeline_name(pipeline_name)
    return _WORKSPACES_DIR / safe_name / "pipeline.yaml"


def _load_pipeline_yaml(pipeline_name: str) -> PipelineYaml:
    return _get_store().load(pipeline_name)


def _dump_pipeline_yaml(pipeline: PipelineYaml) -> str:
    return PipelineStore.to_yaml(pipeline)


async def _write_via_edit_pipeline(
    pipeline_name: str,
    pipeline: PipelineYaml,
    explanation: str,
) -> str:
    from yak_browser_use.tools.edit_pipeline import edit_pipeline

    content = _dump_pipeline_yaml(pipeline)
    result = await edit_pipeline(
        pipeline_name=pipeline_name,
        content=content,
        explanation=explanation,
    )
    return result


from yak_browser_use.compiler.step_type import infer_step_type as _step_type


async def pipeline_view(name: str | None = None, **kwargs) -> dict:
    """View pipeline(s). Without name: list all presets. With name: load full details."""
    if name is None:
        if not _WORKSPACES_DIR.exists():
            return {"ok": True, "presets": []}
        presets = []
        for d in sorted(_WORKSPACES_DIR.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            if not (d / "pipeline.yaml").exists():
                continue
            try:
                meta = _get_store().load_meta(d.name)
            except Exception:
                logger.warning("pipeline_view: failed to parse %s", d / "pipeline.yaml", exc_info=True)
                meta = PipelineMeta(name=d.name, description="(parse error)", step_count=0)
            presets.append({
                "name": meta.name,
                "description": meta.description,
                "step_count": meta.step_count,
            })
        return {"ok": True, "presets": presets}

    try:
        validated = _get_store().load(name)
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
        if s.params:
            step_info["params"] = s.params
        if s.goal_description:
            step_info["goal_description"] = s.goal_description
        if s.browser_ops is not None:
            step_info["browser_ops"] = PipelineStore.ops_to_yaml(s.browser_ops)
        if s.check is not None:
            step_info["check"] = s.check
        steps.append(step_info)

    return {
        "ok": True,
        "name": validated.name,
        "description": validated.description,
        "step_count": len(validated.steps),
        "required_params": validated.required_params,
        "steps": steps,
    }


async def pipeline_update_step(
    pipeline_name: str,
    steps_updates: dict | None = None,
    step_name: str | None = None,
    updates: dict | None = None,
    explanation: str = "",
    **kwargs,
) -> dict:
    if steps_updates is None and step_name is not None and updates is not None:
        steps_updates = {step_name: updates}

    if not steps_updates:
        return {"ok": False, "error": "必须提供 steps_updates（或 step_name + updates）"}

    try:
        validated = _load_pipeline_yaml(pipeline_name)
    except (FileNotFoundError, ValueError) as e:
        return {"ok": False, "error": str(e)}

    store = _get_store()
    errors: list[str] = []
    updated_steps: list[str] = []
    for s_name, s_updates in steps_updates.items():
        if not s_updates:
            errors.append(f"[{s_name}] updates must not be empty")
            continue
        try:
            store.update_step(validated, s_name, s_updates)
            updated_steps.append(s_name)
        except ValueError as e:
            errors.append(f"[{s_name}] {e}")
        except Exception as e:
            errors.append(f"[{s_name}] Validation failed: {e}")

    if errors:
        return {"ok": False, "error": "\n".join(errors)}

    step_names_str = ", ".join(updated_steps)
    await _write_via_edit_pipeline(pipeline_name, validated, explanation)
    return {"ok": True, "result": f"已在 pipeline '{pipeline_name}' 中更新 {len(updated_steps)} 个步骤: {step_names_str}"}


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
    check: dict | None = None,
    explanation: str = "",
    op_type: str | None = None,
    op_args: dict | None = None,
    **kwargs,
) -> dict:
    try:
        validated = _load_pipeline_yaml(pipeline_name)
    except (FileNotFoundError, ValueError) as e:
        return {"ok": False, "error": str(e)}

    step_dict: dict = {
        "name": step_name,
        "description": description,
    }
    if op_type is not None:
        browser_op: dict
        if op_args and "value" in op_args and len(op_args) == 1:
            browser_op = {op_type: op_args["value"]}
        else:
            browser_op = {op_type: op_args or {}}
        step_dict["browser_ops"] = [browser_op]
    elif not heading:
        if browser_ops is not None:
            step_dict["browser_ops"] = browser_ops
        if tool_name is not None:
            step_dict["tool_name"] = tool_name
        if goal_description is not None:
            step_dict["goal_description"] = goal_description
    if depends_on is not None:
        step_dict["depends_on"] = depends_on
    if check is not None:
        step_dict["check"] = check

    try:
        new_step = StepYaml.model_validate(step_dict)
    except Exception as e:
        return {"ok": False, "error": f"Step validation failed: {e}"}

    try:
        _get_store().add_step(validated, new_step, after=after)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
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

    try:
        _get_store().remove_step(validated, step_name)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
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
    if path.exists():
        return {"ok": False, "error": f"Pipeline '{safe_name}' already exists"}

    content = _get_store().save(pipeline_name, pipeline)

    from yak_browser_use.api.state import engine_state

    await push_pipeline_edit_event(
        engine_state,
        edit_id=f"pipe_{int(time.time() * 1000)}",
        original="",
        modified=content,
        explanation=explanation,
    )

    try:
        service = getattr(engine_state, "_service", None)
        if service is not None:
            sessions_mgr = getattr(service, "sessions", None)
            if sessions_mgr is not None and sessions_mgr.active_pipeline == "__chat__":
                sessions_mgr.migrate_session("__chat__", safe_name)
    except Exception:
        logger.warning("pipeline_create: failed to migrate session", exc_info=True)

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

    from yak_browser_use.api.state import engine_state

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

            if tool_name in ("edit_pipeline", "todo", "pipeline_compile", "pipeline_view",
                             "pipeline_create", "pipeline_update_step",
                             "pipeline_add_step", "pipeline_remove_step", "pipeline_finish"):
                continue

            if tool_name.startswith("browser_"):
                op_type = tool_name.replace("browser_", "")
                internal_ops = [{"type": op_type, "value": _first_arg(args)}]
                steps.append({
                    "name": f"step_{step_index}",
                    "description": f"{op_type}: {_fmt_args(args)}",
                    "browser_ops": PipelineStore.ops_to_yaml(internal_ops),
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
            "Review the steps above. Add 'check' fields (必填 — 每步必须显式声明验收条件，"
            "不可省略或传 {}。支持: url_contains/element_exists/text_contains/"
            "element_visible/output_exists/file_contains/js_expression/"
            "json_field_exists/ignore), refine descriptions, "
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


