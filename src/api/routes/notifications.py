"""
Proactive notifications — pull-based for API/dashboard clients.

GET /v1/notifications
  Non-destructive. Returns pending items plus any snoozed items whose
  snooze_until has passed. Ordered by priority desc, then created_at asc.

POST /v1/notifications/{id}/read    → 204 | 404
POST /v1/notifications/{id}/snooze  → 204 | 404 | 422  body: {minutes}
POST /v1/notifications/{id}/dismiss → 204 | 404

All lifecycle ops are scoped to the authenticated customer's hash — a
404 on someone else's ID doesn't leak that the ID exists.
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..auth import get_current_customer
from ..schemas import NotificationResponse, SnoozeRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/notifications", tags=["notifications"])

_PRIORITY_ORDER = {"URGENT": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _store(request: Request):
    return request.app.state.proactive_state_store


@router.get("", response_model=list[NotificationResponse])
async def get_notifications(
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    now = datetime.now(timezone.utc)
    raw = await _store(request).list_pending_notifications(customer_id, now=now)

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
            status=n.get("status", "pending"),
        )
        for n in raw
    ]


@router.post("/{notification_id}/read", status_code=204)
async def mark_read(
    notification_id: str,
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    ok = await _store(request).mark_notification_read(customer_id, notification_id)
    if not ok:
        raise HTTPException(status_code=404)
    return Response(status_code=204)


@router.post("/{notification_id}/snooze", status_code=204)
async def snooze(
    notification_id: str,
    request: Request,
    body: SnoozeRequest = SnoozeRequest(),
    customer_id: str = Depends(get_current_customer),
):
    until = datetime.now(timezone.utc) + timedelta(minutes=body.minutes)
    ok = await _store(request).snooze_notification(customer_id, notification_id, until)
    if not ok:
        raise HTTPException(status_code=404)
    return Response(status_code=204)


@router.post("/{notification_id}/dismiss", status_code=204)
async def dismiss(
    notification_id: str,
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    ok = await _store(request).dismiss_notification(customer_id, notification_id)
    if not ok:
        raise HTTPException(status_code=404)
    return Response(status_code=204)
