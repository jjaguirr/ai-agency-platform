"""
WhatsApp webhook, mounted into the main API.

We don't reimplement webhook handling. The provider abstraction in
src/communication/whatsapp/ already does signature validation, message
parsing, and status-callback routing. We call into it via
webhook_server._handle_incoming, wiring the EA registry as the handler.

Route path matches the standalone webhook server exactly:
  POST /webhook/whatsapp/{customer_id}

Parity with /v1/conversations/message:
  - customer_id validated against _CUSTOMER_ID_PATTERN (422 on mismatch)
  - EA call bounded by _EA_CALL_TIMEOUT
Timeout returns 200 (not 503) — Twilio retries on non-2xx, creating a
storm of duplicates hitting the same hung backend.
"""
import asyncio
import logging

from fastapi import APIRouter, HTTPException, Path, Request, Response

from src.communication.webhook_server import _handle_incoming
from src.communication.whatsapp import IncomingMessage, StatusUpdate
from src.agents.executive_assistant import ConversationChannel

from ..schemas import _CUSTOMER_ID_PATTERN
from .conversations import _EA_CALL_TIMEOUT

logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhooks"])


@router.post("/webhook/whatsapp/{customer_id}")
async def whatsapp_webhook(
    request: Request,
    customer_id: str = Path(pattern=_CUSTOMER_ID_PATTERN),
):
    manager = request.app.state.whatsapp_manager
    ea_registry = request.app.state.ea_registry

    channel = await manager.get_channel(customer_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Unknown customer")

    body = await request.body()
    headers = dict(request.headers)
    url = channel.webhook_url or str(request.url)

    # Signature check before touching the body. Same ordering as the
    # standalone server — don't parse untrusted payloads.
    if not channel.provider.validate_signature(url=url, body=body, headers=headers):
        logger.warning("Invalid webhook signature for customer=%s", customer_id)
        raise HTTPException(status_code=403, detail="Invalid signature")

    events = channel.provider.parse_webhook(
        body, request.headers.get("content-type", ""),
    )

    # EA handler with the same timeout as /v1/conversations/message.
    # Timeout is CAUGHT inside the handler and re-raised — _handle_incoming
    # already wraps exceptions and sends a fallback reply, so the customer
    # gets SOMETHING and we return 200 to Twilio.
    async def ea_handler(*, message: str, conversation_id: str) -> str:
        ea = await ea_registry.get(customer_id)
        try:
            return await asyncio.wait_for(
                ea.handle_customer_interaction(
                    message=message,
                    channel=ConversationChannel.WHATSAPP,
                    conversation_id=conversation_id,
                ),
                timeout=_EA_CALL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error(
                "Webhook EA timed out for customer=%s conv=%s after %.0fs",
                customer_id, conversation_id, _EA_CALL_TIMEOUT,
            )
            # Re-raise so _handle_incoming's exception wrapper fires
            # and sends the fallback reply. We do NOT propagate a 503.
            raise

    for event in events:
        if isinstance(event, IncomingMessage):
            await _handle_incoming(channel, event, ea_handler)
        elif isinstance(event, StatusUpdate):
            await channel.handle_status_callback(event)

    return Response(status_code=200)
