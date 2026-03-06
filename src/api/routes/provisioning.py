"""
Customer provisioning — wraps InfrastructureOrchestrator.

POST /v1/customers/provision
  body: {customer_id?, tier?}
  auth: none (this *creates* the auth token)
  → {customer_id, token, tier}

We don't re-implement provisioning logic. The orchestrator owns the
Docker-network creation, port allocation, service deployment. We mint a
customer_id if one wasn't supplied, call the orchestrator, and hand back
a token.
"""
import logging
import uuid

from fastapi import APIRouter, Request, status

from ..auth import create_token
from ..errors import BadRequestError, ServiceUnavailableError
from ..schemas import ProvisionRequest, ProvisionResponse

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

    return ProvisionResponse(
        customer_id=env.customer_id,
        token=token,
        tier=env.tier,
    )
