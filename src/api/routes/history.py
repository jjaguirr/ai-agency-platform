"""
Conversation history endpoint.

GET /v1/conversations/{conversation_id}/messages
  auth: Bearer token (customer_id claim)
  → {conversation_id, customer_id, messages: [{role, content, timestamp}]}

Tenant-isolated: wrong customer → 404 (not 403).
Empty conversation → 200 with empty list.
Unknown conversation → 404.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth import get_current_customer
from ..schemas import ConversationHistoryResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


@router.get("/{conversation_id}/messages", response_model=ConversationHistoryResponse)
async def get_messages(
    conversation_id: str,
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
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
