from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class StepDef:
    """Represents a single parsed step from a pipeline.yaml file."""

    key: str
    name: str
    description: str = ""
    browser_ops: list[dict] = field(default_factory=list)
    input_schema: dict[str, str] = field(default_factory=dict)
    output_schema: dict[str, str] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    raw_content: str = ""
    system_prompt: str = ""
    step_type: str = ""
    is_goal: bool = False
    goal_description: str = ""
    tool_name: str = ""
    input_ref: dict | str = ""
    output_ref: list[str] = field(default_factory=list)
    params: dict = field(default_factory=dict)

    def to_runtime_dict(self, handler: Callable | None = None) -> dict:
        """Convert to a runtime step dictionary for pipeline execution."""
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "step_type": self.step_type,
            "depends_on": self.depends_on,
            "handler": handler,
            "browser_ops": self.browser_ops,
            "is_goal": self.is_goal,
            "goal_description": self.goal_description,
            "tool_name": self.tool_name,
            "input": self.input_ref if self.input_ref else {},
            "output": self.output_ref if self.output_ref else [],
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "params": self.params,
            "system_prompt": self.system_prompt,
        }


@dataclass
class PipelineDef:
    """Represents a complete parsed pipeline.yaml document."""

    name: str
    description: str = ""
    steps: list[StepDef] = field(default_factory=list)
    frontmatter: dict = field(default_factory=dict)
