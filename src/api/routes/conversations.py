"""
Conversation endpoint — the primary API surface.

POST /v1/conversations/message
  body: {message, channel, conversation_id?}
  auth: Bearer token (customer_id claim)
  → {response, conversation_id}

The EA handles its own partial failures (specialist timeout, LLM degraded)
and returns a fallback string — those are 200s. We only map to 503 when
the EA's handle_customer_interaction *raises*, which means an infrastructure
dependency is hard-down.
"""
import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, Request

from ..auth import get_current_customer
from ..errors import ServiceUnavailableError
from ..schemas import MessageRequest, MessageResponse

# Import at module level so import failures surface at startup, not per-request.
from src.agents.executive_assistant import ConversationChannel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/conversations", tags=["conversations"])

# Wire-format string → enum. Mirrors the Channel Literal in schemas.py.
_CHANNEL_MAP = {
    "phone": ConversationChannel.PHONE,
    "whatsapp": ConversationChannel.WHATSAPP,
    "email": ConversationChannel.EMAIL,
    "chat": ConversationChannel.CHAT,
}

from ..constants import EA_CALL_TIMEOUT


@router.post("/message", response_model=MessageResponse)
async def post_message(
    req: MessageRequest,
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    conversation_id = req.conversation_id or str(uuid.uuid4())
    ea_registry = request.app.state.ea_registry

    try:
        ea = await ea_registry.get(customer_id)
        response_text = await asyncio.wait_for(
            ea.handle_customer_interaction(
                message=req.message,
                channel=_CHANNEL_MAP[req.channel],
                conversation_id=conversation_id,
            ),
            timeout=EA_CALL_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error(
            "EA timed out for customer=%s conv=%s after %.0fs",
            customer_id, conversation_id, EA_CALL_TIMEOUT,
        )
        raise ServiceUnavailableError(
            detail="Assistant temporarily unavailable.",
        )
    except Exception:
        # EA blew up entirely — not a degraded specialist, an actual
        # infra failure. Log the full exception; tell the client nothing.
        logger.exception(
            "EA interaction failed for customer=%s conv=%s",
            customer_id, conversation_id,
        )
        raise ServiceUnavailableError(
            detail="Assistant temporarily unavailable.",
        )

    # Fire-and-forget: extract follow-ups and update interaction time
    proactive_store = getattr(request.app.state, "proactive_state_store", None)
    if proactive_store is not None:
        from src.proactive.inbound import process_inbound_message
        try:
            await process_inbound_message(customer_id, req.message, proactive_store)
        except Exception:
            logger.debug("Proactive inbound hook failed for customer=%s", customer_id)

    return MessageResponse(response=response_text, conversation_id=conversation_id)
