"""
Customer provisioning — wraps InfrastructureOrchestrator.

POST /v1/customers/provision
  body: {customer_id?, tier?, demo?}
  auth: none (this *creates* the auth token)
  → {customer_id, token, tier, dashboard_secret}

We don't re-implement provisioning logic. The orchestrator owns the
Docker-network creation, port allocation, service deployment. We mint a
customer_id if one wasn't supplied, call the orchestrator, and hand back
a token.

After the orchestrator succeeds we seed Redis with default settings, a
dashboard auth secret, and the initial onboarding state so the customer
can immediately message the EA *and* log into the dashboard.
"""
import logging
import secrets
import uuid

from fastapi import APIRouter, Request, status

from ..auth import create_token
from ..errors import BadRequestError, ServiceUnavailableError
from ..schemas import ProvisionRequest, ProvisionResponse, Settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/customers", tags=["provisioning"])


@router.post(
    "/provision",
    response_model=ProvisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def provision_customer(req: ProvisionRequest, request: Request):
    customer_id = req.customer_id or f"cust_{uuid.uuid4().hex[:12]}"
    orchestrator = request.app.state.orchestrator

    try:
        env = await orchestrator.provision_customer_environment(
            customer_id=customer_id,
            tier=req.tier,
        )
    except ValueError:
        logger.warning(
            "Orchestrator rejected provision request for customer=%s tier=%s",
            customer_id, req.tier, exc_info=True,
        )
        raise BadRequestError(
            detail="Provisioning request rejected. Check tier and parameters.",
        )
    except RuntimeError:
        logger.exception("Provisioning failed for customer=%s", customer_id)
        raise ServiceUnavailableError(
            detail="Provisioning infrastructure unavailable.",
        )

    # --- Seed Redis defaults -----------------------------------------------
    redis = request.app.state.redis_client

    # 1. Default settings
    await redis.set(
        f"settings:{customer_id}",
        Settings().model_dump_json(),
    )

    # 2. Dashboard auth secret
    dashboard_secret = secrets.token_urlsafe(24)
    await redis.set(f"auth:{customer_id}:secret", dashboard_secret)

    # 3. Onboarding state
    onboarding_store = getattr(request.app.state, "onboarding_state_store", None)
    if onboarding_store is not None:
        await onboarding_store.initialize(customer_id)

    # 4. Demo mode
    if req.demo:
        from src.onboarding.demo import seed_demo_data
        proactive_store = getattr(request.app.state, "proactive_state_store", None)
        await seed_demo_data(
            redis_client=redis,
            customer_id=customer_id,
            onboarding_store=onboarding_store,
            proactive_store=proactive_store,
        )

    token = create_token(customer_id)

    return ProvisionResponse(
        customer_id=env.customer_id,
        token=token,
        tier=env.tier,
        dashboard_secret=dashboard_secret,
    )
