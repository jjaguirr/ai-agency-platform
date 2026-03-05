"""
FastAPI webhook server for inbound WhatsApp messages + status callbacks.

Exposes an app factory (create_app) — not a module-level app — so tests
and deployments can inject a configured WhatsAppManager.

Routes:
    GET  /health
    POST /webhook/whatsapp/{customer_id}         — inbound messages
    POST /webhook/whatsapp/{customer_id}/status  — delivery status callbacks

Env vars:
    WEBHOOK_PUBLIC_BASE_URL
        The public URL base (scheme + host) that the provider uses to reach us.
        Needed for signature validation when running behind a reverse proxy:
        request.url will be the internal address, but the provider signed the
        public one. Example: https://api.example.com

    WHATSAPP_WEBHOOK_SKIP_SIGNATURE
        Set to "1" / "true" to skip signature validation entirely. Dev-only.

    WEBHOOK_HOST, WEBHOOK_PORT
        For `python -m src.communication.webhook_server` direct execution.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Response, status

from .whatsapp_manager import WhatsAppManager

logger = logging.getLogger(__name__)

_SIG_HEADERS = ("X-Twilio-Signature", "X-Hub-Signature-256")


def create_app(manager: WhatsAppManager) -> FastAPI:
    """Build the FastAPI app, injecting a configured WhatsAppManager."""
    app = FastAPI(
        title="WhatsApp Webhook Server",
        description="Inbound WhatsApp + status callbacks for ai-agency-platform",
        version="2.0.0",
    )

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "service": "whatsapp-webhook-server",
            "active_channels": len(manager._channels),
        }

    @app.post("/webhook/whatsapp/{customer_id}")
    async def inbound(customer_id: str, request: Request):
        form_data = dict(await request.form())

        # Signature check FIRST — before any per-customer channel construction.
        # get_validator is the lightweight path: builds/caches a provider but
        # does NOT call handler_factory or build a channel.
        validate = _get_validator_or_404(manager, customer_id)
        _verify_signature_or_403(request, validate, form_data)

        channel = await manager.get_channel(customer_id)
        try:
            await channel.process_inbound(form_data)
        except Exception:
            logger.exception(
                "Error processing inbound for customer=%s", customer_id
            )
            # Still return 200 so provider doesn't retry-storm; error already logged.
            return Response(content="error", status_code=200, media_type="text/plain")

        return Response(content="ok", status_code=200, media_type="text/plain")

    @app.post("/webhook/whatsapp/{customer_id}/status")
    async def status_callback(customer_id: str, request: Request):
        form_data = dict(await request.form())

        validate = _get_validator_or_404(manager, customer_id)
        _verify_signature_or_403(request, validate, form_data)

        channel = await manager.get_channel(customer_id)
        try:
            await channel.handle_status_callback(form_data)
        except Exception:
            logger.exception(
                "Error processing status callback for customer=%s", customer_id
            )
            return Response(content="error", status_code=200, media_type="text/plain")

        return Response(content="ok", status_code=200, media_type="text/plain")

    return app


# ----------------------------------------------------------------------
# Signature verification
# ----------------------------------------------------------------------

def _skip_signature() -> bool:
    val = os.getenv("WHATSAPP_WEBHOOK_SKIP_SIGNATURE", "").lower()
    return val in ("1", "true", "yes")


def _public_url_for(request: Request) -> str:
    """Reconstruct the URL that the external provider used to reach us.

    Behind a reverse proxy, request.url is the internal address; the provider
    signed the public one. WEBHOOK_PUBLIC_BASE_URL lets us override scheme+host.
    """
    base = os.getenv("WEBHOOK_PUBLIC_BASE_URL")
    if base:
        base = base.rstrip("/")
        path = request.url.path
        query = request.url.query
        if query:
            return f"{base}{path}?{query}"
        return f"{base}{path}"
    return str(request.url)


def _extract_signature(request: Request) -> Optional[str]:
    for header in _SIG_HEADERS:
        val = request.headers.get(header)
        if val:
            return val
    return None


def _get_validator_or_404(manager: WhatsAppManager, customer_id: str):
    """Resolve the signature validator for a customer, or 404 on ANY failure.

    Broad catch is deliberate: the pre-auth boundary must be opaque. Whether
    the customer doesn't exist (RuntimeError), is misconfigured (TypeError/
    ValueError from provider constructor), or config_loader itself blew up
    (KeyError, DB error, whatever) — the caller always sees 404. This closes
    the enumeration oracle where 404-vs-500 would leak which tenants are real.

    The operator still sees the full exception in logs.
    """
    try:
        return manager.get_validator(customer_id)
    except HTTPException:
        raise  # don't swallow our own 4xx/5xx if ever raised upstream
    except Exception:
        logger.exception(
            "Validator resolution failed: customer=%s", customer_id
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")


def _verify_signature_or_403(request: Request, validate, form_data: dict) -> None:
    if _skip_signature():
        return

    signature = _extract_signature(request)
    public_url = _public_url_for(request)
    if not validate(public_url, form_data, signature):
        logger.warning(
            "Rejected webhook (bad signature): path=%s", request.url.path
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid signature")


# ----------------------------------------------------------------------
# Direct execution (dev convenience)
# ----------------------------------------------------------------------

def _build_default_manager() -> WhatsAppManager:
    """Manager for `python -m src.communication.webhook_server`.

    Wires the real ExecutiveAssistant as the message handler. Import is
    deferred so test imports of this module don't drag in the full EA chain.
    """
    from ..agents.executive_assistant import ConversationChannel, ExecutiveAssistant

    _ea_cache: dict = {}

    def handler_factory(customer_id: str):
        if customer_id not in _ea_cache:
            _ea_cache[customer_id] = ExecutiveAssistant(customer_id=customer_id)
        ea = _ea_cache[customer_id]

        async def handler(msg):
            return await ea.handle_customer_interaction(
                msg.content,
                ConversationChannel.WHATSAPP,
                conversation_id=msg.conversation_id,
            )

        return handler

    return WhatsAppManager(handler_factory=handler_factory)


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    host = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    port = int(os.getenv("WEBHOOK_PORT", "8000"))

    manager = _build_default_manager()
    app = create_app(manager)

    logger.info("Starting WhatsApp webhook server on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port)
