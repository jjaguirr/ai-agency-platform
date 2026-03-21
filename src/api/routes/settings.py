"""
Customer settings endpoints for the dashboard.

GET  /v1/settings  -> CustomerSettings (current settings or defaults)
PUT  /v1/settings  -> CustomerSettings (saved settings)

Settings are stored in Redis at ``settings:{customer_id}`` as JSON.
Other systems (proactive intelligence, specialists) can read from this
same key — but wiring those consumers is out of scope for this task.
"""
import json
import logging

from fastapi import APIRouter, Depends, Request

from ..auth import get_current_customer
from ..schemas import CustomerSettings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/settings", tags=["settings"])


def _settings_key(customer_id: str) -> str:
    return f"settings:{customer_id}"


@router.get("", response_model=CustomerSettings)
async def get_settings(
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    redis = request.app.state.redis_client
    raw = await redis.get(_settings_key(customer_id))
    if raw is None:
        return CustomerSettings()
    data = raw.decode() if isinstance(raw, bytes) else raw
    return CustomerSettings.model_validate_json(data)


@router.put("", response_model=CustomerSettings)
async def put_settings(
    settings: CustomerSettings,
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    redis = request.app.state.redis_client
    await redis.set(
        _settings_key(customer_id),
        settings.model_dump_json(),
    )
    return settings
