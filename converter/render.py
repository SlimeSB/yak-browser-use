"""
render.py — Pure rendering of step definitions to agent.md format.

This module handles the rendering of expanded step definitions into
standard agent.md format. It performs NO LLM calls — it is purely
a formatting/serialization layer.
"""
from __future__ import annotations

import re
from typing import Any

from utils.logging import get_logger

logger = get_logger(__name__)


def render_steps_to_agent_md(
    steps: list[dict],
    pipeline_name: str = "auto_generated",
    description: str = "",
    required_params: list[str] | None = None,
) -> str:
    """Render expanded step definitions to standard agent.md format string.

    This is a pure formatting function — no LLM calls, no semantic reasoning.

    Args:
        steps: List of step dicts with fields: name, description, step_type,
               depends_on, input, output, params, tool_name, ops.
        pipeline_name: Name for the pipeline.
        description: Pipeline-level description.
        required_params: List of parameter names required by the pipeline.

    Returns:
        Complete agent.md text as a string.
    """
    _validate_input(steps, required_params)

    name = _clean_name(pipeline_name)

    lines: list[str] = []

    _render_frontmatter(lines, name, required_params)
    _render_header(lines, name, description)

    for i, step in enumerate(steps):
        _render_step(lines, step, i)

    return "\n".join(lines)


def _clean_name(name: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "_", name).strip("_")
    if not cleaned:
        logger.warning("Could not derive pipeline name from input; using 'auto_generated'")
        return "auto_generated"
    return cleaned


def _validate_input(steps: Any, required_params: Any) -> None:
    if not isinstance(steps, list):
        raise TypeError(f"steps must be a list, got {type(steps).__name__}")

    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise TypeError(f"steps[{i}] must be a dict, got {type(step).__name__}")
        for field in ("name", "description", "step_type"):
            if field not in step:
                raise ValueError(f"steps[{i}] missing required field '{field}'")

    if required_params is not None and not isinstance(required_params, list):
        logger.warning("required_params is not a list; treating as empty")


def _render_frontmatter(lines: list[str], name: str, required_params: list[str] | None) -> None:
    lines.append("---")
    lines.append(f'name: "{name}"')
    if required_params:
        lines.append("required_params:")
        for p in required_params:
            lines.append(f"  - {p}")
    lines.append("---")
    lines.append("")


def _render_header(lines: list[str], name: str, description: str) -> None:
    lines.append(f"# {name}")
    lines.append("")
    if description:
        lines.append(f"> {description}")
        lines.append("")


def _render_step(lines: list[str], step: dict, index: int) -> None:
    name = step.get("name", "unnamed_step")
    description = step.get("description", "")
    step_type = step.get("step_type", "")

    lines.append(f"## {name}")
    if description:
        lines.append(f"> {description}")

    depends_on = step.get("depends_on", [])
    if depends_on:
        dep_items = ", ".join(repr(d) for d in depends_on if d)
        if dep_items:
            lines.append(f"depends_on: [{dep_items}]")

    if step_type not in ("browser", "goal", "tool"):
        logger.warning("Unknown step_type '%s'; rendering as goal", step_type)
        lines.append(f"goal: {description}")
        lines.append("")
        return

    if step_type in ("browser", "goal"):
        _render_input_output(lines, step)

    if step_type == "goal":
        lines.append(f"goal: {description}")
        lines.append("")
        return

    if step_type == "tool":
        _render_tool_step(lines, step)
        lines.append("")
        return

    # step_type == "browser"
    ops = step.get("ops") or step.get("browser_ops")
    if not ops:
        logger.warning("browser step '%s' has no ops; degrading to goal", name)
        lines.append(f"goal: {description}")
        lines.append("")
        return

    lines.append("browser:")
    for op in ops:
        if not isinstance(op, dict):
            logger.warning("op is not a dict; skipping")
            continue
        op_type = op.get("type", "")
        op_value = op.get("value")
        if op_value is None:
            logger.warning("op type='%s' missing 'value' field; skipping", op_type)
            continue
        lines.append(f'  - {op_type}: "{op_value}"')

    lines.append("")


def _render_input_output(lines: list[str], step: dict) -> None:
    for key in ("input", "output"):
        data = step.get(key, {})
        if isinstance(data, dict) and data:
            lines.append(f"{key}:")
            for k, v in data.items():
                lines.append(f"  {k}: {v}")
        elif isinstance(data, list) and data:
            lines.append(f"{key}:")
            for item in data:
                lines.append(f"  - {item}")
        elif data and isinstance(data, str):
            lines.append(f"{key}: {data}")


def _render_tool_step(lines: list[str], step: dict) -> None:
    tool_name = step.get("tool_name", "")
    lines.append(f"tool: {tool_name}")

    _render_input_output(lines, step)

    params = step.get("params", {})
    if isinstance(params, dict) and params:
        lines.append("params:")
        for k, v in params.items():
            lines.append(f"  {k}: {v}")
