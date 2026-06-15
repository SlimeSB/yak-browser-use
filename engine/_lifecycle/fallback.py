"""Fallback — page state assessment, recovery plan generation, and failure tracking."""
from __future__ import annotations

import json
from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)


async def assess_page_state(
    helpers: object,
    pipeline_name: str,
    steps: list[dict],
    failed_step_index: int,
    failed_op: dict,
    error: str,
) -> tuple[bool, int]:
    # DEPRECATED: 已被 Agent Swimlane 替代，保留仅为向后兼容
    """Assess whether the current page state is recoverable after a failure.

    Captures URL, title, and body text from the current page, then (in a
    full implementation) calls an LLM to determine if the state is
    recoverable and which step to resume from.

    Current stub: returns (False, 0) — restart from beginning.
    A real implementation would use an LLM call similar to the original.

    Args:
        helpers: CDP helpers for capturing page state.
        pipeline_name: Pipeline name (for logging).
        steps: List of all step definition dicts.
        failed_step_index: Index of the failed step.
        failed_op: The operation dict that failed.
        error: Error message string.

    Returns:
        Tuple of (recoverable: bool, resume_from_step_index: int).
    """
    try:
        url = (await helpers.js("window.location.href") or "").strip()  # type: ignore[union-attr]
        title = (await helpers.js("document.title") or "").strip()  # type: ignore[union-attr]
        body_text = (await helpers.js("document.body.innerText") or "").strip()  # type: ignore[union-attr]
        body_preview = body_text[:2000]
    except Exception as e:
        logger.warning("page assessment: failed to capture page state: %s", e)
        return False, 0

    steps_desc = "\n".join(
        [
            f"  Step {i}: {s.get('description', s.get('name', f'step_{i}'))}"
            for i, s in enumerate(steps)
        ]
    )
    failed_step = steps[failed_step_index] if failed_step_index < len(steps) else {}

    page_state = (
        f"URL: {url}\n"
        f"Title: {title}\n"
        f"Visible page text (first 2000 chars):\n{body_preview}"
    )

    logger.info(
        "page assessment for '%s': step=%d op=%s error=%s\n%s",
        pipeline_name,
        failed_step_index,
        failed_op.get("type", "?"),
        error[:200],
        page_state[:300],
    )

    # Stub: always return unrecoverable. A full implementation would call an
    # LLM with a prompt describing the steps, failed op, and current page state.
    return False, 0


def build_fallback_prompt(
    step: dict,
    executed_ops: list[dict],
    failed_op: dict,
    error: str,
    current_url: str,
    recoverable: bool = True,
    resume_from: int = 0,
    pipeline_steps: list[dict] | None = None,
) -> str:
    """Build a fallback prompt describing the failure and page state.

    Args:
        step: The step definition that failed.
        executed_ops: List of successfully executed operations.
        failed_op: The operation that failed.
        error: Error message.
        current_url: Current URL after failure.
        recoverable: Whether the state is recoverable.
        resume_from: Step index to resume from.
        pipeline_steps: Full list of pipeline steps.

    Returns:
        A formatted prompt string.
    """
    op_type = failed_op.get("type", "?")
    op_value = failed_op.get("value", failed_op.get("selector", ""))

    if not recoverable:
        lines = [
            "## Full Pipeline (restart from beginning)"
            if resume_from == 0
            else f"## Pipeline (restart from step {resume_from})"
        ]
        lines.append("")
        if pipeline_steps:
            start = resume_from if resume_from > 0 else 0
            for i, s in enumerate(pipeline_steps):
                if i < start:
                    continue
                lines.append(f"  Step {i}: {s.get('description', s.get('name', f'step_{i}'))}")
            lines.append("")
        if current_url:
            lines.append(f"## Current page: {current_url}")
        lines.append("The pipeline state is unrecoverable — the page is in an unexpected state.")
        if resume_from > 0:
            lines.append(f"Restart from Step {resume_from} (steps 0-{resume_from - 1} may already be done).")
        else:
            lines.append("Start the ENTIRE pipeline from Step 0.")
        lines.append("")
        lines.append(f"Failed operation: {op_type} on '{op_value}' — {error}")
        return "\n".join(lines)

    goal = step.get("description", step.get("name", ""))
    lines = [f"## Goal: {goal}"]
    if current_url:
        lines.append(f"## Current page: {current_url}")
    lines.append("")
    lines.append(f"A {op_type} operation on '{op_value}' failed: {error}")
    lines.append("")
    if executed_ops:
        lines.append("The current page state is the result of these completed operations:")
        for op in executed_ops:
            lines.append(f"  - {op.get('type', '?')}: {op.get('value', op.get('selector', ''))}")
        lines.append("")
    lines.append("Inspect the current page and complete only the remaining step.")
    return "\n".join(lines)


async def generate_recovery_plan(
    helpers: object,
    steps: list[dict],
    failed_step_index: int,
    compensation_results: list[dict],
    page_state: tuple[bool, int],
    pipeline_name: str,
) -> list[dict] | None:
    # DEPRECATED: 已被 RuntimePlanner 替代，保留仅为向后兼容
    """Generate a recovery plan based on page state and compensation history.

    In a full implementation this would call an LLM to produce replacement
    steps. Current stub returns None.

    Args:
        helpers: CDP helpers.
        steps: Full list of step definitions.
        failed_step_index: Index of the failed step.
        compensation_results: Compensation history list.
        page_state: Tuple of (recoverable, resume_from) from assess_page_state.
        pipeline_name: Pipeline name.

    Returns:
        A list of replacement step dicts, or None if recovery is not possible.
    """
    recoverable, resume_from = page_state

    if not recoverable:
        logger.warning("recovery plan: %s not recoverable (resume_from=%d)", pipeline_name, resume_from)
        return None

    # Stub — a full implementation would call an LLM to generate recovery steps.
    logger.info(
        "recovery plan for '%s': recoverable=True, resume_from=%d (stub — no plan generated)",
        pipeline_name,
        resume_from,
    )
    return None


def track_fallback_failure(pipeline_name: str, guardian: object | None = None) -> None:
    """Record a fallback failure to the guardian's circuit breaker.

    Args:
        pipeline_name: Pipeline name.
        guardian: Optional Guardian instance.
    """
    if guardian is not None:
        # Use duck-typing to avoid circular imports
        if hasattr(guardian, "record_failure"):
            guardian.record_failure(pipeline_name)
