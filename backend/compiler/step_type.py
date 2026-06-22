"""Unified step type inference — browser / tool / goal.

Eliminates 5 ad-hoc implementations scattered across the codebase.
"""


def infer_step_type(step: dict | object) -> str:
    """Infer the step type from a dict or StepYaml/object.

    Priority: explicit step_type > tool_name > is_goal / goal_description > "browser".
    """
    if isinstance(step, dict):
        if step.get("step_type"):
            return step["step_type"]
        if step.get("tool_name"):
            return "tool"
        if step.get("is_goal") or step.get("goal_description"):
            return "goal"
        return "browser"

    # Pydantic model (StepYaml or similar)
    if getattr(step, "browser_ops", None) is not None:
        return "browser"
    if getattr(step, "tool_name", None) is not None:
        return "tool"
    return "goal"
