"""
render.py — Pure rendering of step definitions to pipeline.yaml format.

This module handles the rendering of expanded step definitions into
standard pipeline.yaml format using yaml.dump(). It performs NO LLM calls.
"""
from __future__ import annotations

import yaml

from compiler.schema import PipelineYaml, StepYaml, ops_to_yaml
from utils.logging import get_logger

logger = get_logger(__name__)


def render_steps_to_pipeline(
    steps: list[dict],
    pipeline_name: str = "auto_generated",
    description: str = "",
    required_params: list[str] | None = None,
) -> str:
    """Render expanded step definitions to pipeline.yaml format string.

    Args:
        steps: List of step dicts with fields: name, description, step_type,
               depends_on, ops/browser_ops, input, output, params, tool_name.
        pipeline_name: Name for the pipeline.
        description: Pipeline-level description.
        required_params: List of parameter names required by the pipeline.

    Returns:
        Complete pipeline.yaml text as a string.
    """
    _validate_input(steps)

    name = pipeline_name or "auto_generated"

    step_models: list[StepYaml] = []
    for step_dict in steps:
        step_models.append(_dict_to_step_yaml(step_dict))

    pipeline = PipelineYaml(
        name=name,
        description=description,
        required_params=required_params or [],
        steps=step_models,
    )

    data = pipeline.model_dump(exclude_none=True)
    return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _validate_input(steps: list[dict]) -> None:
    if not isinstance(steps, list):
        raise TypeError(f"steps must be a list, got {type(steps).__name__}")
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise TypeError(f"steps[{i}] must be a dict, got {type(step).__name__}")
        if "name" not in step:
            raise ValueError(f"steps[{i}] missing required field 'name'")


def _dict_to_step_yaml(step: dict) -> StepYaml:
    """Convert an LLM-generated step dict to a StepYaml model."""
    step_type = step.get("step_type", "")
    ops = step.get("ops") or step.get("browser_ops") or []

    browser_ops = None
    tool_name = None
    goal_description = None

    if step_type == "browser" and ops:
        browser_ops = ops_to_yaml(ops)
    elif step_type == "tool":
        tool_name = step.get("tool_name", "")
    elif step_type == "goal" or not step_type:
        goal_description = step.get("description", "")
    else:
        goal_description = step.get("description", "")

    input_data = step.get("input", {})
    if isinstance(input_data, dict) and input_data:
        input_ref = input_data
    elif isinstance(input_data, str) and input_data:
        input_ref = input_data
    else:
        input_ref = None

    output_data = step.get("output", [])
    if isinstance(output_data, list):
        output_ref = [str(v) for v in output_data]
    else:
        output_ref = []

    return StepYaml(
        name=step.get("name", "unnamed_step"),
        description=step.get("description", ""),
        depends_on=step.get("depends_on", []),
        input_ref=input_ref,
        output_ref=output_ref,
        input_schema=step.get("input_schema", {}),
        output_schema=step.get("output_schema", {}),
        params=step.get("params", {}),
        browser_ops=browser_ops,
        tool_name=tool_name,
        goal_description=goal_description,
    )

