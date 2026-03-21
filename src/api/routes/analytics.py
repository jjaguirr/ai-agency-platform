"""
Analytics endpoint — aggregate conversation intelligence for a window.

GET /v1/analytics?range=7d
GET /v1/analytics?since=2026-03-01T00:00:00Z&until=2026-03-15T00:00:00Z

The heavy lifting (GROUP BY, counts, rates) lives in
IntelligenceRepository. This route does window arithmetic and the
trend comparison — current window vs. the immediately preceding window
of the same width.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from ..auth import get_current_customer
from ..schemas import (
    AnalyticsRange, AnalyticsResponse, AnalyticsWindow,
    QualityOverview, TrendPoint,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/analytics", tags=["analytics"])

_RANGE_WIDTHS = {
    "24h": timedelta(hours=24),
    "7d":  timedelta(days=7),
    "30d": timedelta(days=30),
}


def _resolve_window(
    range_: Optional[str], since: Optional[datetime], until: Optional[datetime],
) -> tuple[datetime, datetime, str]:
    """Turn the query params into concrete bounds + a display label.

    Explicit since/until wins. When both are absent, range (defaulting
    to 7d) anchors the window to now.
    """
    if since is not None and until is not None:
        return since, until, "custom"
    now = datetime.now(timezone.utc)
    key = range_ or "7d"
    return now - _RANGE_WIDTHS[key], now, key


@router.get("", response_model=AnalyticsResponse)
async def get_analytics(
    request: Request,
    customer_id: str = Depends(get_current_customer),
    range: Optional[AnalyticsRange] = Query(None),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
):
    s, u, label = _resolve_window(range, since, until)
    window = AnalyticsWindow(since=s.isoformat(), until=u.isoformat(), label=label)

    repo = getattr(request.app.state, "intelligence_repo", None)
    if repo is None:
        return AnalyticsResponse(
            window=window, topics=[], specialists=[],
            quality=QualityOverview(total=0, flags={}),
            trend={},
        )

    topics = await repo.topic_breakdown(customer_id=customer_id, since=s, until=u)
    specialists = await repo.specialist_metrics(customer_id=customer_id, since=s, until=u)
    flags = await repo.quality_counts(customer_id=customer_id, since=s, until=u)

    # Trend: current window vs. the window immediately before it, same
    # width. A 7-day range compares this week to last week; a custom
    # range compares to the equal-length span preceding `since`.
    width = u - s
    cur = await repo.conversation_count(customer_id=customer_id, since=s, until=u)
    prev = await repo.conversation_count(customer_id=customer_id, since=s - width, until=s)
    delta = ((cur - prev) / prev * 100.0) if prev else None

    return AnalyticsResponse(
        window=window,
        topics=topics,
        specialists=specialists,
        quality=QualityOverview(total=cur, flags=flags),
        trend={"conversations": TrendPoint(current=cur, previous=prev, delta_pct=delta)},
    )
