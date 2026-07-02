"""Run state tracking for pipeline execution."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RunContext:
    pipeline_name: str = ""
    run_id: str = ""
    run_dir: Path | None = None
    version: str | None = None
    step_index: int = 0
    current_step: str = ""
    errors: list[dict] = field(default_factory=list)
    compensation_history: list[dict] = field(default_factory=list)
    learned_goals: list[str] = field(default_factory=list)
    upgraded_tools: list[str] = field(default_factory=list)
    failure_context: dict | None = None
