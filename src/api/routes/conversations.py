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

Persistence is a side effect: after a successful EA call, the user
message and assistant reply are written to ConversationRepository. The
EA stays unaware — it still keeps its in-memory history for LLM context;
we just also durably store the exchange. If Postgres is briefly
unavailable the user still gets their reply (storage is not on the
critical path for a live conversation).
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

    # --- Output sanitization ------------------------------------------
    output_pipeline = getattr(request.app.state, "output_pipeline", None)
    if output_pipeline is not None:
        sanitize_result = output_pipeline.sanitize(response_text, customer_id=customer_id)
        response_text = sanitize_result.text
        if sanitize_result.redactions:
            audit_logger = getattr(request.app.state, "audit_logger", None)
            if audit_logger is not None:
                from src.safety.audit import AuditEvent, AuditEventType
                try:
                    await audit_logger.log(AuditEvent(
                        event_type=AuditEventType.PII_REDACTION,
                        customer_id=customer_id,
                        details={"redaction_count": len(sanitize_result.redactions)},
                    ))
                except Exception:
                    logger.debug("Failed to log PII redaction audit event")

    # --- Persistence side effect -------------------------------------
    # Write-after: only persist once we have a reply to persist. A
    # failed EA call doesn't leave a half-recorded exchange in the DB.
    # A failed Postgres write doesn't hide the reply from the user —
    # they already have it; history just won't show this turn. Logged
    # at WARNING because the API is still serving traffic.
    repo = request.app.state.conversation_repo
    if repo is not None:
        try:
            await repo.create_conversation(
                customer_id=customer_id,
                conversation_id=conversation_id,
                channel=req.channel,
            )
            await repo.append_message(
                customer_id=customer_id,
                conversation_id=conversation_id,
                role="user",
                content=req.message,
            )
            await repo.append_message(
                customer_id=customer_id,
                conversation_id=conversation_id,
                role="assistant",
                content=response_text,
            )
        except Exception:
            logger.warning(
                "Persistence failed for customer=%s conv=%s — "
                "reply delivered but not stored",
                customer_id, conversation_id, exc_info=True,
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
