"""Guardian — approval gate, circuit breaker, and tool output validation."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)


class StepReviewInterrupt(Exception):
    """Raised when extra ops need human (or LLM) review before write-back."""

    def __init__(self, reason: str, extra_ops: list, guard_layer: str = "L3") -> None:
        self.reason = reason
        self.extra_ops = extra_ops
        self.guard_layer = guard_layer
        super().__init__(reason)


def step_guard(extra_ops: list, pipeline_name: str, helpers: object) -> str:
    """Classify extra ops as 'interrupt' (navigation) or 'auto_inject'.

    Args:
        extra_ops: List of operation dicts to classify.
        pipeline_name: Pipeline name (used for logging only here).
        helpers: CDP helpers object (reserved for future use).

    Returns:
        'interrupt' if any op is a navigation/goto, 'auto_inject' otherwise.
    """
    for op in extra_ops:
        op_type = op.get("type", "")
        if op_type in ("navigate", "goto", "wait"):
            return "interrupt"
    return "auto_inject"


async def split_by_guard_result(extra_ops: list) -> tuple[list, list]:
    """Split extra ops into L1 (navigation) and L2/L3 (others).

    Args:
        extra_ops: List of operation dicts.

    Returns:
        Tuple of (l1_ops, l2_l3_ops).
    """
    l1_ops: list = []
    l2_l3_ops: list = []
    for op in extra_ops:
        op_type = op.get("type", "")
        if op_type in ("navigate", "goto", "wait"):
            l1_ops.append(op)
        else:
            l2_l3_ops.append(op)
    return l1_ops, l2_l3_ops


def llm_review_extra_ops(
    extra_ops: list,
    step: dict,
    helpers: object | None = None,
) -> tuple[list, list]:
    """Simple LLM-style review — rejects navigations, approves others.

    In a full implementation this would call an LLM. Currently uses a
    rule-based approach as a stub.

    Args:
        extra_ops: List of operation dicts.
        step: Step definition dict.
        helpers: Optional CDP helpers.

    Returns:
        Tuple of (approved_ops, rejected_ops).
    """
    approved: list = []
    rejected: list = []
    for op in extra_ops:
        if op.get("type", "") in ("navigate", "goto"):
            rejected.append(op)
        else:
            approved.append(op)
    return approved, rejected


def create_guardian_from_frontmatter(frontmatter: dict | None = None) -> Guardian:
    """Create a Guardian instance from frontmatter configuration.

    Args:
        frontmatter: Pipeline frontmatter dict, may contain a 'guardian' key.

    Returns:
        Configured Guardian instance.
    """
    gf_config = (frontmatter or {}).get("guardian", {})
    return Guardian(
        approval_steps=gf_config.get("approval_steps", []),
        circuit_breaker_threshold=gf_config.get("circuit_breaker", 3),
        review_enabled=gf_config.get("review", False),
    )


def inject_guardian_config_to_steps(steps: list[dict], frontmatter: dict | None = None) -> None:
    """Inject guardian review_mode/review_port into step data.

    Args:
        steps: List of step definition dicts (mutated in place).
        frontmatter: Pipeline frontmatter dict.
    """
    gf_config = (frontmatter or {}).get("guardian", {})
    for step_data in steps:
        if gf_config.get("review_mode") is not None:
            step_data["review_mode"] = gf_config["review_mode"]
        if gf_config.get("review_port") is not None:
            step_data["review_port"] = gf_config["review_port"]


class Guardian:
    """Validates tool outputs, approval gating, and circuit breaker / STALE tracking.

    Features:
    - Content validation for CSV / JSON output files
    - Approval gating (frontmatter approval_steps or inline approval_required)
    - Circuit breaker (N consecutive failures → STALE marker)
    """

    def __init__(
        self,
        approval_steps: list[str] | None = None,
        circuit_breaker_threshold: int = 3,
        review_enabled: bool = False,
        versions_dir: str | Path | None = None,
    ) -> None:
        self._failure_counts: dict[str, int] = {}
        self.approval_steps = approval_steps or []
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.review_enabled = review_enabled
        self._versions_dir = Path(versions_dir) if versions_dir else None

    # ── content validation ──

    def validate_output(self, output_dir: str | Path, output_files: list[str]) -> dict:
        """Validate that declared output files exist and are well-formed.

        Args:
            output_dir: Directory containing output files.
            output_files: List of file names to validate.

        Returns:
            Dict with ``ok`` (bool) and ``detail`` (str).
        """
        output_dir_path = Path(output_dir)
        detail_parts: list[str] = []

        if not output_files:
            return {"ok": True, "detail": "(empty output declaration — skipped)"}

        for file_name in output_files:
            file_path = output_dir_path / file_name
            if not file_path.exists():
                return {"ok": False, "detail": f"Output file missing: {file_name}"}

            ext = file_path.suffix.lower()
            if ext == ".csv":
                check = self._validate_csv(file_path)
                if not check["ok"]:
                    return check
                detail_parts.append(check["detail"])
            elif ext == ".json":
                check = self._validate_json(file_path)
                if not check["ok"]:
                    return check
                detail_parts.append(check["detail"])

        return {"ok": True, "detail": "; ".join(detail_parts)}

    def _validate_csv(self, path: Path) -> dict:
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                rows = list(reader)
        except Exception as e:
            return {"ok": False, "detail": f"CSV read failed: {e}"}

        if not rows:
            return {"ok": False, "detail": f"CSV is empty: {path.name}"}
        if len(rows[0]) < 1:
            return {"ok": False, "detail": f"CSV has no columns: {path.name}"}

        return {"ok": True, "detail": f"CSV: {len(rows)} rows, {len(rows[0])} columns"}

    def _validate_json(self, path: Path) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                json.load(f)
        except Exception as e:
            return {"ok": False, "detail": f"JSON parse failed: {e}"}
        return {"ok": True, "detail": f"JSON: {path.name} is valid"}

    # ── STALE tracking ──

    def record_failure(self, pipeline_name: str) -> int:
        """Record a failure and return the accumulated failure count.

        Delegates to ``circuit_breaker`` to avoid double-counting.
        """
        self.circuit_breaker(pipeline_name, recent_success=False)
        return self._failure_counts.get(pipeline_name, 0)

    def is_stale(self, pipeline_name: str) -> bool:
        """Check if the pipeline has exceeded the circuit breaker threshold."""
        count = self._failure_counts.get(pipeline_name, 0)
        return count >= self.circuit_breaker_threshold

    def get_failure_count(self, pipeline_name: str) -> int:
        return self._failure_counts.get(pipeline_name, 0)

    def reset_failures(self, pipeline_name: str) -> None:
        self._failure_counts.pop(pipeline_name, None)

    # ── approval gating ──

    def approve(self, step_name: str | None = None, step_def: dict | None = None) -> bool:
        """Check if a step requires manual approval.

        Conditions checked:
        1. step_name is in ``self.approval_steps`` (from frontmatter)
        2. step_def has ``approval_required: true`` (inline on the step)
        3. Circuit breaker has fired (STALE) — blocks all steps

        Returns:
            True if execution can proceed, False if review is needed or pipeline is STALE.
        """
        # Condition 1: frontmatter approval_steps list
        if step_name and self.approval_steps and step_name in self.approval_steps:
            logger.info("guardian: step '%s' requires approval (approval_steps)", step_name)
            return False

        # Condition 2: inline approval_required flag
        if step_def and step_def.get("approval_required"):
            logger.info("guardian: step '%s' requires approval (approval_required)", step_name)
            return False

        # Condition 3: circuit breaker fired (STALE)
        if self.read_stale_marker() is not None:
            logger.warning(
                "guardian: step '%s' blocked — pipeline is STALE (circuit breaker fired)",
                step_name,
            )
            return False

        return True

    def circuit_breaker(self, pipeline_name: str, recent_success: bool) -> bool:
        """Track consecutive failures and signal STALE when threshold exceeded.

        When STALE triggers:
        - Writes a STALE marker file to ``versions_dir`` (if configured)
        - Returns False (circuit open — stop execution)

        Args:
            pipeline_name: Name of the pipeline.
            recent_success: True if the last step succeeded (resets counter).

        Returns:
            True if circuit is closed (safe to proceed), False if open.
        """
        if recent_success:
            self._failure_counts.pop(pipeline_name, None)
            self._clear_stale_marker(pipeline_name)
            return True

        count = self._failure_counts.get(pipeline_name, 0) + 1
        self._failure_counts[pipeline_name] = count
        logger.warning(
            "guardian: %s failure count = %d/%d",
            pipeline_name,
            count,
            self.circuit_breaker_threshold,
        )

        if count >= self.circuit_breaker_threshold:
            logger.error("guardian: %s circuit BREAKER — STALE", pipeline_name)
            self._write_stale_marker(pipeline_name)
            return False
        return True

    def _write_stale_marker(self, pipeline_name: str) -> None:
        """Write a timestamped STALE marker to the versions directory."""
        if self._versions_dir:
            self._versions_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            stale_file = self._versions_dir / f"STALE_{ts}"
            stale_file.write_text(
                f"pipeline: {pipeline_name}\n"
                f"triggered_at: {datetime.now(timezone.utc).isoformat()}\n"
                f"reason: circuit_breaker threshold ({self.circuit_breaker_threshold}) reached\n",
                encoding="utf-8",
            )
            logger.warning("guardian: wrote STALE marker for %s (%s)", pipeline_name, stale_file.name)

    def _clear_stale_marker(self, pipeline_name: str) -> None:
        """Remove all STALE marker files for this pipeline."""
        if self._versions_dir:
            for stale_file in self._versions_dir.glob("STALE*"):
                try:
                    stale_file.unlink()
                    logger.info("guardian: cleared STALE marker: %s", stale_file.name)
                except OSError:
                    pass

    def read_stale_marker(self) -> str | None:
        """Read the most recent STALE marker content, or None if not stale."""
        if self._versions_dir:
            markers = sorted(self._versions_dir.glob("STALE_*"))
            if markers:
                return markers[-1].read_text(encoding="utf-8").strip()
        return None
