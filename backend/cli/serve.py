from __future__ import annotations

import socket
import sys

from utils.logging import get_logger

logger = get_logger(__name__)


def _find_free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _cmd_serve(host: str = "127.0.0.1", port: int = 0) -> None:
    """Start the FastAPI service for the backend.

    Args:
        host: Host to bind to.
        port: Port to listen on (0 = auto-select).
    """
    if port == 0:
        port = _find_free_port()

    try:
        from api.server import create_app
        import uvicorn

        app = create_app()
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)

        logger.info("ybu FastAPI running on http://%s:%d", host, port)
        logger.info("API docs: http://%s:%d/docs", host, port)
        await server.serve()
    except ImportError as e:
        logger.error("Missing dependencies: %s", e)
        logger.error("Please install: pip install fastapi uvicorn websockets")
        sys.exit(1)
    except Exception as e:
        logger.exception("Failed to start server: %s", e)
        sys.exit(1)
