"""Tool registration — OpenAI-compatible tool definitions for browser operations and goal_run.

Provides tool schemas for registration with LLM providers. These are
the tools that the Agent can call during conversation_loop.
"""

from __future__ import annotations

from typing import Any

from utils.logging import get_logger

logger = get_logger(__name__)

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
            "description": "Capture page snapshot. 推荐渐进式使用：simplified 看概览 → interactive+in_viewport+query 精准找 → interactive+query 全量搜 → interactive 全量看。",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["interactive", "full", "simplified"],
                        "description": "simplified（页面概览，含标题/链接/表格，token 最少）→ interactive（可交互元素列表，带 @e_XXXXX ref，token 较多）→ full（截图+HTML，token 最多，一般不需要）。",
                    },
                    "query": {
                        "type": "string",
                        "description": "仅 interactive 模式有效。不以 #/. 开头时按文本/tag/type/role 模糊匹配；以 # 或 . 开头时按 CSS selector 精确匹配。过滤后只有匹配元素会注册高亮和 ref 查找。如果没找到目标，省略 query 重新调用获取全量。",
                    },
                    "in_viewport": {
                        "type": "boolean",
                        "description": "仅 interactive 模式有效。为 true 时只返回当前屏幕可见区域内的元素，减少无关噪音。默认 false（全量）。",
                    },
                },
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
                "properties": {
                    "cached": {
                        "type": "boolean",
                        "description": "If true, read HTML from scratchpad cache instead of CDP. Falls back to CDP if no cache.",
                    },
                },
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
    {
        "type": "function",
        "function": {
            "name": "browser_get_element_by_number",
            "description": "Get detailed information about an interactive element by its reference number (e.g. @e_12345). Looks up from the most recent browser_snapshot cache first, falls back to CDP if not found. Use this to check element details (tag, text, selector) before clicking or filling.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ref": {
                        "type": "string",
                        "description": "Element reference, e.g. '@e_12345', 'e_12345', '12345' (stable CDP backend_node_id).",
                    },
                },
                "required": ["ref"],
            },
        },
    },
]

GOAL_RUN_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "goal_run",
        "description": (
            "Set a complex multi-step goal. The system will guide you to use "
            "todo + browser_* tools to break down and execute the task step by step. "
            "Use this for tasks that require reasoning across multiple pages "
            "or analyzing page content to decide the next action."
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
                        "depends_on (list of strings), check (dict)."
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
                "check": {
                    "type": "object",
                    "description": (
                        "Optional programmatic check conditions for this step. "
                        "Supported keys: url_contains, element_exists, text_contains, element_visible."
                    ),
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
                        "depends_on (list of strings), check (dict)."
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

PIPELINE_FINISH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "pipeline_finish",
        "description": (
            "Signal that the pipeline execution is complete. Call this when you "
            "have finished all remaining pipeline steps. Use status='completed' "
            "for success or status='failed' with a summary if you cannot complete."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["completed", "failed"],
                    "description": "Whether the pipeline completed successfully or failed.",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief summary of what was accomplished or why it failed.",
                },
            },
            "required": ["status"],
        },
    },
}

PIPELINE_COMPILE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "pipeline_compile",
        "description": (
            "Read the current chat session's browser operations and return them as "
            "structured step definitions. This tool is READ-ONLY — it does NOT write "
            "any file. Review the returned steps, add 'check' fields, refine descriptions "
            "and browser_ops, then use pipeline_create (new) or edit_pipeline (existing) "
            "to save the pipeline."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pipeline_name": {
                    "type": "string",
                    "description": "Name for the pipeline preset (used as identifier, not written).",
                },
                "explanation": {
                    "type": "string",
                    "description": "Brief explanation of what was compiled.",
                },
            },
            "required": ["pipeline_name"],
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
    PIPELINE_COMPILE_TOOL,
    PIPELINE_FINISH_TOOL,
]

RECORD_STEP_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "record_step",
        "description": (
            "Record a browser operation as a step in the pipeline.yaml. "
            "Call this AFTER each browser_* operation completes successfully. "
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
                    "description": "The browser operation type: goto, click, fill, scroll, snapshot, source, eval.",
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

TODO_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "todo",
        "description": (
            "Manage a structured task list for your current session. "
            "Use this to track progress on multi-step tasks. "
            "Call without arguments to read the current list. "
            "Pass `todos` with `merge=false` (default) to replace the entire list. "
            "Pass `todos` with `merge=true` to update existing items by id and append new ones. "
            "Each item should have: id (unique string), content (description), "
            "status (one of: pending, in_progress, completed, cancelled)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "description": (
                        "List of todo items. Each item is an object with: "
                        "id (string, auto-generated if omitted), "
                        "content (string, description of the task), "
                        "status (string, one of: pending, in_progress, completed, cancelled). "
                        "Omit this parameter to read the current list."
                    ),
                    "items": {"type": "object"},
                },
                "merge": {
                    "type": "boolean",
                    "description": (
                        "If true, merge the provided todos with the existing list by id "
                        "(update matching ids, append new ones). "
                        "If false (default), replace the entire list."
                    ),
                },
            },
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
    tools.append(TODO_TOOL)
    logger.debug("get_all_tools: registered %d tools (include_goal_run=%s)", len(tools), include_goal_run)
    return tools


def get_browser_tools() -> list[dict[str, Any]]:
    """Get only browser atomics (no goal_run)."""
    tools = list(BROWSER_TOOLS)
    logger.debug("get_browser_tools: registered %d tools", len(tools))
    return tools
