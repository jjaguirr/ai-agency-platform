"""
Customer provisioning endpoint.

Wraps InfrastructureOrchestrator.provision_customer_environment — does not
duplicate any of its Docker/Postgres/port-allocation logic. On success, mints
a JWT scoped to the new customer so the caller can immediately start talking
to the conversation endpoint.

Provisioning itself is unauthenticated: there's no customer yet to scope the
token to. Putting admin auth here is out of scope ("don't build user
management") — lock this down at the ingress layer in production.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..auth import create_token
from ..dependencies import get_orchestrator
from ..schemas import ProvisionRequest, ProvisionResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/customers", tags=["provisioning"])

# DeploymentStatus values that indicate the environment is usable.
# Anything else means we don't hand out a token.
_USABLE_STATUSES = {"healthy", "degraded"}


@router.post("", response_model=ProvisionResponse, status_code=status.HTTP_201_CREATED)
async def provision_customer(
    req: ProvisionRequest,
    request: Request,
    orchestrator=Depends(get_orchestrator),
) -> ProvisionResponse:
    if orchestrator is None:
        raise HTTPException(
            status_code=503,
            detail="Provisioning is not available",
        )

    try:
        env = await orchestrator.provision_customer_environment(
            customer_id=req.customer_id,
            tier=req.tier,
        )
    except Exception as e:
        # The orchestrator can fail on Docker, port allocation, Postgres init.
        # Log the real cause; surface a generic 503 to the client.
        logger.error(
            "Provisioning failed for customer_id=%s: %s",
            req.customer_id, e, exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail="Provisioning failed",
        ) from e

    env_status = env.status.value
    if env_status not in _USABLE_STATUSES:
        logger.error(
            "Provisioned environment unusable: customer_id=%s status=%s",
            env.customer_id, env_status,
        )
        raise HTTPException(
            status_code=503,
            detail=f"Environment provisioned but not usable (status: {env_status})",
        )

    # Mint a token for the ID the orchestrator actually assigned — it may
    # have normalized or rewritten what the client sent.
    token = create_token(env.customer_id, secret=request.app.state.jwt_secret)

    return ProvisionResponse(
        customer_id=env.customer_id,
        tier=env.tier,
        status=env_status,
        token=token,
        created_at=env.created_at.isoformat(),
    )
