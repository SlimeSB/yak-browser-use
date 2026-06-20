"""Iteration budget — limits LLM round-trip count per conversation.

Default max_total=50 (one round-trip = one LLM API call).
Supports goal_run pause/resume so inner browser-use Agent iterations
don't consume the outer budget.
"""

from __future__ import annotations

from utils.logging import get_logger

logger = get_logger(__name__)


class IterationBudget:
    """Tracks remaining LLM round-trips and supports goal_run pause/resume."""

    MIN_TOTAL = 10

    def __init__(self, max_total: int = 50):
        if max_total < self.MIN_TOTAL:
            raise ValueError(
                f"IterationBudget max_total must be >= {self.MIN_TOTAL}, got {max_total}"
            )
        self.max_total = max_total
        self._used: int = 0
        self._paused: bool = False
        logger.debug("IterationBudget created: max_total=%d", max_total)

    @property
    def remaining(self) -> int:
        return max(0, self.max_total - self._used)

    @property
    def used(self) -> int:
        return self._used

    @property
    def is_exhausted(self) -> bool:
        return self.remaining <= 0

    @property
    def is_paused(self) -> bool:
        return self._paused

    def consume(self, count: int = 1) -> int:
        """Consume *count* round-trips. Returns remaining."""
        if not self._paused:
            self._used += count
        remaining = self.remaining
        if remaining <= 0:
            logger.warning(
                "Iteration budget exhausted: used=%d, max_total=%d",
                self._used,
                self.max_total,
            )
        return remaining

    def pause(self) -> None:
        """Pause budget consumption (for goal_run)."""
        self._paused = True
        logger.debug("IterationBudget paused: used=%d", self._used)

    def resume(self) -> None:
        """Resume budget consumption."""
        self._paused = False
        logger.debug("IterationBudget resumed: used=%d", self._used)

    def reset(self) -> None:
        self._used = 0
        self._paused = False

    def exhaust(self) -> None:
        """Immediately exhaust the budget by setting used to max_total.

        Used by pipeline_finish tool to trigger natural exit from
        conversation_loop without modifying the while loop.
        """
        self._used = self.max_total
        self._paused = False
        logger.info("Iteration budget manually exhausted: used=%d, max_total=%d", self._used, self.max_total)

    def to_dict(self) -> dict:
        return {
            "max_total": self.max_total,
            "used": self._used,
            "remaining": self.remaining,
            "paused": self._paused,
        }

    @classmethod
    def from_dict(cls, d: dict) -> IterationBudget:
        budget = cls(max_total=d.get("max_total", 50))
        budget._used = d["used"]
        budget._paused = d.get("paused", False)
        return budget
