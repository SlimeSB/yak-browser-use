"""Preset replay orchestrator — reuses existing pipeline logic.

Creates a workspace, runs steps through StepMachine, dispatches to
executors, handles retries and recovery planning, and finalises
the run with version snapshots.

This is the preset replay mode runner. For chat mode, see runner.py.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import time
import traceback
from copy import deepcopy
from pathlib import Path

from yak_browser_use.engine import truncate_step_result as _truncate_result
from yak_browser_use.engine.events import EventSink
from yak_browser_use.engine.executor import (
    execute_browser_step,
    execute_tool_step,
    mask_sensitive_patterns,
    run_check,
    sanitize_result,
    write_step_json,
)
from yak_browser_use.engine.state import RunContext
from yak_browser_use.engine.step_machine import StepMachine, StepStatus
from yak_browser_use.utils.logging import get_logger
from yak_browser_use.workspace.manager import WorkspaceManager, DEFAULT_MAX_RUNS
from yak_browser_use.workspace.path_guard import PathGuard

logger = get_logger(__name__)


# ── helpers ──


def _write_execution_tree(run_dir: Path, machine: StepMachine, pipeline_name: str) -> None:
    """Write the execution tree to _execution_tree.json in the run directory."""
    tree = machine.to_execution_tree()
    tree["pipeline"] = pipeline_name
    tree_path = run_dir / "_execution_tree.json"
    with open(tree_path, "w", encoding="utf-8") as f:
        json.dump(tree, f, ensure_ascii=False, indent=2)


from yak_browser_use.compiler.step_type import infer_step_type as _step_type


def _safe_dirname(name: str) -> str:
    """Sanitize a step name for use as a directory name."""
    for char in '/\\:*?"<>|':
        name = name.replace(char, "_")
    return name.strip()


def _collect_input_files(input_ref, run_dir: Path) -> dict[str, str]:
    """Resolve step input references to absolute file paths."""
    from yak_browser_use.engine.executor import _resolve_input_files

    return _resolve_input_files(input_ref, run_dir)


def _resolve_step_urls(steps: list[dict], url_aliases: dict[str, str]) -> list[dict]:
    """Replace {key} URL placeholders in steps with actual URLs from aliases.
    
    Returns a new list of step dicts without mutating the caller's list.
    """
    _alias_pattern = re.compile(r"\{([\w-]+)\}")
    result = deepcopy(steps)
    for step in result:
        if step.get("goal_description"):
            step["goal_description"] = _alias_pattern.sub(
                lambda m: url_aliases.get(m.group(1), m.group(0)),
                step["goal_description"],
            )
        for op in step.get("browser_ops", []):
            if op.get("type") == "goto" and op.get("value"):
                op["value"] = _alias_pattern.sub(
                    lambda m: url_aliases.get(m.group(1), m.group(0)),
                    op["value"],
                )
    return result


def _setup_run_logger(run_dir: Path) -> logging.Handler | None:
    """Add a file handler for the current run log file.

    Returns the handler so the caller can clean it up when done.
    """
    run_log = run_dir / "_pipeline.log"
    try:
        handler = logging.FileHandler(str(run_log), encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] [%(levelname)-7s] [%(name)s] %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logging.getLogger().addHandler(handler)
        logger.info("run log: %s", run_log)
        return handler
    except (OSError, PermissionError) as e:
        logger.warning("could not create run log file %s: %s", run_log, e)
    return None


async def _execute_tool_step(
    step_def: dict,
    tools_dir: Path,
    step_dir: Path,
    run_dir: Path,
    ctx: RunContext,
    events: EventSink,
    pg: PathGuard,
    cdp_helpers=None,
    shared_store: dict | None = None,
) -> dict:
    """Execute a tool step with path validation and guardian checks."""
    input_files = _collect_input_files(step_def.get("input", {}), run_dir)
    for path in input_files.values():
        pg.validate_input(path)

    pg.validate_output_dir(str(step_dir))

    result = await execute_tool_step(step_def, tools_dir, step_dir, run_dir, cdp_helpers=cdp_helpers, shared_store=shared_store)
    return result


# ── main pipeline ──


async def run_pipeline(
    pipeline_name: str,
    steps: list[dict],
    cdp_helpers=None,
    max_runs: int = DEFAULT_MAX_RUNS,
    version: str | None = None,
    frontmatter: dict | None = None,
    resume_from_index: int = 0,
    ws_clients: list | None = None,
) -> RunContext:
    """Execute a pipeline: create workspace → run through steps → finalize.

    Preset mode runner. Executes steps programmatically through StepMachine:
    browser and tool steps dispatch to executors; checks run programmatic
    verification. Failed steps retry if configured, then fail terminally.

    Args:
        pipeline_name: Name of the pipeline (used for workspace directory).
        steps: List of step definition dicts.
        cdp_helpers: CDPHelpers instance for browser operations.
        max_runs: Maximum number of runs to keep in the workspace.
        version: Optional version string override.
        frontmatter: Optional pipeline frontmatter dict.
        resume_from_index: Step index to resume from (0 = start).
        ws_clients: Optional list of WebSocket client queues for event broadcast.

    Returns:
        RunContext with pipeline execution results.
    """
    wm = WorkspaceManager(pipeline_name)
    wm.ensure_workspace()

    wm.detect_crashed_runs()
    wm.cleanup_old_runs(max_runs)

    run_dir = wm.create_run("preset")
    wm.set_status(run_dir, "running")

    # Bind browser download path to this run
    if cdp_helpers is not None:
        bridge = getattr(cdp_helpers, "bridge", None)
        if bridge is not None:
            await bridge.set_download_dir(pipeline_name, run_dir.name)

    pg = PathGuard(wm.root, run_dir)
    events = EventSink(run_dir, ws_clients=ws_clients or [])

    run_log_handler: logging.Handler | None = _setup_run_logger(run_dir)

    ver = version or wm.get_latest_version()
    ctx = RunContext(
        pipeline_name=pipeline_name,
        run_id=run_dir.name,
        run_dir=run_dir,
        version=ver,
    )

    # ── URL alias resolution ──
    url_aliases = (frontmatter or {}).get("url_aliases", {})
    if url_aliases:
        steps = _resolve_step_urls(steps, url_aliases)

    events.emit_run_start(pipeline_name, ctx.run_id, ver or "0")

    total_start = time.time()
    logger.info(
        "pipeline [%s] run %s starting: %d steps",
        pipeline_name, ctx.run_id, len(steps),
    )

    if not steps:
        logger.warning("pipeline [%s]: empty steps list, nothing to execute", pipeline_name)
        wm.set_status(run_dir, "completed")
        events.emit_run_end("completed", 0)
        return ctx

    machine = StepMachine(steps, resume_from_index=resume_from_index)
    final_status = "completed"

    shared_store: dict = {}

    constants = (frontmatter or {}).get("constants", {})
    if constants:
        shared_store.update(constants)
        logger.debug("pipeline constants seeded: %s", list(constants.keys()))

    if resume_from_index > 0:
        # Rebuild shared_store from completed step.json snapshots so that
        # template references (${step_name.data.field}) in subsequent steps
        # resolve correctly after resume.
        for i in range(resume_from_index):
            step_def = steps[i]
            step_name = step_def.get("name", f"step_{i}")
            step_dir = run_dir / _safe_dirname(step_name)
            step_json = step_dir / "step.json"
            if step_json.exists():
                try:
                    data = json.loads(step_json.read_text(encoding="utf-8"))
                    shared_store[step_name] = {
                        "ok": data.get("status") == "completed",
                        "data": data,
                    }
                except (json.JSONDecodeError, OSError):
                    pass

    try:
        while not machine.is_done:
            if wm.get_status(run_dir) == "cancelled":
                machine.cancel()
            if machine.check_cancelled():
                logger.info("pipeline [%s] cancelled by external signal", pipeline_name)
                final_status = "cancelled"
                break

            node = machine.begin_step()
            step_def = machine.steps[node.index]

            ctx.step_index = node.index
            ctx.current_step = step_def.get("name", f"step_{node.index}")

            # ── Step directory ──
            step_key = _safe_dirname(ctx.current_step)
            step_dir = run_dir / step_key

            if step_dir.exists():
                try:
                    shutil.rmtree(step_dir)
                except PermissionError as e:
                    logger.warning("Could not clean step directory %s: %s", step_dir, e)
            step_dir.mkdir(parents=True, exist_ok=True)

            step_type = _step_type(step_def)
            events.emit_step_start(ctx.current_step, step_type)

            logger.info(
                "  [%d/%d] %s (%s)",
                node.index + 1, len(machine.steps), ctx.current_step, step_type,
            )

            # ── Dispatch to executor ──
            if step_type == "browser":
                bridge = getattr(cdp_helpers, "bridge", None) if cdp_helpers else None
                if bridge is None:
                    step_result = {
                        "status": "failed",
                        "error": {"code": "NO_BROWSER", "message": "浏览器不可用 — CDP 连接未建立"},
                    }
                else:
                    step_result = await execute_browser_step(
                        step_def, bridge, step_dir, run_dir,
                        shared_store=shared_store,
                    )
            else:
                step_result = await _execute_tool_step(
                    step_def,
                    wm.tools_dir,
                    step_dir,
                    run_dir,
                    ctx,
                    events,
                    pg,
                    cdp_helpers=cdp_helpers,
                    shared_store=shared_store,
                )

            # ── Programmatic check (non-goal steps only) ──
            check_def = step_def.get("check")
            if check_def is not None and step_result["status"] == "completed":
                bridge = getattr(cdp_helpers, "bridge", None) if cdp_helpers else None
                if bridge is None:
                    step_result["status"] = "failed"
                    step_result["error"] = {
                        "code": "CHECK_FAILED",
                        "message": "浏览器不可用，无法执行验收检查",
                    }
                else:
                    check_result = await run_check(check_def, bridge)
                    if not check_result["ok"]:
                        step_result["status"] = "failed"
                        step_result["error"] = {
                            "code": "CHECK_FAILED",
                            "message": check_result.get("error", "验收未通过"),
                        }

            write_step_json(step_dir, sanitize_result(step_result))

            shared_store[ctx.current_step] = {
                "ok": step_result["status"] == "completed",
                "data": step_result,
            }

            # ── Success path ──
            if step_result["status"] == "completed":
                machine.end_step(node, StepStatus.SUCCESS)
                events.emit_step_end(
                    ctx.current_step,
                    step_type,
                    "completed",
                    step_result.get("duration_ms", 0),
                    sanitize_result(step_result.get("input_files")),
                    sanitize_result(step_result.get("output_files")),
                )
                logger.info("  ✓ %s", ctx.current_step)
                machine.advance()

                _write_execution_tree(run_dir, machine, pipeline_name)

            # ── Failure path ──
            else:
                err = step_result.get("error", {})
                error_code = (
                    err.get("code", "RUNTIME_ERROR") if isinstance(err, dict) else "RUNTIME_ERROR"
                )
                error_msg = (
                    err.get("message", str(err)) if isinstance(err, dict) else str(err)
                )

                # Retryable?
                if machine.needs_retry(step_def, error_code):
                    machine.end_step(
                        node,
                        StepStatus.FAILED,
                        error={"code": error_code, "message": error_msg},
                    )
                    events.emit_step_end(
                        ctx.current_step, step_type, "failed",
                        step_result.get("duration_ms", 0),
                    )
                    events.emit_error(
                        ctx.current_step, error_code,
                        mask_sensitive_patterns(error_msg),
                    )
                    _write_execution_tree(run_dir, machine, pipeline_name)
                    retry_attempt = machine._retry_count.get(node.index, 1)
                    delay_sec = machine.get_retry_delay(retry_attempt) / 1000
                    logger.info(
                        "  ... retrying in %.1fs (attempt %d)", delay_sec, retry_attempt,
                    )
                    await asyncio.sleep(delay_sec)
                    continue

                compensation_data = step_result.get("compensation_history")

                # ── Terminal failure ──
                if compensation_data:
                    ctx.compensation_history.append(
                        {
                            "step_index": node.index,
                            "step_name": ctx.current_step,
                            "ops": compensation_data,
                        }
                    )

                ctx.errors.append(
                    {"step": ctx.current_step, "code": error_code, "message": error_msg}
                )
                machine.end_step(
                    node,
                    StepStatus.FAILED,
                    error={"code": error_code, "message": error_msg},
                )
                events.emit_step_end(
                    ctx.current_step, step_type, "failed",
                    step_result.get("duration_ms", 0),
                )
                events.emit_error(
                    ctx.current_step, error_code,
                    mask_sensitive_patterns(error_msg),
                )
                logger.error("  ✗ %s: %s", ctx.current_step, error_msg)

                # Collect failure context for recovery
                step_result_truncated = _truncate_result(step_result, max_chars=10000)
                tree = machine.to_execution_tree()
                tree["pipeline"] = pipeline_name
                completed_steps = [
                    {"index": n.index, "name": machine.steps[n.index].get("name", f"step_{n.index}"), "status": n.status.value}
                    for n in machine.nodes if n.status == StepStatus.SUCCESS
                ]
                ctx.failure_context = {
                    "pipeline_name": pipeline_name,
                    "step_index": node.index,
                    "step_name": ctx.current_step,
                    "step_def": step_def,
                    "error_code": error_code,
                    "error_message": error_msg,
                    "step_result": step_result_truncated,
                    "execution_tree": tree,
                    "completed_steps": completed_steps,
                }
                final_status = "needs_recovery"
                _write_execution_tree(run_dir, machine, pipeline_name)
                # Do NOT set status to "failed" — keep "running" for recovery

                compromised = [
                    op for op in (compensation_data or []) if not op.get("reversible", True)
                ]
                if compromised:
                    node.compromised_ops = compromised

                break

        # ── Finalise run ──
        if not ctx.errors and final_status not in ("paused", "cancelled", "needs_recovery"):
            wm.set_status(run_dir, "completed")
            last_step_dir = run_dir / _safe_dirname(ctx.current_step)
            wm.fill_final(run_dir, last_step_dir)

        total_ms = int((time.time() - total_start) * 1000)
        events.emit_run_end(final_status, total_ms)

        logger.info(
            "pipeline [%s] run %s: %s (%dms)",
            pipeline_name, ctx.run_id, final_status, total_ms,
        )

    except Exception as e:
        wm.set_status(run_dir, "crashed")
        _write_execution_tree(run_dir, machine, pipeline_name)
        events.emit_error(
            "_engine_",
            "RUNTIME_ERROR",
            mask_sensitive_patterns(str(e)),
            traceback.format_exc(),
        )
        logger.error("pipeline [%s] crashed: %s", pipeline_name, e)
        ctx.errors.append({"step": "_engine_", "code": "RUNTIME_ERROR", "message": str(e)})
    finally:
        events.close()
        if run_log_handler is not None:
            logging.getLogger().removeHandler(run_log_handler)
            run_log_handler.close()

    return ctx
