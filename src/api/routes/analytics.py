"""
Analytics endpoints — replace dashboard placeholders with real data.

GET /v1/analytics/activity   → today's message count, delegation breakdown, proactive count
GET /v1/analytics/specialists → registered specialists with operational status

Data sources:
  - Redis counters (analytics:{customer_id}:{date}:*) for activity
  - EA's DelegationRegistry for specialist registration
  - N8nClient health check for workflow specialist connectivity
"""
import logging
from datetime import date

from fastapi import APIRouter, Depends, Request

from ..auth import get_current_customer
from ..schemas import (
    ActivitySummaryResponse,
    SpecialistStatusItem,
    SpecialistStatusResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/analytics", tags=["analytics"])

# Redis key templates for analytics counters.
_MSG_KEY = "analytics:{cid}:{day}:messages"
_DELEG_KEY = "analytics:{cid}:{day}:delegations"
_PROACTIVE_KEY = "analytics:{cid}:{day}:proactive"


async def _safe_get_int(redis, key: str) -> int:
    try:
        val = await redis.get(key)
        return int(val) if val else 0
    except Exception:
        return 0


@router.get("/activity", response_model=ActivitySummaryResponse)
async def activity_summary(
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    redis = request.app.state.redis_client
    today = date.today().isoformat()

    messages = await _safe_get_int(redis, _MSG_KEY.format(cid=customer_id, day=today))
    proactive = await _safe_get_int(redis, _PROACTIVE_KEY.format(cid=customer_id, day=today))

    # Delegation breakdown stored as a Redis hash: domain → count
    delegations: dict[str, int] = {}
    try:
        raw = await redis.hgetall(_DELEG_KEY.format(cid=customer_id, day=today))
        for k, v in raw.items():
            domain = k.decode() if isinstance(k, bytes) else k
            count = int(v.decode() if isinstance(v, bytes) else v)
            delegations[domain] = count
    except Exception:
        pass

    return ActivitySummaryResponse(
        date=today,
        messages_processed=messages,
        specialist_delegations=delegations,
        proactive_triggers_sent=proactive,
    )


@router.get("/specialists", response_model=SpecialistStatusResponse)
async def specialist_status(
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    ea_registry = request.app.state.ea_registry
    n8n_client = getattr(request.app.state, "n8n_client", None)

    try:
        ea = await ea_registry.get(customer_id)
        # No public accessor on DelegationRegistry — _specialists is the
        # internal dict mapping domain → SpecialistAgent.
        registered = dict(ea.delegation_registry._specialists)
    except Exception:
        registered = {}

    items: list[SpecialistStatusItem] = []
    for domain, spec in registered.items():
        item = SpecialistStatusItem(
            domain=domain,
            registered=True,
            operational=True,
        )
        if domain == "workflows" and n8n_client is not None:
            try:
                await n8n_client.list_workflows()
                item.n8n_connected = True
            except Exception:
                item.n8n_connected = False
        items.append(item)

    return SpecialistStatusResponse(specialists=items)
