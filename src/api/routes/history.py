"""
Conversation history endpoints.

GET /v1/conversations/{conversation_id}/messages
  auth: Bearer token (customer_id claim)
  -> {conversation_id, customer_id, messages: [{role, content, timestamp}]}

GET /v1/conversations
  auth: Bearer token (customer_id claim)
  query: limit (default 20, max 100), offset (default 0)
  -> {customer_id, conversations: [{conversation_id, channel, created_at, updated_at}], limit, offset}

Tenant-isolated: wrong customer -> 404 (not 403).
Empty conversation -> 200 with empty list.
Unknown conversation -> 404.

Reads from ConversationRepository (Postgres) when available.
Falls back to EA in-memory history if repo is not configured.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..auth import get_current_customer
from ..schemas import ConversationHistoryResponse, ConversationListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


@router.get("/{conversation_id}/messages", response_model=ConversationHistoryResponse)
async def get_messages(
    conversation_id: str,
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    repo = getattr(request.app.state, "conversation_repo", None)

    if repo is not None:
        history = await repo.get_messages(conversation_id, customer_id)
    else:
        # Fallback to EA in-memory history
        ea_registry = request.app.state.ea_registry
        ea = await ea_registry.get(customer_id)
        history = ea.get_conversation_history(conversation_id)

    if history is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationHistoryResponse(
        conversation_id=conversation_id,
        customer_id=customer_id,
        messages=history,
    )


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    request: Request,
    customer_id: str = Depends(get_current_customer),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    repo = getattr(request.app.state, "conversation_repo", None)

    if repo is not None:
        conversations = await repo.list_conversations(customer_id, limit=limit, offset=offset)
    else:
        conversations = []

    return ConversationListResponse(
        customer_id=customer_id,
        conversations=conversations,
        limit=limit,
        offset=offset,
    )
