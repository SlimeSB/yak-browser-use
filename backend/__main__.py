from __future__ import annotations

import argparse
import asyncio
import sys

from cli._init import init_cli


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ybu — yak-browser-use: a clean, learnable browser automation framework"
    )
    parser.add_argument(
        "--log-level", default=None, choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default DEBUG, overridable via YBU_LOG_LEVEL env var)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── web ──
    web_p = sub.add_parser("web", help="Start the web UI (backend + static frontend)")
    web_p.add_argument("--port", type=int, default=8787, help="Port number (default: 8787)")
    web_p.add_argument("--host", default="127.0.0.1")

    # ── serve ──
    serve_p = sub.add_parser("serve", help="Start the FastAPI service (backend)")
    serve_p.add_argument("--port", type=int, default=0, help="Port number (0 = auto-select)")
    serve_p.add_argument("--host", default="127.0.0.1")

    # ── run ──
    run_p = sub.add_parser("run", help="Execute a pipeline.yaml and print results")
    run_p.add_argument("path", help="Path to .pipeline.yaml file")
    run_p.add_argument(
        "-D", "--param", action="append", default=[], dest="params",
        help="Pipeline parameters as key=value (repeatable)",
    )

    # ── logs ──
    logs_p = sub.add_parser("logs", help="View unified logs (backend, electron, LLM)")
    logs_p.add_argument("--follow", "-f", action="store_true", help="Tail logs live")
    logs_p.add_argument("--source", default="all", choices=["all", "backend", "electron", "llm"],
                        help="Filter by source (default: all)")
    logs_p.add_argument("--lines", "-n", type=int, default=50, help="Number of lines to show per source (default: 50)")
    logs_p.add_argument("--run", default=None, help="Show logs for a specific run_id")

    args = parser.parse_args()

    init_cli(level=args.log_level)

    if args.command == "serve":
        from cli.serve import _cmd_serve
        asyncio.run(_cmd_serve(args.host, args.port))

    elif args.command == "run":
        from cli.run import _cmd_run
        params = {}
        for p in args.params:
            if "=" in p:
                k, v = p.split("=", 1)
                params[k.strip()] = v.strip()
        asyncio.run(_cmd_run(args.path, params=params))

    elif args.command == "logs":
        from cli.logs import _cmd_logs
        asyncio.run(_cmd_logs(source=args.source, lines=args.lines, follow=args.follow, run=args.run))

    elif args.command == "web":
        from cli.web import main as web_main
        web_main(host=args.host, port=args.port)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
