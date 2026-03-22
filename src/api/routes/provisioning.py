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

After infra provisioning succeeds we seed Redis so the customer can
message the EA and log into the dashboard with zero manual steps:
  - default Settings (or demo-configured ones)
  - onboarding state (not_started, or completed for demo)
  - auth secret for dashboard login

Seeding is best-effort — a Redis blip logs a warning but the customer
still gets their token. Infra provisioning is the critical path; seeding
is a convenience that can be done manually if it fails.
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
        # Orchestrator rejected our input. We DON'T echo str(e) — the
        # orchestrator wasn't written with a "ValueError messages are
        # safe for clients" contract. It could leak internal paths,
        # image tags, config details. Log the detail server-side;
        # client gets a fixed message.
        logger.warning(
            "Orchestrator rejected provision request for customer=%s tier=%s",
            customer_id, req.tier, exc_info=True,
        )
        raise BadRequestError(
            detail="Provisioning request rejected. Check tier and parameters.",
        )
    except RuntimeError:
        # Deployment failure — Docker down, ports exhausted, etc.
        logger.exception("Provisioning failed for customer=%s", customer_id)
        raise ServiceUnavailableError(
            detail="Provisioning infrastructure unavailable.",
        )

    token = create_token(customer_id)
    dashboard_secret = await _seed(request, customer_id, demo=req.demo)

    return ProvisionResponse(
        customer_id=env.customer_id,
        token=token,
        tier=env.tier,
        dashboard_secret=dashboard_secret,
    )


async def _seed(request: Request, customer_id: str, *, demo: bool) -> str | None:
    """Best-effort Redis seeding. Returns the dashboard secret on
    success, None on failure. Never raises — seeding failure is not a
    provisioning failure."""
    redis = getattr(request.app.state, "redis_client", None)
    if redis is None:
        return None
    try:
        secret = secrets.token_urlsafe(24)
        await redis.set(f"auth:{customer_id}:secret", secret)

        if demo:
            from src.onboarding.demo_seed import seed_demo_account
            repo = getattr(request.app.state, "conversation_repo", None)
            await seed_demo_account(redis, customer_id, conversation_repo=repo)
        else:
            from src.onboarding.state import OnboardingStateStore
            await redis.set(
                f"settings:{customer_id}", Settings().model_dump_json(),
            )
            await OnboardingStateStore(redis).initialize(customer_id)

        return secret
    except Exception as e:
        logger.warning(
            "Post-provision seeding failed for customer=%s: %s",
            customer_id, e,
        )
        return None
