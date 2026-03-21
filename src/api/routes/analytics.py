"""
Dashboard analytics — today's activity counts + specialist health grid.
Conversation intelligence analytics — topic breakdown, specialist performance.

GET /v1/analytics/activity
    → {date, messages_processed, delegations_by_domain, proactive_triggers_sent}
GET /v1/analytics/specialists
    → {specialists: [{domain, registered, operational, detail}, ...]}
GET /v1/analytics
    → conversation intelligence (topic breakdown, specialist metrics, trends)
"""
import asyncio
import importlib
import logging
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..activity_counters import get_today
from ..auth import get_current_customer
from ..schemas import (
    ActivitySummary, AnalyticsResponse, SpecialistStatus, SpecialistStatusResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/analytics", tags=["analytics"])

# Module names under src.agents.specialists.* — one per dashboard tile.
# Keep in sync with activity_counters._DOMAINS.
_SPECIALIST_DOMAINS = ("finance", "scheduling", "social_media", "workflows")


@router.get("/activity", response_model=ActivitySummary)
async def get_activity(
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    redis = request.app.state.redis_client
    counters = await get_today(redis, customer_id)

    # Proactive trigger count lives in its own store — it predates
    # this endpoint and the heartbeat daemon already increments it.
    proactive = 0
    store = getattr(request.app.state, "proactive_state_store", None)
    if store is not None:
        try:
            proactive = await store.get_daily_count(customer_id)
        except Exception as e:
            logger.debug("proactive count read failed for %s: %s", customer_id, e)

    return ActivitySummary(
        date=date.today().isoformat(),
        messages_processed=counters["messages"],
        delegations_by_domain=counters["delegations"],
        proactive_triggers_sent=proactive,
    )


@router.get("/specialists", response_model=SpecialistStatusResponse)
async def get_specialist_status(
    request: Request,
    _customer_id: str = Depends(get_current_customer),
):
    n8n = getattr(request.app.state, "n8n_client", None)
    statuses = [
        await _probe(domain, n8n) for domain in _SPECIALIST_DOMAINS
    ]
    return SpecialistStatusResponse(specialists=statuses)


async def _probe(domain: str, n8n) -> SpecialistStatus:
    try:
        importlib.import_module(f"src.agents.specialists.{domain}")
        registered = True
    except Exception as e:
        return SpecialistStatus(
            domain=domain, registered=False, operational=False,
            detail=f"import failed: {e}",
        )

    if domain != "workflows":
        return SpecialistStatus(
            domain=domain, registered=registered, operational=registered,
        )

    if n8n is None:
        return SpecialistStatus(
            domain=domain, registered=True, operational=False,
            detail="n8n client not configured",
        )

    try:
        await asyncio.wait_for(n8n.list_workflows(), timeout=2.0)
        return SpecialistStatus(domain=domain, registered=True, operational=True)
    except Exception as e:
        return SpecialistStatus(
            domain=domain, registered=True, operational=False, detail=str(e),
        )


# --- Conversation intelligence analytics ------------------------------------

Period = Literal["24h", "7d", "30d", "custom"]


@router.get("", response_model=AnalyticsResponse)
async def get_analytics(
    request: Request,
    customer_id: str = Depends(get_current_customer),
    period: Period = Query("7d"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
):
    svc = getattr(request.app.state, "analytics_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="Analytics service unavailable")

    from src.intelligence.analytics import compute_time_range

    try:
        range_start, range_end = compute_time_range(
            period, start=start, end=end,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return await svc.get_analytics(
        customer_id=customer_id,
        start=range_start,
        end=range_end,
    )
