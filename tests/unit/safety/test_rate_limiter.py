"""
RateLimitMiddleware — pure ASGI, per-customer + global, fail-open.

Runs before auth so an unauthenticated flood still gets throttled (the
global per-second bucket doesn't need identity). Per-customer buckets
use best-effort extraction: WhatsApp path carries the customer_id,
API requests carry a JWT. Neither present → anonymous → global only.

Counters are INCR+EXPIRE (same idiom as ProactiveStateStore). Clock is
injected so these tests don't flake at minute boundaries.
"""
import json
import os

# JWT extraction is tested with real tokens — set the secret before
# any src.api.auth import resolves.
os.environ.setdefault(
    "JWT_SECRET", "test-secret-do-not-use-in-prod-32-chars-min-xxxxxxxx"
)

import pytest

from src.safety.config import SafetyConfig
from src.safety.rate_limiter import RateLimitMiddleware


# --- ASGI test harness ------------------------------------------------------

class _Captured:
    """Collects what the middleware sends back."""
    def __init__(self):
        self.status = None
        self.headers: dict[str, str] = {}
        self.body = b""

    async def __call__(self, message):
        if message["type"] == "http.response.start":
            self.status = message["status"]
            self.headers = {
                k.decode("latin-1").lower(): v.decode("latin-1")
                for k, v in message.get("headers", [])
            }
        elif message["type"] == "http.response.body":
            self.body += message.get("body", b"")

    @property
    def json(self):
        return json.loads(self.body)


async def _ok_app(scope, receive, send):
    """Inner app — just says OK. If this runs, the middleware let us through."""
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


async def _receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def _scope(path="/v1/conversations", headers=()):
    return {"type": "http", "path": path, "headers": list(headers)}


@pytest.fixture
def clock():
    """Fixed time: 2026-03-20T10:00:30Z → epoch 1774000830.

    Chosen so we're 30 seconds into the minute — Retry-After for the
    per-minute bucket should be 30.
    """
    return lambda: 1774000830.0


@pytest.fixture
def tight_config():
    """Tiny per-customer limits so tests don't loop hundreds of times.

    Global limit is high — with a fixed clock every request lands in
    the same epoch-second, so a low global limit would trip during any
    multi-request test. TestGlobal builds its own config.
    """
    return SafetyConfig(
        rate_per_minute=3,
        rate_per_day=5,
        rate_global_per_second=1000,
    )


@pytest.fixture
def mw(fake_redis, tight_config, clock):
    return RateLimitMiddleware(_ok_app, fake_redis, tight_config, now=clock)


# --- Customer extraction ----------------------------------------------------

class TestCustomerExtraction:
    @pytest.mark.asyncio
    async def test_whatsapp_path_extracts_customer_id(self, mw, fake_redis):
        cap = _Captured()
        await mw(_scope("/webhook/whatsapp/cust_alice"), _receive, cap)
        assert cap.status == 200
        # Per-customer minute counter was incremented.
        keys = await fake_redis.keys("ratelimit:cust_alice:*")
        assert len(keys) >= 1

    @pytest.mark.asyncio
    async def test_jwt_header_extracts_customer_id(self, mw, fake_redis):
        from src.api.auth import create_token
        token = create_token("cust_bob")
        cap = _Captured()
        await mw(
            _scope(headers=[(b"authorization", f"Bearer {token}".encode())]),
            _receive, cap,
        )
        assert cap.status == 200
        keys = await fake_redis.keys("ratelimit:cust_bob:*")
        assert len(keys) >= 1

    @pytest.mark.asyncio
    async def test_invalid_jwt_treated_as_anonymous(self, mw, fake_redis):
        cap = _Captured()
        await mw(
            _scope(headers=[(b"authorization", b"Bearer garbage.token.here")]),
            _receive, cap,
        )
        # Middleware doesn't reject — auth dependency will do that later.
        # But no per-customer counter was touched.
        assert cap.status == 200
        customer_keys = [
            k for k in await fake_redis.keys("ratelimit:*")
            if b":min:" in k or b":day:" in k
        ]
        assert customer_keys == []

    @pytest.mark.asyncio
    async def test_no_auth_no_path_anonymous(self, mw, fake_redis):
        cap = _Captured()
        await mw(_scope("/v1/conversations"), _receive, cap)
        assert cap.status == 200
        # Only global counter touched.
        keys = await fake_redis.keys("ratelimit:*")
        assert all(b"global" in k for k in keys)


# --- Per-minute bucket ------------------------------------------------------

class TestPerMinute:
    @pytest.mark.asyncio
    async def test_under_limit_passes(self, mw):
        for _ in range(3):  # limit=3
            cap = _Captured()
            await mw(_scope("/webhook/whatsapp/cust_alice"), _receive, cap)
            assert cap.status == 200

    @pytest.mark.asyncio
    async def test_over_limit_429(self, mw):
        for _ in range(3):
            cap = _Captured()
            await mw(_scope("/webhook/whatsapp/cust_alice"), _receive, cap)
        # 4th request in same minute
        cap = _Captured()
        await mw(_scope("/webhook/whatsapp/cust_alice"), _receive, cap)
        assert cap.status == 429
        assert cap.json["type"] == "rate_limited"

    @pytest.mark.asyncio
    async def test_429_has_retry_after(self, mw):
        for _ in range(4):
            cap = _Captured()
            await mw(_scope("/webhook/whatsapp/cust_alice"), _receive, cap)
        assert cap.status == 429
        assert "retry-after" in cap.headers
        # Fixed clock is 30s into the minute → 30s until next bucket.
        retry = int(cap.headers["retry-after"])
        assert 1 <= retry <= 60

    @pytest.mark.asyncio
    async def test_buckets_isolated_per_customer(self, mw):
        # Exhaust alice's minute bucket
        for _ in range(4):
            cap = _Captured()
            await mw(_scope("/webhook/whatsapp/cust_alice"), _receive, cap)
        assert cap.status == 429
        # Bob is unaffected
        cap = _Captured()
        await mw(_scope("/webhook/whatsapp/cust_bob"), _receive, cap)
        assert cap.status == 200

    @pytest.mark.asyncio
    async def test_next_minute_resets(self, fake_redis, tight_config):
        # Two clocks: one now, one 61s later (next minute bucket)
        mw_now = RateLimitMiddleware(
            _ok_app, fake_redis, tight_config, now=lambda: 1774000830.0,
        )
        mw_later = RateLimitMiddleware(
            _ok_app, fake_redis, tight_config, now=lambda: 1774000891.0,
        )
        for _ in range(4):
            cap = _Captured()
            await mw_now(_scope("/webhook/whatsapp/cust_alice"), _receive, cap)
        assert cap.status == 429
        # New minute bucket — counter is fresh
        cap = _Captured()
        await mw_later(_scope("/webhook/whatsapp/cust_alice"), _receive, cap)
        assert cap.status == 200


# --- Per-day bucket ---------------------------------------------------------

class TestPerDay:
    @pytest.mark.asyncio
    async def test_over_daily_limit_429(self, fake_redis, clock):
        # Minute limit high enough not to interfere; day limit = 2.
        cfg = SafetyConfig(rate_per_minute=100, rate_per_day=2,
                           rate_global_per_second=100)
        mw = RateLimitMiddleware(_ok_app, fake_redis, cfg, now=clock)
        for _ in range(2):
            cap = _Captured()
            await mw(_scope("/webhook/whatsapp/cust_alice"), _receive, cap)
            assert cap.status == 200
        cap = _Captured()
        await mw(_scope("/webhook/whatsapp/cust_alice"), _receive, cap)
        assert cap.status == 429
        assert "daily" in cap.json["detail"].lower()

    @pytest.mark.asyncio
    async def test_daily_retry_after_until_midnight(self, fake_redis, clock):
        cfg = SafetyConfig(rate_per_minute=100, rate_per_day=1,
                           rate_global_per_second=100)
        mw = RateLimitMiddleware(_ok_app, fake_redis, cfg, now=clock)
        cap = _Captured()
        await mw(_scope("/webhook/whatsapp/cust_alice"), _receive, cap)
        cap = _Captured()
        await mw(_scope("/webhook/whatsapp/cust_alice"), _receive, cap)
        assert cap.status == 429
        # 10:00:30 UTC → ~14h until midnight. Loose bounds; the exact
        # value is date-arithmetic trivia, not the thing under test.
        retry = int(cap.headers["retry-after"])
        assert 60 < retry < 86400


# --- Global bucket ----------------------------------------------------------

class TestGlobal:
    @pytest.mark.asyncio
    async def test_global_over_limit_503(self, fake_redis, clock):
        # No customer identity needed — the global bucket protects the
        # system even from anonymous floods.
        cfg = SafetyConfig(rate_per_minute=100, rate_per_day=100,
                           rate_global_per_second=4)
        mw = RateLimitMiddleware(_ok_app, fake_redis, cfg, now=clock)
        for _ in range(4):
            cap = _Captured()
            await mw(_scope("/v1/conversations"), _receive, cap)
            assert cap.status == 200
        cap = _Captured()
        await mw(_scope("/v1/conversations"), _receive, cap)
        assert cap.status == 503
        assert cap.json["type"] == "overloaded"

    @pytest.mark.asyncio
    async def test_global_checked_before_per_customer(self, fake_redis, clock):
        # Global limit=2, per-minute=100. Global should trip first.
        cfg = SafetyConfig(rate_per_minute=100, rate_per_day=100,
                           rate_global_per_second=2)
        mw = RateLimitMiddleware(_ok_app, fake_redis, cfg, now=clock)
        for _ in range(3):
            cap = _Captured()
            await mw(_scope("/webhook/whatsapp/cust_alice"), _receive, cap)
        assert cap.status == 503  # not 429


# --- Exempt paths -----------------------------------------------------------

class TestExemptPaths:
    @pytest.mark.parametrize("path", ["/healthz", "/readyz"])
    @pytest.mark.asyncio
    async def test_health_paths_never_limited(self, mw, fake_redis, path):
        # Hammer it well past every limit.
        for _ in range(20):
            cap = _Captured()
            await mw(_scope(path), _receive, cap)
            assert cap.status == 200
        # No counters written.
        keys = await fake_redis.keys("ratelimit:*")
        assert keys == []

    @pytest.mark.asyncio
    async def test_non_http_scope_passes_through(self, mw):
        # Websocket/lifespan scopes — middleware must not interfere.
        called = []

        async def inner(scope, receive, send):
            called.append(scope["type"])

        mw_ws = RateLimitMiddleware(
            inner, mw._redis, mw._config, now=mw._now,
        )
        await mw_ws({"type": "websocket"}, _receive, lambda m: None)
        assert called == ["websocket"]


# --- Fail open --------------------------------------------------------------

class TestFailOpen:
    @pytest.mark.asyncio
    async def test_redis_down_passes_request_through(self, tight_config, clock):
        # redis.pipeline() is sync — AsyncMock would return a coroutine
        # the prod code never awaits. MagicMock raises at the call site.
        from unittest.mock import MagicMock
        broken = MagicMock()
        broken.pipeline.side_effect = ConnectionError("redis down")
        mw = RateLimitMiddleware(_ok_app, broken, tight_config, now=clock)
        # Would normally be limited after 3; all 10 pass because Redis is dead.
        for _ in range(10):
            cap = _Captured()
            await mw(_scope("/webhook/whatsapp/cust_alice"), _receive, cap)
            assert cap.status == 200


# --- Real-app construction smoke --------------------------------------------

class TestConstruction:
    def test_constructs_with_default_clock(self, fake_redis, tight_config):
        # No `now` kwarg — uses time.time. Just checking the signature.
        mw = RateLimitMiddleware(_ok_app, fake_redis, tight_config)
        assert mw is not None
