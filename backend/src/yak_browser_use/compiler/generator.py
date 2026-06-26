"""
generator.py — LLM-driven code generation and Action→Ops mapping.

Generates Python handler code from step descriptions and browser_ops,
maps CDP/Selenium actions to the browser_ops format, extracts selectors
from interacted elements, and writes learned ops back to pipeline.yaml files.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from yak_browser_use.compiler.models import StepDef
from yak_browser_use.prompts._loader import load_prompt
from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)


# ── Prompt building ──


def generate_handler_prompt(step_def: StepDef) -> str:
    """Build the LLM prompt for creating a step handler function."""
    logger.debug("generator: generate_handler_prompt for step '%s'", step_def.name)
    step_info = {
        "name": step_def.name,
        "key": step_def.key,
        "description": step_def.description,
        "browser_ops": step_def.browser_ops,
        "input_schema": step_def.input_schema,
        "output_schema": step_def.output_schema,
        "depends_on": step_def.depends_on,
    }
    step_yaml = json.dumps(step_info, ensure_ascii=False, indent=2)

    high_level_tools = ""  # Tool registry is not injected in this version
    result = load_prompt("generate-handler").format(
        step_yaml=step_yaml,
        high_level_tools=high_level_tools,
    )
    logger.debug("generator: generate_handler_prompt result: %s chars", len(result))
    return result


async def generate_handler(
    step_def: StepDef,
    pipeline_name: str,
) -> str | None:
    """Generate a Python handler via LLM and cache it to disk.

    Args:
        step_def: The step definition to generate a handler for.
        pipeline_name: Pipeline name for caching the generated file.

    Returns:
        Generated code as string, or None if generation failed.
    """
    logger.debug(
        "generator: generate_handler for step '%s' in pipeline '%s'",
        step_def.key, pipeline_name,
    )
    from yak_browser_use.utils.browser import create_llm
    from yak_browser_use.llm.messages import UserMessage

    prompt = generate_handler_prompt(step_def)
    llm = create_llm()

    try:
        response = await llm.ainvoke([UserMessage(content=prompt)])
        text = response.content or str(response)

        code = _extract_python_code(text)
        if code:
            _cache_generated_handler(pipeline_name, step_def.key, code)
            logger.debug("generator: generate_handler success for step '%s'", step_def.key)
            return code
    except Exception:
        logger.exception("generator: LLM invocation failed for step '%s'", step_def.key)

    logger.debug("generator: generate_handler failed for step '%s'", step_def.key)
    return None


def _extract_python_code(text: str) -> str:
    """Extract Python code from LLM response, stripping markdown fences."""
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    if "async def handle" in text or "def handle" in text:
        return text.strip()
    return ""


def _cache_generated_handler(pipeline_name: str, step_key: str, code: str) -> None:
    """Persist a generated handler to disk under generated/<pipeline>/."""
    cache_dir = Path("generated") / pipeline_name
    cache_dir.mkdir(parents=True, exist_ok=True)
    handler_file = cache_dir / f"{step_key}.py"
    handler_file.write_text(code, encoding="utf-8")
    logger.debug("Cached handler to %s", handler_file)


def compile_handler_code(code: str) -> Callable | None:
    """Compile a handler code string into a callable via exec()."""
    logger.debug("generator: compile_handler_code: %s chars", len(code))
    import importlib.util
    import sys

    module_name = f"__generated_handler_{hash(code) & 0xFFFFFFFF}"
    try:
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        if spec is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        exec(code, module.__dict__)

        if hasattr(module, "handle"):
            logger.debug("generator: compile_handler_code found 'handle'")
            return module.handle
        if hasattr(module, "main"):
            logger.debug("generator: compile_handler_code found 'main'")
            return module.main
        if hasattr(module, "run"):
            logger.debug("generator: compile_handler_code found 'run'")
            return module.run
    except Exception:
        logger.exception("generator: compile_handler_code failed")

    logger.debug("generator: compile_handler_code could not locate a callable")
    return None


# ── Action → CDP Ops mapping ──


def extract_selectors(el) -> list[str]:
    """Extract CSS selectors and XPath from an interacted element."""
    logger.debug("generator: extract_selectors called")
    selectors: list[str] = []
    if not el:
        return selectors
    attrs = getattr(el, "attributes", {}) or {}
    if isinstance(attrs, dict):
        el_id = attrs.get("id")
        if el_id:
            selectors.append(f"#{el_id}")
        testid = attrs.get("data-testid")
        if testid:
            selectors.append(f"[data-testid='{testid}']")
    ax_name = getattr(el, "ax_name", "") or ""
    if ax_name:
        selectors.append(ax_name)
    xpath = getattr(el, "x_path", "") or ""
    if xpath:
        selectors.append(xpath)
    logger.debug("generator: extract_selectors result: %d selectors", len(selectors))
    return selectors


def _model_action_to_op(action) -> dict | None:
    """Map a browser_use model action to a browser_ops dict entry."""
    action_name = _get_action_name(action)
    params = _get_action_params(action)

    if not action_name:
        return None
    if action_name == "done":
        return None

    mapping = {
        "navigate": ("goto", lambda p: {"type": "goto", "value": p.get("url", "")}),
        "click": ("click", lambda p: _build_click_op(p, action)),
        "input": ("fill", lambda p: _build_fill_op(p, action)),
        "scroll": ("js", lambda p: {"type": "js", "code": f"window.scrollBy(0, {p.get('amount', 300)})"}),
        "go_back": ("js", lambda p: {"type": "js", "code": "window.history.back()"}),
        "wait": ("wait_for_network", lambda p: {"type": "wait_for_network", "value": ""}),
    }

    if action_name in mapping:
        _, factory = mapping[action_name]
        return factory(params)

    # Unknown action — pass through as-is
    return None


def _build_click_op(params: dict, action) -> dict | None:
    el = _get_interacted_element(action)
    selectors = extract_selectors(el)
    if not selectors:
        return None
    bounds = _get_bounds(el)
    op: dict = {"type": "click", "value": selectors[0], "selectors": selectors}
    if bounds:
        op["bounds"] = bounds
    return op


def _build_fill_op(params: dict, action) -> dict:
    value = params.get("text", params.get("value", ""))
    el = _get_interacted_element(action)
    selectors = extract_selectors(el)
    op: dict = {"type": "fill", "selector": selectors[0] if selectors else "", "value": value}
    return op


def _get_action_name(action) -> str:
    if hasattr(action, "action_name"):
        return action.action_name
    if isinstance(action, dict):
        return action.get("action_name", action.get("type", ""))
    return ""


def _get_action_params(action) -> dict:
    if hasattr(action, "params"):
        return getattr(action, "params", {}) or {}
    if hasattr(action, "model_dump"):
        return action.model_dump()
    if isinstance(action, dict):
        return {k: v for k, v in action.items() if k not in ("action_name", "type", "interacted_element")}
    return {}


def _get_interacted_element(action):
    if hasattr(action, "interacted_element"):
        return action.interacted_element
    if isinstance(action, dict):
        return action.get("interacted_element")
    return None


def _get_bounds(el) -> list | None:
    if not el:
        return None
    bounds = getattr(el, "bounds", None)
    if bounds:
        if hasattr(bounds, "x") and hasattr(bounds, "width"):
            return [bounds.x, bounds.y, bounds.width, bounds.height]
        if isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
            return list(bounds[:4])
    return None


def model_actions_to_ops(model_actions) -> list[dict]:
    """Convert a list of browser_use ModelActions to browser_ops format.

    Args:
        model_actions: Iterable of action objects from browser_use.

    Returns:
        list[dict] of ops in {type, value, ...} format.
    """
    logger.debug("generator: model_actions_to_ops: %d actions", len(model_actions))
    ops: list[dict] = []
    for action in model_actions:
        op = _model_action_to_op(action)
        if op:
            ops.append(op)
    logger.debug("generator: model_actions_to_ops result: %d ops", len(ops))
    return ops


# ── Write-back to pipeline.yaml ──

from yak_browser_use.compiler.pipeline_store import PipelineStore


def write_pipeline_learned(
    yaml_text: str,
    step_name: str,
    new_browser_ops: list[dict],
) -> str:
    """Write newly learned browser_ops back into a pipeline.yaml step.

    Parses the YAML via PipelineStore, finds the step by name, sets
    browser_ops (already internal format — no conversion needed on load),
    and returns the updated YAML text.

    Args:
        yaml_text: Full pipeline.yaml text.
        step_name: Name of the step to update.
        new_browser_ops: List of op dicts in internal format {type, value, ...}.

    Returns:
        Updated pipeline.yaml text.
    """
    try:
        pipeline = PipelineStore.from_yaml(yaml_text)
    except Exception:
        logger.warning("write_pipeline_learned: invalid YAML structure, returning original")
        return yaml_text

    for step in pipeline.steps:
        if step.name == step_name:
            step.browser_ops = new_browser_ops
            logger.debug("write_pipeline_learned: updated step '%s'", step_name)
            break
    else:
        logger.warning("write_pipeline_learned: step '%s' not found, returning original", step_name)
        return yaml_text

    return PipelineStore.to_yaml(pipeline)
