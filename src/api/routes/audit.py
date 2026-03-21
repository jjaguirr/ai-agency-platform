"""Audit trail endpoint.

GET /v1/audit — returns paginated audit events for the authenticated customer.
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
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    audit_logger = getattr(request.app.state, "audit_logger", None)
    if audit_logger is None:
        return AuditListResponse(
            customer_id=customer_id, events=[], offset=offset, limit=limit,
        )

    events_raw = await audit_logger.list_events(
        customer_id, offset=offset, limit=limit,
    )
    events = [
        AuditEventResponse(
            timestamp=e.get("timestamp", ""),
            event_type=e.get("event_type", ""),
            correlation_id=e.get("correlation_id"),
            details=e.get("details", {}),
        )
        for e in events_raw
    ]
    return AuditListResponse(
        customer_id=customer_id, events=events, offset=offset, limit=limit,
    )
