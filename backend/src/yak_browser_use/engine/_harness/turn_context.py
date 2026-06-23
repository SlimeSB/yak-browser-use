"""Turn context — per-turn preparation and interrupt/resume state management."""

from __future__ import annotations

from dataclasses import dataclass, field

from yak_browser_use.engine._harness.tool_guardrails import ToolCallGuardrailState
from yak_browser_use.engine._harness.iteration_budget import IterationBudget
from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TurnContext:
    """Per-turn execution context with retry counters and interrupt state."""

    tool_retries: int = 0
    json_retries: int = 0
    empty_content_retries: int = 0
    api_retries: int = 0
    max_tool_retries: int = 3
    max_json_retries: int = 2
    max_empty_content_retries: int = 2
    max_api_retries: int = 3

    turn_messages_snapshot: list[dict] = field(default_factory=list)

    def reset(self) -> None:
        """Reset all retry counters at turn start."""
        self.tool_retries = 0
        self.json_retries = 0
        self.empty_content_retries = 0
        self.api_retries = 0
        self.turn_messages_snapshot.clear()
        logger.debug("TurnContext reset: retry counters cleared")

    def snapshot(self, messages: list[dict]) -> None:
        """Save messages for later restore (interrupt scenario)."""
        self.turn_messages_snapshot = list(messages)


@dataclass
class InterruptState:
    """Serializable conversation state for interrupt save/restore."""

    messages: list[dict] = field(default_factory=list)
    budget: dict | None = None
    error_info: dict | None = None
    last_tool_result: dict | None = None

    def to_dict(self) -> dict:
        return {
            "messages": self.messages,
            "budget": self.budget,
            "error_info": self.error_info,
            "last_tool_result": self.last_tool_result,
        }

    @classmethod
    def from_dict(cls, d: dict) -> InterruptState:
        return cls(
            messages=d.get("messages", []),
            budget=d.get("budget"),
            error_info=d.get("error_info"),
            last_tool_result=d.get("last_tool_result"),
        )


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


def save_interrupt_state(
    messages: list[dict],
    budget: IterationBudget,
    error_info: dict | None = None,
    last_tool_result: dict | None = None,
) -> InterruptState:
    """Create interrupt state for save/restore."""
    return InterruptState(
        messages=list(messages),
        budget=budget.to_dict(),
        error_info=error_info,
        last_tool_result=last_tool_result,
    )
