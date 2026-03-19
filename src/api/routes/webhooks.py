"""
WhatsApp webhook, mounted into the main API.

We don't reimplement webhook handling. The provider abstraction in
src/communication/whatsapp/ already does signature validation, message
parsing, and status-callback routing. We call into it via
webhook_server._handle_incoming, wiring the EA registry as the handler.

Route path matches the standalone webhook server exactly:
  POST /webhook/whatsapp/{customer_id}
"""
import asyncio
import logging

from fastapi import APIRouter, HTTPException, Path, Request, Response

from src.communication.webhook_server import _handle_incoming
from src.communication.whatsapp import IncomingMessage, StatusUpdate
from src.agents.executive_assistant import ConversationChannel

from ..constants import EA_CALL_TIMEOUT
from ..schemas import _CUSTOMER_ID_PATTERN

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

    # Build an EA handler bound to this customer's EA instance.
    # Timeout prevents a hung EA from blocking Twilio's retry window —
    # non-2xx causes duplicate message storms.
    async def ea_handler(*, message: str, conversation_id: str) -> str:
        ea = await ea_registry.get(customer_id)
        try:
            return await asyncio.wait_for(
                ea.handle_customer_interaction(
                    message=message,
                    channel=ConversationChannel.WHATSAPP,
                    conversation_id=conversation_id,
                ),
                timeout=EA_CALL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error(
                "EA timed out for webhook customer=%s conv=%s after %.0fs",
                customer_id, conversation_id, EA_CALL_TIMEOUT,
            )
            return ""

    for event in events:
        if isinstance(event, IncomingMessage):
            await _handle_incoming(channel, event, ea_handler)
            # Fire-and-forget: extract follow-ups and update interaction time
            proactive_store = getattr(request.app.state, "proactive_state_store", None)
            if proactive_store is not None:
                from src.proactive.inbound import process_inbound_message
                try:
                    await process_inbound_message(
                        customer_id, event.body, proactive_store,
                    )
                except Exception:
                    logger.debug("Proactive inbound hook failed for customer=%s", customer_id)
        elif isinstance(event, StatusUpdate):
            await channel.handle_status_callback(event)

    return Response(status_code=200)
