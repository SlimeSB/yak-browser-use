"""CompensationRegistry — tracks browser operations for rollback planning."""
from __future__ import annotations

from dataclasses import dataclass

from utils.logging import get_logger

logger = get_logger(__name__)

UNDO_MAP: dict[str, str | None] = {
    "fill": "clear",
    "goto": "go_back",
    "click": None,
    "wait": None,
    "snapshot": None,
    "get_html": None,
    "eval": None,
    "wait_for_network": None,
}


@dataclass
class OpRecord:
    """Record of a single browser operation with rollback metadata."""

    op_index: int
    op_type: str
    params: dict
    suggested_undo: str | None = None
    reversible: bool = True

    def to_dict(self) -> dict:
        return {
            "op_index": self.op_index,
            "op_type": self.op_type,
            "params": self.params,
            "suggested_undo": self.suggested_undo,
            "reversible": self.reversible,
        }


class CompensationRegistry:
    """Tracks browser operations to support rollback on failure.

    Each operation is recorded with its type, parameters, and a suggested
    undo action. On failure, call ``suggest_rollback()`` to get a reversed
    list of operations that should be undone.
    """

    def __init__(self) -> None:
        self._ops: list[OpRecord] = []

    def register_op(self, op_type: str, params: dict) -> OpRecord:
        """Register an operation for potential rollback tracking.

        Args:
            op_type: The type of operation (e.g. 'click', 'fill', 'goto').
            params: A dict of parameters passed to the operation.

        Returns:
            The created OpRecord.
        """
        op_index = len(self._ops)
        suggested_undo = self.compute_undo(op_type)
        reversible = suggested_undo is not None
        record = OpRecord(
            op_index=op_index,
            op_type=op_type,
            params=params,
            suggested_undo=suggested_undo,
            reversible=reversible,
        )
        self._ops.append(record)
        logger.debug("Registered op: index=%d, type=%s, undo=%s", op_index, op_type, suggested_undo)
        return record

    @staticmethod
    def compute_undo(op_type: str) -> str | None:
        """Return the suggested undo action for a given operation type."""
        return UNDO_MAP.get(op_type)

    def suggest_rollback(self, failed_index: int) -> list[dict]:
        """Build a rollback plan — reversed ops before the failed index.

        Args:
            failed_index: The index (in self._ops) of the failed operation.

        Returns:
            A list of OpRecord dicts in reverse order (last-executed first).
        """
        rollback: list[dict] = []
        for record in reversed(self._ops[:failed_index]):
            rollback.append(record.to_dict())
        logger.info(
            "Suggested rollback: failed_index=%d, ops_to_undo=%d",
            failed_index,
            len(rollback),
        )
        return rollback

    def to_list(self) -> list[dict]:
        """Export all registered operations as plain dicts."""
        return [r.to_dict() for r in self._ops]
