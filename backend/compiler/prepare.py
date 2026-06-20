"""Shared pipeline preparation — parse, resolve, and order steps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from utils.logging import get_logger

logger = get_logger(__name__)


def prepare_steps(content: str, pipeline_path: Path) -> tuple[Any, list[dict]]:
    """Parse pipeline.yaml and prepare ordered steps.

    Returns (parsed_frontmatter_plus, steps_data).
    """
    from compiler.graph import build_graph, get_execution_order, validate_file_refs
    from compiler.parser import parse_pipeline
    from compiler.resolver import resolve

    parsed = parse_pipeline(content)

    dag = build_graph(parsed.steps)
    validate_file_refs(parsed.steps)
    execution_order = get_execution_order(dag)

    step_key_map = {s.key: s for s in parsed.steps}
    ordered_steps = [step_key_map[k] for k in execution_order]

    steps_data: list[dict] = []
    for step in ordered_steps:
        handler = resolve(step, parsed.name)
        step_data = step.to_runtime_dict(handler)
        steps_data.append(step_data)

    logger.info("Prepared %d steps for pipeline '%s'", len(steps_data), parsed.name)
    return parsed, steps_data
