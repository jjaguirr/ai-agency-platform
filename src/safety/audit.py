"""
AuditLogger — append-only audit trail, Redis-backed.

One list per customer: audit:{customer_id}. Events RPUSHed as JSON,
LTRIMmed to a configurable cap. Same async Redis client and idioms as
ProactiveStateStore (src/proactive/state.py).

Logging is best-effort: Redis down → log WARNING, move on. Audit
failure must not block the request path. Listing is also best-effort:
Redis down → return empty list (the API endpoint degrades gracefully).

Message content is never stored. hash_message() gives ops a stable
identifier to correlate incidents across systems without putting PII
in the audit log.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import List

from .models import AuditEvent

logger = logging.getLogger(__name__)


def hash_message(message: str) -> str:
    """SHA-256 hex digest of a message, for PII-safe audit correlation."""
    return hashlib.sha256(message.encode("utf-8")).hexdigest()


def _key(customer_id: str) -> str:
    return f"audit:{customer_id}"


class AuditLogger:
    """Redis list writer/reader for the audit trail.

    Constructed once per app instance, stored on app.state. The Redis
    client is shared — same one the routes and ProactiveStateStore use.
    """

    def __init__(self, redis_client, max_events: int = 10_000) -> None:
        self._r = redis_client
        self._max = max_events

    # --- Write --------------------------------------------------------------

    async def log(self, customer_id: str, event: AuditEvent) -> None:
        """Append one event. Never raises."""
        key = _key(customer_id)
        payload = json.dumps(event.to_dict())
        try:
            # Pipeline RPUSH + LTRIM atomically. LTRIM with a negative
            # start keeps the last N: LTRIM key -N -1 means "keep from
            # Nth-from-end through end". Oldest fall off the front.
            pipe = self._r.pipeline()
            pipe.rpush(key, payload)
            pipe.ltrim(key, -self._max, -1)
            await pipe.execute()
        except Exception:
            logger.warning(
                "Audit log write failed for customer=%s event_type=%s",
                customer_id, event.event_type.value, exc_info=True,
            )

    # --- Read ---------------------------------------------------------------

    async def list_events(
        self, customer_id: str, *, limit: int, offset: int,
    ) -> List[AuditEvent]:
        """Return events newest-first, paginated. Never raises."""
        key = _key(customer_id)
        try:
            # Storage order is oldest→newest (RPUSH). For newest-first
            # pagination we want the tail slice, reversed.
            #
            # With N items stored (indices 0..N-1):
            #   offset=0, limit=3 → want items [N-1, N-2, N-3]
            #   offset=3, limit=3 → want items [N-4, N-5, N-6]
            #
            # LRANGE with negative indices: -1 is last, -2 is second-last.
            #   start = -(offset + limit)
            #   stop  = -(offset + 1)    — or -1 if offset==0
            #
            # Edge: if the slice runs past the front of the list, LRANGE
            # clamps. If offset alone runs past, stop index would be
            # invalid (e.g., -(100+1) when only 1 item) — clamp returns
            # extra items from the wrong range. Easier to LLEN first and
            # guard; an extra round-trip per page is fine for an admin
            # endpoint.
            n = await self._r.llen(key)
            if n == 0 or offset >= n:
                return []

            # Convert newest-first (offset, limit) to oldest-first
            # storage indices.
            stop_idx = n - 1 - offset              # newest in page
            start_idx = max(0, stop_idx - limit + 1)  # oldest in page

            raw = await self._r.lrange(key, start_idx, stop_idx)
            events = []
            for item in reversed(raw):
                decoded = item.decode() if isinstance(item, bytes) else item
                events.append(AuditEvent.from_dict(json.loads(decoded)))
            return events
        except Exception:
            logger.warning(
                "Audit log read failed for customer=%s", customer_id,
                exc_info=True,
            )
            return []
