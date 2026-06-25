"""Executor — three step executors for browser, tool, and goal step types.

Each executor has two layers:
- **Core functions** (execute_browser_op / execute_tool / execute_goal):
  No file I/O, suitable for chat mode tool_executor.
- **Pipeline wrappers** (execute_browser_step / execute_tool_step / execute_goal_step):
  Call core functions + write artifacts (step.json, screenshots, output files).

Result dict format: {ok, result, error, duration_ms, ...}
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from functools import partial
from pathlib import Path
from typing import Any

from yak_browser_use.utils.helpers import prepend_resolve_errors
from yak_browser_use.utils.logging import get_logger

from yak_browser_use.cdp.protocols import BrowserBridge
from yak_browser_use.cdp.playwright_bridge import A11yNotAvailable
from yak_browser_use.engine._lifecycle.compensation import CompensationRegistry

logger = get_logger(__name__)

ERROR_CODES: dict[str, str] = {
    "SYNTAX_ERROR": "Tool code compile/syntax failure",
    "RUNTIME_ERROR": "Tool execution runtime exception",
    "TIMEOUT_ERROR": "Tool execution timeout",
    "OUTPUT_ERROR": "Output file missing or empty",
    "INPUT_ERROR": "Input file not found or unreadable",
    "BROWSER_ERROR": "Browser operation failed",
    "BROWSER_UNAVAILABLE": "Browser not available",
    "CHECK_FAILED": "Step check validation failed",
    "GUARDIAN_ERROR": "Guardian validation failed",
    "PATH_ERROR": "Path security check failed",
    "LLM_ERROR": "LLM tool code generation failed",
}

SENSITIVE_KEYS: frozenset = frozenset({
    "text", "value", "credential", "password", "secret", "token", "key", "api_key",
})

_SENSITIVE_PATTERN = re.compile(
    r"(?<![a-zA-Z0-9_])("
    r"[a-zA-Z_][a-zA-Z0-9_]*"
    r")(\s*[:=]\s*)"
    r"([^\s,\'\"\]}\)]+)",
)

_CREDENTIAL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(sk-[a-zA-Z0-9_\-]{20,})"), "sk-***"),
    (re.compile(r"(Bearer\s+)[a-zA-Z0-9_\-\.]{8,}"), r"\1***"),
    (re.compile(r"(-----BEGIN\s.*?KEY-----)"), "***KEY BLOCK***"),
]

DEFAULT_OP_TIMEOUT = 30


# ── Masking / sanitizing ──


def mask_sensitive_patterns(text: str) -> str:
    """Mask sensitive key=value patterns and credential strings in text."""
    def _replacer(m: re.Match) -> str:
        key = m.group(1).lower()
        sep = m.group(2)
        value = m.group(3)
        if key in SENSITIVE_KEYS and len(value) > 2:
            return f"{m.group(1)}{sep}***"
        return m.group(0)

    result = _SENSITIVE_PATTERN.sub(_replacer, text)
    for pattern, replacement in _CREDENTIAL_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def sanitize_result(data, sensitive_keys: frozenset = SENSITIVE_KEYS):
    """Recursively sanitize sensitive values in a nested data structure."""
    from yak_browser_use.params.manager import ParamRef

    if isinstance(data, ParamRef):
        return str(data)
    if isinstance(data, dict):
        return {
            k: "***" if (isinstance(k, str) and k.lower() in sensitive_keys)
            else sanitize_result(v, sensitive_keys)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [sanitize_result(item, sensitive_keys) for item in data]
    if isinstance(data, str):
        return mask_sensitive_patterns(data)
    return data


# ──────────────────────────────────────────────────────────────
#  Core execution functions (no file I/O — for chat mode)
# ──────────────────────────────────────────────────────────────


async def execute_browser_op(
    op_type: str,
    params: dict,
    bridge: BrowserBridge,
    element_map: dict | None = None,
) -> dict:
    """Execute a single browser operation (goto/click/fill/snapshot/scroll/source/eval + new ops).

    Returns: {ok, result, error, duration_ms, screenshot_base64?, html?}
    Does NOT write files — suitable for chat mode tool_executor.
    """
    import base64

    start = time.time()
    result: dict = {
        "ok": True,
        "result": None,
        "error": None,
        "duration_ms": 0,
    }

    try:
        async with asyncio.timeout(DEFAULT_OP_TIMEOUT):
            if op_type == "goto":
                url = params.get("url", "")
                await bridge.goto(url)
                if hasattr(bridge, "reset_ref_map"):
                    await bridge.reset_ref_map()
                else:
                    logger.debug("bridge has no reset_ref_map, skipping ref map reset")
                result["result"] = {"url": url}

            elif op_type == "click":
                selector = params.get("selector", "")
                click_count = params.get("clickCount", 1)
                if not selector:
                    raise ValueError("click op missing selector")
                selector = await _resolve_element_ref(selector, element_map, bridge)
                await bridge.click(selector, click_count)
                result["result"] = {"selector": selector}

            elif op_type == "fill":
                selector = params.get("selector", "")
                text = params.get("text", params.get("value", ""))
                if isinstance(text, dict) and "param_key" in text:
                    from yak_browser_use.params.manager import resolve_param
                    text = resolve_param(text["param_key"])
                selector = await _resolve_element_ref(selector, element_map, bridge)
                await bridge.fill(selector, text)  # type: ignore[arg-type]
                result["result"] = {"selector": selector}

            elif op_type == "snapshot":
                mode = params.get("mode", "aria")
                query = params.get("query", "")
                in_viewport = params.get("in_viewport", False)
                if mode == "a11y" or mode == "interactive":
                    try:
                        snapshot = await bridge.a11y_snapshot()
                    except A11yNotAvailable:
                        logger.warning(
                            "a11y snapshot not available in this browser environment, "
                            "falling back to progressive mode"
                        )
                        snapshot = await bridge._progressive_snapshot(query=query)
                        snapshot["degraded"] = True
                        snapshot["_fallback_reason"] = "accessibility_tree_unavailable"
                    result["result"] = snapshot
                elif mode == "aria" or mode == "simplified":
                    snapshot = await bridge.aria_snapshot()
                    result["result"] = snapshot
                elif mode == "progressive":
                    snapshot = await bridge._progressive_snapshot(query=query)
                    expand_key = params.get("expand_key", "")
                    if expand_key and hasattr(bridge, "expand_branch"):
                        expanded = await bridge.expand_branch(key=expand_key)
                        if isinstance(expanded, dict) and "elements" in expanded:
                            snapshot["_expanded"] = expanded
                    result["result"] = snapshot
                else:
                    snapshot = await bridge.capture_snapshot()
                    result["result"] = {}
                    png_data = snapshot.get("screenshot_base64", "")
                    if png_data:
                        result["screenshot_base64"] = png_data
                        result["result"]["has_screenshot"] = True
                    html_data = snapshot.get("html", "")
                    if html_data:
                        result["html"] = html_data
                        result["result"]["has_html"] = True
                    result["result"]["url"] = snapshot.get("url", "")
                    result["result"]["title"] = snapshot.get("title", "")

            elif op_type == "scroll":
                direction = params.get("direction", "down")
                amount = params.get("amount", 300)
                js_code = _build_scroll_js(direction, amount)
                await bridge.evaluate(js_code)
                result["result"] = {"direction": direction, "amount": amount}

            elif op_type == "source":
                cached = params.get("cached", False)
                if hasattr(bridge, "get_page_html"):
                    html = await bridge.get_page_html(cached=cached)
                else:
                    html = await bridge.source()
                result["html"] = html
                result["result"] = {"length": len(html)}

            elif op_type == "lookup_selector":
                ref = params.get("ref", "")
                if not ref:
                    raise ValueError("lookup_selector missing ref")
                if hasattr(bridge, "ensure_highlights"):
                    await bridge.ensure_highlights()
                if hasattr(bridge, "get_element_by_index"):
                    el_info = bridge.get_element_by_index(ref)
                    result["result"] = el_info
                else:
                    result["result"] = {"ref": ref, "error": "bridge does not support element lookup"}

            # ── New ops ──

            elif op_type == "hover":
                selector = params.get("selector", "")
                selector = await _resolve_element_ref(selector, element_map, bridge)
                await bridge.hover(selector)
                result["result"] = {"selector": selector}

            elif op_type == "unhover":
                selector = params.get("selector", "")
                selector = await _resolve_element_ref(selector, element_map, bridge)
                await bridge.unhover(selector)
                result["result"] = {"selector": selector}

            elif op_type == "focus":
                selector = params.get("selector", "")
                selector = await _resolve_element_ref(selector, element_map, bridge)
                await bridge.focus(selector)
                result["result"] = {"selector": selector}

            elif op_type == "select":
                selector = params.get("selector", "")
                selector = await _resolve_element_ref(selector, element_map, bridge)
                value = params.get("value", "")
                mode = params.get("mode", "value")
                await bridge.select(selector, value, mode)
                result["result"] = {"selector": selector}

            elif op_type == "clear":
                selector = params.get("selector", "")
                selector = await _resolve_element_ref(selector, element_map, bridge)
                mode = params.get("mode", "js")
                await bridge.clear(selector, mode)
                result["result"] = {"selector": selector}

            elif op_type == "keyboard":
                mode = params.get("mode", "key")
                if mode == "key":
                    key = params.get("key", "")
                    await bridge.keyboard_press(key)
                elif mode == "text":
                    text = params.get("text", "")
                    if isinstance(text, dict) and "param_key" in text:
                        from yak_browser_use.params.manager import resolve_param
                        text = resolve_param(text["param_key"])
                    await bridge.keyboard_type(text)  # type: ignore[arg-type]
                result["result"] = {"mode": mode}

            elif op_type == "press_key":
                key = params.get("key", "")
                await bridge.keyboard_press(key)
                result["result"] = {"key": key}

            elif op_type == "type_text":
                text = params.get("text", "")
                is_param = isinstance(text, dict) and "param_key" in text
                if is_param:
                    from yak_browser_use.params.manager import resolve_param
                    text = resolve_param(text["param_key"])
                await bridge.keyboard_type(text)  # type: ignore[arg-type]
                result["result"] = {"text": "***" if is_param else text}

            elif op_type == "navigate":
                action = params.get("action", "back")
                await bridge.navigate(action)
                result["result"] = {"action": action}

            elif op_type == "wait":
                mode = params.get("mode", "time")
                await bridge.wait(**params)
                result["result"] = {"mode": mode}

            elif op_type == "tab":
                action = params.get("action", "list")
                if action == "new":
                    url = params.get("url", "about:blank")
                    r = await bridge.tab_new(url)
                elif action == "switch":
                    tid = params.get("target_id", "")
                    r = await bridge.tab_switch(tid)
                elif action == "close":
                    tid = params.get("target_id", "")
                    r = await bridge.tab_close(tid)
                elif action == "list":
                    r = await bridge.tab_list()
                else:
                    r = {"error": f"Unknown tab action: {action}"}
                result["result"] = r

            elif op_type == "copy":
                selector = params.get("selector", "")
                r = await bridge.copy_to_clipboard(selector)
                result["result"] = r

            elif op_type == "paste":
                selector = params.get("selector", "")
                index = params.get("index", -1)
                r = await bridge.paste_from_clipboard(selector, index)
                result["result"] = r

            else:
                raise ValueError(f"Unknown browser op type: {op_type}")

    except TimeoutError:
        result["ok"] = False
        result["error"] = f"Operation timeout ({DEFAULT_OP_TIMEOUT}s)"
    except Exception as e:
        result["ok"] = False
        result["error"] = str(e)

    result["duration_ms"] = int((time.time() - start) * 1000)
    return result


def _build_scroll_js(direction: str, amount: int) -> str:
    """Build JS code for page scrolling."""
    if direction == "down":
        return f"window.scrollBy(0, {amount});"
    elif direction == "up":
        return f"window.scrollBy(0, -{amount});"
    else:
        return f"window.scrollBy(0, {amount});"


def _write_full_artifacts(core_result: dict, step_dir: Path, _base64, _time) -> None:
    """Write screenshot and HTML artifacts from a full snapshot result."""
    png_data = core_result.get("screenshot_base64", "")
    if png_data:
        ts = int(_time.time())
        png_path = step_dir / f"screenshot_{ts}.png"
        png_path.write_bytes(_base64.b64decode(png_data))
    html_data = core_result.get("html", "")
    if html_data:
        html_path = step_dir / "page.html"
        html_path.write_text(html_data, encoding="utf-8")


async def _resolve_element_ref(selector: str, element_map: dict | None, bridge: BrowserBridge | None = None) -> str:
    """Resolve @-prefixed element references (e.g. @a_0, @p_12345, @e_42) to CSS selectors.

    In chat mode (element_map is None), falls back to bridge.get_element_by_index().
    """
    if selector.startswith("@"):
        if element_map:
            resolved = element_map.get(selector)
            if resolved is None:
                raise ValueError(f"Unknown element reference: {selector}")
            return resolved
        if bridge is not None and hasattr(bridge, "get_element_by_index"):
            el_info = bridge.get_element_by_index(selector)
            if "error" in el_info:
                raise ValueError(f"Element reference {selector}: {el_info['error']}")
            return el_info.get("selector", selector)
    return selector


async def execute_tool(
    tool_name: str,
    params: dict,
    tools_dir: Path,
    cdp_helpers: object | None = None,
) -> dict:
    """Execute a tool by importing and calling its function.

    No file I/O — returns result dict directly. Suitable for chat mode.

    Returns: {ok, result, error, duration_ms, output_files?}
    """
    import importlib.util
    import sys

    start = time.time()
    result: dict = {
        "ok": True,
        "result": None,
        "error": None,
        "duration_ms": 0,
    }

    if not tool_name:
        result["ok"] = False
        result["error"] = "tool_name is required"
        result["duration_ms"] = int((time.time() - start) * 1000)
        return result

    tool_path = tools_dir / f"{tool_name}.py"
    if not tool_path.exists():
        result["ok"] = False
        result["error"] = f"Tool file not found: {tool_path}"
        result["duration_ms"] = int((time.time() - start) * 1000)
        return result

    try:
        module_name = f"tools_{tool_name}"
        if module_name in sys.modules:
            del sys.modules[module_name]
        spec = importlib.util.spec_from_file_location(module_name, str(tool_path))
        if spec is None or spec.loader is None:
            result["ok"] = False
            result["error"] = f"Cannot load module: {tool_path}"
            result["duration_ms"] = int((time.time() - start) * 1000)
            return result
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception as e:
        result["ok"] = False
        result["error"] = str(e)
        result["duration_ms"] = int((time.time() - start) * 1000)
        return result

    tool_func = getattr(module, tool_name, None)
    if not tool_func:
        result["ok"] = False
        result["error"] = f"Function '{tool_name}' not found in {tool_path}"
        result["duration_ms"] = int((time.time() - start) * 1000)
        return result

    capabilities = getattr(module, "CAPABILITIES", [])

    if capabilities and "browser" in capabilities and cdp_helpers is None:
        result["ok"] = False
        result["error"] = f"Tool '{tool_name}' requires browser"
        result["duration_ms"] = int((time.time() - start) * 1000)
        return result

    try:
        from yak_browser_use.engine.ops import build_tool_kwargs

        kwargs = build_tool_kwargs(tool_func, cdp_helpers=cdp_helpers)
        kwargs["input_files"] = params.get("input_files", {})
        kwargs["output_dir"] = params.get("output_dir", "")
        kwargs.update({k: v for k, v in params.items()
                       if k not in ("input_files", "output_dir")})

        if asyncio.iscoroutinefunction(tool_func):
            ret = await tool_func(**kwargs)
        else:
            loop = asyncio.get_running_loop()
            ret = await loop.run_in_executor(None, partial(tool_func, **kwargs))
        result["result"] = ret
    except Exception as e:
        result["ok"] = False
        result["error"] = str(e)

    result["duration_ms"] = int((time.time() - start) * 1000)
    return result


# ──────────────────────────────────────────────────────────────
#  Programmatic check (step verification)
# ──────────────────────────────────────────────────────────────


async def run_check(check_def: dict | None, bridge: BrowserBridge) -> dict:
    """Run programmatic checks against the current page state.

    Supports four check conditions:
    - url_contains: current URL contains the given string
    - element_exists: CSS selector exists in the DOM
    - text_contains: page body text contains the given string
    - element_visible: CSS selector is visible (not display:none/visibility:hidden)

    All conditions must pass for the check to succeed.

    Returns: {ok, result, error?}
    """
    if not check_def:
        return {"ok": True, "result": "无验收条件，默认通过"}

    try:
        current_url = ""
        try:
            if hasattr(bridge, "page") and bridge.page:
                current_url = bridge.page.url
            else:
                url_result = await bridge.evaluate("window.location.href")
                current_url = str(url_result) if url_result else ""
        except Exception as e:
            logger.debug("run_check: failed to get current URL: %s", e)

        for key in check_def:
            value = check_def[key]
            if not isinstance(value, str) or not value:
                return {
                    "ok": False,
                    "result": f"{key}: 无效参数",
                    "error": f"{key} 需要非空字符串值，实际为 {type(value).__name__}",
                    "current_url": current_url,
                }

        if "url_contains" in check_def:
            expected = check_def["url_contains"]
            if expected not in current_url:
                return {
                    "ok": False,
                    "result": "url_contains: 失败",
                    "error": f"URL 不包含 '{expected}'，当前: {current_url[:100]}",
                    "current_url": current_url,
                }

        if "element_exists" in check_def:
            selector = check_def["element_exists"]
            exists = await bridge.evaluate(
                f"!!document.querySelector({_json_dumps(selector)})"
            )
            if not exists:
                return {
                    "ok": False,
                    "result": "element_exists: 失败",
                    "error": f"元素 '{selector}' 不存在",
                    "current_url": current_url,
                }

        if "text_contains" in check_def:
            expected = check_def["text_contains"]
            body_text = await bridge.evaluate("document.body.innerText || ''")
            body_text = str(body_text) if body_text else ""
            if expected not in body_text:
                return {
                    "ok": False,
                    "result": "text_contains: 失败",
                    "error": f"页面文本不包含 '{expected}'",
                    "current_url": current_url,
                }

        if "element_visible" in check_def:
            selector = check_def["element_visible"]
            visible = await bridge.evaluate(
                f"(function(){{"
                f"var el=document.querySelector({_json_dumps(selector)});"
                f"if(!el)return false;"
                f"var s=getComputedStyle(el);"
                f"return s.display!=='none'&&s.visibility!=='hidden'&&el.offsetWidth>0;"
                f"}})()"
            )
            if not visible:
                return {
                    "ok": False,
                    "result": "element_visible: 失败",
                    "error": f"元素 '{selector}' 不可见或不存在",
                    "current_url": current_url,
                }

        passed_checks = [k for k in check_def if k]
        if len(passed_checks) == 1:
            result_msg = f"{passed_checks[0]}: 通过"
        else:
            result_msg = f"{', '.join(passed_checks)}: 全部通过" if passed_checks else "check: 通过"
        return {"ok": True, "result": result_msg, "current_url": current_url}

    except Exception as e:
        return {
            "ok": False,
            "result": "验收执行出错",
            "error": str(e),
        }


def _json_dumps(s: str) -> str:
    """JSON-encode a string for safe embedding in JS."""
    return json.dumps(s)


# ──────────────────────────────────────────────────────────────
#  Pipeline wrappers (call core functions + write artifacts)
# ──────────────────────────────────────────────────────────────


async def execute_browser_step(
    step: dict,
    bridge: BrowserBridge,
    step_dir: Path,
    run_dir: Path,
    shared_store: dict | None = None,
) -> dict:
    """Execute a browser step: run ops via PlaywrightBridge, write step.json + artifacts.

    Delegates to execute_browser_op() for each individual operation,
    then writes screenshots and HTML to step_dir.
    """
    import base64
    import json as _json

    from yak_browser_use.engine._param_resolver import resolve_params

    ops = step.get("browser_ops", [])
    registry = CompensationRegistry()
    element_map: dict[str, str] = {}
    result: dict = {
        "step": step.get("name", ""),
        "type": "browser",
        "status": "completed",
        "duration_ms": 0,
        "ops": [],
        "params": step.get("params", {}),
        "final_url": "",
        "error": {"code": None, "message": None, "stack": None},
    }

    start = time.time()
    for op in ops:
        op_type = op.get("type", "")
        value = op.get("value", "")
        op_params = {k: v for k, v in op.items() if k != "type"}
        await registry.register_op(op_type, op_params)

        op_record: dict = {"type": op_type, "ok": True, "duration_ms": 0}

        if op_type in ("goto", "click", "fill", "snapshot", "scroll", "source",
                        "lookup_selector", "hover", "unhover", "focus", "select", "clear", "keyboard",
                        "press_key", "type_text",
                        "navigate", "wait", "tab", "copy", "paste"):
            if op_type == "goto":
                core_params = {"url": value}
                op_record["url"] = value
            elif op_type == "click":
                selector = value or op.get("selector", "")
                core_params = {"selector": selector}
                op_record["selector"] = selector
            elif op_type == "fill":
                text = value
                core_params = {"selector": op.get("selector", ""), "text": text}
                op_record["selector"] = op.get("selector", "")
                op_record["text"] = text
            elif op_type == "snapshot":
                core_params = {"mode": op.get("mode", "progressive"),
                                "expand_key": op.get("expand_key", "")}
            elif op_type == "scroll":
                core_params = {"direction": op.get("direction", "down"),
                                "amount": op.get("amount", 300)}
            elif op_type == "source":
                core_params = {}
            elif op_type == "lookup_selector":
                core_params = {"ref": op.get("ref", value)}
                op_record["ref"] = core_params["ref"]
            elif op_type == "hover":
                core_params = {"selector": value or op.get("selector", "")}
            elif op_type == "unhover":
                core_params = {"selector": value or op.get("selector", "")}
            elif op_type == "focus":
                core_params = {"selector": value or op.get("selector", "")}
            elif op_type == "clear":
                core_params = {"selector": value or op.get("selector", ""),
                               "mode": op.get("mode", "js")}
            elif op_type == "copy":
                core_params = {"selector": value or op.get("selector", "")}
            elif op_type == "paste":
                core_params = {"selector": value or op.get("selector", ""),
                               "index": op.get("index", -1)}
            elif op_type == "keyboard":
                mode = op.get("mode", "key")
                if mode == "key":
                    core_params = {"mode": "key", "key": value or op.get("key", "")}
                else:
                    core_params = {"mode": "text", "text": value or op.get("text", "")}
            elif op_type == "select":
                core_params = {"selector": op.get("selector", ""),
                               "value": op.get("value", value),
                               "mode": op.get("mode", "value")}
            elif op_type == "navigate":
                core_params = {"action": value or op.get("action", "back")}
            elif op_type == "tab":
                core_params = {"action": value or op.get("action", "list"),
                               "url": op.get("url", "about:blank"),
                               "target_id": op.get("target_id", "")}
            elif op_type == "wait":
                mode = op.get("mode", "time")
                if mode == "time" and value:
                    core_params = {"mode": "time", "duration": int(float(value) * 1000)}
                else:
                    core_params = {k: v for k, v in op.items() if k != "type"}
            else:
                core_params = {k: v for k, v in op.items() if k != "type"}

            core_params, _ = resolve_params(core_params, shared_store)

            retry = op.get("retry", 0)
            optional = op.get("optional", False)

            core_result = None
            for attempt in range(retry + 1):
                try:
                    core_result = await execute_browser_op(op_type, core_params, bridge, element_map)
                except Exception as e:
                    if attempt < retry:
                        await asyncio.sleep(1)
                        continue
                    if optional:
                        op_record["ok"] = False
                        op_record["skipped"] = True
                        op_record["error"] = str(e)
                        op_record["duration_ms"] = 0
                        result["ops"].append(op_record)
                        core_result = None
                        break
                    raise

                if not core_result["ok"]:
                    if attempt < retry:
                        await asyncio.sleep(1)
                        continue
                    if optional:
                        op_record["ok"] = False
                        op_record["skipped"] = True
                        op_record["error"] = core_result.get("error", "")
                        op_record["duration_ms"] = core_result["duration_ms"]
                        result["ops"].append(op_record)
                        core_result = None
                        break
                break

            if core_result is None:
                continue

            op_record["ok"] = core_result["ok"]
            op_record["duration_ms"] = core_result["duration_ms"]

            if core_result["ok"]:
                if op_type == "snapshot":
                    snap_result = core_result.get("result", {})
                    snap_mode = snap_result.get("mode", "full")
                    if snap_mode == "progressive":
                        elements = snap_result.get("elements", [])
                        elements_path = step_dir / "elements.json"
                        elements_path.write_text(_json.dumps(elements, ensure_ascii=False, indent=2), encoding="utf-8")
                        element_map = {el["ref"]: el["selector"] for el in elements if el.get("ref") and el.get("selector")}
                    elif snap_mode == "simplified":
                        summary = snap_result.get("summary", "")
                        lists_data = snap_result.get("lists", [])
                        tables_data = snap_result.get("tables", [])
                        (step_dir / "page_summary.txt").write_text(summary, encoding="utf-8")
                        (step_dir / "detected_lists.json").write_text(_json.dumps(lists_data, ensure_ascii=False, indent=2), encoding="utf-8")
                        (step_dir / "detected_tables.json").write_text(_json.dumps(tables_data, ensure_ascii=False, indent=2), encoding="utf-8")
                    else:
                        _write_full_artifacts(core_result, step_dir, base64, time)
                elif op_type == "source":
                    html_data = core_result.get("html", "")
                    if html_data:
                        html_path = step_dir / "page.html"
                        html_path.write_text(html_data, encoding="utf-8")
                if op_type == "goto":
                    result["final_url"] = value
                if op_type in ("goto", "click", "fill", "navigate", "tab", "wait") and hasattr(bridge, "ensure_highlights"):
                    try:
                        await bridge.ensure_highlights()
                    except Exception:
                        logger.warning("ensure_highlights failed after %s op", op_type, exc_info=True)
            else:
                op_record["error"] = core_result["error"]
                result["status"] = "failed"
                result["error"] = {
                    "code": "TIMEOUT_ERROR" if "timeout" in str(core_result.get("error", "")).lower()
                            else "BROWSER_ERROR",
                    "message": core_result["error"],
                    "stack": None,
                }
                result["ops"].append(op_record)
                result["duration_ms"] = int((time.time() - start) * 1000)
                result["compensation_history"] = registry.to_list()
                result["suggest_rollback"] = await registry.suggest_rollback(len(registry._ops) - 1)
                return result
        elif op_type == "wait_for_network":
            op_start = time.time()
            await bridge.wait_for_network_idle()
            op_record["duration_ms"] = int((time.time() - op_start) * 1000)
        elif op_type == "get_html":
            op_start = time.time()
            html = await bridge.get_page_html()
            html_path = step_dir / "page.html"
            html_path.write_text(html, encoding="utf-8")
            op_record["duration_ms"] = int((time.time() - op_start) * 1000)

        result["ops"].append(op_record)

    result["duration_ms"] = int((time.time() - start) * 1000)
    return result


async def execute_tool_step(
    step: dict,
    tools_dir: Path,
    step_dir: Path,
    run_dir: Path,
    cdp_helpers: object | None = None,
    shared_store: dict | None = None,
) -> dict:
    """Execute a tool step: import the tool module, call its function, validate output.

    Delegates to execute_tool() for core execution, then validates
    output files and writes them to step_dir.
    """
    tool_name = step.get("tool_name", "")
    input_ref = step.get("input", {})
    output_files = step.get("output", [])
    params = step.get("params", {})

    result: dict = {
        "step": step.get("name", ""),
        "type": "tool",
        "tool": tool_name,
        "status": "completed",
        "duration_ms": 0,
        "input_files": {},
        "output_files": [],
        "params": params,
        "error": {"code": None, "message": None, "stack": None},
    }

    if not tool_name:
        result["status"] = "failed"
        result["error"] = {"code": "INPUT_ERROR", "message": "tool_name is required", "stack": None}
        return result

    start = time.time()
    input_files = _resolve_input_files(input_ref, run_dir)
    result["input_files"] = input_files

    core_params = {
        "input_files": input_files,
        "output_dir": str(step_dir),
        **params,
    }

    from yak_browser_use.engine._param_resolver import resolve_params
    from yak_browser_use.tools.registry import registry, ToolContext as RegistryToolContext

    resolved_params, resolve_errors = resolve_params(core_params, shared_store)

    ctx = RegistryToolContext(
        cdp_helpers=cdp_helpers,
        tools_dir=tools_dir,
        shared_store=shared_store,
    )
    dispatch_result = await registry.dispatch(tool_name, resolved_params, ctx)

    if dispatch_result.get("ok") is False and dispatch_result.get("error", "").startswith("Unknown tool:"):
        core_result = await execute_tool(tool_name, resolved_params, tools_dir, cdp_helpers)
    else:
        core_result = dispatch_result

    prepend_resolve_errors(core_result, resolve_errors)

    result["duration_ms"] = core_result.get("duration_ms", 0)

    if not core_result["ok"]:
        result["status"] = "failed"
        is_timeout = "timeout" in str(core_result.get("error", "")).lower()
        result["error"] = {
            "code": "TIMEOUT_ERROR" if is_timeout else "RUNTIME_ERROR",
            "message": core_result["error"],
            "stack": None,
        }
        return result

    missing = _check_outputs(output_files, step_dir)
    if missing:
        result["status"] = "failed"
        result["error"] = {
            "code": "OUTPUT_ERROR",
            "message": f"Output files missing: {missing}",
            "stack": None,
        }
    else:
        result["output_files"] = [str(step_dir / f) for f in output_files]

    return result


# ── Result writing ──


def write_step_json(step_dir: Path, result: dict) -> None:
    """Atomically write the step result to ``step.json`` via ``.tmp`` rename."""
    import shutil

    tmp_path = step_dir / "step.json.tmp"
    real_path = step_dir / "step.json"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    shutil.move(str(tmp_path), str(real_path))


# ── Input / output helpers ──


def _resolve_input_files(input_ref: str | dict, run_dir: Path) -> dict[str, str]:
    """Resolve input file references to absolute paths.

    Supports:
    - String refs like ``"step_name.file_name"``
    - Dict refs like ``{"key": "step_name.file_name"}``
    - Absolute ``/path`` refs (blocked — raises ValueError)
    - ``data/`` prefix refs resolved relative to the workspace root

    Args:
        input_ref: Input file reference.
        run_dir: Run directory used for resolving step-relative paths.

    Returns:
        Dict of input key → absolute file path.

    Raises:
        ValueError: If an absolute path or ``..`` traversal is detected.
    """
    if isinstance(input_ref, str):
        key = _default_input_key(input_ref)
        return {key: str(_resolve_path(input_ref, run_dir))}
    if isinstance(input_ref, dict):
        return {k: str(_resolve_path(v, run_dir)) for k, v in input_ref.items()}
    return {}


def _resolve_path(ref: str, run_dir: Path) -> Path:
    """Resolve a single file reference to an absolute path.

    Args:
        ref: File reference string.
        run_dir: Run directory.

    Returns:
        Resolved Path.

    Raises:
        ValueError: If path starts with ``/`` (absolute) or contains ``..``.
    """
    if ref.startswith("/"):
        logger.error("Absolute path ref rejected: %s — would bypass workspace isolation", ref)
        raise ValueError(f"Absolute path reference rejected (violates workspace isolation): {ref}")

    if ".." in ref.replace("\\", "/").split("/"):
        raise ValueError(f"Path traversal rejected: {ref}")

    # data/ prefix → workspace root
    if ref.startswith("data/"):
        # Resolve relative to workspace root (run_dir/../../data/)
        return run_dir.parents[2] / ref

    # step_key.file_name → run_dir/step_key/file_name
    parts = ref.split(".", 1)
    step_key = parts[0]
    file_name = parts[1] if len(parts) > 1 else ""
    resolved = run_dir / step_key / file_name
    if not resolved.exists():
        logger.warning("Input path not found: %s", resolved)
    return resolved


def _default_input_key(ref: str) -> str:
    """Generate a default input key for a string reference.

    ``"step_name.file_name"`` → ``"step_name"``
    ``"some_file.txt"`` → ``"input"``
    """
    parts = ref.split(".", 1)
    return parts[0] if len(parts) > 1 else "input"


def _check_outputs(output_files: list[str], step_dir: Path) -> list[str]:
    """Check that all declared output files exist in the step directory.

    Args:
        output_files: List of file names (relative to step_dir).
        step_dir: Step artifact directory.

    Returns:
        List of missing file names (empty = all present).
    """
    missing: list[str] = []
    for f in output_files:
        if isinstance(f, str):
            if not (step_dir / f).exists():
                missing.append(f)
    return missing
