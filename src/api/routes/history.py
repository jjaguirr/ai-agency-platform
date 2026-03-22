"""
Conversation history endpoints.

GET /v1/conversations?tags=finance&tags=scheduling
  → {conversations: [{id, channel, created_at, updated_at,
                       summary, tags, quality_signals}]}

GET /v1/conversations/{conversation_id}/messages
  → {conversation_id, customer_id, messages: [{role, content, timestamp}]}

Both auth: Bearer token (customer_id claim).
Both tenant-isolated at the repository query level.

Backing store is ConversationRepository (Postgres). The EA's in-memory
history is no longer consulted on these paths — that's the whole point
of the feature: history outlives EA LRU eviction.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..auth import get_current_customer
from ..schemas import (
    ConversationHistoryResponse,
    ConversationListResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    request: Request,
    customer_id: str = Depends(get_current_customer),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    tags: list[str] | None = Query(None),
):
    repo = request.app.state.conversation_repo
    if repo is None:
        # Storage not configured (tests that don't care about this
        # route). Empty result rather than 500.
        return ConversationListResponse(conversations=[])

    # Enriched variant adds message_count + specialist_domains per row
    # via a LATERAL aggregation. Same ordering/paging contract as the
    # plain list_conversations — this is a strict superset.
    convs = await repo.list_conversations_enriched(
        customer_id=customer_id, limit=limit, offset=offset,
        tags=tags,
    )
    return ConversationListResponse(conversations=convs)


@router.get("/{conversation_id}/messages", response_model=ConversationHistoryResponse)
async def get_messages(
    conversation_id: str,
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    repo = request.app.state.conversation_repo
    if repo is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    history = await repo.get_messages(
        customer_id=customer_id, conversation_id=conversation_id)

    if history is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationHistoryResponse(
        conversation_id=conversation_id,
        customer_id=customer_id,
        messages=history,
    )
