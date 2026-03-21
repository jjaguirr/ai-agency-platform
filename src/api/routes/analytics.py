"""Analytics endpoint for conversation intelligence.

GET /v1/analytics?period=7d
GET /v1/analytics?period=custom&start=2026-03-01T00:00:00Z&end=2026-03-21T00:00:00Z
"""
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..auth import get_current_customer
from ..schemas import AnalyticsResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/analytics", tags=["analytics"])

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
