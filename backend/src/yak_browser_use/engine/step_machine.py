"""Step state machine — manages step lifecycle and DAG traversal."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)

RETRYABLE_ERRORS = {"BROWSER_ERROR", "TIMEOUT_ERROR", "RUNTIME_ERROR"}
NON_RETRYABLE_ERRORS = {
    "GUARDIAN_ERROR", "SYNTAX_ERROR", "INPUT_ERROR",
    "OUTPUT_ERROR", "PATH_ERROR", "REVIEW_INTERRUPT",
}


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    PENDING_REVIEW = "pending_review"


@dataclass
class StepNode:
    index: int
    key: str
    name: str
    step_type: str
    status: StepStatus = StepStatus.PENDING
    parent_index: int | None = None
    children: list[int] = field(default_factory=list)
    goto: str | None = None
    error: dict | None = None
    duration_ms: int = 0
    start_time: float = 0.0
    compromised_ops: list[dict] | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "index": self.index,
            "key": self.key,
            "name": self.name,
            "step_type": self.step_type,
            "status": self.status.value,
            "parent_index": self.parent_index,
            "children": self.children,
            "goto": self.goto,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }
        if self.compromised_ops is not None:
            d["compromised_ops"] = self.compromised_ops
        return d


class StepMachine:
    """Manages sequential step execution with retry, fork, and recovery support."""

    def __init__(self, steps: list[dict[str, Any]], resume_from_index: int = 0):
        self.steps = steps
        self._index = resume_from_index
        self.nodes: list[StepNode] = []
        self._fork_stack: list[int] = []
        self._cancel_flag = False
        self._retry_count: dict[int, int] = {}

    @property
    def is_done(self) -> bool:
        return self._index >= len(self.steps) or self._cancel_flag

    @property
    def current_index(self) -> int:
        return self._index

    def begin_step(self) -> StepNode:
        step_def = self.steps[self._index]
        key = step_def.get("key", f"step_{self._index}")
        name = step_def.get("name", key)
        from yak_browser_use.compiler.step_type import infer_step_type
        step_type = infer_step_type(step_def)

        parent_index = self._fork_stack[-1] if self._fork_stack else None
        node = StepNode(
            index=self._index,
            key=key,
            name=name,
            step_type=step_type,
            status=StepStatus.RUNNING,
            parent_index=parent_index,
            start_time=time.time(),
        )
        if parent_index is not None:
            for n in self.nodes:
                if n.index == parent_index and node.index not in n.children:
                    n.children.append(node.index)
        self.nodes.append(node)
        logger.info("step machine: begin step %d (%s)", self._index, name)
        return node

    def end_step(self, node: StepNode, status: StepStatus, error: dict | None = None) -> None:
        node.status = status
        node.duration_ms = int((time.time() - node.start_time) * 1000)
        if error:
            node.error = error
            logger.warning("step machine: step %d %s: %s", node.index, status.value, error.get("message", ""))
        else:
            logger.info("step machine: end step %d (%s): %s (%dms)", node.index, node.name, status.value, node.duration_ms)

    def advance(self, goto: str | None = None) -> None:
        self._retry_count = {}
        if goto:
            self._fork_stack.append(self._index)
            for i, step_def in enumerate(self.steps):
                if step_def.get("key") == goto or step_def.get("name") == goto:
                    self._index = i
                    logger.info("step machine: goto step %d (%s)", i, goto)
                    return
            logger.warning("step machine: goto target %s not found, advancing to next step", goto)
            self._index += 1
        else:
            self._index += 1

    def fork_back(self) -> None:
        if self._fork_stack:
            self._index = self._fork_stack.pop()
            logger.info("step machine: fork back to step %d", self._index)
        else:
            logger.warning("step machine: fork_back called but fork stack is empty")

    def needs_retry(self, step_def: dict, error_code: str) -> bool:
        if error_code in NON_RETRYABLE_ERRORS:
            return False
        if error_code not in RETRYABLE_ERRORS:
            return False
        max_retries = step_def.get("params", {}).get("max_retries", 0)
        if max_retries <= 0:
            return False
        idx = self._index
        current_count = self._retry_count.get(idx, 0)
        self._retry_count[idx] = current_count + 1
        if self._retry_count[idx] <= max_retries:
            logger.warning("step machine: retrying step %d (%s), attempt %d/%d",
                           idx, step_def.get("name", ""), self._retry_count[idx], max_retries)
            return True
        return False

    def get_retry_delay(self, attempt: int, base_ms: float = 500, max_ms: float = 8000, jitter_ratio: float = 0.5) -> float:
        exponent = max(0, attempt - 1)
        delay = min(base_ms * (2 ** exponent), max_ms)
        seed = (time.time_ns() ^ (attempt * 0x9E3779B9)) & 0xFFFFFFFF
        jitter = random.Random(seed).uniform(0, jitter_ratio * delay)
        return delay + jitter

    def replace_remaining(self, new_steps: list[dict[str, Any]]) -> None:
        executed_count = self._index
        self.steps = self.steps[:executed_count] + new_steps
        self._fork_stack.clear()
        self.nodes = [n for n in self.nodes if n.index <= executed_count]
        logger.info("step machine: replaced remaining steps, executed=%d, new_total=%d",
                     executed_count, len(self.steps))

    def cancel(self) -> None:
        self._cancel_flag = True
        logger.info("step machine: cancel requested")

    def check_cancelled(self) -> bool:
        return self._cancel_flag

    def to_execution_tree(self) -> dict:
        return {
            "total_steps": len(self.steps),
            "nodes": [node.to_dict() for node in self.nodes],
        }
