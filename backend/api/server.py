"""FastAPI application factory for Yak Browser-Use."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from utils.logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup setup and shutdown cleanup."""
    from tools.registry import build_registry

    logger.info("Yak Browser-Use API starting …")
    build_registry()
    logger.info("Tool registry built")
    yield
    from api.state import engine_state

    await engine_state.cleanup()
    logger.info("Yak Browser-Use API stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from api.routes import register_all_routes
    from api.errors import register_error_handlers

    app = FastAPI(
        title="Yak Browser-Use API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── CORS ────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes & error handlers ────────────────────────────────────
    register_all_routes(app)
    register_error_handlers(app)

    return app
