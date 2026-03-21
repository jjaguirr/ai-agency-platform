"""
Dashboard analytics — today's activity counts + specialist health grid.

GET /v1/analytics/activity
    → {date, messages_processed, delegations_by_domain, proactive_triggers_sent}
    Read-only Redis counters. Zeros for fresh customers.

GET /v1/analytics/specialists
    → {specialists: [{domain, registered, operational, detail}, ...]}
    Fixed four-domain list. registered = module imports cleanly;
    operational = registered AND external deps reachable. Only workflows
    has an external probe today (n8n list_workflows()).

Both are read-only landing-page endpoints: no failure mode is allowed to
500 them. Probe errors become operational=False with detail populated;
counter errors become zeros.
"""
import asyncio
import importlib
import logging
from datetime import date

from fastapi import APIRouter, Depends, Request

from ..activity_counters import get_today
from ..auth import get_current_customer
from ..schemas import ActivitySummary, SpecialistStatus, SpecialistStatusResponse

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
    # registered = "the code is there". An optional-dep ImportError at
    # module top level (e.g., someone ships a specialist that needs a
    # lib the container doesn't have) shows up here as False + detail.
    try:
        importlib.import_module(f"src.agents.specialists.{domain}")
        registered = True
    except Exception as e:
        return SpecialistStatus(
            domain=domain, registered=False, operational=False,
            detail=f"import failed: {e}",
        )

    # operational = registered AND external service reachable. Only
    # workflows has a service to talk to today; the other three are
    # pure-Python until someone wires a calendar API / accounting API /
    # social platform client, at which point add a probe branch here.
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
        # Same 2s cap as the settings probe — the dashboard loads both
        # on the same page, so a slow n8n shouldn't cost 4s.
        await asyncio.wait_for(n8n.list_workflows(), timeout=2.0)
        return SpecialistStatus(domain=domain, registered=True, operational=True)
    except Exception as e:
        return SpecialistStatus(
            domain=domain, registered=True, operational=False, detail=str(e),
        )
