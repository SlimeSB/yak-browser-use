"""Turn context — per-turn preparation."""

from __future__ import annotations

from dataclasses import dataclass

from yak_browser_use.engine._harness.tool_guardrails import ToolCallGuardrailState
from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TurnContext:
    """Per-turn execution context with retry counters."""

    tool_retries: int = 0
    json_retries: int = 0
    empty_content_retries: int = 0
    api_retries: int = 0
    max_tool_retries: int = 3
    max_json_retries: int = 2
    max_empty_content_retries: int = 2
    max_api_retries: int = 3


def build_turn_context(
    guardrail_state: ToolCallGuardrailState | None = None,
) -> TurnContext:
    """Build a fresh TurnContext, resetting guardrails and counters.

    Called at the start of every turn in the conversation loop.
    """
    if guardrail_state is not None:
        guardrail_state.reset()
    ctx = TurnContext()
    logger.debug("Built fresh TurnContext")
    return ctx
