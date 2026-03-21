"""
RateLimitMiddleware — per-customer + global throttle, pure ASGI.

Runs outermost in the middleware stack so an unauthenticated flood
still hits the global bucket before any of the heavier machinery (auth,
EA registry, LLM calls) gets involved. Per-customer buckets need an
identity; the middleware extracts it best-effort from the two places
it actually appears:

  /webhook/whatsapp/{customer_id}  — Twilio posts here; path-embedded
  Authorization: Bearer <jwt>      — API clients; customer_id claim

If neither yields an identity the request is anonymous — global bucket
only. The auth dependency will reject it later with a proper 401; the
rate limiter's job is just bucketing, not authz.

Counters are INCR-on-a-time-bucketed-key, same as ProactiveStateStore
(src/proactive/state.py:90). The key includes the bucket epoch so a
new minute/day/second is a new key — counters reset for free, EXPIRE
is just garbage collection.

Fail-open: Redis down → log WARNING and let the request through. Rate
limiting is abuse protection; a Redis blip shouldn't take down the API.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional

from .config import SafetyConfig

logger = logging.getLogger(__name__)

_EXEMPT_PATHS = ("/healthz", "/readyz")

# Matches the webhook route at src/api/routes/webhooks.py:28. The
# customer_id format mirrors _CUSTOMER_ID_PATTERN in schemas.py but
# we don't need to be strict here — extraction is best-effort, and a
# malformed ID just means the per-customer bucket is keyed on garbage,
# which is harmless (the webhook route itself will 404).
_WHATSAPP_PATH = re.compile(r"^/webhook/whatsapp/([a-zA-Z0-9_-]+)")


class RateLimitMiddleware:
    def __init__(
        self,
        app,
        redis_client,
        config: SafetyConfig,
        *,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.app = app
        self._redis = redis_client
        self._config = config
        self._now = now

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        customer_id = self._extract_customer(scope)

        try:
            verdict = await self._check_limits(customer_id)
        except Exception:
            # Redis unavailable. Let the request through — worse to
            # block everything than to briefly under-throttle.
            logger.warning("Rate limit check failed; passing through",
                           exc_info=True)
            await self.app(scope, receive, send)
            return

        if verdict is not None:
            status, retry_after, body = verdict
            await _short_circuit(send, status, retry_after, body)
            return

        await self.app(scope, receive, send)

    # --- Customer extraction ------------------------------------------------

    def _extract_customer(self, scope) -> Optional[str]:
        # WhatsApp path carries it directly.
        m = _WHATSAPP_PATH.match(scope.get("path", ""))
        if m:
            return m.group(1)

        # Otherwise: crack open the JWT if there is one. This is the
        # same decode the auth dependency does, but we swallow every
        # failure — the dependency will produce the real 401, we just
        # want a bucketing key when one is available.
        token = _bearer_token(scope.get("headers", []))
        if token is None:
            return None

        # Import here: src.api.auth reads JWT_SECRET at call time, and
        # this module may be imported before the env is configured in
        # contexts that never actually run the middleware.
        from src.api.auth import InvalidTokenError, decode_token
        try:
            return decode_token(token).get("customer_id")
        except (InvalidTokenError, Exception):
            return None

    # --- Counter check ------------------------------------------------------

    async def _check_limits(
        self, customer_id: Optional[str],
    ) -> Optional[tuple[int, Optional[int], dict]]:
        """Returns (status, retry_after, body) if over a limit, else None.

        All counters increment in one Redis pipeline — one round-trip
        per request regardless of how many buckets we track. The INCR
        result is the new count; comparing against the limit after the
        increment means the Nth request is allowed and the (N+1)th is
        not, which is the intuitive reading of "N per minute".

        Global is checked first because its failure mode (503 overloaded)
        is about protecting the system, not about being fair to the
        customer. If we're at the global cap, per-customer status is moot.
        """
        now = self._now()
        epoch_sec = int(now)
        epoch_min = epoch_sec // 60
        today = date.fromtimestamp(now).isoformat()

        pipe = self._redis.pipeline()

        global_key = f"ratelimit:global:{epoch_sec}"
        pipe.incr(global_key)
        pipe.expire(global_key, 2)

        if customer_id is not None:
            min_key = f"ratelimit:{customer_id}:min:{epoch_min}"
            day_key = f"ratelimit:{customer_id}:day:{today}"
            pipe.incr(min_key)
            pipe.expire(min_key, 120)
            pipe.incr(day_key)
            pipe.expire(day_key, 172800)

        results = await pipe.execute()
        # Results: [global_count, global_exp_ok, min_count?, min_exp_ok?, ...]
        global_count = results[0]

        if global_count > self._config.rate_global_per_second:
            return (503, None, {
                "type": "overloaded",
                "detail": "Service is at capacity. Please retry shortly.",
            })

        if customer_id is None:
            return None

        min_count = results[2]
        day_count = results[4]

        if min_count > self._config.rate_per_minute:
            # Seconds remaining until the next minute bucket. At least 1
            # so clients don't retry immediately on a boundary tick.
            retry = max(1, 60 - (epoch_sec % 60))
            return (429, retry, {
                "type": "rate_limited",
                "detail": (
                    f"Rate limit of {self._config.rate_per_minute} "
                    f"requests per minute exceeded."
                ),
            })

        if day_count > self._config.rate_per_day:
            retry = _seconds_until_utc_midnight(now)
            return (429, retry, {
                "type": "rate_limited",
                "detail": (
                    f"Daily limit of {self._config.rate_per_day} "
                    f"requests exceeded."
                ),
            })

        return None


# --- Helpers ----------------------------------------------------------------

def _bearer_token(headers) -> Optional[str]:
    for name, value in headers:
        if name.lower() == b"authorization":
            # "Bearer <token>" — case-insensitive scheme, single space.
            parts = value.decode("latin-1").split(" ", 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                return parts[1]
    return None


def _seconds_until_utc_midnight(now: float) -> int:
    dt = datetime.fromtimestamp(now, tz=timezone.utc)
    tomorrow = (dt + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    return max(1, int((tomorrow - dt).total_seconds()))


async def _short_circuit(
    send, status: int, retry_after: Optional[int], body: dict,
) -> None:
    headers = [(b"content-type", b"application/json")]
    if retry_after is not None:
        headers.append((b"retry-after", str(retry_after).encode("latin-1")))
    payload = json.dumps(body).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": headers,
    })
    await send({"type": "http.response.body", "body": payload})
