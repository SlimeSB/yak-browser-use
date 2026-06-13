"""FastAPI application factory for Yak Browser-Use."""

from __future__ import annotations

from fastapi import FastAPI
from utils.logging import get_logger

logger = get_logger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from api.routes import register_all_routes
    from api.errors import register_error_handlers
    from api.state import engine_state

    app = FastAPI(
        title="Yak Browser-Use API",
        version="0.1.0",
    )

    # ── CORS ────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Lifecycle events ────────────────────────────────────────────

    @app.on_event("startup")
    async def startup() -> None:
        logger.info("Yak Browser-Use API starting …")

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await engine_state.cleanup()
        logger.info("Yak Browser-Use API stopped")

    # ── Routes & error handlers ────────────────────────────────────
    register_all_routes(app)
    register_error_handlers(app)

    return app
