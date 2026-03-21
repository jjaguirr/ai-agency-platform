"""
Daily activity counters for the dashboard's "today at a glance" card.

Redis keys:
    activity:{customer_id}:messages:{YYYY-MM-DD}
    activity:{customer_id}:delegation:{domain}:{YYYY-MM-DD}

48h TTL — mirrors ProactiveStateStore.increment_daily_count. Generous
enough to survive timezone skew (a customer whose "today" is UTC-tomorrow
still reads the right key) and self-cleaning so there's no key-reaper job.

Proactive trigger counts are NOT here — ProactiveStateStore already owns
those. The activity endpoint reads from both.

All writers are fire-and-forget: the conversations route wraps these in
try/except so a Redis blip never costs the customer their reply.
"""
from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)

_TTL = 48 * 3600

# Fixed domain list. These are the only specialist modules that exist;
# get_today iterates this rather than SCAN-ing Redis (SCAN is O(n) over
# the whole keyspace and interacts badly with a shared db 0). If a fifth
# specialist lands, add it here.
_DOMAINS = ("finance", "scheduling", "social_media", "workflows")


def _messages_key(customer_id: str, d: date) -> str:
    return f"activity:{customer_id}:messages:{d.isoformat()}"


def _delegation_key(customer_id: str, domain: str, d: date) -> str:
    return f"activity:{customer_id}:delegation:{domain}:{d.isoformat()}"


async def incr_messages(redis, customer_id: str) -> None:
    key = _messages_key(customer_id, date.today())
    await redis.incr(key)
    await redis.expire(key, _TTL)


async def incr_delegation(redis, customer_id: str, domain: str) -> None:
    key = _delegation_key(customer_id, domain, date.today())
    await redis.incr(key)
    await redis.expire(key, _TTL)


async def get_today(redis, customer_id: str) -> dict:
    """
    Single-round-trip read of every counter that matters for today.

    Returns {"messages": int, "delegations": {domain: int, ...}}.
    Domains with zero delegations are omitted — the dashboard treats
    missing-key as zero, no need to pad the wire format.

    Any Redis failure → zeros. This is a dashboard nicety, not an SLA.
    """
    today = date.today()
    msg_key = _messages_key(customer_id, today)
    deleg_keys = [_delegation_key(customer_id, d, today) for d in _DOMAINS]

    try:
        vals = await redis.mget(msg_key, *deleg_keys)
    except Exception as e:
        logger.debug("activity counter read failed for %s: %s", customer_id, e)
        return {"messages": 0, "delegations": {}}

    # mget returns None for absent keys; bytes or str for present ones.
    def _int(v) -> int:
        return int(v) if v else 0

    messages = _int(vals[0])
    delegations = {
        domain: _int(v)
        for domain, v in zip(_DOMAINS, vals[1:])
        if v  # drop zero-count domains
    }
    return {"messages": messages, "delegations": delegations}
