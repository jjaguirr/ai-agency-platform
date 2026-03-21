"""
GET /v1/workflows — customer's deployed automations.

Read-only; management happens through the conversation (WorkflowSpecialist).
This endpoint is what a dashboard hits. Tenant scoping comes from the
JWT claim — there is no customer_id query param to get wrong.
"""
from fastapi import APIRouter, Depends, Request

from ..auth import get_current_customer
from ..schemas import WorkflowResponse

router = APIRouter(prefix="/v1/workflows", tags=["workflows"])


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    store = getattr(request.app.state, "workflow_store", None)
    if store is None:
        return []
    raw = await store.list_workflows(customer_id)
    return [
        WorkflowResponse(
            workflow_id=w["workflow_id"],
            name=w["name"],
            status=w["status"],
            created_at=w["created_at"],
        )
        for w in raw
    ]
