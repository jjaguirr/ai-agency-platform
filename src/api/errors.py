"""
Structured API errors.

Every non-success response carries {type, detail} JSON. No stack traces,
no internal error messages leak to clients. Exception handlers are
registered in app.py.
"""
import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Base for all intentionally-raised API errors."""

    def __init__(self, *, status_code: int, error_type: str, detail: str):
        self.status_code = status_code
        self.error_type = error_type
        self.detail = detail
        super().__init__(detail)


class BadRequestError(APIError):
    def __init__(self, detail: str):
        super().__init__(status_code=400, error_type="bad_request", detail=detail)


class ServiceUnavailableError(APIError):
    def __init__(self, detail: str):
        super().__init__(status_code=503, error_type="service_unavailable",
                         detail=detail)


# --- Handlers -------------------------------------------------------------

async def handle_api_error(_: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"type": exc.error_type, "detail": exc.detail},
    )


async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort catch-all. Logs the full exception; client gets nothing."""
    logger.exception(
        "Unhandled exception on %s %s", request.method, request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={
            "type": "internal_error",
            "detail": "An internal error occurred.",
        },
    )
