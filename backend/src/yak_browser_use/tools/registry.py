"""ToolRegistry — unified tool registration, schema query, and dispatch routing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)

# ── Lazy-loaded dispatch maps (imported once, cached) ────────────────────────

_pipeline_dispatch: dict | None = None
_skill_dispatch: dict | None = None


def _get_pipeline_dispatch() -> dict:
    global _pipeline_dispatch
    if _pipeline_dispatch is None:
        from yak_browser_use.engine._harness.pipeline_tools import (
            pipeline_load,
            pipeline_list,
            pipeline_update_step,
            pipeline_add_step,
            pipeline_remove_step,
            pipeline_create,
            pipeline_compile,
        )
        _pipeline_dispatch = {
            "pipeline_load": pipeline_load,
            "pipeline_list": pipeline_list,
            "pipeline_update_step": pipeline_update_step,
            "pipeline_add_step": pipeline_add_step,
            "pipeline_remove_step": pipeline_remove_step,
            "pipeline_create": pipeline_create,
            "pipeline_compile": pipeline_compile,
        }
    return _pipeline_dispatch


def _get_skill_dispatch() -> dict:
    global _skill_dispatch
    if _skill_dispatch is None:
        from yak_browser_use.engine._harness.skill_tools import (
            skill_list,
            skill_view,
            skill_create,
            skill_edit,
            skill_delete,
        )
        _skill_dispatch = {
            "skill_list": skill_list,
            "skill_view": skill_view,
            "skill_create": skill_create,
            "skill_edit": skill_edit,
            "skill_delete": skill_delete,
        }
    return _skill_dispatch


@dataclass
class ToolDef:
    name: str
    schema: dict
    handler: Callable


@dataclass
class ToolContext:
    cdp_helpers: object | None = None
    tools_dir: Path | None = None
    pipeline_name: str = ""
    budget: object | None = None
    llm_call: Callable | None = None
    interrupt_check: Callable[[], bool] | None = None
    stream_callback: Callable[[dict], None] | None = None
    shared_store: dict | None = None


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDef] = {}

    def register(self, name: str, schema: dict, handler: Callable) -> None:
        self._tools[name] = ToolDef(name=name, schema=schema, handler=handler)
        logger.debug("tool registered: %s", name)

    def get_schemas(self) -> list[dict]:
        return [
            {"type": "function", "function": {**td.schema, "name": td.name}}
            for td in self._tools.values()
        ]

    def get_names(self) -> list[str]:
        return list(self._tools.keys())

    def filter(self, allowed: set[str]) -> list[dict]:
        return [
            {"type": "function", "function": {**self._tools[n].schema, "name": n}}
            for n in allowed
            if n in self._tools
        ]

    async def dispatch(self, name: str, args: dict, ctx: ToolContext) -> dict:
        td = self._tools.get(name)
        if td is None:
            return {"ok": False, "error": f"Unknown tool: {name}"}
        return await td.handler(args, ctx)


registry = ToolRegistry()


def build_registry() -> None:
    if registry._tools:
        return
    try:
        _build_registry_impl()
    except Exception:
        registry._tools.clear()
        raise


def _build_registry_impl() -> None:
    from yak_browser_use.engine.executor import execute_browser_op, execute_tool

    # ── browser_* tools ──────────────────────────────────────────────

    _BROWSER_OPS = [
        "goto", "click", "fill", "snapshot", "scroll", "source", "eval",
        "get_element_by_number", "hover", "unhover", "focus", "select",
        "clear", "keyboard", "press_key", "type_text", "navigate", "wait",
        "tab", "copy", "paste", "expand_branch",
    ]

    _BROWSER_SCHEMAS: dict[str, dict] = {
        "goto": {
            "description": "Navigate the browser to a specified URL.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "The URL to navigate to."}},
                "required": ["url"],
            },
        },
        "click": {
            "description": "Click an element on the page using a CSS selector. Use clickCount=2 for double-click.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector for the element to click."},
                    "clickCount": {"type": "integer", "description": "Number of clicks. 1 = single click (default), 2 = double-click."},
                },
                "required": ["selector"],
            },
        },
        "fill": {
            "description": "Fill text into an input element identified by CSS selector. NOTE: This clears existing content first. To append text without clearing, use browser_focus + browser_type_text instead. For passwords/secrets, use text={\"param_key\": \"key-name\"} — the value is resolved server-side and never appears in conversation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector for the input element."},
                    "text": {
                        "oneOf": [
                            {"type": "string", "description": "Plain text to fill into the input."},
                            {"type": "object",
                             "properties": {"param_key": {"type": "string", "description": "Stored credential key name. The secret value is resolved server-side and never appears in conversation."}},
                             "required": ["param_key"],
                             "description": "Use a stored credential instead of plain text."},
                        ],
                        "description": "Text to fill, or {\"param_key\": \"my-pwd\"} to use a stored secret.",
                    },
                },
                "required": ["selector", "text"],
            },
        },
        "snapshot": {
            "description": "Capture page snapshot.\n"
                           "aria（默认推荐）采用 Playwright aria_snapshot(mode='ai') 获取 YAML 语义树，\n"
                           "展示页面所有可交互元素的 role/name 层级结构，LLM 友好、token 最少。\n"
                           "适合先了解页面结构和可用操作，然后配合其他动作执行。\n"
                           "a11y 采用 CDP Accessibility.getFullAXTree 获取结构化元素列表，\n"
                           "每个元素带 ref/role/name/nth/selector，可间接用于 click/fill/hover 等操作。\n"
                           "progressive 采用 CDP DOM 深度扫描 + 密度自适应折叠，\n"
                           "最多 200 元素，密集容器折叠后可用 expand_branch 展开浏览。\n"
                           "适合订单列表、搜索结果等复杂长页面。\n"
                           "full 截图+HTML 全量转储作为最后兜底可用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["aria", "a11y", "progressive", "full"],
                        "description": "aria（默认推荐）YAML 语义树，LLM 友好、token 少，适合了解页面结构；"
                                       "a11y 结构化元素列表（带 ref/selector），适合后续操作；"
                                       "progressive DOM 深度扫描+折叠，适合长列表复杂页面；"
                                       "full 截图+HTML 全量转储。",
                    },
                    "query": {
                        "type": "string",
                        "description": "仅 progressive/interactive 模式有效。不以 #/. 开头时按文本/tag/type/role 模糊匹配；以 # 或 . 开头时按 CSS selector 精确匹配。",
                    },
                    "in_viewport": {
                        "type": "boolean",
                        "description": "仅 interactive 模式有效。为 true 时只返回当前屏幕可见区域内的元素。",
                    },
                },
            },
        },
        "expand_branch": {
            "description": "Expand a folded container from a progressive snapshot. Each folded container only shows a few representative items; use this to browse deeper. Returns paginated elements (limit=30 per page, use offset for next page).",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Container key from folded_containers list, e.g. 'c_117'"},
                    "limit": {"type": "integer", "description": "Max items to return (default 30)."},
                    "offset": {"type": "integer", "description": "Pagination offset for subsequent pages."},
                },
                "required": ["key"],
            },
        },
        "scroll": {
            "description": "Scroll the current page up or down.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down"], "description": "Direction to scroll."},
                    "amount": {"type": "integer", "description": "Amount in pixels to scroll (default 300)."},
                },
                "required": ["direction"],
            },
        },
        "source": {
            "description": "Get the full HTML source of the current page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cached": {"type": "boolean", "description": "If true, read HTML from scratchpad cache instead of CDP. Falls back to CDP if no cache."},
                },
            },
        },
        "eval": {
            "description": "Execute arbitrary JavaScript code on the current page and return the result.",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string", "description": "JavaScript code to execute."}},
                "required": ["code"],
            },
        },
        "get_element_by_number": {
            "description": "Get detailed information about an interactive element by its prog_label (hierarchical path like '0-2-175') or ref number. The badge on the page shows the prog_label; use it to look up element details (selector, tag, text) before clicking or filling.",
            "parameters": {
                "type": "object",
                "properties": {"ref": {"type": "string", "description": "Element prog_label (e.g. '0-2-175' shown on badge) or numeric ref."}},
                "required": ["ref"],
            },
        },
        "hover": {
            "description": "Hover the mouse over an element identified by CSS selector. Playwright auto-waits for the element to be visible and scrolls it into view.",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string", "description": "CSS selector for the element to hover over."}},
                "required": ["selector"],
            },
        },
        "unhover": {
            "description": "Move the mouse away from the current element (to page top-left corner).",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string", "description": "CSS selector for the element to unhover from (informational, mouse moves to 0,0)."}},
                "required": ["selector"],
            },
        },
        "focus": {
            "description": "Focus an element on the page. Use before browser_type_text to append text without clearing.",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string", "description": "CSS selector for the element to focus."}},
                "required": ["selector"],
            },
        },
        "select": {
            "description": "Select an option from a <select> dropdown element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector for the <select> element."},
                    "value": {"type": "string", "description": "Option value, label text, or index number to select."},
                    "mode": {"type": "string", "enum": ["value", "label", "index"], "description": "How to match the option: 'value' (option value attribute), 'label' (display text), 'index' (0-based position). Default: 'value'."},
                },
                "required": ["selector", "value"],
            },
        },
        "clear": {
            "description": "Clear the content of an input element. Default uses JS (sets value=''), mode='pw' uses Playwright native clear.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector for the input element to clear."},
                    "mode": {"type": "string", "enum": ["js", "pw"], "description": "Clear mode: 'js' (default, sets value='' via JS), 'pw' (Playwright native clear)."},
                },
                "required": ["selector"],
            },
        },
        "keyboard": {
            "description": "Press a key or type text. mode='key' for single keys (e.g. 'Enter', 'Tab'), mode='text' to type a string. For passwords/secrets in mode='text', use text={\"param_key\": \"key-name\"} — the value is resolved server-side and never appears in conversation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["key", "text"], "description": "'key' to press a single key, 'text' to type a string."},
                    "key": {"type": "string", "description": "Key or key combination to press (mode='key'). e.g. 'Enter', 'Tab', 'Control+A'."},
                    "text": {
                        "oneOf": [
                            {"type": "string", "description": "Plain text to type (mode='text')."},
                            {"type": "object",
                             "properties": {"param_key": {"type": "string", "description": "Stored credential key name."}},
                             "required": ["param_key"],
                             "description": "Use a stored credential instead of plain text."},
                        ],
                        "description": "Text to type, or {\"param_key\": \"my-pwd\"} to use a stored secret.",
                    },
                },
                "required": [],
            },
        },
        "press_key": {
            "description": "Press a keyboard key or key combination (e.g. 'Enter', 'Control+A', 'Escape').",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string", "description": "Key or key combination to press (e.g. 'Enter', 'Tab', 'Control+A', 'ArrowDown')."}},
                "required": ["key"],
            },
        },
        "type_text": {
            "description": "Type text character by character into the currently focused element. Does NOT clear existing content — use browser_focus first to position cursor, then type_text to append. For passwords/secrets, use text={\"param_key\": \"key-name\"} — the value is resolved server-side and never appears in conversation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "oneOf": [
                            {"type": "string", "description": "Plain text to type character by character."},
                            {"type": "object",
                             "properties": {"param_key": {"type": "string", "description": "Stored credential key name."}},
                             "required": ["param_key"],
                             "description": "Use a stored credential instead of plain text."},
                        ],
                        "description": "Text to type, or {\"param_key\": \"my-pwd\"} to use a stored secret.",
                    },
                },
                "required": ["text"],
            },
        },
        "navigate": {
            "description": "Navigate browser history: go back, forward, or reload the current page.",
            "parameters": {
                "type": "object",
                "properties": {"action": {"type": "string", "enum": ["back", "forward", "reload"], "description": "Navigation action: 'back' (previous page), 'forward' (next page), 'reload' (refresh current page)."}},
                "required": ["action"],
            },
        },
        "wait": {
            "description": "Wait for a condition: time duration, element to appear, or page load state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["time", "selector", "load"], "description": "Wait mode: 'time' (duration in ms), 'selector' (wait for element), 'load' (page load state). Default: 'time'."},
                    "duration": {"type": "integer", "description": "Time in milliseconds to wait (mode='time'). Default: 1000."},
                    "selector": {"type": "string", "description": "CSS selector to wait for (mode='selector')."},
                    "state": {"type": "string", "enum": ["load", "domcontentloaded", "networkidle"], "description": "Page load state to wait for (mode='load'). Default: 'load'."},
                },
                "required": [],
            },
        },
        "tab": {
            "description": "Manage browser tabs: create new, switch to, close, or list all tabs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["new", "switch", "close", "list"], "description": "Tab action: 'new' (create tab), 'switch' (switch to tab), 'close' (close tab), 'list' (list all tabs)."},
                    "url": {"type": "string", "description": "URL to open in new tab (action='new'). Default: about:blank."},
                    "target_id": {"type": "string", "description": "Target tab ID to switch to or close (action='switch' or 'close')."},
                },
                "required": ["action"],
            },
        },
        "copy": {
            "description": "Copy text content from an element on the page.",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string", "description": "CSS selector for the element to copy text from."}},
                "required": ["selector"],
            },
        },
        "paste": {
            "description": "Paste clipboard content into an input element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector for the input element to paste into."},
                    "index": {"type": "integer", "description": "Character position to insert at. -1 (default) appends to end."},
                },
                "required": ["selector"],
            },
        },
    }

    for op_type in _BROWSER_OPS:
        schema = _BROWSER_SCHEMAS.get(op_type, {})

        def _make_browser_handler(op: str):
            async def handler(args: dict, ctx: ToolContext) -> dict:
                if ctx.cdp_helpers is None:
                    return {"ok": False, "error": "浏览器不可用 — 请确保 CDP 连接已建立"}
                bridge = ctx.cdp_helpers.bridge if hasattr(ctx.cdp_helpers, "bridge") else ctx.cdp_helpers
                return await execute_browser_op(op, args, bridge)
            return handler

        registry.register(f"browser_{op_type}", schema, _make_browser_handler(op_type))

    # ── pipeline_* tools ─────────────────────────────────────────────

    _PIPELINE_SCHEMAS = {
        "pipeline_load": {
            "description": "Load a pipeline preset and return a structured summary (step list, types, dependencies, required_params). Does NOT return the full YAML content — use this to understand the pipeline structure before making changes.",
            "parameters": {
                "type": "object",
                "properties": {"pipeline_name": {"type": "string", "description": "Name of the pipeline preset to load."}},
                "required": ["pipeline_name"],
            },
        },
        "pipeline_list": {
            "description": "List all available pipeline presets. Returns name, description, and step count for each preset.",
            "parameters": {"type": "object", "properties": {}},
        },
        "pipeline_update_step": {
            "description": "Incrementally update a single step in a pipeline. Only the fields provided in `updates` are modified; all other fields stay unchanged. When changing browser_ops, tool_name, or goal_description, mutually exclusive fields are automatically cleared.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pipeline_name": {"type": "string", "description": "Name of the pipeline preset to modify."},
                    "step_name": {"type": "string", "description": "Name of the step to update."},
                    "updates": {"type": "object", "description": "Fields to update on the step. Supported keys: browser_ops (list of single-key dicts), tool_name (string), goal_description (string), description (string), depends_on (list of strings), check (dict)."},
                    "explanation": {"type": "string", "description": "Human-readable explanation of what was changed and why."},
                },
                "required": ["pipeline_name", "step_name", "updates"],
            },
        },
        "pipeline_add_step": {
            "description": "Add a new step to a pipeline. If `after` is provided, the step is inserted after the named step; otherwise it is appended to the end. Set `heading=true` to create an outline placeholder step with only name + description (no browser_ops/tool_name/goal_description).",
            "parameters": {
                "type": "object",
                "properties": {
                    "pipeline_name": {"type": "string", "description": "Name of the pipeline preset to modify."},
                    "step_name": {"type": "string", "description": "Unique name for the new step."},
                    "description": {"type": "string", "description": "Human-readable description of what this step does."},
                    "browser_ops": {"type": "array", "description": "List of browser operations, each as a single-key dict (e.g. [{\"goto\": \"https://example.com\"}]). Mutually exclusive with tool_name and goal_description.", "items": {"type": "object"}},
                    "tool_name": {"type": "string", "description": "Name of a custom tool to invoke. Mutually exclusive with browser_ops and goal_description."},
                    "goal_description": {"type": "string", "description": "Description for a goal_run step. Mutually exclusive with browser_ops and tool_name."},
                    "depends_on": {"type": "array", "description": "List of step names this step depends on.", "items": {"type": "string"}},
                    "check": {"type": "object", "description": "Optional programmatic check conditions for this step. Supported keys: url_contains, element_exists, text_contains, element_visible."},
                    "after": {"type": "string", "description": "Name of the step to insert after. Omit to append."},
                    "heading": {"type": "boolean", "description": "Set to true to create an outline placeholder step without browser_ops, tool_name, or goal_description."},
                    "explanation": {"type": "string", "description": "Human-readable explanation of what was changed and why."},
                },
                "required": ["pipeline_name", "step_name", "description"],
            },
        },
        "pipeline_remove_step": {
            "description": "Remove a step from a pipeline. Dependencies on the removed step are automatically cleaned up from other steps.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pipeline_name": {"type": "string", "description": "Name of the pipeline preset to modify."},
                    "step_name": {"type": "string", "description": "Name of the step to remove."},
                    "explanation": {"type": "string", "description": "Human-readable explanation of what was changed and why."},
                },
                "required": ["pipeline_name", "step_name"],
            },
        },
        "pipeline_create": {
            "description": "Create a new pipeline preset from a list of steps. Fails if a pipeline with the same name already exists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pipeline_name": {"type": "string", "description": "Name for the new pipeline preset."},
                    "description": {"type": "string", "description": "Human-readable description of the pipeline."},
                    "steps": {"type": "array", "description": "List of step objects. Each step must have: name (string), description (string). Optional: browser_ops (list of dicts), tool_name (string), goal_description (string), depends_on (list of strings), check (dict).", "items": {"type": "object"}},
                    "explanation": {"type": "string", "description": "Human-readable explanation of what was created and why."},
                },
                "required": ["pipeline_name", "description", "steps"],
            },
        },
        "pipeline_compile": {
            "description": "Read the current chat session's browser operations and return them as structured step definitions. This tool is READ-ONLY — it does NOT write any file. Review the returned steps, add 'check' fields, refine descriptions and browser_ops, then use pipeline_create (new) or pipeline_update_step (existing) to save the pipeline.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pipeline_name": {"type": "string", "description": "Name for the pipeline preset (used as identifier, not written)."},
                    "explanation": {"type": "string", "description": "Brief explanation of what was compiled."},
                },
                "required": ["pipeline_name"],
            },
        },
        "pipeline_finish": {
            "description": "Signal that the pipeline execution is complete. Call this when you have finished all remaining pipeline steps. Use status='completed' for success or status='failed' with a summary if you cannot complete.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["completed", "failed"], "description": "Whether the pipeline completed successfully or failed."},
                    "summary": {"type": "string", "description": "Brief summary of what was accomplished or why it failed."},
                },
                "required": ["status"],
            },
        },
    }

    for name, schema in _PIPELINE_SCHEMAS.items():
        if name == "pipeline_finish":

            async def _pipeline_finish_handler(args: dict, ctx: ToolContext) -> dict:
                status = args.get("status", "")
                if status not in ("completed", "failed"):
                    logger.warning("pipeline_finish: invalid status '%s', defaulting to 'completed'", status)
                    status = "completed"
                summary = args.get("summary", "")
                if ctx.budget is not None:
                    ctx.budget.exhaust()
                return {"ok": True, "status": status, "summary": summary, "_pipeline_finish": True}

            registry.register("pipeline_finish", schema, _pipeline_finish_handler)
        else:

            def _make_pipeline_handler(hn: str):
                async def handler(args: dict, ctx: ToolContext) -> dict:
                    fn = _get_pipeline_dispatch()[hn]
                    result = await fn(**args)
                    if isinstance(result, str):
                        return {"ok": True, "result": result}
                    if "result" not in result and result.get("ok"):
                        result["result"] = json.dumps(
                            {k: v for k, v in result.items() if k not in ("ok", "result")},
                            ensure_ascii=False,
                        )
                    return result
                return handler

            registry.register(name, schema, _make_pipeline_handler(name))

    # ── goal_run ─────────────────────────────────────────────────────

    registry.register("goal_run", {
        "description": "Set a complex multi-step goal. The system will guide you to use todo + browser_* tools to break down and execute the task step by step. Use this for tasks that require reasoning across multiple pages or analyzing page content to decide the next action.",
        "parameters": {
            "type": "object",
            "properties": {"description": {"type": "string", "description": "A clear description of what the Agent should accomplish."}},
            "required": ["description"],
        },
    }, _goal_run_handler)

    # ── todo ─────────────────────────────────────────────────────────

    registry.register("todo", {
        "description": "Manage a structured task list for your current session. Use this to track progress on multi-step tasks. Call without arguments to read the current list. Pass `todos` with `merge=false` (default) to replace the entire list. Pass `todos` with `merge=true` to update existing items by id and append new ones. Each item should have: id (unique string), content (description), status (one of: pending, in_progress, completed, cancelled).",
        "parameters": {
            "type": "object",
            "properties": {
                "todos": {"type": "array", "description": "List of todo items. Each item is an object with: id (string, auto-generated if omitted), content (string, description of the task), status (string, one of: pending, in_progress, completed, cancelled). Omit this parameter to read the current list.", "items": {"type": "object"}},
                "merge": {"type": "boolean", "description": "If true, merge the provided todos with the existing list by id (update matching ids, append new ones). If false (default), replace the entire list."},
            },
        },
    }, _todo_handler)

    # ── file_read / file_write / format_convert ──────────────────────

    registry.register("file_read", {
        "description": "读取文本文件内容，返回原始文本（不做格式解析）。二进制文件会提示使用 format_convert。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "head": {"type": "integer", "description": "返回前 N 行，0 表示全部（默认 20）"},
                "max_chars": {"type": "integer", "description": "最大返回字符数（默认 3000）"},
                "encoding": {"type": "string", "description": "文件编码，为空时自动检测（UTF-8 → GBK fallback）"},
            },
            "required": ["path"],
        },
    }, _file_read_handler)

    registry.register("file_write", {
        "description": "将文本内容写入文件，自动创建父目录。content 支持 {key} 引用：content: \"{key}\" 可从 shared_store 读取其他 tool 的输出数据，避免大数据绕经 LLM 上下文。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "要写入的文本内容"},
                "encoding": {"type": "string", "description": "文件编码（默认 utf-8）"},
            },
            "required": ["path", "content"],
        },
    }, _file_write_handler)

    registry.register("format_convert", {
        "description": "转换文件格式（xlsx/csv/json 互转）。根据文件扩展名自动识别源/目标格式，也可显式指定。",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "源文件路径"},
                "target": {"type": "string", "description": "目标文件路径"},
                "source_fmt": {"type": "string", "description": "源格式（xlsx/csv/json），为空时从扩展名推断"},
                "target_fmt": {"type": "string", "description": "目标格式（xlsx/csv/json），为空时从扩展名推断"},
            },
            "required": ["source", "target"],
        },
    }, _format_convert_handler)

    # ── skill_* tools ────────────────────────────────────────────────

    _SKILL_SCHEMAS = {
        "skill_list": {
            "description": "List all available skills with their names, descriptions, and tags.",
            "parameters": {"type": "object", "properties": {}},
        },
        "skill_view": {
            "description": "View the full content of a skill (including YAML frontmatter and body).",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "The name of the skill to view."}},
                "required": ["name"],
            },
        },
        "skill_create": {
            "description": "Create a new skill. The frontmatter (name, description, tags) is generated automatically from the parameters — you do NOT need to write YAML frontmatter in the content. The content should be the skill body in Markdown format.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name (kebab-case, e.g. 'web-search')."},
                    "description": {"type": "string", "description": "Short description of what this skill does."},
                    "content": {"type": "string", "description": "The skill body in Markdown (no YAML frontmatter needed)."},
                    "tags": {"type": "array", "description": "Optional tags for categorization.", "items": {"type": "string"}},
                },
                "required": ["name", "description", "content"],
            },
        },
        "skill_edit": {
            "description": "Edit an existing skill. By default only the body is replaced (frontmatter is preserved). Use raw=true to replace the entire file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The name of the skill to edit."},
                    "content": {"type": "string", "description": "New body content (default mode) or full file content including frontmatter (raw mode)."},
                    "raw": {"type": "boolean", "description": "If true, replace the entire file (must include valid frontmatter)."},
                },
                "required": ["name", "content"],
            },
        },
        "skill_delete": {
            "description": "Delete a skill. Pre-installed skills (with 'system' tag) are protected. Use absorbed_into to record where the skill's content should be merged.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The name of the skill to delete."},
                    "absorbed_into": {"type": "string", "description": "Optional: name of the skill that absorbs this one's content."},
                },
                "required": ["name"],
            },
        },
    }

    for name, schema in _SKILL_SCHEMAS.items():

        def _make_skill_handler(hn: str):
            async def handler(args: dict, ctx: ToolContext) -> dict:
                fn = _get_skill_dispatch()[hn]
                return fn(**args)
            return handler

        registry.register(name, schema, _make_skill_handler(name))

    # ── record_step ──────────────────────────────────────────────────

    registry.register("record_step", {
        "description": "Record a browser operation as a step in the pipeline.yaml. Call this AFTER each browser_* operation completes successfully. This appends the step to the pipeline so it can be replayed later. When op_type is omitted, creates an outline placeholder step with only name + description — fill it later by calling record_step again with the same step_name and op_type.",
        "parameters": {
            "type": "object",
            "properties": {
                "pipeline_name": {"type": "string", "description": "Name of the pipeline preset to record into."},
                "step_name": {"type": "string", "description": "Unique name for this step, e.g. 'step_1', 'step_2'."},
                "description": {"type": "string", "description": "Human-readable description of what this step does."},
                "op_type": {"type": "string", "description": "The browser operation type: goto, click, fill, scroll, snapshot, source, eval. Omit to create an outline placeholder step."},
                "op_args": {"type": "object", "description": "The exact arguments passed to the browser operation, e.g. {\"url\": \"https://baidu.com\"}."},
                "explanation": {"type": "string", "description": "Brief explanation of why this step is needed in the pipeline."},
            },
            "required": ["pipeline_name", "step_name", "description"],
        },
    }, _record_step_handler)

    # ── eval_agent ───────────────────────────────────────────────────

    registry.register("eval_agent", {
        "description": "启动子 Agent 处理复杂 DOM 操作或验证码识别。会额外消耗 LLM token，仅在 browser_eval 无法直接完成时使用。子 Agent 可执行多次 browser_eval + browser_snapshot 迭代试错。",
        "parameters": {
            "type": "object",
            "properties": {
                "purpose": {"type": "string", "description": "eval agent 的任务目标描述"},
                "snapshot": {"type": "string", "description": "当前页面的 simplified snapshot 文本"},
                "max_attempts": {"type": "integer", "description": "最大 eval 尝试次数（默认 3）"},
                "source_key": {"type": "string", "description": "可选，指定结果存入 shared_store 的 key。设置后子 Agent 的结果可通过其他 tool 的 {key} 引用，避免大数据绕经 LLM 上下文。"},
            },
            "required": ["purpose", "snapshot"],
        },
    }, _eval_agent_handler)

    # ── captcha ───────────────────────────────────────────────────────

    registry.register("captcha", {
        "description": "识别验证码图片。支持文字验证码（OCR）和滑块缺口检测。提供 dom_selector 时自动从页面 img 元素提取图片数据，无需手动传 image_bytes。",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["ocr", "slide"],
                    "description": "验证码类型：ocr（识别文字）、slide（检测滑块缺口位置）"
                },
                "dom_selector": {
                    "type": "string",
                    "description": "页面中验证码图片元素的 CSS 选择器（如 img[alt*='验证码']）。提供后自动从页面提取图片数据，无需手动传 image_bytes 或 image_path。"
                },
                "image_bytes": {
                    "type": "string",
                    "description": "验证码图片的 base64 编码数据（纯 base64 字符串，不带 data:image/... 前缀）"
                },
                "image_path": {
                    "type": "string",
                    "description": "验证码图片的文件路径（preset 模式下替代 image_bytes）"
                },
                "background_bytes": {
                    "type": "string",
                    "description": "仅 slide 模式需要：滑块背景图的 base64 编码数据"
                }
            },
            "required": ["type"]
        },
    }, _captcha_handler)

    logger.info("build_registry: registered %d tools", len(registry._tools))


# ── Handler functions ──────────────────────────────────────────────────────


async def _captcha_handler(args: dict, ctx: ToolContext) -> dict:
    from yak_browser_use.tools.captcha import captcha

    # dom_selector → extract image from page via CDP, no base64 in LLM context
    if args.get("dom_selector"):
        if not ctx.cdp_helpers:
            return {"ok": False, "error": "dom_selector 需要浏览器连接"}
        selector = args.pop("dom_selector")
        bridge = getattr(ctx.cdp_helpers, "bridge", None)
        if bridge is None:
            return {"ok": False, "error": "浏览器不可用"}
        safe_sel = selector.replace("'", "\\'")
        js = (
            "(()=>{"
            "const e=document.querySelector('" + safe_sel + "');"
            "if(!e)return{error:'NOT_FOUND'};"
            "if(e.tagName!=='IMG')return{error:'NOT_IMG'};"
            "const c=document.createElement('canvas');"
            "c.width=e.naturalWidth;c.height=e.naturalHeight;"
            "c.getContext('2d').drawImage(e,0,0);"
            "return{data:c.toDataURL('image/png').split(',')[1]};"
            "})()"
        )
        try:
            result = await bridge.evaluate(js)
        except Exception as e:
            return {"ok": False, "error": f"从页面提取图片失败: {e}"}
        if isinstance(result, dict):
            if "error" in result:
                return {"ok": False, "error": result["error"]}
            b64 = result.get("data", "")
            if b64:
                args["image_bytes"] = b64
            else:
                return {"ok": False, "error": "提取到的图片数据为空"}
        else:
            return {"ok": False, "error": f"页面 JS 返回异常: {result}"}

    kwargs = {k: args[k] for k in ("type", "image_bytes", "image_path", "background_bytes") if k in args}
    return await captcha(**kwargs)


async def _goal_run_handler(args: dict, ctx: ToolContext) -> dict:
    description = args.get("description", args.get("goal", ""))
    return {
        "ok": True,
        "result": (
            f"目标已设定: {description}\n\n"
            f"请用 todo 工具将目标拆解为 3-6 个步骤逐项执行。"
            f"每步完成后调 record_step。不确定时直接问我。"
        ),
    }


async def _todo_handler(args: dict, ctx: ToolContext) -> dict:
    from yak_browser_use.tools.todo_store import current_store
    from yak_browser_use.tools.todo import todo

    store = current_store.get()
    todos = args.get("todos")
    merge = args.get("merge", False)
    result_str = await todo(todos=todos, merge=merge, store=store)
    return {"ok": True, "result": result_str}


async def _file_read_handler(args: dict, ctx: ToolContext) -> dict:
    from yak_browser_use.tools.file_read import file_read
    return await file_read(**args)


async def _file_write_handler(args: dict, ctx: ToolContext) -> dict:
    from yak_browser_use.tools.file_write import file_write
    return await file_write(**args)


async def _format_convert_handler(args: dict, ctx: ToolContext) -> dict:
    from yak_browser_use.tools.format_convert import format_convert
    return await format_convert(**args)


async def _record_step_handler(args: dict, ctx: ToolContext) -> dict:
    from yak_browser_use.engine.executor import execute_tool
    return await execute_tool(
        tool_name="record_step",
        params=args,
        tools_dir=ctx.tools_dir or Path("."),
        cdp_helpers=ctx.cdp_helpers,
    )


async def _eval_agent_handler(args: dict, ctx: ToolContext) -> dict:
    from yak_browser_use.engine._harness.tool_executor import _handle_eval_agent
    return await _handle_eval_agent(
        fn_args=args,
        cdp_helpers=ctx.cdp_helpers,
        llm_call=ctx.llm_call,
        budget=ctx.budget,
        interrupt_check=ctx.interrupt_check,
        stream_callback=ctx.stream_callback,
        pipeline_name=ctx.pipeline_name,
        shared_store=ctx.shared_store,
    )
