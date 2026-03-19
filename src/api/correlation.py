"""
Request correlation ID — middleware, contextvar, logging filter.

Pure-ASGI middleware (not BaseHTTPMiddleware) so the response-start
hook fires even when an exception handler replaces the response. The
contextvar makes the ID available to every logger without threading it
through function signatures.

Lifecycle:
  1. Request arrives. Middleware reads X-Request-ID or generates UUID4.
  2. Contextvar set for the duration of the ASGI call.
  3. CorrelationIdFilter injects the contextvar into every LogRecord.
  4. Response start: header appended.
  5. Contextvar reset.

Outside a request the contextvar holds "-" — safe to log from anywhere.
"""
import logging
import uuid
from contextvars import ContextVar
from typing import Optional

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")
_HEADER_NAME = b"x-request-id"


def get_correlation_id() -> str:
    """Current correlation ID, or '-' outside a request."""
    return _correlation_id.get()


class CorrelationIdFilter(logging.Filter):
    """Attach the current correlation ID to every LogRecord.

    Note: logger-level filters don't apply to propagated records — if
    you attach this to the root logger, records from child loggers will
    bypass it. Attach to a *handler*, or use install_correlation_log_factory()
    for global coverage.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = _correlation_id.get()
        return True


def install_correlation_log_factory() -> None:
    """
    Wrap the global LogRecord factory so every record created — from any
    logger, via any path — carries correlation_id at creation time.

    Unlike a logger-level filter, this covers propagated records too.
    Idempotent: re-installing is a no-op.
    """
    current = logging.getLogRecordFactory()
    if getattr(current, "_correlation_wrapped", False):
        return

    def factory(*args, **kwargs):
        record = current(*args, **kwargs)
        record.correlation_id = _correlation_id.get()
        return record

    factory._correlation_wrapped = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(factory)


class CorrelationIdMiddleware:
    """
    Pure ASGI middleware. Sets the contextvar before dispatch, injects
    X-Request-ID on every response including error-handler responses.

    Starlette's BaseHTTPMiddleware sits *inside* the exception-handler
    wrapper — an exception handler replacing the response would bypass
    its dispatch hook. Raw ASGI middleware wraps the whole app, so the
    send-hook fires regardless of who produced the response.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        cid: Optional[str] = None
        for name, value in scope.get("headers", []):
            if name.lower() == _HEADER_NAME:
                cid = value.decode("latin-1")
                break
        if not cid:
            cid = str(uuid.uuid4())

        token = _correlation_id.set(cid)
        cid_bytes = cid.encode("latin-1")

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((_HEADER_NAME, cid_bytes))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            _correlation_id.reset(token)
