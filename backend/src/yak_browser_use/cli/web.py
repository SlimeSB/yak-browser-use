"""CLI entry point for `uvx yak-browser-use` — starts backend and opens browser."""

from __future__ import annotations

import webbrowser
import uvicorn

from yak_browser_use.api.server import create_app
from yak_browser_use.cli._init import init_cli


def main(host: str = "127.0.0.1", port: int = 8787) -> None:
    init_cli()
    app = create_app()
    webbrowser.open(f"http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
