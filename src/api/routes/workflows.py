"""
Customer workflows endpoint — tenant-scoped.

GET /v1/workflows
  auth: Bearer token (customer_id claim)
  -> list[WorkflowSummaryResponse]
"""
import logging

from fastapi import APIRouter, Depends, Request

from ..auth import get_current_customer
from ..schemas import WorkflowSummaryResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/workflows", tags=["workflows"])


@router.get("", response_model=list[WorkflowSummaryResponse])
async def list_workflows(
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    tracker = request.app.state.workflow_tracker
    if tracker is None:
        return []
    workflows = await tracker.list_workflows(customer_id)
    return [
        WorkflowSummaryResponse(
            workflow_id=w.workflow_id,
            name=w.name,
            status=w.status,
            created_at=w.created_at,
        )
        for w in workflows
    ]
