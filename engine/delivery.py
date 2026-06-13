"""Delivery report — writes markdown delivery reports for completed steps."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)

STATUS_ICONS = {
    "completed": "\u2705",
    "partial": "\u26a0\ufe0f",
    "failed": "\u274c",
    "interrupted": "\u23f9",
}

DELIVERY_TEMPLATE = """# {step_name}

**Pipeline**: {pipeline_name}
**Goal**: {goal_description}
**Status**: {icon} {status}
**Duration**: {duration_ms}ms
**Generated**: {generated_at}
{saved_version_line}
"""


def write_delivery_report(
    step_dir: Path,
    *,
    pipeline_name: str,
    step_name: str,
    goal_description: str,
    status: str,
    duration_ms: int,
    saved_version: str | None = None,
) -> Path:
    """Write a delivery report markdown file to the step directory.

    Args:
        step_dir: Directory for the step artifact.
        pipeline_name: Name of the pipeline.
        step_name: Name of the step.
        goal_description: Goal description text.
        status: Step status string.
        duration_ms: Duration in milliseconds.
        saved_version: Optional saved version identifier.

    Returns:
        Path to the written report file.
    """
    icon = STATUS_ICONS.get(status, "\u2753")
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    saved_version_line = f"**Saved Version**: {saved_version}" if saved_version is not None else ""

    content = DELIVERY_TEMPLATE.format(
        step_name=step_name,
        pipeline_name=pipeline_name,
        goal_description=goal_description,
        icon=icon,
        status=status,
        duration_ms=duration_ms,
        generated_at=generated_at,
        saved_version_line=saved_version_line,
    )

    report_path = step_dir / "delivery-report.md"
    report_path.write_text(content, encoding="utf-8")
    logger.info(
        "Wrote delivery report: path=%s, pipeline=%s, step=%s, status=%s, duration_ms=%d",
        report_path,
        pipeline_name,
        step_name,
        status,
        duration_ms,
    )
    return report_path
