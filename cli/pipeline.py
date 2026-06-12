"""Pipeline management CLI commands — superset of the frontend API."""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)


# ── compile (dry-run) ──

async def _cmd_compile(path: str) -> None:
    """Compile pipeline.yaml without executing — display DAG and step info.

    Args:
        path: Path to pipeline.yaml file.
    """
    from cli.tools import _cmd_tool_dry_run
    await _cmd_tool_dry_run(path)


# ── list pipelines ──

def _cmd_list() -> None:
    """List all pipelines in the workspace."""
    from workspace.manager import WorkspaceManager

    # Use root workspace dir (same as WorkspaceManager uses internally)
    base_dir = Path.home() / ".lbu" / "workspaces"

    if not base_dir.exists():
        print("(no workspace)")
        return

    pipelines = sorted(
        [d.name for d in base_dir.iterdir() if d.is_dir() and not d.name.startswith(".")],
    )
    if not pipelines:
        print("(no pipelines)")
        return

    print(f"\n  Pipelines ({len(pipelines)}):")
    for name in pipelines:
        wm = WorkspaceManager(name)
        runs_dir = [d for d in wm.runs_dir.iterdir()
                    if d.is_dir() and _looks_like_run_id(d.name)] if wm.runs_dir.exists() else []
        latest_ver = ""
        if wm.versions_dir.exists():
            lat_path = wm.versions_dir / "LATEST"
            if lat_path.exists():
                latest_ver = f" (v{lat_path.read_text(encoding='utf-8').strip()})"
        print(f"  - {name}{latest_ver}  [{len(runs_dir)} runs]")
    print()


# ── pipeline status ──

def _cmd_status(pipeline_name: str) -> None:
    """View the latest run status for a pipeline.

    Args:
        pipeline_name: Name of the pipeline.
    """
    from workspace.manager import WorkspaceManager

    wm = WorkspaceManager(pipeline_name)
    runs = wm.list_runs()
    if not runs:
        print(f"\n  Pipeline '{pipeline_name}': no runs\n")
        return

    latest = runs[0]
    print(f"\n  Pipeline: {pipeline_name}")
    print(f"  Latest Run ID:    {latest.get('run_id', '?')}")
    print(f"  Status:           {latest.get('status', '?')}")
    em_dash = "\u2014"
    print(f"  Current Step:     {latest.get('current_step', em_dash)}")
    print(f"  Version:          {latest.get('version', em_dash)}")
    print(f"  Created At:       {latest.get('created_at', em_dash)}")
    print(f"  Completed At:     {latest.get('completed_at', em_dash)}\n")


# ── list runs ──

def _cmd_runs(pipeline_name: str) -> None:
    """List all runs for a pipeline.

    Args:
        pipeline_name: Name of the pipeline.
    """
    from workspace.manager import WorkspaceManager

    wm = WorkspaceManager(pipeline_name)
    runs = wm.list_runs()
    if not runs:
        print(f"\n  Pipeline '{pipeline_name}': no runs\n")
        return

    print(f"\n  Runs for '{pipeline_name}':")
    for r in runs:
        status_icon = {"completed": "\u2713", "failed": "\u2717", "running": "\u25cf",
                        "paused": "\u23f8", "cancelled": "\u2715", "crashed": "\u2620"}.get(
                            r.get("status", ""), "?")
        em_dash = "\u2014"
        print(f"  {status_icon} {r.get('run_id', '?')}  {r.get('status', '?'):10s}  "
              f"step: {r.get('current_step', em_dash) or em_dash:20s}  "
              f"created: {r.get('created_at', em_dash)}")
    print()


# ── cancel pipeline ──

async def _cmd_cancel(pipeline_name: str, run_id: str) -> None:
    """Cancel a running or paused pipeline.

    Args:
        pipeline_name: Name of the pipeline.
        run_id: Run ID to cancel.
    """
    from workspace.manager import WorkspaceManager

    wm = WorkspaceManager(pipeline_name)
    run_dir = wm.root / "runs" / run_id
    if not run_dir.exists():
        logger.error("Run not found: %s/%s", pipeline_name, run_id)
        sys.exit(1)

    status = wm.get_status(run_dir)
    if status not in ("running", "paused"):
        logger.error("Pipeline status is '%s' — cannot cancel", status)
        sys.exit(1)

    wm.set_status(run_dir, "cancelled")
    print(f"  \u2713 Pipeline '{pipeline_name}' run {run_id} cancelled")


# ── restart pipeline ──

async def _cmd_restart(pipeline_name: str, run_id: str | None = None) -> None:
    """Restart a paused or failed pipeline.

    Args:
        pipeline_name: Name of the pipeline.
        run_id: Optional run ID (default: auto-select latest paused/failed).
    """
    from api.service import PipelineService
    from api.state import engine_state
    from engine.runner import run_pipeline
    from workspace.manager import WorkspaceManager
    from workspace.version_manager import VersionManager

    wm = WorkspaceManager(pipeline_name)

    # If no run_id specified, find the latest paused/failed run
    if run_id is None:
        runs = wm.list_runs()
        for r in runs:
            if r.get("status") in ("paused", "failed"):
                run_id = r.get("run_id")
                break
        if run_id is None:
            logger.error("No paused/failed runs found")
            sys.exit(1)

    run_dir = wm.root / "runs" / run_id
    if not run_dir.exists():
        logger.error("Run not found: %s/%s", pipeline_name, run_id)
        sys.exit(1)

    status = wm.get_status(run_dir)
    if status not in ("paused", "failed"):
        logger.error("Pipeline status is '%s' — need paused or failed", status)
        sys.exit(1)

    if engine_state.browser is None:
        logger.error("Chrome not connected. Please run: lbu daemon start")
        sys.exit(1)

    resume_from_index = 0
    exec_tree_path = run_dir / "_execution_tree.json"
    if exec_tree_path.exists():
        tree = json.loads(exec_tree_path.read_text(encoding="utf-8"))
        nodes = tree.get("nodes", [])
        success_nodes = [n for n in nodes if n.get("status") == "success"]
        if success_nodes:
            last_success = max(success_nodes, key=lambda n: n.get("index", 0))
            resume_from_index = last_success.get("index", 0) + 1

    vm = VersionManager(wm.versions_dir, pipeline_name)
    latest_ver = vm.get_latest()
    if not latest_ver:
        logger.error("No pipeline version found")
        sys.exit(1)

    loaded = vm.load_version(latest_ver)
    if not loaded:
        logger.error("Version data not found")
        sys.exit(1)

    pipeline_path, _ = loaded
    pipeline_text = pipeline_path.read_text(encoding="utf-8")
    parsed, steps = PipelineService.prepare_steps(pipeline_text, pipeline_path=pipeline_path)

    from engine._lifecycle.guardian import create_guardian_from_frontmatter
    guardian = create_guardian_from_frontmatter(parsed.frontmatter)

    print(f"\n  \u25b6 Restarting Pipeline '{pipeline_name}' run {run_id}")
    print(f"  resume_from_index: {resume_from_index}\n")

    import time
    ts = int(time.time())
    snapshot_path = wm.versions_dir / f"snapshot_{ts}.pipeline.yaml"
    snapshot_path.write_text(pipeline_text, encoding="utf-8")

    ctx = await run_pipeline(
        pipeline_name=pipeline_name,
        steps=steps,
        cdp_helpers=engine_state.browser,
        pipeline_path=snapshot_path,
        frontmatter=parsed.frontmatter,
        resume_from_index=resume_from_index,
        guardian=guardian,
    )

    final_status = "completed" if not ctx.errors else "failed"
    print(f"\n  Pipeline status: {final_status}")
    if ctx.errors:
        for err in ctx.errors:
            print(f"  \u2717 {err}")


# ── review suggestions ──

async def _cmd_review(pipeline_name: str, suggestion_id: str, action: str, reason: str = "") -> None:
    """Approve or reject a suggested action.

    Args:
        pipeline_name: Name of the pipeline.
        suggestion_id: Suggestion ID.
        action: 'approve' or 'reject'.
        reason: Review reason (required for reject).
    """
    from workspace.manager import WorkspaceManager
    wm = WorkspaceManager(pipeline_name)
    sug_path = wm.root / "suggestions" / "suggestions.json"
    if not sug_path.exists():
        old_path = Path("logs") / "learn" / pipeline_name / "suggestions.json"
        if old_path.exists():
            sug_path = old_path
        else:
            logger.error("Suggestions file not found")
            sys.exit(1)

    file_size = sug_path.stat().st_size
    if file_size > 10 * 1024 * 1024:
        logger.warning("Suggestions file is large (%d MB), loading may be slow", file_size // (1024 * 1024))
    data = json.loads(sug_path.read_text(encoding="utf-8"))
    target = next((item for item in data if item.get("id") == suggestion_id), None)
    if not target:
        logger.error("Suggestion '%s' not found", suggestion_id)
        sys.exit(1)

    if action == "approve":
        target["status"] = "approved"
        target["reason"] = reason or "approved via CLI"
        _apply_approval(pipeline_name, target, suggestion_id)
        print(f"  \u2713 Approved suggestion {suggestion_id}")
    elif action == "reject":
        if not reason:
            logger.error("Rejecting requires a --reason argument")
            sys.exit(1)
        target["status"] = "rejected"
        target["reason"] = reason
        extra_ops = target.get("extra_ops", [])
        for op in extra_ops:
            op["reason"] = reason
        from compiler.diff import add_to_rejected
        add_to_rejected(pipeline_name, extra_ops, "human")
        print(f"  \u2713 Rejected suggestion {suggestion_id}")
    else:
        logger.error("Unknown action: %s (available: approve, reject)", action)
        sys.exit(1)

    sug_dir = wm.root / "suggestions"
    sug_dir.mkdir(parents=True, exist_ok=True)
    new_path = sug_dir / "suggestions.json"
    new_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _apply_approval(pipeline_name: str, target: dict, suggestion_id: str) -> None:
    """Apply an approved suggestion to create a new version.

    Args:
        pipeline_name: Pipeline name.
        target: Approved suggestion dict.
        suggestion_id: Suggestion ID.
    """
    extra_ops = target.get("extra_ops", [])
    if not extra_ops:
        return

    from workspace.version_manager import VersionManager
    from workspace.manager import WorkspaceManager
    from compiler.parser import parse_pipeline
    from compiler.diff import merge_extra_ops
    from compiler.generator import write_pipeline_learned

    wm = WorkspaceManager(pipeline_name)
    vm = VersionManager(wm.versions_dir, pipeline_name)
    latest = vm.get_latest()
    if not latest:
        return

    loaded = vm.load_version(latest)
    if not loaded:
        return

    pipeline_path, _ = loaded
    source_text = pipeline_path.read_text(encoding="utf-8")
    parsed = parse_pipeline(source_text)

    step_name = pipeline_name
    if parsed.steps:
        step_name = parsed.steps[-1].name

    original_ops = parsed.steps[-1].browser_ops if parsed.steps else []
    all_ops = merge_extra_ops(original_ops + extra_ops, extra_ops, original_ops)
    new_text = write_pipeline_learned(source_text, step_name, all_ops, pipeline_name)

    temp_pipeline = wm.root / f"_review_{suggestion_id}.pipeline.yaml"
    temp_pipeline.write_text(new_text, encoding="utf-8")
    try:
        vm.create_version(
            trigger_run_id=f"review_{suggestion_id}",
            summary=f"approved via CLI: {target.get('summary', suggestion_id)}",
            pipe_pipeline=temp_pipeline,
            tools_dir=wm.tools_dir,
        )
    finally:
        if temp_pipeline.exists():
            temp_pipeline.unlink()


# ── dispatch ──

_HANDLER_ARGS = {
    "compile": {"path": str},
    "list": {},
    "status": {"pipeline_name": str},
    "runs": {"pipeline_name": str},
    "cancel": {"pipeline_name": str, "run_id": str},
    "restart": {"pipeline_name": str, "run_id": (str, type(None))},
    "review": {"pipeline_name": str, "suggestion_id": str, "action": str, "reason": str},
}


async def dispatch(cmd: str, **kwargs) -> None:
    """Dispatch a pipeline subcommand.

    Args:
        cmd: Subcommand name (compile, list, status, runs, cancel, restart, review).
        **kwargs: Arguments specific to the subcommand.
    """
    handlers = {
        "compile": _cmd_compile,
        "list": _cmd_list,
        "status": _cmd_status,
        "runs": _cmd_runs,
        "cancel": _cmd_cancel,
        "restart": _cmd_restart,
        "review": _cmd_review,
    }
    handler = handlers.get(cmd)
    if handler is None:
        logger.error("Unknown pipeline subcommand: %s (available: %s)", cmd, ", ".join(handlers))
        sys.exit(1)

    names = list(_HANDLER_ARGS.get(cmd, {}))
    bound = {k: kwargs[k] for k in names if k in kwargs}
    result = handler(**bound)
    if inspect.iscoroutine(result):
        await result


def _looks_like_run_id(name: str) -> bool:
    import re
    return bool(re.match(r"^\d{8}_\d{6}(_\d+)?$", name))
