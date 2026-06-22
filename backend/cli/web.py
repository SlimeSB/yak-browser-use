"""CLI entry point for `uvx yak-browser-use` — starts backend and opens browser."""

from __future__ import annotations

import webbrowser
import uvicorn

from api.server import create_app


def main(host: str = "127.0.0.1", port: int = 8787) -> None:
    """Start the FastAPI server and open the browser."""
    app = create_app()
    webbrowser.open(f"http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
