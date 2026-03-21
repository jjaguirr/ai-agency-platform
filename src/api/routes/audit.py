"""
GET /v1/audit — customer's own safety audit trail.

Same auth dependency as conversations: a customer's token shows that
customer's events, nothing more. Tenant isolation is the Redis key
prefix inside AuditLogger; we just pass the JWT's customer_id through.

pipeline=None (pre-safety tests, or a deployment that skips the safety
layer) returns an empty list rather than 500 — same degradation pattern
as history.py uses for conversation_repo=None.
"""
import logging

from fastapi import APIRouter, Depends, Query, Request

from ..auth import get_current_customer
from ..schemas import AuditEventResponse, AuditListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/audit", tags=["audit"])


@router.get("", response_model=AuditListResponse)
async def list_audit_events(
    request: Request,
    customer_id: str = Depends(get_current_customer),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    pipeline = getattr(request.app.state, "safety_pipeline", None)
    if pipeline is None or pipeline.audit is None:
        return AuditListResponse(events=[])

    events = await pipeline.audit.list_events(
        customer_id, limit=limit, offset=offset,
    )
    # AuditEvent.to_dict() already produces the wire shape (event_type
    # as the enum's string value). Let Pydantic validate field presence;
    # no manual reconstruction.
    return AuditListResponse(
        events=[AuditEventResponse(**e.to_dict()) for e in events],
    )
