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
            "description": "Click an element on the page using a CSS selector. Use clickCount=2 for double-click.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for the element to click.",
                    },
                    "clickCount": {
                        "type": "integer",
                        "description": "Number of clicks. 1 = single click (default), 2 = double-click.",
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
            "description": "Fill text into an input element identified by CSS selector. NOTE: This clears existing content first. To append text without clearing, use browser_focus + browser_type_text instead.",
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
    {
        "type": "function",
        "function": {
            "name": "browser_hover",
            "description": "Hover the mouse over an element identified by CSS selector. Playwright auto-waits for the element to be visible and scrolls it into view.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for the element to hover over.",
                    },
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_unhover",
            "description": "Move the mouse away from the current element (to page top-left corner).",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for the element to unhover from (informational, mouse moves to 0,0).",
                    },
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_focus",
            "description": "Focus an element on the page. Use before browser_type_text to append text without clearing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for the element to focus.",
                    },
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_press_key",
            "description": "Press a keyboard key or key combination (e.g. 'Enter', 'Control+A', 'Escape').",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Key or key combination to press (e.g. 'Enter', 'Tab', 'Control+A', 'ArrowDown').",
                    },
                },
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_type_text",
            "description": "Type text character by character into the currently focused element. Does NOT clear existing content — use browser_focus first to position cursor, then type_text to append.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text to type character by character.",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_select",
            "description": "Select an option from a <select> dropdown element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for the <select> element.",
                    },
                    "value": {
                        "type": "string",
                        "description": "Option value, label text, or index number to select.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["value", "label", "index"],
                        "description": "How to match the option: 'value' (option value attribute), 'label' (display text), 'index' (0-based position). Default: 'value'.",
                    },
                },
                "required": ["selector", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_clear",
            "description": "Clear the content of an input element. Default uses JS (sets value=''), mode='pw' uses Playwright native clear.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for the input element to clear.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["js", "pw"],
                        "description": "Clear mode: 'js' (default, sets value='' via JS), 'pw' (Playwright native clear).",
                    },
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_copy",
            "description": "Copy text content from an element on the page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for the element to copy text from.",
                    },
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_paste",
            "description": "Paste clipboard content into an input element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "CSS selector for the input element to paste into.",
                    },
                    "index": {
                        "type": "integer",
                        "description": "Character position to insert at. -1 (default) appends to end.",
                    },
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Navigate browser history: go back, forward, or reload the current page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["back", "forward", "reload"],
                        "description": "Navigation action: 'back' (previous page), 'forward' (next page), 'reload' (refresh current page).",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_wait",
            "description": "Wait for a condition: time duration, element to appear, or page load state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["time", "selector", "load"],
                        "description": "Wait mode: 'time' (duration in ms), 'selector' (wait for element), 'load' (page load state). Default: 'time'.",
                    },
                    "duration": {
                        "type": "integer",
                        "description": "Time in milliseconds to wait (mode='time'). Default: 1000.",
                    },
                    "selector": {
                        "type": "string",
                        "description": "CSS selector to wait for (mode='selector').",
                    },
                    "state": {
                        "type": "string",
                        "enum": ["load", "domcontentloaded", "networkidle"],
                        "description": "Page load state to wait for (mode='load'). Default: 'load'.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_tab",
            "description": "Manage browser tabs: create new, switch to, close, or list all tabs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["new", "switch", "close", "list"],
                        "description": "Tab action: 'new' (create tab), 'switch' (switch to tab), 'close' (close tab), 'list' (list all tabs).",
                    },
                    "url": {
                        "type": "string",
                        "description": "URL to open in new tab (action='new'). Default: about:blank.",
                    },
                    "target_id": {
                        "type": "string",
                        "description": "Target tab ID to switch to or close (action='switch' or 'close').",
                    },
                },
                "required": ["action"],
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
            "and browser_ops, then use pipeline_create (new) or pipeline_update_step (existing) "
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

SKILL_LIST_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "skill_list",
        "description": "List all available skills with their names, descriptions, and tags.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
}

SKILL_VIEW_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "skill_view",
        "description": "View the full content of a skill (including YAML frontmatter and body).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The name of the skill to view.",
                },
            },
            "required": ["name"],
        },
    },
}

SKILL_CREATE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "skill_create",
        "description": (
            "Create a new skill. The frontmatter (name, description, tags) is "
            "generated automatically from the parameters — you do NOT need to "
            "write YAML frontmatter in the content. The content should be the "
            "skill body in Markdown format."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Skill name (kebab-case, e.g. 'web-search').",
                },
                "description": {
                    "type": "string",
                    "description": "Short description of what this skill does.",
                },
                "content": {
                    "type": "string",
                    "description": "The skill body in Markdown (no YAML frontmatter needed).",
                },
                "tags": {
                    "type": "array",
                    "description": "Optional tags for categorization.",
                    "items": {"type": "string"},
                },
            },
            "required": ["name", "description", "content"],
        },
    },
}

SKILL_EDIT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "skill_edit",
        "description": (
            "Edit an existing skill. By default only the body is replaced "
            "(frontmatter is preserved). Use raw=true to replace the entire file."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The name of the skill to edit.",
                },
                "content": {
                    "type": "string",
                    "description": (
                        "New body content (default mode) or full file content "
                        "including frontmatter (raw mode)."
                    ),
                },
                "raw": {
                    "type": "boolean",
                    "description": "If true, replace the entire file (must include valid frontmatter).",
                },
            },
            "required": ["name", "content"],
        },
    },
}

SKILL_DELETE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "skill_delete",
        "description": (
            "Delete a skill. Pre-installed skills (with 'system' tag) are protected. "
            "Use absorbed_into to record where the skill's content should be merged."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The name of the skill to delete.",
                },
                "absorbed_into": {
                    "type": "string",
                    "description": "Optional: name of the skill that absorbs this one's content.",
                },
            },
            "required": ["name"],
        },
    },
}

FILE_READ_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "file_read",
        "description": "读取文本文件内容，返回原始文本（不做格式解析）。二进制文件会提示使用 format_convert。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径",
                },
                "head": {
                    "type": "integer",
                    "description": "返回前 N 行，0 表示全部（默认 20）",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "最大返回字符数（默认 3000）",
                },
                "encoding": {
                    "type": "string",
                    "description": "文件编码，为空时自动检测（UTF-8 → GBK fallback）",
                },
            },
            "required": ["path"],
        },
    },
}

FILE_WRITE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "file_write",
        "description": "将文本内容写入文件，自动创建父目录。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径",
                },
                "content": {
                    "type": "string",
                    "description": "要写入的文本内容",
                },
                "encoding": {
                    "type": "string",
                    "description": "文件编码（默认 utf-8）",
                },
            },
            "required": ["path", "content"],
        },
    },
}

FORMAT_CONVERT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "format_convert",
        "description": "在 xlsx/csv/json 之间转换文件格式。支持 6 种转换方向，格式可从文件扩展名自动推断。",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "源文件路径",
                },
                "target": {
                    "type": "string",
                    "description": "目标文件路径",
                },
                "source_fmt": {
                    "type": "string",
                    "description": "源格式（xlsx/csv/json），为空时从扩展名推断",
                },
                "target_fmt": {
                    "type": "string",
                    "description": "目标格式（xlsx/csv/json），为空时从扩展名推断",
                },
            },
            "required": ["source", "target"],
        },
    },
}

EVAL_AGENT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "eval_agent",
        "description": (
            "启动子 Agent 处理复杂 DOM 操作或验证码识别。"
            "会额外消耗 LLM token，仅在 browser_eval 无法直接完成时使用。"
            "子 Agent 可执行多次 browser_eval + browser_snapshot 迭代试错。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "purpose": {
                    "type": "string",
                    "description": "eval agent 的任务目标描述",
                },
                "snapshot": {
                    "type": "string",
                    "description": "当前页面的 simplified snapshot 文本",
                },
                "max_attempts": {
                    "type": "integer",
                    "description": "最大 eval 尝试次数（默认 3）",
                },
            },
            "required": ["purpose", "snapshot"],
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
    tools.extend([
        SKILL_LIST_TOOL,
        SKILL_VIEW_TOOL,
        SKILL_CREATE_TOOL,
        SKILL_EDIT_TOOL,
        SKILL_DELETE_TOOL,
    ])
    tools.append(FILE_READ_TOOL)
    tools.append(FILE_WRITE_TOOL)
    tools.append(FORMAT_CONVERT_TOOL)
    tools.append(EVAL_AGENT_TOOL)
    logger.debug("get_all_tools: registered %d tools (include_goal_run=%s)", len(tools), include_goal_run)
    return tools


def get_browser_tools() -> list[dict[str, Any]]:
    """Get only browser atomics (no goal_run)."""
    tools = list(BROWSER_TOOLS)
    logger.debug("get_browser_tools: registered %d tools", len(tools))
    return tools
