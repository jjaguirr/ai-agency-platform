"""
Proactive notifications endpoint — pull-based for API clients.

GET /v1/notifications
  auth: Bearer token (customer_id claim)
  -> list[NotificationResponse]

Retrieves pending proactive messages, ordered by priority (desc) then
timestamp (asc). Marks as delivered on retrieval — subsequent calls
return empty until new notifications are generated.
"""
import logging

from fastapi import APIRouter, Depends, Request

from ..auth import get_current_customer
from ..schemas import NotificationResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/notifications", tags=["notifications"])

_PRIORITY_ORDER = {"URGENT": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


@router.get("", response_model=list[NotificationResponse])
async def get_notifications(
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    state_store = request.app.state.proactive_state_store
    raw = await state_store.pop_pending_notifications(customer_id)

    # Sort by priority (desc) then timestamp (asc)
    raw.sort(key=lambda n: (
        _PRIORITY_ORDER.get(n.get("priority", "LOW"), 3),
        n.get("created_at", ""),
    ))

    return [
        NotificationResponse(
            id=n.get("id", ""),
            domain=n.get("domain", ""),
            trigger_type=n.get("trigger_type", ""),
            priority=n.get("priority", "LOW"),
            title=n.get("title", ""),
            message=n.get("message", ""),
            created_at=n.get("created_at", ""),
        )
        for n in raw
    ]
