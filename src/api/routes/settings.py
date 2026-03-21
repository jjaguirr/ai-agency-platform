"""
Customer settings — dashboard-writable configuration.

GET  /v1/settings   → Settings (defaults if never set)
PUT  /v1/settings   body: Settings → Settings

Persisted as JSON in Redis at `settings:{customer_id}`. Other systems
(proactive heartbeat, EA personality prompt) read the same key — wiring
those consumers is out of scope here; this route only owns storage.

PUT is whole-document replace, not PATCH. The dashboard always submits
the full form so partial updates aren't needed yet.
"""
import json
import logging

from fastapi import APIRouter, Depends, Request

from ..auth import get_current_customer
from ..schemas import Settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/settings", tags=["settings"])

_REDIS_KEY = "settings:{customer_id}"


@router.get("", response_model=Settings)
async def get_settings(
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    redis = request.app.state.redis_client
    raw = await redis.get(_REDIS_KEY.format(customer_id=customer_id))
    if raw is None:
        settings = Settings()
    else:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        # model_validate tolerates extra keys we've since removed and fills
        # defaults for keys we've since added — forward-compatible storage.
        settings = Settings.model_validate(json.loads(raw))

    # Live n8n health check — overrides stored value.
    # Calendar stays False until an integration exists.
    n8n_client = getattr(request.app.state, "n8n_client", None)
    if n8n_client is not None:
        try:
            await n8n_client.list_workflows()
            settings.connected_services.n8n = True
        except Exception:
            settings.connected_services.n8n = False

    return settings


@router.put("", response_model=Settings)
async def put_settings(
    body: Settings,
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    redis = request.app.state.redis_client
    await redis.set(
        _REDIS_KEY.format(customer_id=customer_id),
        body.model_dump_json(),
    )
    return body
