"""ASGI rate-limit middleware.

Pure ASGI — no BaseHTTPMiddleware overhead. Follows the pattern in
src/api/middleware.py (CorrelationMiddleware).

Applied before auth. Extracts customer_id from JWT payload via best-effort
base64 decode (no signature verification — auth handles that). Falls back
to global-only limit for unauthenticated or unparseable tokens.
"""
from __future__ import annotations

import base64
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from .config import SafetyConfig

logger = logging.getLogger(__name__)

def _extract_customer_id(headers: list[tuple[bytes, bytes]]) -> str | None:
    """Best-effort JWT payload decode — no signature check."""
    for name, value in headers:
        if name == b"authorization":
            token_str = value.decode("latin-1")
            if token_str.lower().startswith("bearer "):
                token = token_str[7:]
                parts = token.split(".")
                if len(parts) == 3:
                    try:
                        payload_b64 = parts[1]
                        # Add padding
                        payload_b64 += "=" * (4 - len(payload_b64) % 4)
                        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                        cid = payload.get("customer_id")
                        if isinstance(cid, str) and cid.strip():
                            return cid
                    except Exception:
                        pass
            break
    return None


class RateLimitMiddleware:
    """Redis-backed rate limiter. Three tiers: global, per-customer/minute, per-customer/day.

    Uses simple INCR-per-time-bucket counting (not sorted sets) to minimise
    Redis round-trips — one INCR + one conditional EXPIRE per check.

    Fail-open: if Redis is unreachable the request passes through. This
    trades temporary rate-limit bypass for availability.
    """

    def __init__(self, app: Any, *, redis_client: Any, config: SafetyConfig):
        self.app = app
        self._redis = redis_client
        self._cfg = config

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Only rate-limit API/webhook paths
        path = scope.get("path", "")
        if not any(path.startswith(p) for p in ("/v1/", "/webhook/")):
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers", [])

        # 1. Global rate limit
        try:
            global_blocked = await self._check_global()
        except Exception:
            global_blocked = False  # Redis down — fail open

        if global_blocked:
            await self._send_error(send, 503, "service_overloaded",
                                   "Service temporarily overloaded. Please try again.",
                                   retry_after="1")
            return

        # 2. Per-customer limits (only if customer identifiable)
        customer_id = _extract_customer_id(headers)
        if customer_id:
            try:
                minute_blocked = await self._check_per_minute(customer_id)
                if minute_blocked:
                    await self._send_error(send, 429, "rate_limit_exceeded",
                                           "Rate limit exceeded. Please slow down.",
                                           retry_after="60")
                    return

                daily_blocked = await self._check_per_day(customer_id)
                if daily_blocked:
                    await self._send_error(send, 429, "rate_limit_exceeded",
                                           "Daily message limit reached. Limit resets at midnight UTC.",
                                           retry_after="3600")
                    return
            except Exception:
                pass  # Redis down — fail open

        await self.app(scope, receive, send)

    async def _check_global(self) -> bool:
        """Check global requests-per-second across all customers.

        Key ``rate:global:{unix_second}`` expires after 2 s — slightly past
        the 1 s window so the key survives potential clock jitter between
        the INCR and EXPIRE commands.
        """
        now = int(time.time())
        key = f"rate:global:{now}"
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, 2)
        return count > self._cfg.global_rps

    async def _check_per_minute(self, customer_id: str) -> bool:
        """Check per-customer messages-per-minute.

        Key ``rate:min:{cid}:{minute_epoch}`` expires after 120 s (2x the
        window). The extra minute prevents under-counting when a request
        arrives at second 59 of a minute bucket — the key must survive
        until the next bucket is safely past.
        """
        now = int(time.time())
        minute = now // 60
        key = f"rate:min:{customer_id}:{minute}"
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, 120)
        return count > self._cfg.per_customer_per_minute

    async def _check_per_day(self, customer_id: str) -> bool:
        """Check per-customer messages-per-day.

        Key ``rate:day:{cid}:{YYYYMMDD}`` expires after 172 800 s (2 days).
        The extra day handles customers near the UTC date boundary — their
        bucket must survive long enough that both ``today`` and ``yesterday``
        keys coexist without premature eviction.
        """
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        key = f"rate:day:{customer_id}:{today}"
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, 172800)
        return count > self._cfg.per_customer_per_day

    @staticmethod
    async def _send_error(send, status: int, error_type: str, detail: str,
                          retry_after: str | None = None) -> None:
        """Write a JSON error response directly to the ASGI ``send`` callable.

        503 for global overload, 429 for per-customer limits.
        ``Retry-After`` header is included when the caller provides a value.
        """
        body = json.dumps({"type": error_type, "detail": detail}).encode()
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ]
        if retry_after:
            headers.append((b"retry-after", retry_after.encode()))
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": headers,
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })
