"""
Exception handlers.

Every error response is structured JSON. HTTPException keeps its status code
and intentional detail message. Anything else — unhandled exceptions from
handlers, dependencies, middleware — becomes a generic 500 with the real
cause logged server-side and nothing leaked to the client.

Pydantic validation errors (422) are left to FastAPI's default handler:
those messages are field-level, safe to surface, and more useful to clients
than a generic envelope.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    # Starlette's HTTPException is the base — fastapi.HTTPException inherits
    # from it. Registering the base catches both our own raises AND the
    # router's 404/405 for missing routes.
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)


async def _http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    # The detail is intentional — whoever raised the exception chose it.
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
        headers=getattr(exc, "headers", None),
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log the full traceback; the client gets nothing identifying.
    logger.exception(
        "Unhandled exception on %s %s", request.method, request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )
