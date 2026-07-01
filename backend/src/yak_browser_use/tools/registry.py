"""ToolRegistry — unified tool registration, schema query, and dispatch routing."""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any

from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)

# Truncation limits for chat-mode extract tools.
# shared_store always holds the full data; only the LLM-facing response is truncated.
LIST_TRUNC_LIMIT = 50
TABLE_TRUNC_LIMIT = 100


def _auto_csv(data: Any) -> str:
    """Convert a list of dicts to CSV text with auto-extracted headers."""
    if not isinstance(data, list):
        return str(data)
    if not data:
        return ""
    fields: set[str] = set()
    for item in data:
        if isinstance(item, dict):
            fields.update(item.keys())
    fields_sorted = sorted(fields)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(fields_sorted)
    for item in data:
        if isinstance(item, dict):
            row = []
            for f in fields_sorted:
                val = item.get(f, "")
                if isinstance(val, (dict, list)):
                    val = json.dumps(val, ensure_ascii=False)
                row.append(val)
            writer.writerow(row)
        else:
            writer.writerow([item])
    return buf.getvalue()


# ── Lazy-loaded dispatch maps (imported once, cached) ────────────────────────

_pipeline_dispatch: dict | None = None
_skill_dispatch: dict | None = None


def _get_pipeline_dispatch() -> dict:
    global _pipeline_dispatch
    if _pipeline_dispatch is None:
        from yak_browser_use.engine._harness.pipeline_tools import (
            pipeline_view,
            pipeline_update_step,
            pipeline_add_step,
            pipeline_remove_step,
            pipeline_create,
            pipeline_compile,
        )
        _pipeline_dispatch = {
            "pipeline_view": pipeline_view,
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
        "goto", "click", "fill", "snapshot", "scroll",
        "lookup_selector", "hover", "unhover", "focus", "select",
        "clear", "keyboard", "press_key", "type_text", "navigate", "wait",
        "tab", "copy", "paste",
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
                           "最多 200 元素，密集容器折叠后可用 expand_key 参数展开浏览。\n"
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
                        "description": "a11y/progressive 模式有效。仅按文本/tag/type/role 模糊匹配，不支持 CSS selector。",
                    },
                    "expand_key": {
                        "type": "string",
                        "description": "仅 progressive 模式有效。指定要展开的折叠容器 key（如 'c_0'），展开后合并到 snapshot 返回中。替代原 expand_branch 独立 op。",
                    },
                },
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
            "description": "Get the HTML source of the current page. Without selector: returns full page HTML. With selector: returns outerHTML of the matching element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cached": {"type": "boolean", "description": "If true, read HTML from bridge cache instead of CDP. Falls back to CDP if no cache."},
                    "selector": {"type": "string", "description": "Optional CSS selector. When provided, returns outerHTML of the first matching element instead of full page source."},
                },
            },
        },
        "lookup_selector": {
            "description": "查找页面上指定元素的 CSS selector。每次调用刷新页面缓存确保最新。",
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

    # ── browser_source (registered separately — writes to shared_store) ──

    async def _source_handler(args: dict, ctx: ToolContext) -> dict:
        if ctx.cdp_helpers is None:
            return {"ok": False, "error": "浏览器不可用 — 请确保 CDP 连接已建立"}
        bridge = ctx.cdp_helpers.bridge if hasattr(ctx.cdp_helpers, "bridge") else ctx.cdp_helpers

        output_to = args.get("output_to")
        if not output_to or not isinstance(output_to, str):
            return {
                "ok": False,
                "error": "browser_source requires a non-empty 'output_to' parameter — specify a shared_store key name (e.g. output_to=\"page_html\")",
            }

        result = await execute_browser_op("source", args, bridge)
        if not result.get("ok"):
            return result

        html = result.pop("html", "")
        if html and ctx.shared_store is not None:
            ctx.shared_store[output_to] = html

        size = len(html)
        note = (
            f"HTML 已写入 shared_store['{output_to}'] ({size:,} 字节)。"
            f" 使用 data_browse(key=\"{output_to}\") 分页浏览内容，"
            f" 或使用 browser_eval_js(code=...) 进行精准提取。"
        )
        if size > 100_000:
            note += (
                f" ⚠️ HTML 较大，建议优先使用 browser_snapshot 获取页面结构，"
                f" 或使用 browser_eval_js 精准提取所需数据。"
            )

        return {
            "ok": True,
            "result": {
                "output_to": output_to,
                "size": size,
                "note": note,
            },
        }

    registry.register("browser_source", {
        "description": (
            "⚠️ HEAVY TOOL — 获取当前页面的完整 HTML 源代码。\n"
            "【必须】提供 output_to 参数指定 shared_store 键名，HTML 将写入 shared_store 而非返回给 LLM。\n"
            "返回结果仅含元信息（size/output_to/note），不含 HTML 原文。\n"
            "使用 data_browse(key=output_to) 分页浏览存储的 HTML 内容。\n"
            "【推荐替代】优先使用 browser_snapshot 获取页面结构（更轻量），"
            "或使用 browser_eval_js 进行精准数据提取。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "output_to": {
                    "type": "string",
                    "description": "【必须】shared_store 键名，HTML 将写入 shared_store[output_to]，后续可通过 data_browse(key=...) 读取。",
                },
                "cached": {"type": "boolean", "description": "If true, read HTML from bridge cache instead of CDP. Falls back to CDP if no cache."},
                "selector": {"type": "string", "description": "Optional CSS selector. When provided, returns outerHTML of the first matching element instead of full page source."},
                "strip_styles": {"type": "boolean", "description": "Strip <style> and <script> tags from HTML (default: true)."},
                "only_body": {"type": "boolean", "description": "Return only <body> content (default: false)."},
            },
            "required": ["output_to"],
        },
    }, _source_handler)

    # ── browser_eval_js (formerly eval_js) ──────────────────────────

    async def _eval_js_handler(args: dict, ctx: ToolContext) -> dict:
        if ctx.cdp_helpers is None:
            return {"ok": False, "error": "浏览器不可用 — 请确保 CDP 连接已建立"}
        bridge = ctx.cdp_helpers.bridge if hasattr(ctx.cdp_helpers, "bridge") else ctx.cdp_helpers
        code = args.get("code", "")
        try:
            result = await bridge.evaluate(code)
            output_to = args.get("output_to")
            if output_to and ctx.shared_store is not None:
                ctx.shared_store[output_to] = result
            return_format = args.get("return_format", "raw")
            if return_format == "json":
                return {"ok": True, "result": json.dumps(result, ensure_ascii=False)}
            elif return_format == "csv":
                if isinstance(result, list):
                    return {"ok": True, "result": _auto_csv(result)}
                return {"ok": True, "result": f"return_format=csv requires array result, got {type(result).__name__}"}
            return {"ok": True, "result": result}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    registry.register("browser_eval_js", {
        "description": "[需 CDP] 在浏览器当前页面执行任意 JavaScript 代码并返回结果。支持 output_to 将结果存入 shared_store，支持 return_format 控制返回格式。",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "要执行的 JavaScript 代码。"},
                "output_to": {"type": "string", "description": "可选，将执行结果存入 shared_store 的变量名，后续工具可通过 {key} 引用。"},
                "return_format": {"type": "string", "enum": ["raw", "json", "csv"], "description": "返回格式：raw（默认，原样返回）、json（JSON 序列化）、csv（数组转为 CSV 文本）。"},
            },
            "required": ["code"],
        },
    }, _eval_js_handler)

    # ── pipeline_* tools ─────────────────────────────────────────────

    _PIPELINE_SCHEMAS = {
        "pipeline_view": {
            "description": "View pipeline(s). Without `name`: list all available presets (name, description, step count). With `name`: load a pipeline preset and return step details including full browser_ops list.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Optional pipeline name. Omit to list all presets."}},
            },
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
                    "goal_description": {"type": "string", "description": "High-level goal description for this step. Mutually exclusive with browser_ops and tool_name."},
                    "depends_on": {"type": "array", "description": "List of step names this step depends on.", "items": {"type": "string"}},
                    "check": {"type": "object", "description": "Programmatic check conditions for this step. Use {} to skip verification. Supported keys: url_contains, element_exists, text_contains, element_visible."},
                    "after": {"type": "string", "description": "Name of the step to insert after. Omit to append."},
                    "heading": {"type": "boolean", "description": "Set to true to create an outline placeholder step without browser_ops, tool_name, or goal_description."},
                    "explanation": {"type": "string", "description": "Human-readable explanation of what was changed and why."},
                },
                "required": ["pipeline_name", "step_name", "description", "check"],
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
                    "steps": {"type": "array", "description": "List of step objects. Each step must have: name (string), description (string), check (dict, use {} to skip). Optional: browser_ops (list of dicts), tool_name (string), goal_description (string), depends_on (list of strings).", "items": {"type": "object"}},
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
        "description": "将文本内容写入文件，自动创建父目录。content 支持 {key} 模板替换：{content} 中的 {varname} 会被替换为 shared_store 中对应变量的 JSON 序列化值。",
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
        "description": "转换文件格式（xlsx/csv/json 互转）。根据文件扩展名自动识别源/目标格式，也可显式指定。提供 source_json 可从内存数据直接转换。支持 output_to 将转换后文件的绝对路径存入 shared_store。",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "源文件路径（与 source_json 二选一，source_json 优先）"},
                "target": {"type": "string", "description": "目标文件路径"},
                "source_fmt": {"type": "string", "description": "源格式（xlsx/csv/json），为空时从扩展名推断"},
                "target_fmt": {"type": "string", "description": "目标格式（xlsx/csv/json），为空时从扩展名推断"},
                "source_json": {"type": "array", "description": "JSON 数组（直接从内存数据转换，优先于 source）", "items": {"type": "object"}},
                "output_to": {"type": "string", "description": "可选，转换成功后目标文件的绝对路径存入 shared_store 的变量名。"},
            },
            "required": ["target"],
        },
    }, _format_convert_handler)

    # ── read_data ─────────────────────────────────────────────────────

    registry.register("read_data", {
        "description": "读取文件内容，支持渐进式披露（limit/offset 控制行数）。唯一可返回文件全文的工具。二进制文件可通过 convert_to 参数自动转换格式后再读取。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "limit": {"type": "integer", "description": "最大返回行数（默认 20，必须大于 0）"},
                "offset": {"type": "integer", "description": "起始行号（0-based，默认 0）"},
                "encoding": {"type": "string", "description": "文件编码，为空时自动检测"},
                "convert_to": {"type": "string", "description": "目标格式（csv/json），二进制文件先转换再读取"},
            },
            "required": ["path"],
        },
    }, _read_data_handler)

    # ── browser_wait_for_download (formerly wait_for_download) ───────

    registry.register("browser_wait_for_download", {
        "description": "[需 CDP] 等待浏览器下载的文件就绪。文件内容自动存入 shared_store，返回 key 和 size。后续用 data_browse(key=...) 分页浏览。",
        "parameters": {
            "type": "object",
            "properties": {
                "timeout": {"type": "integer", "description": "最长等待秒数（默认 60）"},
            },
        },
    }, _wait_for_download_handler)

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

    # ── eval_agent (removed — main agent uses browser_eval_js + browser_snapshot) ─

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
                    "description": "验证码图片的 base64 编码数据（支持纯 base64 或 data:image/...;base64, 前缀格式）"
                },
                "image_path": {
                    "type": "string",
                    "description": "验证码图片的文件路径（preset 模式下替代 image_bytes）"
                },
                "background_bytes": {
                    "type": "string",
                    "description": "仅 slide 模式需要：滑块背景图的 base64 编码数据（支持纯 base64 或 data:image/...;base64, 前缀格式）"
                }
            },
            "required": ["type"]
        },
    }, _captcha_handler)

    # ── data_keys / data_browse ───────────────────────────────────────

    registry.register("data_keys", {
        "description": "列出 shared_store 中所有 key，返回每个 key 的名称、类型（list/dict/str/other）和大小（元素数或字符数）。",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    }, _data_keys_handler)

    registry.register("data_browse", {
        "description": "分页浏览 shared_store 中指定 key 的值。元素列表使用 _build_snapshot_summary 格式逐行输出，字符串截断显示，字典输出 key 列表加截断的 repr。",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "要浏览的 key 名称。"},
                "limit": {"type": "integer", "description": "每页返回数量（元素个数或字符数），默认 20，最大 100。"},
                "offset": {"type": "integer", "description": "起始偏移量，默认 0。"},
            },
            "required": ["key"],
        },
    }, _data_browse_handler)

    # ── browser_extract_* tools (chat-mode data extraction) ──────────────

    from yak_browser_use.tools.extract import (
        EXTRACT_LIST_JS,
        EXTRACT_TABLE_JS,
        EXTRACT_DETAILS_JS,
    )
    from yak_browser_use.tools.extract_fields import (
        _safe_selector,
        _build_selector_js,
        _build_field_extraction_js,
        _build_table_selector_js,
        _build_details_selector_js,
    )

    async def _browser_extract_list_handler(args: dict, ctx: ToolContext) -> dict:
        if ctx.cdp_helpers is None:
            return {"ok": False, "error": "浏览器不可用 — 请确保 CDP 连接已建立"}
        bridge = ctx.cdp_helpers.bridge if hasattr(ctx.cdp_helpers, "bridge") else ctx.cdp_helpers
        selector = args.get("selector", "")
        fields = args.get("fields", None)
        output_to = args.get("output_to", None)

        if fields is not None and not isinstance(fields, dict):
            return {"ok": False, "error": "fields 参数必须是 object 类型（如 {\"title\": \"h3\"}）"}

        if fields and not selector:
            return {"ok": False, "error": "fields 参数需要同时提供 selector"}

        if fields:
            js = _build_field_extraction_js(selector, fields)
        elif selector:
            js = _build_selector_js(selector)
        else:
            js = EXTRACT_LIST_JS

        try:
            items = await bridge.evaluate(js)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        if not isinstance(items, list):
            items = []

        full_data = items
        truncated = len(items) > LIST_TRUNC_LIMIT
        if truncated:
            items = items[:LIST_TRUNC_LIMIT]

        result: dict = {"ok": True, "items": items, "count": len(items)}
        if truncated:
            result["_truncated"] = True
            result["total"] = len(full_data)

        if output_to and ctx.shared_store is not None:
            ctx.shared_store[output_to] = full_data
            result["_output_to"] = output_to

        return result

    registry.register("browser_extract_list", {
        "description": "[需 CDP] 从当前页面提取列表数据。支持自定义 CSS selector 和字段映射（fields）。结果可选存入 shared_store。",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "可选，CSS selector 定位列表容器。省略时自动检测常见列表结构（li、role=listitem 等）。"},
                "output_to": {"type": "string", "description": "可选，将完整提取结果存入 shared_store 的变量名。"},
                "fields": {
                    "type": "object",
                    "description": "可选，字段映射字典。key 为输出字段名，value 为 CSS selector（如 'h3'）或 '@attr' 获取属性。需要同时提供 selector。",
                    "additionalProperties": {"type": "string"},
                },
            },
        },
    }, _browser_extract_list_handler)

    async def _browser_extract_table_handler(args: dict, ctx: ToolContext) -> dict:
        if ctx.cdp_helpers is None:
            return {"ok": False, "error": "浏览器不可用 — 请确保 CDP 连接已建立"}
        bridge = ctx.cdp_helpers.bridge if hasattr(ctx.cdp_helpers, "bridge") else ctx.cdp_helpers
        selector = args.get("selector", "")
        output_to = args.get("output_to", None)

        if selector:
            js = _build_table_selector_js(selector)
        else:
            js = EXTRACT_TABLE_JS

        try:
            result = await bridge.evaluate(js)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        if not isinstance(result, dict):
            result = {"headers": [], "rows": []}

        full_rows = result.get("rows", [])
        truncated = len(full_rows) > TABLE_TRUNC_LIMIT
        display_rows = full_rows[:TABLE_TRUNC_LIMIT] if truncated else full_rows

        ret: dict = {"ok": True, "headers": result.get("headers", []), "rows": display_rows}
        if truncated:
            ret["_truncated"] = True
            ret["total_rows"] = len(full_rows)

        if output_to and ctx.shared_store is not None:
            ctx.shared_store[output_to] = {"headers": result.get("headers", []), "rows": full_rows}
            ret["_output_to"] = output_to

        return ret

    registry.register("browser_extract_table", {
        "description": "[需 CDP] 从当前页面提取表格数据（headers + rows）。支持自定义 CSS selector。结果可选存入 shared_store。",
        "parameters": {
            "type": "object",
            "properties": {
                "output_to": {"type": "string", "description": "可选，将完整提取结果存入 shared_store 的变量名。"},
                "selector": {"type": "string", "description": "可选，CSS selector 定位表格容器。省略时自动检测常见表格结构。"},
            },
        },
    }, _browser_extract_table_handler)

    async def _browser_extract_details_handler(args: dict, ctx: ToolContext) -> dict:
        if ctx.cdp_helpers is None:
            return {"ok": False, "error": "浏览器不可用 — 请确保 CDP 连接已建立"}
        bridge = ctx.cdp_helpers.bridge if hasattr(ctx.cdp_helpers, "bridge") else ctx.cdp_helpers
        selector = args.get("selector", "")
        output_to = args.get("output_to", None)

        if selector:
            js = _build_details_selector_js(selector)
        else:
            js = EXTRACT_DETAILS_JS

        try:
            result = await bridge.evaluate(js)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        if not isinstance(result, dict):
            result = {"text": "", "details": []}

        ret: dict = {"ok": True, "text": result.get("text", ""), "details": result.get("details", [])}

        if output_to and ctx.shared_store is not None:
            ctx.shared_store[output_to] = result
            ret["_output_to"] = output_to

        return ret

    registry.register("browser_extract_details", {
        "description": "[需 CDP] 从当前页面提取结构化详情（key-value 对）。支持自定义 CSS selector 限定容器。结果可选存入 shared_store。",
        "parameters": {
            "type": "object",
            "properties": {
                "output_to": {"type": "string", "description": "可选，将完整提取结果存入 shared_store 的变量名。"},
                "selector": {"type": "string", "description": "可选，CSS selector 定位详情容器。省略时自动检测常见详情结构。"},
            },
        },
    }, _browser_extract_details_handler)

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


async def _todo_handler(args: dict, ctx: ToolContext) -> dict:
    from yak_browser_use.tools.todo_store import current_store
    from yak_browser_use.tools.todo import todo

    store = current_store.get()
    todos = args.get("todos")
    merge = args.get("merge", False)
    result_str = await todo(todos=todos, merge=merge, store=store)
    return {"ok": True, "result": result_str}


async def _file_read_handler(args: dict, ctx: ToolContext) -> dict:
    from yak_browser_use.tools._path_utils import validate_path
    from yak_browser_use.tools.file_read import _BINARY_EXTENSIONS
    path = args.get("path", "")
    if not path:
        return {"ok": False, "error": "path is required"}
    try:
        p = validate_path(path, pipeline=ctx.pipeline_name or None)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    if not p.exists():
        return {"ok": False, "error": f"文件不存在 — {path}"}
    if not p.is_file():
        return {"ok": False, "error": f"路径不是文件 — {path}"}
    encoding = args.get("encoding", "")
    is_binary = p.suffix.lower() in _BINARY_EXTENSIONS
    return {"ok": True, "path": path, "size": p.stat().st_size, "encoding": encoding or "auto", "binary": is_binary}


async def _file_write_handler(args: dict, ctx: ToolContext) -> dict:
    from yak_browser_use.tools._path_utils import validate_path
    from yak_browser_use.workspace.manager import WORKSPACES_ROOT
    path = args.get("path", "")
    content = args.get("content", "")
    if not path:
        return {"ok": False, "error": "path is required"}
    try:
        p = validate_path(path, pipeline=ctx.pipeline_name or None)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    if ctx.pipeline_name:
        pipeline_root = (WORKSPACES_ROOT / ctx.pipeline_name).resolve()
        if p.parent == pipeline_root or p == pipeline_root:
            return {"ok": False, "error": f"不允许写入 workspace 根目录: {path}，请使用子目录（如 downloads/）"}
    _VAR_PATTERN = re.compile(r'\{(\w+)\}')
    warnings: list[str] = []
    store = ctx.shared_store
    if store is not None:

        def _replace_var(m: re.Match) -> str:
            key = m.group(1)
            if key in store:
                return json.dumps(store[key], ensure_ascii=False)
            warnings.append(f"变量 {key} 未找到")
            return m.group(0)

        content = _VAR_PATTERN.sub(_replace_var, content)
    from yak_browser_use.tools.file_write import file_write
    result = await file_write(path=path, content=content, encoding=args.get("encoding", "utf-8"), pipeline=ctx.pipeline_name or None)
    if result.get("ok"):
        ret = {"ok": True, "path": path, "size": len(content)}
        if warnings:
            ret["_warnings"] = warnings
        return ret
    return result


async def _format_convert_handler(args: dict, ctx: ToolContext) -> dict:
    source = args.get("source", "")
    target = args.get("target", "")
    source_fmt = args.get("source_fmt", "")
    target_fmt = args.get("target_fmt", "")
    source_json = args.get("source_json", None)
    output_to = args.get("output_to", None)
    if not source and source_json is None:
        return {"ok": False, "error": "source or source_json is required"}
    if not target:
        return {"ok": False, "error": "target is required"}
    from yak_browser_use.tools.format_convert import format_convert
    result = await format_convert(
        source=source,
        target=target,
        source_fmt=source_fmt,
        target_fmt=target_fmt,
        source_json=source_json,
        pipeline=ctx.pipeline_name or None,
    )
    if result.get("ok") and output_to and ctx.shared_store is not None:
        from yak_browser_use.tools._path_utils import validate_path
        try:
            abs_path = str(validate_path(target, pipeline=ctx.pipeline_name or None))
            ctx.shared_store[output_to] = abs_path
            result["_output_to"] = output_to
        except ValueError as e:
            result["_output_to_warning"] = f"路径解析失败，未存入 shared_store: {e}"
    return result


async def _read_data_handler(args: dict, ctx: ToolContext) -> dict:
    from yak_browser_use.tools._path_utils import validate_path
    from yak_browser_use.workspace.manager import WORKSPACES_ROOT
    from yak_browser_use.tools.read_data import read_data

    path = args.get("path", "")
    if ctx.pipeline_name and path:
        try:
            p = validate_path(path, pipeline=ctx.pipeline_name)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        pipeline_root = (WORKSPACES_ROOT / ctx.pipeline_name).resolve()
        if p.parent == pipeline_root or p == pipeline_root:
            return {"ok": False, "error": f"不允许读取 workspace 根目录: {path}，文件应在子目录中"}

    return await read_data(pipeline=ctx.pipeline_name or None, **args)


async def _wait_for_download_handler(args: dict, ctx: ToolContext) -> dict:
    if ctx.cdp_helpers is None:
        return {"ok": False, "error": "浏览器不可用 — 请确保 CDP 连接已建立"}
    bridge = ctx.cdp_helpers.bridge if hasattr(ctx.cdp_helpers, "bridge") else ctx.cdp_helpers
    timeout = args.get("timeout", 60)
    result = await bridge.wait_for_download(timeout=timeout)
    if not result.get("ok"):
        return result

    full_path = result["path"]
    try:
        content = Path(full_path).read_text(encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": f"读取下载文件失败: {e}"}

    rel_key = f"downloads/{Path(full_path).name}"
    ss = ctx.shared_store
    if ss is not None:
        ss[rel_key] = content

    return {"ok": True, "key": rel_key, "size": len(content)}


async def _data_keys_handler(args: dict, ctx: ToolContext) -> dict:
    ss = ctx.shared_store
    if ss is None:
        return {"ok": False, "error": "shared_store 不可用"}
    keys = []
    for name, value in ss.items():
        if isinstance(value, list):
            typ = "list"
            size = len(value)
        elif isinstance(value, dict):
            typ = "dict"
            size = len(value)
        elif isinstance(value, str):
            typ = "str"
            size = len(value)
        else:
            typ = "other"
            size = 0
        keys.append({"name": name, "type": typ, "size": size})
    return {"ok": True, "keys": keys}


async def _data_browse_handler(args: dict, ctx: ToolContext) -> dict:
    ss = ctx.shared_store
    if ss is None:
        return {"ok": False, "error": "shared_store 不可用"}
    key = args.get("key", "")
    if key not in ss:
        return {"ok": False, "error": f"key '{key}' 不存在"}
    value = ss[key]
    limit = max(min(args.get("limit", 20), 100), 1)
    offset = max(args.get("offset", 0), 0)

    if isinstance(value, list):
        total = len(value)
        page = value[offset:offset + limit]
        if page and all(isinstance(el, dict) and ("ref" in el or "tag" in el) for el in page):
            from yak_browser_use.utils.helpers import build_snapshot_summary
            items = []
            for el in page:
                line = build_snapshot_summary([el], "", "")
                if "\n" in line:
                    line = line.rsplit("\n", 1)[-1]
                items.append(line)
            return {"ok": True, "key": key, "offset": offset, "limit": limit, "total": total, "items": items}
        items = [repr(x) for x in page]
        return {"ok": True, "key": key, "offset": offset, "limit": limit, "total": total, "items": items}
    elif isinstance(value, str):
        total = len(value)
        preview = value[offset:offset + limit]
        return {"ok": True, "key": key, "offset": offset, "limit": limit, "total": total, "preview": preview}
    elif isinstance(value, dict):
        ks = list(value.keys())
        preview = repr(value)[:limit] if limit else repr(value)
        return {"ok": True, "key": key, "keys": ks, "preview": preview}
    return {"ok": True, "key": key, "offset": offset, "limit": limit, "value": repr(value)[:limit]}



