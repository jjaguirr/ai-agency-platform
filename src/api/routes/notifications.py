"""
Proactive notifications endpoint — pull-based for API clients.

GET  /v1/notifications                       → list[NotificationResponse]
POST /v1/notifications/{notification_id}/read    → 200
POST /v1/notifications/{notification_id}/snooze  → 200
POST /v1/notifications/{notification_id}/dismiss → 200

Retrieves pending proactive messages, ordered by priority (desc) then
timestamp (asc). Persistent notifications support read/snooze/dismiss
lifecycle. Legacy list-based notifications are also returned for backward
compatibility.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth import get_current_customer
from ..schemas import NotificationResponse, SnoozeRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/notifications", tags=["notifications"])

_PRIORITY_ORDER = {"URGENT": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


@router.get("", response_model=list[NotificationResponse])
async def get_notifications(
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    state_store = request.app.state.proactive_state_store

    # Persistent lifecycle notifications
    persistent = await state_store.list_notifications(
        customer_id, now=datetime.now(timezone.utc),
    )

    # Legacy list-based notifications (backward compat)
    legacy = await state_store.pop_pending_notifications(customer_id)

    combined = persistent + legacy

    # Sort by priority (desc) then timestamp (asc)
    combined.sort(key=lambda n: (
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
        for n in combined
    ]


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: str,
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    state_store = request.app.state.proactive_state_store
    ok = await state_store.mark_notification_read(customer_id, notification_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "ok"}


@router.post("/{notification_id}/snooze")
async def snooze(
    notification_id: str,
    request: Request,
    customer_id: str = Depends(get_current_customer),
    body: Optional[SnoozeRequest] = None,
):
    state_store = request.app.state.proactive_state_store
    duration = (body.duration_seconds if body else 3600)
    until = datetime.now(timezone.utc) + timedelta(seconds=duration)
    ok = await state_store.snooze_notification(customer_id, notification_id, until)
    if not ok:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "ok"}


@router.post("/{notification_id}/dismiss")
async def dismiss(
    notification_id: str,
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    state_store = request.app.state.proactive_state_store
    ok = await state_store.dismiss_notification(customer_id, notification_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "ok"}
