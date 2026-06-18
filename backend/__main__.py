from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from dotenv import load_dotenv

root_env = Path(__file__).resolve().parent.parent / ".env"
local_env = Path(__file__).resolve().parent / ".env"
if root_env.exists():
    load_dotenv(dotenv_path=root_env)
if local_env.exists():
    load_dotenv(dotenv_path=local_env, override=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ybu — yak-browser-use: a clean, learnable browser automation framework"
    )
    parser.add_argument(
        "--log-level", default=None, choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default DEBUG, overridable via YBU_LOG_LEVEL env var)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── run ──
    run_p = sub.add_parser("run", help="Execute a pipeline.yaml or raw document")
    run_p.add_argument("path", help="Path to pipeline.yaml (.pipeline.yaml executes directly, other formats are auto-converted)")
    run_p.add_argument("--convert", action="store_true", help="Force conversion before execution")
    run_p.add_argument("--verbose", action="store_true", help="Emit full event stream")
    run_p.add_argument("--mode", default="auto", choices=["auto", "static", "learn", "replay"])
    run_p.add_argument("--engine", default="programmatic", choices=["programmatic", "agent"],
                       help="Execution engine: programmatic (three-tier fallback) or agent (LLM-driven)")
    run_p.add_argument(
        "-D", "--param", action="append", default=[], dest="params",
        help="Pass pipeline parameters as key=value (repeatable). e.g. -D keyword=\"pizza oven\" -D price_min=80",
    )

    # ── serve ──
    serve_p = sub.add_parser("serve", help="Start the FastAPI service (backend)")
    serve_p.add_argument("--port", type=int, default=0, help="Port number (0 = auto-select)")
    serve_p.add_argument("--host", default="127.0.0.1")

    # ── convert ──
    convert_p = sub.add_parser("convert", help="Convert a natural-language document to pipeline.yaml format")
    convert_p.add_argument("path", help="Input document path (.md / .txt)")
    convert_p.add_argument("--output", "-o", default=None, help="Output file path (default: <cwd>/<stem>.pipeline.yaml)")
    convert_p.add_argument("--name", "-n", default=None, help="Pipeline name (default: inferred from filename)")

    # ── debug ──
    debug_p = sub.add_parser("debug", help="Debugging tools")
    debug_sub = debug_p.add_subparsers(dest="debug_cmd", required=True)

    debug_sub.add_parser("chrome", help="Deep Chrome diagnostics (equivalent to chrome inspect)")
    events_p = debug_sub.add_parser("events", help="EventSink event monitoring")
    events_p.add_argument("--tail", action="store_true", help="Live tail mode")
    ckpt_p = debug_sub.add_parser("checkpoints", help="Checkpoint management")
    ckpt_p.add_argument("--last", action="store_true", help="View the latest checkpoint")
    state_p = debug_sub.add_parser("state", help="State dump")
    state_p.add_argument("path", help="Path to state.json")

    # ── chrome ──
    chrome_p = sub.add_parser("chrome", help="Chrome debugging tools")
    chrome_sub = chrome_p.add_subparsers(dest="chrome_cmd", required=True)

    chrome_sub.add_parser("status", help="Chrome status snapshot (process / ports / env vars)")
    chrome_sub.add_parser("inspect", help="Deep diagnostics (test every discovery level)")
    chrome_sub.add_parser("connect", help="Attempt to establish a WebSocket connection")
    launch_p = chrome_sub.add_parser("launch", help="Launch user Chrome (won't kill existing processes)")
    launch_p.add_argument("--profile", default=None, help="Chrome user profile directory name (e.g. Default, Profile 1)")
    chrome_sub.add_parser("restart", help="Force-kill Chrome and relaunch")
    chrome_sub.add_parser("isolated", help="Launch isolated Playwright browser")

    # ── Chrome Profile management ──
    profile_p = chrome_sub.add_parser("profile", help="Chrome user profile management")
    profile_sub = profile_p.add_subparsers(dest="profile_cmd", required=True)
    profile_sub.add_parser("list", help="List all user profiles")
    profile_use_p = profile_sub.add_parser("use", help="Select a user profile")
    profile_use_p.add_argument("profile_name")

    # ── Browser operation commands ──
    chrome_sub.add_parser("goto", help="Navigate to a URL").add_argument("url")
    chrome_sub.add_parser("click", help="Click an element").add_argument("selector")
    fill_p = chrome_sub.add_parser("fill", help="Fill a text input")
    fill_p.add_argument("selector")
    fill_p.add_argument("text")
    chrome_sub.add_parser("scroll", help="Scroll the page").add_argument("direction", choices=["down", "up"])
    chrome_sub.add_parser("back", help="Go back")
    chrome_sub.add_parser("snapshot", help="Take a screenshot + HTML snapshot").add_argument("--mode", default="full", choices=["full", "interactive", "simplified"], help="Snapshot mode (default: full)")
    chrome_sub.add_parser("source", help="Get page HTML")
    chrome_sub.add_parser("wait", help="Wait (seconds)").add_argument("seconds", type=float)
    chrome_sub.add_parser("eval", help="Execute JavaScript").add_argument("js")

    # ── Tab management ──
    tab_p = chrome_sub.add_parser("tab", help="Tab management")
    tab_sub = tab_p.add_subparsers(dest="tab_cmd", required=True)
    tab_sub.add_parser("list", help="List all tabs")
    tab_sub.add_parser("switch", help="Switch to a tab").add_argument("targetId")
    tab_sub.add_parser("close", help="Close a tab").add_argument("targetId")
    tab_sub.add_parser("new", help="Create a new tab").add_argument("url")

    # ── param (replaces auth) ──
    param_p = sub.add_parser("param", help="Persistent parameter management (replaces old credentials system)")
    param_sub = param_p.add_subparsers(dest="param_cmd", required=True)
    param_set_p = param_sub.add_parser("set", help="Set a parameter value")
    param_set_p.add_argument("key", help="Parameter key")
    param_set_p.add_argument("value", help="Parameter value")
    param_sub.add_parser("list", help="List all parameter keys")
    param_del_p = param_sub.add_parser("delete", help="Delete a parameter")
    param_del_p.add_argument("key", help="Parameter key to delete")

    # ── daemon ──
    daemon_p = sub.add_parser("daemon", help="Chrome daemon lifecycle management")
    daemon_sub = daemon_p.add_subparsers(dest="daemon_cmd", required=True)
    daemon_sub.add_parser("start", help="Start the Chrome daemon")
    daemon_sub.add_parser("stop", help="Stop the Chrome daemon")
    daemon_sub.add_parser("status", help="Show daemon status")

    # ── tool ──
    tool_p = sub.add_parser("tool", help="Tool debugging (_PH- lifecycle, prompt preview, etc.)")
    tool_sub = tool_p.add_subparsers(dest="tool_cmd", required=True)

    tool_prompt_p = tool_sub.add_parser("prompt", help="Display the LLM generation prompt for _PH- tool steps (no LLM call)")
    tool_prompt_p.add_argument("path", help="pipeline.yaml file path")
    tool_prompt_p.add_argument("--step", default=None, help="Only show a specific step (key)")

    tool_dryrun_p = tool_sub.add_parser("dry-run", help="Compile without executing, showing DAG and step info")
    tool_dryrun_p.add_argument("path", help="pipeline.yaml file path")

    tool_runph_p = tool_sub.add_parser("run-ph", help="Single-step _PH- lifecycle test")
    tool_runph_p.add_argument("path", help="pipeline.yaml file path")
    tool_runph_p.add_argument("--step", required=True, help="Step key name")
    tool_runph_p.add_argument("--llm-response", default=None, help="Path to a preset LLM response file (skips real call)")

    # ── logs ──
    logs_p = sub.add_parser("logs", help="View unified logs (backend, electron, LLM)")
    logs_p.add_argument("--follow", "-f", action="store_true", help="Tail logs live")
    logs_p.add_argument("--source", default="all", choices=["all", "backend", "electron", "llm"],
                        help="Filter by source (default: all)")
    logs_p.add_argument("--lines", "-n", type=int, default=50, help="Number of lines to show per source (default: 50)")

    # ── pipeline ──
    pipeline_p = sub.add_parser("pipeline", help="Pipeline management (compile, status, restart, etc.)")
    pipeline_sub = pipeline_p.add_subparsers(dest="pipeline_cmd", required=True)

    pipeline_compile_p = pipeline_sub.add_parser("compile", help="Compile without executing, showing DAG and step info")
    pipeline_compile_p.add_argument("path", help="pipeline.yaml file path")

    pipeline_sub.add_parser("list", help="List all pipelines")

    pipeline_status_p = pipeline_sub.add_parser("status", help="View latest pipeline run status")
    pipeline_status_p.add_argument("name", help="Pipeline name")

    pipeline_runs_p = pipeline_sub.add_parser("runs", help="List all runs for a pipeline")
    pipeline_runs_p.add_argument("name", help="Pipeline name")

    pipeline_cancel_p = pipeline_sub.add_parser("cancel", help="Cancel a running pipeline")
    pipeline_cancel_p.add_argument("name", help="Pipeline name")
    pipeline_cancel_p.add_argument("run_id", help="Run ID")

    pipeline_restart_p = pipeline_sub.add_parser("restart", help="Restart a paused or failed pipeline")
    pipeline_restart_p.add_argument("name", help="Pipeline name")
    pipeline_restart_p.add_argument("run_id", nargs="?", default=None, help="Run ID (default: auto-select latest paused/failed)")

    pipeline_review_p = pipeline_sub.add_parser("review", help="Approve or reject a suggested action")
    pipeline_review_p.add_argument("name", help="Pipeline name")
    pipeline_review_p.add_argument("id", help="Suggestion ID")
    pipeline_review_p.add_argument("action", choices=["approve", "reject"], help="Review action")
    pipeline_review_p.add_argument("--reason", "-r", default="", help="Review reason (required for reject)")

    args = parser.parse_args()

    from utils.logging import setup_logging
    setup_logging(level=args.log_level)

    if args.command == "run":
        from cli.run import _cmd_run  # noqa: E402
        params = {}
        for p in args.params:
            if "=" in p:
                k, v = p.split("=", 1)
                params[k.strip()] = v.strip()
        asyncio.run(_cmd_run(args.path, convert=args.convert, verbose=args.verbose, mode=args.mode, params=params, engine=args.engine))

    elif args.command == "chrome":
        from cli.chrome import dispatch as chrome_dispatch  # noqa: E402
        _CHROME_ARG_MAP = {
            "goto": ["url"],
            "click": ["selector"],
            "fill": ["selector", "text"],
            "scroll": ["direction"],
            "back": [],
            "snapshot": ["mode"],
            "source": [],
            "wait": ["seconds"],
            "eval": ["js"],
            "tab": ["tab_cmd", "targetId", "url"],
            "launch": ["profile"],
            "profile": ["profile_cmd", "profile_name"],
        }
        extra = {k: getattr(args, k) for k in _CHROME_ARG_MAP.get(args.chrome_cmd, []) if hasattr(args, k)}
        asyncio.run(chrome_dispatch(args.chrome_cmd, **extra))

    elif args.command == "serve":
        from cli.serve import _cmd_serve  # noqa: E402
        asyncio.run(_cmd_serve(args.host, args.port))

    elif args.command == "convert":
        from cli.convert import _cmd_convert  # noqa: E402
        asyncio.run(_cmd_convert(args.path, output=args.output, name=args.name))

    elif args.command == "debug":
        from cli.debug import _cmd_debug  # noqa: E402
        if args.debug_cmd == "chrome":
            from cli.chrome import dispatch as chrome_dispatch
            asyncio.run(chrome_dispatch("inspect"))
        elif args.debug_cmd == "events":
            asyncio.run(_cmd_debug("events", tail=args.tail))
        elif args.debug_cmd == "checkpoints":
            asyncio.run(_cmd_debug("checkpoints", last=args.last))
        elif args.debug_cmd == "state":
            asyncio.run(_cmd_debug("state", path=args.path))

    elif args.command == "param":
        from cli.param import _cmd_param_set, _cmd_param_list, _cmd_param_delete  # noqa: E402
        if args.param_cmd == "set":
            _cmd_param_set(args.key, args.value)
        elif args.param_cmd == "list":
            _cmd_param_list()
        elif args.param_cmd == "delete":
            _cmd_param_delete(args.key)

    elif args.command == "daemon":
        from cli.daemon import dispatch as daemon_dispatch  # noqa: E402
        asyncio.run(daemon_dispatch(args.daemon_cmd))

    elif args.command == "tool":
        from cli.tools import dispatch as tool_dispatch  # noqa: E402
        extra = {}
        if args.tool_cmd == "prompt":
            extra = {"step_key": args.step}
        elif args.tool_cmd == "run-ph":
            extra = {"step_key": args.step, "llm_response_path": args.llm_response}
        asyncio.run(tool_dispatch(args.tool_cmd, pipeline_path=args.path, **extra))

    elif args.command == "logs":
        from cli.logs import _cmd_logs  # noqa: E402
        asyncio.run(_cmd_logs(source=args.source, lines=args.lines, follow=args.follow))

    elif args.command == "pipeline":
        from cli.pipeline import dispatch as pipeline_dispatch  # noqa: E402
        extra = {}
        if args.pipeline_cmd == "compile":
            extra = {"path": args.path}
        elif args.pipeline_cmd in ("status", "runs"):
            extra = {"pipeline_name": args.name}
        elif args.pipeline_cmd == "cancel":
            extra = {"pipeline_name": args.name, "run_id": args.run_id}
        elif args.pipeline_cmd == "restart":
            extra = {"pipeline_name": args.name, "run_id": args.run_id}
        elif args.pipeline_cmd == "review":
            extra = {"pipeline_name": args.name, "suggestion_id": args.id, "action": args.action, "reason": args.reason}
        asyncio.run(pipeline_dispatch(args.pipeline_cmd, **extra))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
