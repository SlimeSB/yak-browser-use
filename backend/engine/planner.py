"""RuntimePlanner — single-shot LLM call to generate replacement browser_ops.

Used by the preset pipeline runner when a browser op fails and retries
are exhausted. The planner sends the failed op, goal, error, and
simplified page HTML to the LLM and parses the response into a list of
replacement browser_ops.
"""

from __future__ import annotations

import json
import re
from typing import Callable

from utils.logging import get_logger

logger = get_logger(__name__)

_VALID_OP_TYPES: frozenset[str] = frozenset({
    "goto", "click", "fill", "snapshot", "scroll", "source",
    "eval", "wait", "wait_for_network",
})

_PLANNER_SYSTEM_PROMPT = """You are a browser automation recovery planner. A browser operation has failed.
Your job is to generate replacement browser_ops that achieve the same goal.

Output ONLY a JSON array of browser operation objects. Each object must have a "type" field and relevant parameters.

Supported operation types and their required parameters:
- goto: {"type": "goto", "value": "<url>"}
- click: {"type": "click", "value": "<css_selector>"} or {"type": "click", "selector": "<css_selector>"}
- fill: {"type": "fill", "selector": "<css_selector>", "value": "<text>"}
- snapshot: {"type": "snapshot", "mode": "a11y|progressive|interactive|simplified|full", "query": "<optional>", "in_viewport": true|false}
- expand_branch: {"type": "expand_branch", "key": "c_N", "limit": 30, "offset": 0}
- scroll: {"type": "scroll", "direction": "up|down", "amount": 300}
- source: {"type": "source"}
- eval: {"type": "eval", "code": "<javascript>"}
- wait: {"type": "wait", "value": "<seconds>"}
- wait_for_network: {"type": "wait_for_network"}

Return ONLY the JSON array, no other text. Example:
[{"type": "click", "selector": "#search-btn"}, {"type": "wait", "value": "2"}]

If you cannot determine replacement operations, return an empty array []."""


class RuntimePlanner:
    """Single-shot LLM-based planner for generating replacement browser_ops.

    Called when a browser op fails and retries are exhausted. Sends the
    failed op details, step goal, error message, and simplified page HTML
    to the LLM and returns a list of replacement browser_ops.
    """

    def __init__(self, llm_call: Callable):
        self._llm_call = llm_call

    async def plan_replacement_ops(
        self,
        *,
        failed_op: dict,
        goal_description: str,
        error_message: str,
        simplified_html: str,
    ) -> list[dict] | None:
        """Generate replacement browser_ops for a failed operation.

        Args:
            failed_op: The operation dict that failed.
            goal_description: Description of the step's goal.
            error_message: Error message from the failure.
            simplified_html: Simplified HTML summary of the current page.

        Returns:
            List of replacement browser_ops dicts, or None if planning failed.
        """
        prompt = self._build_planner_prompt(
            failed_op=failed_op,
            goal_description=goal_description,
            error_message=error_message,
            simplified_html=simplified_html,
        )

        messages = [
            {"role": "system", "content": _PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self._llm_call(messages, tools=[])
        except Exception as e:
            logger.warning("RuntimePlanner: LLM call failed: %s", e)
            return None

        content = getattr(response, "content", "") or ""
        return self._parse_ops_response(content)

    def _build_planner_prompt(
        self,
        *,
        failed_op: dict,
        goal_description: str,
        error_message: str,
        simplified_html: str,
    ) -> str:
        """Build the LLM prompt for replacement ops generation."""
        op_type = failed_op.get("type", "unknown")
        op_params = {k: v for k, v in failed_op.items() if k != "type"}

        lines = [
            "## Step Goal",
            goal_description or "(no description)",
            "",
            "## Failed Operation",
            f"Type: {op_type}",
        ]
        if op_params:
            lines.append(f"Params: {json.dumps(op_params, ensure_ascii=False)}")
        lines.extend([
            f"Error: {error_message or '(no error details)'}",
            "",
            "## Current Page State (simplified HTML)",
        ])

        html_preview = simplified_html[:8000] if simplified_html else "(no page state available)"
        lines.append(html_preview)
        lines.append("")
        lines.append("Generate replacement browser_ops as a JSON array.")

        return "\n".join(lines)

    def _parse_ops_response(self, content: str) -> list[dict] | None:
        """Parse the LLM response into a list of browser_ops dicts.

        Handles both pure JSON arrays and JSON arrays wrapped in markdown
        code fences.
        """
        if not content:
            return None

        cleaned = content.strip()

        json_match = re.search(r"```(?:json)?\s*(\[.*\])\s*```", cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(1)

        bracket_start = cleaned.find("[")
        bracket_end = cleaned.rfind("]")
        if bracket_start != -1 and bracket_end != -1 and bracket_end > bracket_start:
            cleaned = cleaned[bracket_start:bracket_end + 1]

        try:
            ops = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning("RuntimePlanner: failed to parse LLM response as JSON: %s", e)
            return None

        if not isinstance(ops, list):
            logger.warning("RuntimePlanner: expected JSON array, got %s", type(ops).__name__)
            return None

        valid_ops = []
        for op in ops:
            if isinstance(op, dict) and op.get("type") in _VALID_OP_TYPES:
                valid_ops.append(op)
            else:
                logger.warning("RuntimePlanner: skipping invalid op: %s", op)

        if not valid_ops:
            logger.info("RuntimePlanner: LLM returned empty or all-invalid ops array")
        return valid_ops if valid_ops else None
