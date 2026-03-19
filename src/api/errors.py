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


class NotFoundError(APIError):
    def __init__(self, detail: str):
        super().__init__(status_code=404, error_type="not_found", detail=detail)


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


async def handle_validation_error(_: Request, exc) -> JSONResponse:
    """
    Normalize Pydantic validation failures to our {type, detail} shape.

    FastAPI's default 422 body is a list of dicts with keys
    {type, loc, msg, input, ctx}. Problems with that:
      - Shape differs from every other error we return
      - `msg` embeds the regex pattern ("String should match '^...$'")
      - `ctx` contains the raw pattern again
      - `input` echoes the rejected value — for an injection attempt,
        that means the attack payload appears in our "blocked" response

    We keep the field path (useful to the client) and a terse reason
    derived from Pydantic's `type` code (safe — no patterns, no input).
    Everything else is dropped.

    `exc` is a fastapi.exceptions.RequestValidationError. We take it
    untyped to avoid importing FastAPI exception classes at module
    scope (keeps this module standalone-testable).
    """
    parts: list[str] = []
    for err in exc.errors():
        # loc is e.g. ("body", "customer_id") or ("body", "nested", "field")
        # Drop the "body"/"query"/"path" prefix — the client knows which
        # part of their request they sent.
        loc = err.get("loc", ())
        field = ".".join(str(p) for p in loc if p not in ("body", "query", "path"))
        field = field or "request"

        # Pydantic's `type` is machine-readable and safe: "missing",
        # "string_pattern_mismatch", "literal_error", "int_parsing",
        # etc. Map a few common ones to human phrasing; fall back to
        # the raw code (still safe — no pattern/input in it).
        code = err.get("type", "invalid")
        reason = {
            "missing": "required",
            "string_pattern_mismatch": "invalid format",
            "literal_error": "not an allowed value",
            "string_too_short": "too short",
            "string_too_long": "too long",
        }.get(code, code)

        parts.append(f"{field}: {reason}")

    return JSONResponse(
        status_code=422,
        content={
            "type": "validation_error",
            "detail": "; ".join(parts) if parts else "Request validation failed.",
        },
    )
