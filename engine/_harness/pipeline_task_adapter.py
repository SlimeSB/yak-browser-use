"""Pipeline task adapter — converts compiler StepDef[] into conversation_loop TaskDescriptor.

Only used in preset replay mode. Chat mode skips this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepInfo:
    """Single step info extracted from a StepDef."""
    key: str
    name: str
    description: str = ""
    step_type: str = ""
    status: str = "pending"


@dataclass
class TaskDescriptor:
    """Describes a pipeline task for injection into conversation_loop."""

    pipeline_name: str
    goal: str = ""
    steps: list[StepInfo] = field(default_factory=list)
    frontmatter: dict = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.steps)

    @property
    def completed(self) -> int:
        return sum(1 for s in self.steps if s.status == "completed")

    @property
    def progress(self) -> str:
        return f"{self.completed}/{self.total}"

    def format(self) -> str:
        """Return markdown-formatted task description for system prompt injection."""
        lines: list[str] = []
        lines.append(f"## Pipeline: {self.pipeline_name}")
        if self.goal:
            lines.append(f"目标: {self.goal}")
        lines.append("")
        lines.append(f"进度: {self.progress}")
        lines.append("")
        lines.append("### 步骤列表")
        for step in self.steps:
            status_mark = "[已完成]" if step.status == "completed" else "[待完成]"
            lines.append(f"- {status_mark} {step.name}: {step.description}")
        lines.append("")
        lines.append("你可以通过 pipeline_control 工具管理进度。")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "pipeline_name": self.pipeline_name,
            "goal": self.goal,
            "steps": [
                {
                    "key": s.key,
                    "name": s.name,
                    "description": s.description,
                    "step_type": s.step_type,
                    "status": s.status,
                }
                for s in self.steps
            ],
            "progress": self.progress,
        }


class PipelineTaskAdapter:
    """Converts compiler StepDef[] into a TaskDescriptor."""

    def __init__(self, step_defs: list[dict[str, Any]], frontmatter: dict | None = None):
        self.step_defs = step_defs
        self.frontmatter = frontmatter or {}

    def build_descriptor(self) -> TaskDescriptor:
        """Convert StepDef list to TaskDescriptor."""
        pipeline_name = self.frontmatter.get("name", "unnamed_pipeline")
        goal = self.frontmatter.get("goal", self.frontmatter.get("description", ""))

        steps: list[StepInfo] = []
        for i, step_def in enumerate(self.step_defs):
            key = step_def.get("key", f"step_{i}")
            name = step_def.get("name", key)
            description = step_def.get("goal_description", "")
            if not description:
                description = step_def.get("description", "")
            if not description and step_def.get("tool_name"):
                description = f"Run tool: {step_def['tool_name']}"

            step_type = step_def.get("step_type", "")
            if not step_type:
                if step_def.get("is_goal"):
                    step_type = "goal"
                elif step_def.get("tool_name"):
                    step_type = "tool"
                else:
                    step_type = "browser"

            steps.append(StepInfo(
                key=key,
                name=name,
                description=description,
                step_type=step_type,
                status="pending",
            ))

        return TaskDescriptor(
            pipeline_name=pipeline_name,
            goal=goal,
            steps=steps,
            frontmatter=self.frontmatter,
        )
