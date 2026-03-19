"""
Request correlation: ASGI middleware + log-record factory.

Every request gets a correlation ID (client-provided X-Request-ID or a
generated UUID4). The ID is stored in a ContextVar so downstream code can
read it without explicit threading. A custom LogRecord factory injects it
into every LogRecord at creation time (works for all loggers, not just root).
"""
import contextvars
import uuid
from typing import Optional

import logging


correlation_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)

_REQUEST_ID_HEADER = b"x-request-id"


def install_correlation_logging() -> None:
    """Replace the global LogRecord factory to inject correlation_id.

    Unlike a Filter on the root logger (which only runs for records
    logged directly by the root logger, not propagated ones), the
    record factory runs at record *creation* time for every logger.

    Idempotent — safe to call from multiple create_app() invocations.
    """
    current = logging.getLogRecordFactory()
    if getattr(current, "_correlation_aware", False):
        return

    def factory(*args, **kwargs):
        record = current(*args, **kwargs)
        record.correlation_id = correlation_id.get() or "-"
        return record

    factory._correlation_aware = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(factory)


class CorrelationMiddleware:
    """Pure ASGI middleware — no BaseHTTPMiddleware overhead.

    Sets the ContextVar on the way in, injects the response header on
    the way out. Handles both normal responses and unhandled exceptions
    (error handlers fire inside the app; we wrap the header around
    whatever comes back).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract client-provided ID or generate one
        request_id = None
        for header_name, header_value in scope.get("headers", []):
            if header_name == _REQUEST_ID_HEADER:
                request_id = header_value.decode("latin-1")
                break
        if not request_id:
            request_id = str(uuid.uuid4())

        token = correlation_id.set(request_id)

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            correlation_id.reset(token)
