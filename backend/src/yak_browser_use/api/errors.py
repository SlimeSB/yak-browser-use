"""Custom API error classes and FastAPI error handler registration."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)


class APIError(Exception):
    """Client error — returns 400 (or another expected status code)."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code


class ServerError(APIError):
    """Server error — returns 500."""

    def __init__(self, message: str):
        super().__init__(message, status_code=500)


def register_error_handlers(app: FastAPI) -> None:
    """Register global exception handlers on a FastAPI application."""

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"error": "Validation error", "details": exc.errors()},
        )

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=404,
            content={"error": "Not found"},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )
