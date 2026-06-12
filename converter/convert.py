"""
convert.py — NL → pipeline.yaml document conversion pipeline.

Two-phase conversion:
    Phase 1 — Plan:  Call LLM with planner-plan.md prompt to extract steps.
    Phase 2 — Render: Format the extracted plan as pipeline.yaml using render.py.

The optional expand phase enriches each step with browser operations
using the planner-expand.md prompt.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from converter.render import render_steps_to_pipeline
from prompts._loader import load_prompt
from utils.logging import get_logger

logger = get_logger(__name__)


def _read_document(input_path: str | Path) -> str:
    """Read document content from a file path or return raw text."""
    path = Path(input_path)
    if path.suffix.lower() in (".md", ".txt") and path.exists():
        return path.read_text(encoding="utf-8")
    return str(input_path)


async def convert_document(input_path: str, pipeline_name: str | None = None) -> str:
    """Convert a natural language document to pipeline.yaml format.

    Two-phase conversion:
    1. Plan — Call LLM with planner-plan.md to extract structured steps.
    2. Render — Format the extracted steps as pipeline.yaml via render.py.

    Args:
        input_path: Path to .md/.txt file, or raw text content.
        pipeline_name: Optional name for the generated pipeline.
                       If not provided, derived from the file stem.

    Returns:
        Complete pipeline.yaml content as a string.

    Raises:
        ValueError: If no steps can be extracted from the document.
    """
    logger.info("Starting document conversion: %s", input_path)

    try:
        content = _read_document(input_path)

        if pipeline_name is None:
            path = Path(input_path)
            if path.suffix.lower() in (".md", ".txt") and path.exists():
                pipeline_name = path.stem
            else:
                pipeline_name = "auto_generated"

        # Phase 1: Plan — extract steps from document
        plan = await _plan(content, pipeline_name=pipeline_name)
        if not plan.get("steps"):
            raise ValueError(
                "Could not extract business steps from the document. "
                "Please check that the document contains actionable steps."
            )

        # Phase 2 (optional): Expand — enrich each step with browser ops
        expanded = await _expand_all(plan, content)
        steps = expanded.get("steps", plan.get("steps", []))

        # Render as pipeline.yaml
        result = render_steps_to_pipeline(
            steps=steps,
            pipeline_name=expanded.get("pipeline_name", pipeline_name),
            description=expanded.get("description", ""),
            required_params=expanded.get("required_params"),
        )
        logger.info("Conversion complete: %s", expanded.get("pipeline_name", pipeline_name))
        return result

    except Exception as e:
        logger.error("Conversion failed: %s", e)
        raise


async def _plan(document_content: str, pipeline_name: str | None = None) -> dict:
    """Phase 1: Call LLM with planner-plan.md to extract step definitions.

    Args:
        document_content: The raw document text.
        pipeline_name: Optional pipeline name hint.

    Returns:
        Dict with keys: pipeline_name, description, required_params, steps.
    """
    from utils.browser import create_llm
    from browser_use.llm.messages import UserMessage

    prompt_template = load_prompt("planner-plan")
    prompt = prompt_template.format(document_content=document_content)

    logger.debug("Planner prompt: %d characters", len(prompt))

    llm = create_llm()
    response = await llm.ainvoke([UserMessage(content=prompt)])
    text = response.completion if hasattr(response, "completion") else str(response)

    plan = _extract_json(text)
    if not plan:
        raise ValueError("LLM did not return a valid plan JSON. Raw response:\n" + text[:500])

    # Ensure required fields exist
    plan.setdefault("pipeline_name", pipeline_name or "auto_generated")
    plan.setdefault("description", "")
    plan.setdefault("required_params", [])
    plan.setdefault("steps", [])

    logger.info(
        "Plan extracted: %s (%d steps, %d params)",
        plan["pipeline_name"], len(plan["steps"]), len(plan["required_params"]),
    )
    return plan


async def _expand_all(plan: dict, document_content: str) -> dict:
    """Phase 2 (optional): Expand each step with browser ops.

    Calls LLM for each browser or goal step to generate detailed ops.

    Args:
        plan: The plan dict from _plan().
        document_content: The original document text.

    Returns:
        Updated plan dict with ops filled in for steps that need them.
    """
    from utils.browser import create_llm
    from browser_use.llm.messages import UserMessage

    prompt_template = load_prompt("planner-expand")

    prior_expanded_ops: list[list[dict]] = []
    expanded_steps: list[dict] = []

    for idx, step in enumerate(plan.get("steps", [])):
        step_type = step.get("step_type", "")
        if step_type not in ("browser", "goal"):
            # Tool steps don't need browser ops
            step.setdefault("ops", [])
            expanded_steps.append(step)
            prior_expanded_ops.append([])
            continue

        prompt = prompt_template.format(
            step_index=idx,
            step_name=step.get("name", ""),
            step_description=step.get("description", ""),
            step_type=step_type,
            document_content=document_content,
            prior_expanded_ops=json.dumps(prior_expanded_ops, ensure_ascii=False),
        )

        llm = create_llm()
        response = await llm.ainvoke([UserMessage(content=prompt)])
        text = response.completion if hasattr(response, "completion") else str(response)

        ops = _extract_ops(text)
        step["ops"] = ops
        expanded_steps.append(step)
        prior_expanded_ops.append(ops)

        logger.debug("Step '%s' expanded: %d ops", step.get("name"), len(ops))

    plan["steps"] = expanded_steps
    return plan


def _extract_json(text: str) -> dict | None:
    """Extract the first JSON object from LLM response text.

    Handles markdown-fenced JSON blocks and raw JSON.
    """
    # Try to find a ```json ... ``` block first
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if json_match:
        candidate = json_match.group(1).strip()
    else:
        candidate = text.strip()

    # Find the first { and last }
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    candidate = candidate[start : end + 1]

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON from LLM response")
        return None


def _extract_ops(text: str) -> list[dict]:
    """Extract an ops array from LLM response text.

    Tries parsing as JSON first, falling back to regex extraction
    of an array inside the response.
    """
    # Try full JSON parse
    content = text.strip()
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)```", content, re.DOTALL)
    if json_match:
        candidate = json_match.group(1).strip()
    else:
        candidate = content

    start = candidate.find("[")
    end = candidate.rfind("]")
    if start != -1 and end != -1 and end > start:
        candidate = candidate[start : end + 1]

    try:
        result = json.loads(candidate)
        if isinstance(result, list):
            return result
    except (json.JSONDecodeError, TypeError):
        pass

    # Fallback: try to find standalone ops
    ops: list[dict] = []
    op_pattern = re.compile(r'\{\s*"type"\s*:\s*"([^"]+)"\s*,\s*"value"\s*:\s*"([^"]*)"\s*\}')
    for match in op_pattern.finditer(content):
        ops.append({"type": match.group(1), "value": match.group(2)})

    if ops:
        return ops

    logger.warning("Could not extract ops from LLM response")
    return []
