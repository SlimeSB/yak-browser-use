"""Tool executor — sequential tool call execution for chat and preset modes.

Delegates to executor.py core functions (execute_browser_op / execute_tool
/ execute_goal) for actual execution. Both chat mode and preset replay mode
use the same executor core.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Callable

from yak_browser_use.utils.helpers import prepend_resolve_errors
from yak_browser_use.utils.logging import get_logger

from yak_browser_use.engine._harness.tool_guardrails import ToolCallGuardrailState
from yak_browser_use.prompts._loader import load_prompt

logger = get_logger(__name__)

# Event type constants — shared between conversation_loop and tool_executor
EVENT_TURN_START = "turn_start"
EVENT_LLM_TURN = "llm_turn"
EVENT_TOOL_START = "chat.tool_start"
EVENT_TOOL_END = "chat.tool_end"
EVENT_ERROR = "chat.error"

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
    llm_call: Callable | None = None,
    shared_store: dict | None = None,
) -> None:
    """Execute tool calls one at a time, sequentially.

    Args:
        messages: The conversation messages list (mutated in-place).
        tool_calls: List of LLM tool call dicts.
        cdp_helpers: CDPHelpers instance for browser operations.
        tools_dir: Directory containing tool Python files.
        pipeline_name: Current pipeline name.
        guardrail_state: Per-turn guardrail state.
        budget: Iteration budget (paused during CDP reconnect, not consumed here).
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
                "type": EVENT_TOOL_START,
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
                llm_call=llm_call,
                interrupt_check=interrupt_check,
                shared_store=shared_store,
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

        if result_dict.get("_pipeline_finish"):
            break

        if ok and fn_name in ("browser_goto", "browser_click", "browser_fill", "browser_scroll") and cdp_helpers is not None:
            await _auto_refresh_highlights(cdp_helpers)
            if hasattr(cdp_helpers, "bridge") and cdp_helpers.bridge is not None:
                await cdp_helpers.bridge.wait_for_page_scan()

        if stream_callback:
            stream_callback({
                "type": EVENT_TOOL_END,
                "tool_name": fn_name,
                "ok": ok,
                "duration_ms": result_dict.get("duration_ms", int((time.time() - start) * 1000)),
                "error": error_msg if not ok else None,
                "id": tool_call_id,
            })

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
    llm_call: Callable | None = None,
    interrupt_check: Callable[[], bool] | None = None,
    shared_store: dict | None = None,
) -> dict:
    """Route a single tool call to the correct executor core function.

    Handles:
    - TimeoutError 1x retry
    - CDP reconnect with 3x exponential backoff
    - Unrecoverable error detection
    - Parameter template resolution via shared_store
    """
    from yak_browser_use.engine.executor import execute_tool
    from yak_browser_use.engine._param_resolver import resolve_params, strip_pointer
    from yak_browser_use.tools.registry import registry, ToolContext as RegistryToolContext

    reconnect_attempts = 0
    timeout_retried = False

    while True:
        try:
            # ── Scratchpad caching (before dispatch) ─────────────────
            if fn_name == "browser_source" and fn_args.get("cached"):
                cached_result = _try_scratchpad_source_read()
                if cached_result is not None:
                    return cached_result

            # ── Strip 'bind' (framework param) before resolve ────
            source_key = strip_pointer(fn_args.pop("bind", ""))

            # ── Resolve parameter templates ──────────────────────────
            resolved_args, resolve_errors = resolve_params(fn_args, shared_store)

            # ── Dispatch via registry ────────────────────────────────
            ctx = RegistryToolContext(
                cdp_helpers=cdp_helpers,
                tools_dir=tools_dir,
                pipeline_name=pipeline_name,
                budget=budget,
                llm_call=llm_call,
                interrupt_check=interrupt_check,
                stream_callback=stream_callback,
                shared_store=shared_store,
            )

            result = await registry.dispatch(fn_name, resolved_args, ctx)

            if result.get("ok") is False and result.get("error", "").startswith("Unknown tool:"):
                result = await execute_tool(
                    tool_name=fn_name,
                    params=resolved_args,
                    tools_dir=tools_dir or Path("."),
                    cdp_helpers=cdp_helpers,
                )

            # ── Write to shared_store if 'bind' specified ────────
            if source_key and shared_store is not None:
                shared_store[source_key] = result

            prepend_resolve_errors(result, resolve_errors)

            return result

        except TimeoutError as e:
            if not timeout_retried:
                timeout_retried = True
                logger.info("tool_executor: timeout, retrying (1/1)")
                await asyncio.sleep(0.5)
                continue
            raise

        except asyncio.CancelledError:
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
                bridge_restarted = False
                if cdp_helpers and hasattr(cdp_helpers, "bridge"):
                    try:
                        await cdp_helpers.bridge.stop()
                    except Exception:
                        logger.debug("PlaywrightBridge stop before restart failed", exc_info=True)
                    try:
                        await cdp_helpers.bridge.start()
                        bridge_restarted = True
                    except Exception as e:
                        logger.warning("PlaywrightBridge restart failed: %s", e)
                if budget is not None and budget.is_paused:
                    if bridge_restarted:
                        budget.resume()
                    else:
                        budget.resume()
                        budget.exhaust()
                timeout_retried = False
                continue
            if _is_cdp_disconnect(e) and reconnect_attempts >= _CDP_RECONNECT_MAX and stream_callback:
                stream_callback({
                    "type": EVENT_ERROR,
                    "message": "浏览器连接丢失，请检查 Chrome 是否运行",
                })
            raise


def _is_cdp_disconnect(error: Exception) -> bool:
    """Check if an exception is a CDP connection error."""
    msg = str(error).lower()
    cls_name = type(error).__name__.lower()
    if "targetclosed" in cls_name or "browserclosed" in cls_name:
        return True
    if "websocket" in cls_name:
        return True
    cdp_patterns = [
        "target closed",
        "browser has been closed",
        "browser closed",
        "connection closed while reading from",
        "protocol error",
    ]
    return any(p in msg for p in cdp_patterns)


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
        if result_dict.get("_pipeline_finish"):
            return json.dumps({"status": result_dict.get("status", ""), "summary": result_dict.get("summary", "")}, ensure_ascii=False)
        r = result_dict.get("result", "")
        if isinstance(r, str):
            return r
        return str(r)
    else:
        return f"Error executing {tool_name}: {result_dict.get('error', 'unknown error')}"


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


async def _auto_refresh_highlights(cdp_helpers: object) -> None:
    """Refresh DOM highlights after a tool call that may have changed the page.

    Pushes the bridge's cached ``_last_highlight_elements`` into the browser
    renderer so badge positions stay in sync after click / fill / goto / scroll.
    """
    from yak_browser_use.engine.scratchpad import sync_element_map as scratchpad_sync_element_map
    if not hasattr(cdp_helpers, "add_dom_highlights"):
        return
    try:
        bridge = cdp_helpers.bridge if hasattr(cdp_helpers, "bridge") else None
        elements = getattr(bridge, "_last_highlight_elements", []) if bridge else []
        highlight_result = await cdp_helpers.add_dom_highlights(elements)
        element_map = highlight_result.get("element_map", {})
        if element_map:
            elements_for_sync = [
                {"ref": ref, "selector": info.get("selector", "")}
                for ref, info in element_map.items()
            ]
            scratchpad_sync_element_map(elements_for_sync)
    except Exception:
        logger.debug("auto_refresh_highlights failed", exc_info=True)


def _apply_heavy_data_filter(
    fn_name: str,
    fn_args: dict,
    result_dict: dict,
) -> None:
    from yak_browser_use.engine.scratchpad import get as get_scratchpad
    from yak_browser_use.engine.scratchpad import store as store_scratchpad
    from yak_browser_use.engine.scratchpad import store_raw_html as scratchpad_store_raw_html
    """Extract heavy data from browser_snapshot/browser_source results.

    Writes large payloads (HTML, elements, screenshots) to scratchpad and
    replaces result_dict["result"] with concise summaries.
    """
    if not result_dict.get("ok"):
        return

    if fn_name == "browser_snapshot":
        mode = fn_args.get("mode", "aria")

        if mode in ("aria", "simplified"):
            # aria snapshot returns mode="aria"
            result_payload = result_dict.get("result", {})
            if isinstance(result_payload, dict) and result_payload.get("degraded"):
                result_payload.pop("screenshot_base64", None)
                result_payload.pop("html", None)
                store_scratchpad({
                    "elements": [],
                    "url": result_payload.get("url", ""),
                    "title": result_payload.get("title", ""),
                })
                result_dict["result"] = "ARIA 快照已获取（降级为 full 模式），数据已缓存"
            return

        result_payload = result_dict.get("result", {})

        if mode in ("a11y", "interactive"):
            if isinstance(result_payload, dict):
                # a11y → progressive fallback: data is progressive format
                if result_payload.get("degraded"):
                    elements = result_payload.get("elements", [])
                    folded = result_payload.get("folded_containers", [])
                    branch_info = result_payload.get("branch_index", {})
                    url = result_payload.get("url", "")
                    title = result_payload.get("title", "")
                    store_scratchpad({
                        "elements": elements,
                        "folded_containers": folded,
                        "branch_index": branch_info,
                        "url": url,
                        "title": title,
                    })
                    result_dict["result"] = (
                        "⚠️ Accessibility Tree 不可用，已降级到 progressive 模式\n\n"
                        + get_scratchpad().summary
                    )
                else:
                    elements = result_payload.get("elements", [])
                    url = result_payload.get("url", "")
                    title = result_payload.get("title", "")
                    store_scratchpad({
                        "elements": elements,
                        "url": url,
                        "title": title,
                    })
                    result_dict["result"] = get_scratchpad().summary
            else:
                result_dict["result"] = "a11y 快照已获取（摘要不可用）"
                logger.warning("browser_snapshot a11y returned non-dict result, using fallback")
            return

        if mode == "progressive":
            if isinstance(result_payload, dict):
                elements = result_payload.get("elements", [])
                folded = result_payload.get("folded_containers", [])
                branch_info = result_payload.get("branch_index", {})
                url = result_payload.get("url", "")
                title = result_payload.get("title", "")
                store_scratchpad({
                    "elements": elements,
                    "folded_containers": folded,
                    "branch_index": branch_info,
                    "url": url,
                    "title": title,
                })
                result_dict["result"] = get_scratchpad().summary
            else:
                result_dict["result"] = "progressive 快照已获取（摘要不可用）"
                logger.warning("browser_snapshot progressive returned non-dict result, using fallback")
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


def _try_scratchpad_source_read() -> dict | None:
    from yak_browser_use.engine.scratchpad import get as get_scratchpad
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
