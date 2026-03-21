"""ASGI input safety middleware.

Intercepts POST requests to conversation/webhook endpoints, runs the
input pipeline, and short-circuits with a structured error if rejected.

Pure ASGI — follows CorrelationMiddleware pattern in src/api/middleware.py.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .audit import AuditEvent, AuditEventType, AuditLogger
from .input_pipeline import InputPipeline
from .rate_limiter import _extract_customer_id

logger = logging.getLogger(__name__)

# Paths where input checking applies
_CHECKED_PREFIXES = ("/v1/conversations/", "/webhook/whatsapp/")


class SafetyMiddleware:
    """ASGI middleware that runs inbound messages through the input pipeline.

    Intercepts POST requests to conversation and webhook endpoints, buffers
    the body, extracts the message text, and runs ``InputPipeline.check()``.
    Rejected messages get a 422 JSON response without ever reaching the route
    handler. Allowed messages are replayed downstream via a wrapped ``receive``
    callable.

    Body text extraction tries three JSON keys to cover all entry points:
    ``message`` (API conversations), ``body``/``Body`` (Twilio/WhatsApp webhooks).
    """

    def __init__(self, app: Any, *, input_pipeline: InputPipeline, audit_logger: AuditLogger):
        self.app = app
        self._pipeline = input_pipeline
        self._audit = audit_logger

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()

        # Only check POST to conversation/webhook paths
        if method != "POST" or not any(path.startswith(p) for p in _CHECKED_PREFIXES):
            await self.app(scope, receive, send)
            return

        # Buffer the request body
        body_chunks: list[bytes] = []
        body_complete = False

        async def buffering_receive():
            nonlocal body_complete
            message = await receive()
            if message["type"] == "http.request":
                body_chunks.append(message.get("body", b""))
                body_complete = not message.get("more_body", False)
            return message

        # We need the full body to extract the message text. Read it all.
        while not body_complete:
            await buffering_receive()

        raw_body = b"".join(body_chunks)

        # Try to extract the message text from the JSON body
        message_text = None
        try:
            parsed = json.loads(raw_body)
            if isinstance(parsed, dict):
                message_text = parsed.get("message") or parsed.get("body") or parsed.get("Body")
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        if message_text and isinstance(message_text, str):
            check = self._pipeline.check(message_text)

            if not check.allowed:
                # Log audit event
                customer_id = _extract_customer_id(scope.get("headers", []))
                if customer_id:
                    event_type = AuditEventType.INJECTION_DETECTED if check.rejection_code == "high_injection_risk" else AuditEventType.INPUT_REJECTED
                    try:
                        await self._audit.log(AuditEvent(
                            event_type=event_type,
                            customer_id=customer_id,
                            details={
                                "rejection_code": check.rejection_code,
                                "message_length": len(message_text),
                            },
                        ))
                    except Exception:
                        logger.debug("Failed to log audit event for input rejection")

                # Return structured error
                await self._send_rejection(send, check.rejection_reason or "Input rejected.")
                return

            # Log medium-risk detections at WARNING (still allowed through)
            if check.prompt_guard_result and check.prompt_guard_result.injection_risk >= 0.3:
                logger.warning(
                    "Medium injection risk detected (score=%.2f, patterns=%s)",
                    check.prompt_guard_result.injection_risk,
                    check.prompt_guard_result.injection_patterns,
                )
                customer_id = _extract_customer_id(scope.get("headers", []))
                if customer_id:
                    try:
                        await self._audit.log(AuditEvent(
                            event_type=AuditEventType.INJECTION_DETECTED,
                            customer_id=customer_id,
                            details={
                                "risk": check.prompt_guard_result.injection_risk,
                                "patterns": check.prompt_guard_result.injection_patterns,
                            },
                        ))
                    except Exception:
                        pass

        # Replay buffered body to downstream
        body_sent = False

        async def replay_receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {
                    "type": "http.request",
                    "body": raw_body,
                    "more_body": False,
                }
            # After replaying, pass through to original receive for disconnect etc.
            return await receive()

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _send_rejection(send: Any, detail: str) -> None:
        """Write a 422 JSON rejection directly to the ASGI ``send`` callable.

        The detail message is the customer-facing rejection reason from
        ``InputCheckResult.rejection_reason`` — deliberately vague for
        injection blocks so attackers get no signal.
        """
        body = json.dumps({"type": "input_rejected", "detail": detail}).encode()
        await send({
            "type": "http.response.start",
            "status": 422,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })
