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

EDIT_PIPELINE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "edit_pipeline",
        "description": (
            "Edit the current pipeline.yaml file. When you need to modify the pipeline "
            "structure (add/remove steps, change descriptions, adjust browser_ops), "
            "call this tool with the full updated YAML content. The user will see a "
            "diff preview and can confirm or revert your changes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pipeline_name": {
                    "type": "string",
                    "description": "Name of the pipeline preset to edit.",
                },
                "content": {
                    "type": "string",
                    "description": "Full YAML content to write to the pipeline file.",
                },
                "explanation": {
                    "type": "string",
                    "description": "Human-readable explanation of what was changed and why.",
                },
                "edit_id": {
                    "type": "string",
                    "description": "Optional edit ID. If you are editing the same pipeline multiple times in one turn, pass the same edit_id to accumulate changes into a single review.",
                },
            },
            "required": ["pipeline_name", "content", "explanation"],
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
    tools.append(EDIT_PIPELINE_TOOL)
    return tools


def get_browser_tools() -> list[dict[str, Any]]:
    """Get only browser atomics (no goal_run)."""
    return list(BROWSER_TOOLS)
