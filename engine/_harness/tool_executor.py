"""Tool executor — sequential tool call execution for chat and preset modes.

Delegates to executor.py core functions (execute_browser_op / execute_tool
/ execute_goal) for actual execution. Both chat mode and preset replay mode
use the same executor core.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Callable

from utils.logging import get_logger

from engine._harness.tool_guardrails import ToolCallGuardrailState
from engine._harness.iteration_budget import IterationBudget
from engine.scratchpad import get as get_scratchpad
from engine.scratchpad import store as store_scratchpad
from engine.scratchpad import store_raw_html as scratchpad_store_raw_html
from engine.scratchpad import sync_element_map as scratchpad_sync_element_map
from prompts._loader import load_prompt

logger = get_logger(__name__)

# CDP reconnect backoff (3 tries: 1s / 2s / 4s)
_CDP_RECONNECT_DELAYS = [1.0, 2.0, 4.0]
_CDP_RECONNECT_MAX = 3


class UnrecoverableError(Exception):
    """Raised when a tool call encounters an unrecoverable error."""


_UNRECOVERABLE_KEYWORDS = frozenset({
    "permission denied", "chrome crashed", "browser closed",
    "window closed", "target closed", "browser has been closed",
    "page crashed", "devtools disconnected",
})


def _is_unrecoverable(error: Exception) -> bool:
    """Check if an error is unrecoverable and should terminate the task."""
    msg = str(error).lower()
    return any(kw in msg for kw in _UNRECOVERABLE_KEYWORDS)


async def execute_tool_calls_sequential(
    messages: list[dict],
    tool_calls: list[dict],
    *,
    cdp_helpers: object | None = None,
    tools_dir: Path | None = None,
    pipeline_name: str = "",
    guardrail_state: ToolCallGuardrailState | None = None,
    budget: IterationBudget | None = None,
    interrupt_check: Callable[[], bool] | None = None,
    stream_callback: Callable[[dict], None] | None = None,
) -> None:
    """Execute tool calls one at a time, sequentially.

    Args:
        messages: The conversation messages list (mutated in-place).
        tool_calls: List of LLM tool call dicts.
        cdp_helpers: CDPHelpers instance for browser operations.
        tools_dir: Directory containing tool Python files.
        pipeline_name: Current pipeline name.
        guardrail_state: Per-turn guardrail state.
        budget: Iteration budget (paused during goal_run, not consumed here).
        interrupt_check: Callable returning True if conversation is interrupted.
        stream_callback: Optional callback for streaming events.

    No return value — results are appended directly to *messages*.
    Raises UnrecoverableError on unrecoverable failures.
    """
    for tc in tool_calls:
        if interrupt_check and interrupt_check():
            logger.info("tool_executor: interrupt detected, skipping remaining tool calls")
            break

        fn_name = _extract_function_name(tc)
        fn_args = _extract_function_args(tc)
        tool_call_id = tc.get("id", "")

        logger.info("tool_executor: executing %s(%s)", fn_name, _truncate_args(fn_args))

        if stream_callback:
            stream_callback({
                "type": "chat.tool_start",
                "tool_name": fn_name,
                "args": fn_args,
                "id": tool_call_id,
            })

        if guardrail_state:
            guard_result = guardrail_state.before_call(fn_name, fn_args)
            if guard_result is not True:
                _append_tool_result(messages, tool_call_id, fn_name,
                                    _format_guarded_result(str(guard_result)))
                continue

        start = time.time()
        try:
            result_dict = await _execute_single_tool_call(
                fn_name=fn_name,
                fn_args=fn_args,
                cdp_helpers=cdp_helpers,
                tools_dir=tools_dir,
                pipeline_name=pipeline_name,
                budget=budget,
                stream_callback=stream_callback,
            )
        except UnrecoverableError:
            raise
        except Exception as e:
            if _is_unrecoverable(e):
                logger.error("tool_executor: unrecoverable error: %s", e)
                raise UnrecoverableError(str(e)) from e
            result_dict = {
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "duration_ms": int((time.time() - start) * 1000),
            }

        ok = result_dict.get("ok", False)
        error_msg = result_dict.get("error", "")

        _apply_heavy_data_filter(fn_name, fn_args, result_dict)

        result_text = _format_tool_result(fn_name, result_dict)

        if guardrail_state:
            warning = guardrail_state.after_call(
                fn_name, fn_args,
                ok=ok,
                result_str=result_text,
            )
            if warning:
                result_text += f"\n\n{_format_tool_warning(warning)}"

        _append_tool_result(messages, tool_call_id, fn_name, result_text)

        if ok and fn_name in ("browser_goto", "browser_click", "browser_fill") and cdp_helpers is not None:
            if hasattr(cdp_helpers, "add_dom_highlights"):
                try:
                    highlight_result = await cdp_helpers.add_dom_highlights()
                    element_map = highlight_result.get("element_map", {})
                    if element_map:
                        elements_for_sync = [
                            {"ref": ref, "selector": info.get("selector", "")}
                            for ref, info in element_map.items()
                        ]
                        scratchpad_sync_element_map(elements_for_sync)
                except Exception:
                    pass

        if stream_callback:
            stream_callback({
                "type": "chat.tool_end",
                "tool_name": fn_name,
                "ok": ok,
                "duration_ms": result_dict.get("duration_ms", 0),
                "error": error_msg if not ok else None,
                "id": tool_call_id,
            })

        if not ok and fn_name == "goal_run" and stream_callback:
            stream_callback({"type": "chat.error", "message": error_msg})

    if guardrail_state:
        guardrail_state.reset()


async def _execute_single_tool_call(
    fn_name: str,
    fn_args: dict,
    cdp_helpers: object | None,
    tools_dir: Path | None,
    pipeline_name: str,
    budget: IterationBudget | None = None,
    stream_callback: Callable[[dict], None] | None = None,
) -> dict:
    """Route a single tool call to the correct executor core function.

    Handles:
    - TimeoutError 1x retry
    - CDP reconnect with 3x exponential backoff
    - Unrecoverable error detection
    """
    from engine.executor import execute_browser_op, execute_tool

    reconnect_attempts = 0

    while True:
        try:
            if fn_name.startswith("browser_"):
                op_type = fn_name.replace("browser_", "")

                if op_type == "get_element_by_number":
                    cached_result = _try_scratchpad_element_lookup(fn_args)
                    if cached_result is not None:
                        return cached_result

                if op_type == "source" and fn_args.get("cached"):
                    cached_result = _try_scratchpad_source_read()
                    if cached_result is not None:
                        return cached_result

                return await execute_browser_op(op_type, fn_args, cdp_helpers)

            elif fn_name.startswith("pipeline_"):
                from engine._harness.pipeline_tools import (
                    pipeline_load,
                    pipeline_list,
                    pipeline_update_step,
                    pipeline_add_step,
                    pipeline_remove_step,
                    pipeline_create,
                )

                dispatch = {
                    "pipeline_load": pipeline_load,
                    "pipeline_list": pipeline_list,
                    "pipeline_update_step": pipeline_update_step,
                    "pipeline_add_step": pipeline_add_step,
                    "pipeline_remove_step": pipeline_remove_step,
                    "pipeline_create": pipeline_create,
                }

                handler = dispatch.get(fn_name)
                if handler is None:
                    return {"ok": False, "error": f"Unknown pipeline tool: {fn_name}"}

                result_str = await handler(**fn_args)
                import json
                try:
                    return json.loads(result_str)
                except (json.JSONDecodeError, TypeError):
                    return {"ok": True, "result": result_str}

            elif fn_name == "goal_run":
                description = fn_args.get("description", fn_args.get("goal", ""))
                return {
                    "ok": True,
                    "result": (
                        f"目标已设定: {description}\n\n"
                        f"请用 todo 工具将目标拆解为 3-6 个步骤逐项执行。"
                        f"每步完成后调 record_step。不确定时直接问我。"
                    ),
                }

            elif fn_name == "todo":
                from tools.todo_store import current_store
                from tools.todo import todo

                store = current_store.get()
                todos = fn_args.get("todos")
                merge = fn_args.get("merge", False)
                result_str = await todo(todos=todos, merge=merge, store=store)
                return {"ok": True, "result": result_str}

            else:
                return await execute_tool(
                    tool_name=fn_name,
                    params=fn_args,
                    tools_dir=tools_dir or Path("."),
                    cdp_helpers=cdp_helpers,
                )

        except TimeoutError as e:
            if reconnect_attempts == 0:
                reconnect_attempts += 1
                logger.info("tool_executor: timeout, retrying (1/1)")
                await asyncio.sleep(0.5)
                continue
            raise

        except Exception as e:
            if _is_unrecoverable(e):
                raise UnrecoverableError(str(e)) from e

            if _is_cdp_disconnect(e) and reconnect_attempts < _CDP_RECONNECT_MAX:
                reconnect_attempts += 1
                delay = _CDP_RECONNECT_DELAYS[reconnect_attempts - 1]
                logger.warning(
                    "tool_executor: CDP disconnect, reconnecting attempt %d/%d (delay %.1fs)",
                    reconnect_attempts, _CDP_RECONNECT_MAX, delay,
                )
                if budget is not None and not budget.is_paused:
                    budget.pause()
                await asyncio.sleep(delay)
                if cdp_helpers and hasattr(cdp_helpers, "_daemon"):
                    try:
                        await cdp_helpers._daemon.start()  # type: ignore[union-attr]
                    except Exception as e:
                        logger.debug("CDP daemon restart failed: %s", e)
                if budget is not None and budget.is_paused:
                    budget.resume()
                if reconnect_attempts >= _CDP_RECONNECT_MAX and stream_callback:
                    stream_callback({
                        "type": "chat.error",
                        "message": "浏览器连接丢失，请检查 Chrome 是否运行",
                    })
                continue
            raise


def _is_cdp_disconnect(error: Exception) -> bool:
    """Check if an exception is a CDP connection error."""
    msg = str(error).lower()
    cls_name = type(error).__name__.lower()
    return (
        "connection" in cls_name
        or "websocket" in cls_name
        or "connection" in msg
        or "closed" in msg
        or "eof" in msg
    )


def _extract_function_name(tool_call: dict) -> str:
    fn = tool_call.get("function", tool_call)
    return fn.get("name", "")


def _extract_function_args(tool_call: dict) -> dict:
    fn = tool_call.get("function", tool_call)
    args_str = fn.get("arguments", "{}")
    if isinstance(args_str, dict):
        return args_str
    import json
    try:
        return json.loads(args_str)
    except (json.JSONDecodeError, TypeError):
        return {}


def _append_tool_result(
    messages: list[dict],
    tool_call_id: str,
    tool_name: str,
    content: str,
) -> None:
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": content,
    })


def _format_tool_result(tool_name: str, result_dict: dict) -> str:
    if result_dict.get("ok"):
        r = result_dict.get("result", "")
        if isinstance(r, str):
            return r
        return str(r)
    else:
        return load_prompt("guidance/error_recovery") + "\n\n" + \
            f"Error executing {tool_name}: {result_dict.get('error', 'unknown error')}"


def _format_guarded_result(guard_result: str) -> str:
    try:
        prefix = load_prompt("guardrails/blocked")
        return f"{prefix} {guard_result}"
    except Exception:
        return f"[Blocked] {guard_result}"


def _format_tool_warning(warning: str) -> str:
    try:
        prefix = load_prompt("guardrails/warning_prefix")
        return f"{prefix} {warning}"
    except Exception:
        return f"[Tool loop warning] {warning}"


def _truncate_args(args: dict, max_len: int = 120) -> str:
    s = str(args)
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


# Alias for spec compatibility
execute_tool_calls = execute_tool_calls_sequential


def _apply_heavy_data_filter(
    fn_name: str,
    fn_args: dict,
    result_dict: dict,
) -> None:
    """Extract heavy data from browser_snapshot/browser_source results.

    Writes large payloads (HTML, elements, screenshots) to scratchpad and
    replaces result_dict["result"] with concise summaries.
    """
    if not result_dict.get("ok"):
        return

    if fn_name == "browser_snapshot":
        mode = fn_args.get("mode", "interactive")

        if mode == "simplified":
            result_payload = result_dict.get("result", {})
            if isinstance(result_payload, dict) and result_payload.get("degraded"):
                result_payload.pop("screenshot_base64", None)
                result_payload.pop("html", None)
                store_scratchpad({
                    "elements": [],
                    "url": result_payload.get("url", ""),
                    "title": result_payload.get("title", ""),
                })
                result_dict["result"] = "简化快照已获取（降级为 full 模式），数据已缓存"
            return

        result_payload = result_dict.get("result", {})

        if mode == "interactive":
            if isinstance(result_payload, dict):
                degraded = result_payload.get("degraded", False)
                elements = result_payload.get("elements", [])
                url = result_payload.get("url", "")
                title = result_payload.get("title", "")
                store_scratchpad({
                    "elements": elements,
                    "url": url,
                    "title": title,
                })
                if degraded:
                    result_payload.pop("screenshot_base64", None)
                    result_payload.pop("html", None)
                    el_count = len(elements)
                    result_dict["result"] = f"\U0001F4F8 快照已获取（降级为 full 模式，{el_count}个可交互元素），数据已缓存"
                else:
                    result_dict["result"] = get_scratchpad().summary
            else:
                result_dict["result"] = "快照已获取（摘要不可用）"
                logger.warning("browser_snapshot interactive returned non-dict result, using fallback")
            return

        elif mode == "full":
            result_dict.pop("screenshot_base64", "")
            html = result_dict.pop("html", "")
            result_payload_val = result_dict.get("result", {})
            url = result_payload_val.get("url", "") if isinstance(result_payload_val, dict) else ""
            title = result_payload_val.get("title", "") if isinstance(result_payload_val, dict) else ""
            store_scratchpad({
                "elements": [],
                "url": url,
                "title": title,
            })
            if html:
                scratchpad_store_raw_html(html)
            result_dict["result"] = "\U0001F4F8 完整快照已获取（含截图+HTML），数据已缓存"
            return

        else:
            result_dict["result"] = "快照已获取（无摘要）"
            logger.warning("browser_snapshot: unknown mode '%s', using fallback", mode)
            return

    if fn_name == "browser_source":
        result_payload = result_dict.get("result", {})
        if isinstance(result_payload, dict) and result_payload.get("cached"):
            result_dict.pop("html", None)
            return
        html = result_dict.pop("html", "")
        if html:
            scratchpad_store_raw_html(html)
            result_payload = {"length": len(html)}
            if fn_args.get("cached"):
                result_payload["cached"] = False
                result_payload["note"] = "无缓存，已从 CDP 获取"
            result_dict["result"] = result_payload
        return


def _normalize_ref(ref: str) -> str:
    """Normalize an element reference to @eN format."""
    ref = ref.strip()
    if ref.startswith("@"):
        return ref
    if ref.startswith("e") and ref[1:].isdigit():
        return f"@{ref}"
    return f"@e{ref}"


def _try_scratchpad_element_lookup(fn_args: dict) -> dict | None:
    """Try to resolve browser_get_element_by_number from scratchpad cache.

    Returns a result dict if found, None to fall through to CDP.
    """
    raw_ref = fn_args.get("ref", "")
    if not raw_ref:
        return None

    sp = get_scratchpad()
    normalized = _normalize_ref(raw_ref)

    if not sp.element_map:
        return None

    selector = sp.element_map.get(normalized)
    if selector is None:
        return None

    el_info = None
    for el in sp.elements:
        if el.get("ref") == normalized:
            el_info = el
            break

    if el_info is None:
        return {
            "ok": True,
            "result": {
                "ref": normalized,
                "selector": selector,
            },
        }

    return {
        "ok": True,
        "result": {
            "ref": normalized,
            "tag": el_info.get("tag", ""),
            "type": el_info.get("type", ""),
            "text": el_info.get("text", ""),
            "selector": selector,
        },
    }


def _try_scratchpad_source_read() -> dict | None:
    """Try to read browser_source from scratchpad cache.

    Returns a result dict with cached HTML length, or None to fall through to CDP.
    """
    sp = get_scratchpad()
    if sp.raw_html:
        length = len(sp.raw_html)
        return {
            "ok": True,
            "result": {"length": length, "cached": True},
            "html": sp.raw_html,
        }
    return None
