from __future__ import annotations

from typing import Union

from pydantic import BaseModel, Field, model_validator

from compiler.models import PipelineDef, StepDef


class StepYaml(BaseModel):
    """Pydantic model for a single step in pipeline.yaml."""

    name: str
    description: str = ""
    depends_on: list[str] = []
    system_prompt: str = ""
    input_ref: Union[dict, str, None] = None
    output_ref: list[str] = []
    input_schema: dict[str, str] = {}
    output_schema: dict[str, str] = {}
    params: dict = {}
    browser_ops: list[dict] | None = None
    tool_name: str | None = None
    goal_description: str | None = None
    check: dict | None = None

    @model_validator(mode="after")
    def _check_mutual_exclusion(self):
        present = [
            f
            for f, val in [
                ("browser_ops", self.browser_ops),
                ("tool_name", self.tool_name),
                ("goal_description", self.goal_description),
            ]
            if val is not None
        ]
        if len(present) > 1:
            raise ValueError(
                f"Steps cannot mix type fields: {', '.join(present)} are mutually exclusive. "
                f"Use only one of browser_ops, tool_name, or goal_description."
            )
        return self

    def to_step_def(self) -> StepDef:
        """Convert to internal StepDef dataclass."""
        if self.browser_ops is not None:
            resolved_type = "browser"
            is_goal = False
            resolved_goal_desc = ""
            resolved_tool = ""
            resolved_browser_ops = [_convert_browser_op(op) for op in self.browser_ops]
        elif self.tool_name is not None:
            resolved_type = "tool"
            is_goal = False
            resolved_goal_desc = ""
            resolved_tool = self.tool_name
            resolved_browser_ops = []
        elif self.goal_description is not None:
            resolved_type = "goal"
            is_goal = True
            resolved_goal_desc = self.goal_description
            resolved_tool = ""
            resolved_browser_ops = []
        else:
            resolved_type = "goal"
            is_goal = True
            resolved_goal_desc = self.description
            resolved_tool = ""
            resolved_browser_ops = []

        return StepDef(
            key=self.name,
            name=self.name,
            description=self.description,
            browser_ops=resolved_browser_ops,
            input_schema=self.input_schema,
            output_schema=self.output_schema,
            depends_on=self.depends_on,
            raw_content="",
            system_prompt=self.system_prompt,
            step_type=resolved_type,
            is_goal=is_goal,
            goal_description=resolved_goal_desc,
            tool_name=resolved_tool,
            input_ref=self.input_ref if self.input_ref is not None else "",
            output_ref=self.output_ref,
            params=self.params,
            check=self.check,
        )


class PipelineYaml(BaseModel):
    """Pydantic model for the top-level pipeline.yaml structure."""

    name: str
    description: str = ""
    required_params: list[str] = []
    system_prompt: str = ""
    url_aliases: dict[str, str] = {}
    steps: list[StepYaml] = Field(..., min_length=1)

    def to_pipeline_def(self) -> PipelineDef:
        """Convert to internal PipelineDef dataclass."""
        return PipelineDef(
            name=self.name,
            description=self.description,
            steps=[s.to_step_def() for s in self.steps],
            frontmatter={
                "name": self.name,
                "description": self.description,
                "required_params": self.required_params,
                "system_prompt": self.system_prompt,
                "url_aliases": self.url_aliases,
            },
        )


def _convert_browser_op(op: dict) -> dict:
    """Convert a single-key browser operation dict to internal format."""
    for key, val in op.items():
        if isinstance(val, dict):
            result = {"type": key, **val}
        else:
            result = {"type": key, "value": val}
        return result
    return {}


def ops_to_yaml(ops: list[dict]) -> list[dict]:
    """Convert internal format ops to YAML single-key format.

    {type: "goto", value: "url"} → {goto: "url"}
    {type: "fill", selector, value} → {fill: {selector, value}}
    """
    result: list[dict] = []
    for op in ops:
        op_type = op.get("type", "")
        rest = {k: v for k, v in op.items() if k != "type"}
        if len(rest) == 1 and "value" in rest:
            result.append({op_type: rest["value"]})
        elif rest:
            result.append({op_type: rest})
        else:
            result.append({op_type: op.get("value", "")})
    return result
