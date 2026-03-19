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
from ..errors import NotFoundError, ServiceUnavailableError
from ..schemas import (
    ConversationHistoryResponse,
    HistoryMessage,
    MessageRequest,
    MessageResponse,
)

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

# EA has an internal specialist_timeout (15s) but the overall LangGraph
# run has no bound. A hung LLM endpoint or half-open mem0 connection would
# otherwise hold this request — and its worker — indefinitely.
_EA_CALL_TIMEOUT = 60.0


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
            timeout=_EA_CALL_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error(
            "EA timed out for customer=%s conv=%s after %.0fs",
            customer_id, conversation_id, _EA_CALL_TIMEOUT,
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

    return MessageResponse(response=response_text, conversation_id=conversation_id)


@router.get("/{conversation_id}/messages", response_model=ConversationHistoryResponse)
async def get_history(
    conversation_id: str,
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    """
    Return the message history for a conversation.

    Tenant-isolated by construction: we look up the EA keyed by the
    JWT's customer_id, then ask *that* EA for the conversation. A token
    for customer A can never reach customer B's EA. Wrong-tenant and
    doesn't-exist are indistinguishable — both 404.

    Uses peek(), not get(): a read must not trigger an EA build.
    """
    ea_registry = request.app.state.ea_registry
    ea = ea_registry.peek(customer_id)
    if ea is None:
        raise NotFoundError(detail="Conversation not found.")

    history = ea.get_conversation_history(conversation_id)
    if history is None:
        raise NotFoundError(detail="Conversation not found.")

    # Channel from the first message (all messages in a conversation
    # share a channel). Empty history → no channel yet.
    channel = history[0].get("channel") if history else None

    return ConversationHistoryResponse(
        conversation_id=conversation_id,
        customer_id=customer_id,
        channel=channel,
        messages=[
            HistoryMessage(
                role=m["role"], content=m["content"], timestamp=m["timestamp"]
            )
            for m in history
        ],
    )
