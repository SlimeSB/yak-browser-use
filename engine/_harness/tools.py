"""Tool registration — OpenAI-compatible tool definitions for browser operations and goal_run.

Provides tool schemas for registration with LLM providers. These are
the tools that the Agent can call during conversation_loop.
"""

from __future__ import annotations

from typing import Any

BROWSER_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "browser_goto",
            "description": "Navigate the browser to a specified URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to navigate to.",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Click an element on the page using a CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for the element to click.",
                    },
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_fill",
            "description": "Fill text into an input element identified by CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for the input element.",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to fill into the input.",
                    },
                },
                "required": ["selector", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_snapshot",
            "description": "Capture a screenshot and HTML snapshot of the current page.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_scroll",
            "description": "Scroll the current page up or down.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down"],
                        "description": "Direction to scroll.",
                    },
                    "amount": {
                        "type": "integer",
                        "description": "Amount in pixels to scroll (default 300).",
                    },
                },
                "required": ["direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_source",
            "description": "Get the full HTML source of the current page.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_eval",
            "description": "Execute arbitrary JavaScript code on the current page and return the result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "JavaScript code to execute.",
                    },
                },
                "required": ["code"],
            },
        },
    },
]

GOAL_RUN_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "goal_run",
        "description": (
            "Use browser-use autonomous Agent to complete a complex multi-step task. "
            "Use this only when the task requires reasoning across multiple pages "
            "or analyzing page content to decide the next action. "
            "For single atomic operations, prefer the browser_* tools."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "A clear description of what the Agent should accomplish.",
                },
            },
            "required": ["description"],
        },
    },
}

PIPELINE_LOAD_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "pipeline_load",
        "description": (
            "Load a pipeline preset and return a structured summary (step list, types, "
            "dependencies, required_params). Does NOT return the full YAML content — "
            "use this to understand the pipeline structure before making changes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pipeline_name": {
                    "type": "string",
                    "description": "Name of the pipeline preset to load.",
                },
            },
            "required": ["pipeline_name"],
        },
    },
}

PIPELINE_LIST_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "pipeline_list",
        "description": (
            "List all available pipeline presets. Returns name, description, and "
            "step count for each preset."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
}

PIPELINE_UPDATE_STEP_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "pipeline_update_step",
        "description": (
            "Incrementally update a single step in a pipeline. Only the fields "
            "provided in `updates` are modified; all other fields stay unchanged. "
            "When changing browser_ops, tool_name, or goal_description, mutually "
            "exclusive fields are automatically cleared."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pipeline_name": {
                    "type": "string",
                    "description": "Name of the pipeline preset to modify.",
                },
                "step_name": {
                    "type": "string",
                    "description": "Name of the step to update.",
                },
                "updates": {
                    "type": "object",
                    "description": (
                        "Fields to update on the step. Supported keys: browser_ops "
                        "(list of single-key dicts), tool_name (string), "
                        "goal_description (string), description (string), "
                        "depends_on (list of strings)."
                    ),
                },
                "explanation": {
                    "type": "string",
                    "description": "Human-readable explanation of what was changed and why.",
                },
            },
            "required": ["pipeline_name", "step_name", "updates"],
        },
    },
}

PIPELINE_ADD_STEP_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "pipeline_add_step",
        "description": (
            "Add a new step to a pipeline. If `after` is provided, the step is "
            "inserted after the named step; otherwise it is appended to the end."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pipeline_name": {
                    "type": "string",
                    "description": "Name of the pipeline preset to modify.",
                },
                "step_name": {
                    "type": "string",
                    "description": "Unique name for the new step.",
                },
                "description": {
                    "type": "string",
                    "description": "Human-readable description of what this step does.",
                },
                "browser_ops": {
                    "type": "array",
                    "description": (
                        "List of browser operations, each as a single-key dict "
                        "(e.g. [{\"goto\": \"https://example.com\"}]). "
                        "Mutually exclusive with tool_name and goal_description."
                    ),
                    "items": {"type": "object"},
                },
                "tool_name": {
                    "type": "string",
                    "description": (
                        "Name of a custom tool to invoke. "
                        "Mutually exclusive with browser_ops and goal_description."
                    ),
                },
                "goal_description": {
                    "type": "string",
                    "description": (
                        "Description for a goal_run step. "
                        "Mutually exclusive with browser_ops and tool_name."
                    ),
                },
                "depends_on": {
                    "type": "array",
                    "description": "List of step names this step depends on.",
                    "items": {"type": "string"},
                },
                "after": {
                    "type": "string",
                    "description": "Name of the step to insert after. Omit to append.",
                },
                "explanation": {
                    "type": "string",
                    "description": "Human-readable explanation of what was changed and why.",
                },
            },
            "required": ["pipeline_name", "step_name", "description"],
        },
    },
}

PIPELINE_REMOVE_STEP_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "pipeline_remove_step",
        "description": (
            "Remove a step from a pipeline. Dependencies on the removed step "
            "are automatically cleaned up from other steps."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pipeline_name": {
                    "type": "string",
                    "description": "Name of the pipeline preset to modify.",
                },
                "step_name": {
                    "type": "string",
                    "description": "Name of the step to remove.",
                },
                "explanation": {
                    "type": "string",
                    "description": "Human-readable explanation of what was changed and why.",
                },
            },
            "required": ["pipeline_name", "step_name"],
        },
    },
}

PIPELINE_CREATE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "pipeline_create",
        "description": (
            "Create a new pipeline preset from a list of steps. "
            "Fails if a pipeline with the same name already exists."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pipeline_name": {
                    "type": "string",
                    "description": "Name for the new pipeline preset.",
                },
                "description": {
                    "type": "string",
                    "description": "Human-readable description of the pipeline.",
                },
                "steps": {
                    "type": "array",
                    "description": (
                        "List of step objects. Each step must have: name (string), "
                        "description (string). Optional: browser_ops (list of dicts), "
                        "tool_name (string), goal_description (string), "
                        "depends_on (list of strings)."
                    ),
                    "items": {"type": "object"},
                },
                "explanation": {
                    "type": "string",
                    "description": "Human-readable explanation of what was created and why.",
                },
            },
            "required": ["pipeline_name", "description", "steps"],
        },
    },
}

PIPELINE_TOOLS: list[dict[str, Any]] = [
    PIPELINE_LOAD_TOOL,
    PIPELINE_LIST_TOOL,
    PIPELINE_UPDATE_STEP_TOOL,
    PIPELINE_ADD_STEP_TOOL,
    PIPELINE_REMOVE_STEP_TOOL,
    PIPELINE_CREATE_TOOL,
]

RECORD_STEP_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "record_step",
        "description": (
            "Record a browser operation as a step in the pipeline.yaml. "
            "Call this AFTER each browser_* or goal_run operation completes successfully. "
            "This appends the step to the pipeline so it can be replayed later."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pipeline_name": {
                    "type": "string",
                    "description": "Name of the pipeline preset to record into.",
                },
                "step_name": {
                    "type": "string",
                    "description": "Unique name for this step, e.g. 'step_1', 'step_2'.",
                },
                "description": {
                    "type": "string",
                    "description": "Human-readable description of what this step does.",
                },
                "op_type": {
                    "type": "string",
                    "description": "The browser operation type: goto, click, fill, scroll, snapshot, source, eval, or goal_run.",
                },
                "op_args": {
                    "type": "object",
                    "description": "The exact arguments passed to the browser operation, e.g. {\"url\": \"https://baidu.com\"}.",
                },
                "explanation": {
                    "type": "string",
                    "description": "Brief explanation of why this step is needed in the pipeline.",
                },
            },
            "required": ["pipeline_name", "step_name", "description", "op_type", "op_args"],
        },
    },
}


def get_all_tools(include_goal_run: bool = True) -> list[dict[str, Any]]:
    """Get the full list of registered tools.

    Args:
        include_goal_run: If True, include the goal_run tool.

    Returns:
        List of OpenAI-compatible tool definitions.
    """
    tools = list(BROWSER_TOOLS)
    if include_goal_run:
        tools.append(GOAL_RUN_TOOL)
    tools.extend(PIPELINE_TOOLS)
    tools.append(RECORD_STEP_TOOL)
    return tools


def get_browser_tools() -> list[dict[str, Any]]:
    """Get only browser atomics (no goal_run)."""
    return list(BROWSER_TOOLS)
