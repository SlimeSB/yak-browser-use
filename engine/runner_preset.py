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
from pathlib import Path

from engine.events import EventSink
from engine.executor import (
    execute_browser_step,
    execute_goal_step,
    execute_tool_step,
    mask_sensitive_patterns,
    run_check,
    sanitize_result,
    write_step_json,
)
from engine.state import RunContext
from engine.step_machine import StepMachine, StepStatus
from utils.logging import get_logger
from workspace.manager import WorkspaceManager, DEFAULT_MAX_RUNS
from workspace.path_guard import PathGuard

logger = get_logger(__name__)


# ── helpers ──


def _write_execution_tree(run_dir: Path, machine: StepMachine, pipeline_name: str) -> None:
    """Write the execution tree to _execution_tree.json in the run directory."""
    tree = machine.to_execution_tree()
    tree["pipeline"] = pipeline_name
    tree_path = run_dir / "_execution_tree.json"
    with open(tree_path, "w", encoding="utf-8") as f:
        json.dump(tree, f, ensure_ascii=False, indent=2)


def _step_type(step_def: dict) -> str:
    """Infer the step type: browser / tool / goal."""
    if step_def.get("step_type"):
        return step_def["step_type"]
    if step_def.get("tool_name"):
        return "tool"
    if step_def.get("is_goal"):
        return "goal"
    return "browser"


def _safe_dirname(name: str) -> str:
    """Sanitize a step name for use as a directory name."""
    for char in '/\\:*?"<>|':
        name = name.replace(char, "_")
    return name.strip()


def _collect_input_files(input_ref, run_dir: Path) -> dict[str, str]:
    """Resolve step input references to absolute file paths."""
    from engine.executor import _resolve_input_files

    return _resolve_input_files(input_ref, run_dir)


def _resolve_step_urls(steps: list[dict], url_aliases: dict[str, str]) -> None:
    """Replace {key} URL placeholders in steps with actual URLs from aliases."""
    _alias_pattern = re.compile(r"\{([\w-]+)\}")
    for step in steps:
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


async def _execute_tool_step_with_guardian(
    step_def: dict,
    tools_dir: Path,
    step_dir: Path,
    run_dir: Path,
    ctx: RunContext,
    events: EventSink,
    pg: PathGuard,
    pipeline_path: Path | None = None,
    cdp_helpers=None,
) -> dict:
    """Execute a tool step with path validation and guardian checks.

    If the tool name starts with ``_PH-``, checks whether the file exists.
    Code generation is handled by the agent via the ph-tool-generation skill.
    """
    tool_name = step_def.get("tool_name", "")

    # _PH- tool → gate check + execute + validate + rename
    if tool_name.startswith("_PH-"):
        from engine._lifecycle.tool_runner import ToolRunner

        runner = ToolRunner(tools_dir, ctx.pipeline_name)

        if not runner.tool_exists(tool_name):
            return {
                "status": "failed",
                "error": {
                    "code": "TOOL_NOT_GENERATED",
                    "message": (
                        f"Tool '{tool_name}' has not been generated yet. "
                        f"Use the ph-tool-generation skill to generate code first."
                    ),
                },
            }

        input_files = _collect_input_files(step_def.get("input", {}), run_dir)
        for path in input_files.values():
            pg.validate_input(path)

        exec_result = await runner.load_and_call(
            tool_name,
            input_files,
            str(step_dir),
            cdp_helpers=cdp_helpers,
            func_name=runner.strip_ph_prefix(tool_name),
            **step_def.get("params", {}),
        )
        if not exec_result.get("ok"):
            return {
                "status": "failed",
                "error": {
                    "code": exec_result.get("error_code", "RUNTIME_ERROR"),
                    "message": exec_result.get("error", ""),
                },
            }

        guard_result = runner.guardian.validate_output(
            str(step_dir), step_def.get("output", [])
        )
        if not guard_result.get("ok"):
            return {
                "status": "failed",
                "error": {
                    "code": "GUARDIAN_ERROR",
                    "message": guard_result.get("detail", "Guardian validation failed"),
                },
            }

        rename_result = runner.rename_ph_file(tool_name)
        if rename_result.get("ok"):
            runner.update_pipeline_refs(
                tool_name, runner.strip_ph_prefix(tool_name), pipeline_path,
            )
            ctx.upgraded_tools.append(rename_result.get("new", ""))
            return {
                "status": "completed",
                "upgraded": True,
                "upgraded_name": rename_result.get("new"),
            }

        return {
            "status": "failed",
            "error": {
                "code": "RENAME_ERROR",
                "message": rename_result.get("error", ""),
            },
        }

    # Regular tool → direct execution
    input_files = _collect_input_files(step_def.get("input", {}), run_dir)
    for path in input_files.values():
        pg.validate_input(path)

    pg.validate_output_dir(str(step_dir))

    result = await execute_tool_step(step_def, tools_dir, step_dir, run_dir, cdp_helpers=cdp_helpers)
    return result


# ── main pipeline ──


async def run_pipeline(
    pipeline_name: str,
    steps: list[dict],
    cdp_helpers=None,
    max_runs: int = DEFAULT_MAX_RUNS,
    version: str | None = None,
    pipeline_path: Path | None = None,
    frontmatter: dict | None = None,
    resume_from_index: int = 0,
    guardian=None,
    ws_clients: list | None = None,
) -> RunContext:
    """Execute a pipeline: create workspace → run through steps → finalize.

    Args:
        pipeline_name: Name of the pipeline (used for workspace directory).
        steps: List of step definition dicts.
        cdp_helpers: CDPHelpers instance for browser operations.
        max_runs: Maximum number of runs to keep in the workspace.
        version: Optional version string override.
        pipeline_path: Optional path to pipeline.yaml for snapshot and goal agent context.
        frontmatter: Optional pipeline frontmatter dict.
        resume_from_index: Step index to resume from (0 = start).
        guardian: Optional Guardian instance for approval gating.
        ws_clients: Optional list of WebSocket client queues for event broadcast.

    Returns:
        RunContext with pipeline execution results.
    """
    wm = WorkspaceManager(pipeline_name)
    wm.ensure_workspace()

    wm.detect_crashed_runs()
    wm.cleanup_old_runs(max_runs)

    run_dir = wm.create_run()
    wm.set_status(run_dir, "running")

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
        _resolve_step_urls(steps, url_aliases)

    events.emit_run_start(pipeline_name, ctx.run_id, ver or "0")

    # ── Snapshot pipeline.yaml at start ──
    if pipeline_path and pipeline_path.exists():
        wm.versions_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = wm.versions_dir / f"snapshot_{int(time.time())}.pipeline.yaml"
        try:
            shutil.copy2(pipeline_path, snapshot_path)
        except PermissionError:
            if str(pipeline_path.resolve()) != str(snapshot_path.resolve()):
                raise
        logger.info("snapshot saved: %s", snapshot_path)
        # Also copy to workspace root
        pipe_path = wm.root / "pipeline.yaml"
        shutil.copy2(pipeline_path, pipe_path)
        logger.info("pipeline.yaml saved: %s", pipe_path)

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

            # ── Guardian approval gate ──
            review_mode = (frontmatter or {}).get("review_mode", "human")
            if guardian is not None and review_mode != "none":
                approved = guardian.approve(
                    step_name=ctx.current_step,
                    step_def=step_def,
                )
                if not approved:
                    machine.end_step(
                        node,
                        StepStatus.PENDING_REVIEW,
                        error={
                            "code": "REVIEW_INTERRUPT",
                            "message": f"Step '{ctx.current_step}' requires manual approval",
                        },
                    )
                    wm.set_status(run_dir, "paused", current_step=ctx.current_step)
                    events.emit_step_end(ctx.current_step, _step_type(step_def), "paused", 0)
                    events.emit_error(ctx.current_step, "REVIEW_INTERRUPT", "Step requires manual approval")
                    logger.info("  ⏸ %s: requires manual approval", ctx.current_step)
                    final_status = "paused"
                    _write_execution_tree(run_dir, machine, pipeline_name)
                    break

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
                step_result = await execute_browser_step(
                    step_def, cdp_helpers, step_dir, run_dir,
                )
            elif step_type == "goal":
                step_result = await execute_goal_step(
                    step_def=step_def,
                    cdp_helpers=cdp_helpers,
                    step_dir=step_dir,
                    run_dir=run_dir,
                    tools_dir=wm.tools_dir,
                    pipeline_name=pipeline_name,
                    frontmatter=frontmatter,
                    pipeline_path=pipeline_path,
                )
            else:
                step_result = await _execute_tool_step_with_guardian(
                    step_def,
                    wm.tools_dir,
                    step_dir,
                    run_dir,
                    ctx,
                    events,
                    pg,
                    pipeline_path=pipeline_path,
                    cdp_helpers=cdp_helpers,
                )

            # ── Programmatic check (non-goal steps only) ──
            check_def = step_def.get("check")
            if check_def is not None and step_type != "goal" and step_result["status"] == "completed":
                check_result = await run_check(check_def, cdp_helpers)
                if not check_result["ok"]:
                    step_result["status"] = "failed"
                    step_result["error"] = {
                        "code": "CHECK_FAILED",
                        "message": check_result.get("error", "验收未通过"),
                    }

            write_step_json(step_dir, sanitize_result(step_result))

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

                # ── Planner: recovery planning ──
                recovery_steps = None
                try:
                    from engine._lifecycle.fallback import assess_page_state
                    from engine.planner import RuntimePlanner

                    failed_op = {}
                    if compensation_data:
                        for op in reversed(compensation_data):
                            if not op.get("ok", True):
                                failed_op = op
                                break
                    if not failed_op and step_def.get("browser_ops"):
                        failed_op = (
                            step_def["browser_ops"][-1]
                            if step_def["browser_ops"]
                            else {}
                        )

                    page_state = await assess_page_state(
                        helpers=cdp_helpers,
                        pipeline_name=pipeline_name,
                        steps=machine.steps,
                        failed_step_index=node.index,
                        failed_op=failed_op,
                        error=error_msg,
                    )

                    planner = RuntimePlanner()
                    recovery_steps = await planner.replan_on_failure.replan(
                        helpers=cdp_helpers,
                        steps=machine.steps,
                        failed_step_index=node.index,
                        compensation_results=compensation_data or [],
                        page_state=page_state,
                        pipeline_name=pipeline_name,
                    )
                except Exception as e:
                    logger.warning("planner: recovery planning degraded: %s", e)

                if recovery_steps:
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
                    logger.warning(
                        "  ↻ %s: recovering with %d new steps",
                        ctx.current_step, len(recovery_steps),
                    )
                    machine.replace_remaining(recovery_steps)
                    _write_execution_tree(run_dir, machine, pipeline_name)
                    continue

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
                wm.set_status(run_dir, "failed")
                final_status = "failed"
                _write_execution_tree(run_dir, machine, pipeline_name)

                compromised = [
                    op for op in (compensation_data or []) if not op.get("reversible", True)
                ]
                if compromised:
                    node.compromised_ops = compromised

                break

        # ── Finalise run ──
        if not ctx.errors and final_status not in ("paused", "cancelled"):
            wm.set_status(run_dir, "completed")
            last_step_dir = run_dir / _safe_dirname(ctx.current_step)
            wm.fill_final(run_dir, last_step_dir)

        # ── Version snapshot at end ──
        if pipeline_path and pipeline_path.exists():
            from workspace.version_manager import VersionManager

            vm = VersionManager(wm.versions_dir, ctx.pipeline_name)
            upgraded = getattr(ctx, "upgraded_tools", [])
            learned = getattr(ctx, "learned_goals", [])
            summary_parts = []
            if upgraded:
                summary_parts.append(f"upgraded tools: {', '.join(upgraded)}")
            if learned:
                summary_parts.append(f"learned goals: {', '.join(learned)}")
            if not summary_parts:
                summary_parts.append(f"pipeline {final_status}")
            vm.create_version(
                trigger_run_id=ctx.run_id,
                summary="; ".join(summary_parts),
                pipe_pipeline=pipeline_path,
                tools_dir=wm.tools_dir,
                upgraded_tools=upgraded,
                learned_goals=learned,
            )
            logger.info("version snapshot created for run %s", ctx.run_id)

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
