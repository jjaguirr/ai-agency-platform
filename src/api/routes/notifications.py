"""
GET /v1/notifications — pull-model proactive messages.

Customers without a push channel (or when push delivery failed) collect
proactive messages here. Each GET drains the queue — once retrieved, a
notification is considered delivered and won't be returned again. The
client is expected to display immediately or persist locally.

Ordered priority DESC then created_at ASC so the most urgent + oldest
thing is always at the top of the list.
"""
import logging

from fastapi import APIRouter, Depends, Request

from ..auth import get_current_customer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["notifications"])


@router.get("/notifications")
async def get_notifications(
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    # Import inside the handler — this route module loads at app-factory
    # time, but the proactive package pulls in things the API test suite
    # doesn't always need. Lazy keeps the import surface tight.
    from src.agents.proactive.state import ProactiveStateStore

    store = ProactiveStateStore(redis=request.app.state.redis_client)
    triggers = await store.drain_notifications(customer_id)

    return {
        "notifications": [
            {
                "domain": t.domain,
                "trigger_type": t.trigger_type,
                "priority": t.priority.name.lower(),
                "title": t.title,
                "message": t.suggested_message,
                "payload": t.payload,
                "created_at": t.created_at.isoformat(),
            }
            for t in triggers
        ]
    }
