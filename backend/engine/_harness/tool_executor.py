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

from utils.logging import get_logger

from engine._harness.tool_guardrails import ToolCallGuardrailState
from engine._harness.iteration_budget import IterationBudget
from prompts._loader import load_prompt

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

        if stream_callback:
            stream_callback({
                "type": EVENT_TOOL_END,
                "tool_name": fn_name,
                "ok": ok,
                "duration_ms": result_dict.get("duration_ms", 0),
                "error": error_msg if not ok else None,
                "id": tool_call_id,
            })

        if not ok and fn_name == "goal_run" and stream_callback:
            stream_callback({"type": EVENT_ERROR, "message": error_msg})

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
    from engine.executor import execute_tool
    from engine._param_resolver import resolve_params
    from tools.registry import registry, ToolContext as RegistryToolContext

    reconnect_attempts = 0
    timeout_retried = False

    while True:
        try:
            # ── Scratchpad caching (before dispatch) ─────────────────
            if fn_name == "browser_get_element_by_number":
                cached_result = _try_scratchpad_element_lookup(fn_args)
                if cached_result is not None:
                    return cached_result

            if fn_name == "browser_source" and fn_args.get("cached"):
                cached_result = _try_scratchpad_source_read()
                if cached_result is not None:
                    return cached_result

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

            # ── Write to shared_store if source_key specified ────────
            # Use fn_args (original) not resolved_args: source_key is a routing
            # param, not a data param — template resolver won't touch it, but
            # reading from fn_args makes the intent explicit.
            source_key = fn_args.get("source_key")
            if source_key and shared_store is not None and fn_name != "eval_agent":
                shared_store[source_key] = {
                    "ok": result.get("ok", False),
                    "data": result,
                }

            # ── Prepend resolve errors to tool result ────────────────
            if resolve_errors:
                warning = f"⚠️ 参数模板解析失败: {resolve_errors}"
                if result.get("ok"):
                    existing = result.get("result", "")
                    if isinstance(existing, str):
                        result["result"] = warning + "\n\n" + existing
                    else:
                        result["result"] = warning
                else:
                    existing = result.get("error", "")
                    result["error"] = warning + "\n\n" + existing

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


async def _handle_eval_agent(
    fn_args: dict,
    cdp_helpers: object | None,
    llm_call: Callable | None,
    budget: IterationBudget | None,
    interrupt_check: Callable[[], bool] | None,
    stream_callback: Callable[[dict], None] | None,
    pipeline_name: str = "",
    shared_store: dict | None = None,
) -> dict:
    """Handle eval_agent tool call: launch subagent with restricted tools."""
    if llm_call is None:
        return {"ok": False, "error": "eval_agent requires LLM access"}

    purpose = fn_args.get("purpose", "")
    snapshot = fn_args.get("snapshot", "")
    try:
        max_attempts = max(1, min(10, int(fn_args.get("max_attempts", 3))))
    except (TypeError, ValueError):
        max_attempts = 3
    # output_dir is reserved for future pipeline-mode eval_agent invocations
    # (LLM tool schema does not expose this parameter — chat mode always skips CSV write)
    output_dir = fn_args.get("output_dir", "")

    from engine.eval_agent import EvalAgent
    from engine._harness.conversation_loop import Agent

    eval_config = EvalAgent(max_attempts=max_attempts)
    system_prompt = eval_config.build_system_prompt(purpose=purpose, snapshot=snapshot)
    tools = eval_config.get_restricted_tools()

    eval_budget = IterationBudget(max_total=10)
    messages: list[dict] = [{"role": "user", "content": f"任务: {purpose}"}]

    agent = Agent(
        llm_call=llm_call,
        system_prompt=system_prompt,
        messages=messages,
        tools=tools,
        cdp_helpers=cdp_helpers,
        budget=eval_budget,
        interrupt_check=interrupt_check,
        stream_callback=stream_callback,
        shared_store=shared_store,
    )

    try:
        result = await asyncio.wait_for(
            agent.run(),
            timeout=120,
        )
    except asyncio.TimeoutError:
        partial = _extract_eval_summary(messages)
        _write_eval_csv(output_dir, purpose, success=False, result=partial)
        return {"ok": False, "error": "eval agent 超时（120s）", "partial_result": partial}

    if result.interrupted:
        partial = _extract_eval_summary(messages)
        _write_eval_csv(output_dir, purpose, success=False, result=partial)
        return {"ok": False, "error": "eval agent 被中断", "partial_result": partial}

    final_text = result.final_response or _extract_eval_summary(messages)
    _write_eval_csv(output_dir, purpose, success=True, result=final_text)
    _append_eval_to_pipeline(pipeline_name, purpose, final_text)

    eval_result = {"ok": True, "result": final_text}

    source_key = fn_args.get("source_key")
    if source_key and shared_store is not None:
        shared_store[source_key] = {
            "ok": True,
            "data": eval_result,
        }

    return eval_result


def _extract_eval_summary(messages: list[dict]) -> str:
    """Extract the last meaningful response from eval agent messages."""
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and msg.get("content"):
            return str(msg["content"])[:2000]
    return "eval agent 完成，无文本输出"


def _write_eval_csv(
    output_dir: str,
    purpose: str,
    success: bool,
    result: str,
) -> None:
    """Write eval agent result to CSV if output_dir is available."""
    if not output_dir:
        return
    import csv
    from pathlib import Path

    p = Path(output_dir) / "eval_result.csv"
    file_exists = p.exists()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["purpose", "success", "result"])
            writer.writerow([purpose, str(success), result[:1000]])
    except Exception as e:
        logger.debug("_write_eval_csv: failed for '%s': %s", purpose, e)


def _append_eval_to_pipeline(
    pipeline_name: str,
    purpose: str,
    result: str,
) -> None:
    """Append eval agent result as a step to pipeline yaml.

    Read-modify-write is safe in practice: eval_agent tool calls execute
    sequentially inside ``execute_tool_calls_sequential``, so concurrent
    writes to the same pipeline yaml cannot occur.
    """
    if not pipeline_name:
        return
    import yaml
    from pathlib import Path
    from engine._harness.pipeline_tools import _resolve_pipeline_path

    tmp = None
    try:
        yaml_path = _resolve_pipeline_path(pipeline_name)
        if yaml_path is None or not yaml_path.exists():
            return
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        steps = data.get("steps", [])
        import time
        step_name = f"eval_{int(time.time())}"
        steps.append({
            "name": step_name,
            "description": f"eval_agent: {purpose[:100]}",
            "step_type": "tool",
            "tool_name": "eval_agent",
            "params": {
                "purpose": purpose,
                "result": result[:500],
            },
        })
        data["steps"] = steps
        tmp = yaml_path.with_suffix(yaml_path.suffix + ".tmp")
        try:
            tmp.write_text(
                yaml.dump(data, default_flow_style=False, allow_unicode=True),
                encoding="utf-8",
            )
            import shutil
            shutil.move(str(tmp), str(yaml_path))
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    logger.warning("_append_eval_to_pipeline: tmp cleanup failed", exc_info=True)
    except Exception as e:
        logger.debug("_append_eval_to_pipeline: failed for '%s': %s", pipeline_name, e)
        if tmp is not None and tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                logger.warning("_append_eval_to_pipeline: tmp cleanup failed on exception path", exc_info=True)


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


async def _auto_refresh_highlights(cdp_helpers: object) -> None:
    """Refresh DOM highlights periodically — background guard."""
    from engine.scratchpad import sync_element_map as scratchpad_sync_element_map
    if not hasattr(cdp_helpers, "add_dom_highlights"):
        return
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
        logger.debug("auto_refresh_highlights failed", exc_info=True)


def _apply_heavy_data_filter(
    fn_name: str,
    fn_args: dict,
    result_dict: dict,
) -> None:
    from engine.scratchpad import get as get_scratchpad
    from engine.scratchpad import store as store_scratchpad
    from engine.scratchpad import store_raw_html as scratchpad_store_raw_html
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
    """Normalize an element reference to @e_XXXXX format."""
    ref = ref.strip()
    if ref.startswith("@"):
        if ref.lower().startswith("@e") and not ref.startswith("@e_") and ref[2:].isdigit():
            return "@e_" + ref[2:]
        return ref
    if ref.startswith("e_"):
        return f"@{ref}"
    if ref.startswith("e") and ref[1:].isdigit():
        return "@e_" + ref[1:]
    return f"@e_{ref}"


def _try_scratchpad_element_lookup(fn_args: dict) -> dict | None:
    from engine.scratchpad import get as get_scratchpad
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
    from engine.scratchpad import get as get_scratchpad
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
