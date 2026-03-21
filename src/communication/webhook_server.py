"""
FastAPI webhook server for WhatsApp — provider-agnostic.

Each customer's WhatsApp number is configured (in the provider console) to
POST webhooks to /webhook/whatsapp/{customer_id}. The server:
  1. Resolves the customer's channel via WhatsAppManager
  2. Validates the webhook signature via the provider (403 on failure)
  3. Parses events via the provider (IncomingMessage | StatusUpdate)
  4. Routes IncomingMessage → EA handler → sends reply
  5. Routes StatusUpdate → store update
  6. Returns 200 to acknowledge receipt
"""
import logging
from dataclasses import asdict
from typing import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, Response

from .whatsapp import IncomingMessage, StatusUpdate
from .whatsapp_manager import WhatsAppManager
from src.safety.splitter import split_for_whatsapp

logger = logging.getLogger(__name__)

# EA handler signature: (message, conversation_id) -> response text
# The real wiring uses ExecutiveAssistant.handle_customer_interaction;
# tests inject a mock.
EAHandler = Callable[..., Awaitable[str]]

_FALLBACK_REPLY = "I'm having trouble processing that. Give me a moment."


def build_app(*, manager: WhatsAppManager, ea_handler: EAHandler) -> FastAPI:
    """
    Build the webhook FastAPI app with injected dependencies.

    `manager`: resolves customer_id → WhatsAppChannel
    `ea_handler`: async callable(message: str, conversation_id: str) -> str
    """
    app = FastAPI(title="WhatsApp Webhook Server", version="2.0.0")

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "service": "whatsapp-webhook-server",
        }

    @app.post("/webhook/whatsapp/{customer_id}")
    async def handle_webhook(customer_id: str, request: Request):
        channel = await manager.get_channel(customer_id)
        if channel is None:
            raise HTTPException(status_code=404, detail="Unknown customer")

        body = await request.body()
        headers = dict(request.headers)
        # Validate against the configured public webhook URL. Behind a proxy
        # or load balancer, request.url reconstructs the INTERNAL address,
        # which won't match what the provider signed. Fall back to request
        # URL only if no canonical URL is configured (bare dev setup).
        url = channel.webhook_url or str(request.url)

        # Signature validation MUST happen before parsing the body.
        if not channel.provider.validate_signature(url=url, body=body, headers=headers):
            logger.warning("Invalid webhook signature for customer=%s", customer_id)
            raise HTTPException(status_code=403, detail="Invalid signature")

        events = channel.provider.parse_webhook(
            body, request.headers.get("content-type", "")
        )

        for event in events:
            if isinstance(event, IncomingMessage):
                await _handle_incoming(channel, event, ea_handler)
            elif isinstance(event, StatusUpdate):
                await channel.handle_status_callback(event)

        return Response(status_code=200)

    return app


async def _handle_incoming(channel, event: IncomingMessage,
                           ea_handler: EAHandler) -> None:
    """Process one incoming message: EA → reply. Errors get a fallback reply."""
    base_msg = await channel.handle_incoming_message(asdict(event))
    await channel.store.record_inbound(
        customer_id=channel.customer_id,
        conversation_id=base_msg.conversation_id,
        msg=event,
    )
    try:
        response_text = await ea_handler(
            message=base_msg.content,
            conversation_id=base_msg.conversation_id,
        )
    except Exception:
        logger.exception(
            "EA handler failed for customer=%s msg=%s",
            channel.customer_id, event.provider_message_id,
        )
        response_text = _FALLBACK_REPLY

    # Twilio truncates past ~1600 chars. split_for_whatsapp breaks at
    # sentence boundaries; short replies come back as [text] so the
    # common case is still one send. Each chunk is sent independently —
    # one network blip drops that chunk but the rest go out, which beats
    # the alternative (customer gets nothing).
    for chunk in split_for_whatsapp(response_text):
        if not chunk:
            continue
        try:
            await channel.send_message(base_msg.from_number, chunk)
        except Exception:
            logger.exception(
                "Failed to send reply chunk for customer=%s to=%s",
                channel.customer_id, base_msg.from_number,
            )


# --- Production entrypoint ------------------------------------------------

def create_default_app() -> FastAPI:
    """
    Build app with real dependencies from environment.
    Used by uvicorn: `uvicorn src.communication.webhook_server:app`
    """
    from .whatsapp import WhatsAppConfig
    from ..agents.executive_assistant import ConversationChannel, ExecutiveAssistant

    mgr = WhatsAppManager()
    # Register default customer from env (for single-tenant dev setup)
    default_cfg = WhatsAppConfig.from_env()
    if default_cfg.from_number and default_cfg.credentials.get("account_sid"):
        mgr.register_customer("default", default_cfg)

    # One EA instance per process; multi-tenant EA routing is manager's concern later
    ea_instances: dict[str, ExecutiveAssistant] = {}

    async def ea_handler(message: str, conversation_id: str) -> str:
        if "default" not in ea_instances:
            ea_instances["default"] = ExecutiveAssistant(customer_id="default")
        ea = ea_instances["default"]
        return await ea.handle_customer_interaction(
            message=message,
            channel=ConversationChannel.WHATSAPP,
            conversation_id=conversation_id,
        )

    return build_app(manager=mgr, ea_handler=ea_handler)
