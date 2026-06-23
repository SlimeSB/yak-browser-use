"""FastAPI application factory for Yak Browser-Use."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup setup and shutdown cleanup."""
    from yak_browser_use.tools.registry import build_registry

    logger.info("Yak Browser-Use API starting …")
    build_registry()
    logger.info("Tool registry built")
    yield
    from yak_browser_use.api.state import engine_state

    await engine_state.cleanup()
    logger.info("Yak Browser-Use API stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from yak_browser_use.api.routes import register_all_routes
    from yak_browser_use.api.errors import register_error_handlers

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

    # ── Static files (Web mode) ────────────────────────────────────
    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    if os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
