"""
Conversation endpoint — route a customer message through the EA.

The EA is async, per-customer, and never raises. This handler:
  1. Resolves customer_id from the bearer token
  2. Fetches the customer's EA from the pool (creates on first use)
  3. Awaits handle_customer_interaction
  4. Returns whatever the EA said, 200, even if the EA degraded internally
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from src.agents.executive_assistant import ConversationChannel

from ..auth import require_auth
from ..dependencies import EAPool, get_ea_pool
from ..schemas import MessageRequest, MessageResponse

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


@router.post("/message", response_model=MessageResponse)
async def send_message(
    req: MessageRequest,
    customer_id: str = Depends(require_auth),
    pool: EAPool = Depends(get_ea_pool),
) -> MessageResponse:
    ea = await pool.get(customer_id)

    # Map the validated string to the EA's enum. The Literal type in the
    # schema already guarantees this lookup succeeds.
    channel = ConversationChannel(req.channel)

    response_text = await ea.handle_customer_interaction(
        message=req.message,
        channel=channel,
        conversation_id=req.conversation_id,
    )

    return MessageResponse(
        response=response_text,
        customer_id=customer_id,
        conversation_id=req.conversation_id,
    )
