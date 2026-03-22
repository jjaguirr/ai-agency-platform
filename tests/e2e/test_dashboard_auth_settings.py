"""E2E: Dashboard auth (login) and settings CRUD.

Login trades a pre-shared secret for a JWT. Settings persist to Redis
and are tenant-isolated.
"""
import pytest

from src.api.auth import create_token


@pytest.mark.e2e
class TestLogin:
    """POST /v1/auth/login trades a pre-shared secret for a JWT."""

    async def test_valid_credentials(self, client, fake_redis):
        await fake_redis.set("auth:cust_login:secret", "s3cret-phrase-long-enough")

        resp = await client.post(
            "/v1/auth/login",
            json={"customer_id": "cust_login", "secret": "s3cret-phrase-long-enough"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["customer_id"] == "cust_login"
        token = body["token"]
        parts = token.split(".")
        assert len(parts) == 3, "token should be a JWT with three dot-separated segments"
        assert all(len(p) > 0 for p in parts)

    async def test_wrong_secret(self, client, fake_redis):
        await fake_redis.set("auth:cust_login:secret", "correct-secret")

        resp = await client.post(
            "/v1/auth/login",
            json={"customer_id": "cust_login", "secret": "wrong-secret"},
        )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"

    async def test_unknown_customer(self, client):
        """Same 'Invalid credentials' as wrong_secret — prevents customer ID enumeration."""
        resp = await client.post(
            "/v1/auth/login",
            json={"customer_id": "cust_ghost", "secret": "any"},
        )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"

    async def test_login_returns_usable_token(self, client, fake_redis):
        """The returned token works for authenticated endpoints."""
        await fake_redis.set("auth:cust_login:secret", "my-secret-value")

        login_resp = await client.post(
            "/v1/auth/login",
            json={"customer_id": "cust_login", "secret": "my-secret-value"},
        )
        token = login_resp.json()["token"]

        resp = await client.get(
            "/v1/settings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200


@pytest.mark.e2e
class TestTokenExpiry:
    """Expired JWTs are rejected by the auth middleware."""

    async def test_expired_token_rejected(self, client):
        token = create_token("cust_a", expires_in=-1)

        resp = await client.get(
            "/v1/settings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401


@pytest.mark.e2e
class TestSettings:
    """GET/PUT /v1/settings — defaults, round-trip persistence, tenant isolation."""

    async def test_default_settings(self, client, headers_a):
        resp = await client.get("/v1/settings", headers=headers_a)

        assert resp.status_code == 200
        body = resp.json()
        # Verify all defaults from Settings model
        assert body["working_hours"]["start"] == "09:00"
        assert body["working_hours"]["end"] == "18:00"
        assert body["working_hours"]["timezone"] == "UTC"
        assert body["briefing"]["enabled"] is True
        assert body["briefing"]["time"] == "08:00"
        assert body["proactive"]["priority_threshold"] == "MEDIUM"
        assert body["proactive"]["daily_cap"] == 5
        assert body["proactive"]["idle_nudge_minutes"] == 120
        assert body["personality"]["tone"] == "professional"
        assert body["personality"]["language"] == "en"
        assert body["personality"]["name"] == "Assistant"
        assert body["connected_services"]["calendar"] is False
        assert body["connected_services"]["n8n"] is False

    async def test_put_get_roundtrip(self, client, headers_a):
        settings = {
            "working_hours": {"start": "07:00", "end": "20:00", "timezone": "US/Pacific"},
            "briefing": {"enabled": False, "time": "06:30"},
            "proactive": {
                "priority_threshold": "HIGH",
                "daily_cap": 10,
                "idle_nudge_minutes": 45,
            },
            "personality": {
                "tone": "friendly",
                "language": "en",
                "name": "Max",
            },
            "connected_services": {"calendar": True, "n8n": False},
        }

        put_resp = await client.put(
            "/v1/settings", json=settings, headers=headers_a,
        )
        assert put_resp.status_code == 200
        # PUT returns the saved body
        assert put_resp.json()["personality"]["name"] == "Max"

        get_resp = await client.get("/v1/settings", headers=headers_a)
        assert get_resp.status_code == 200
        body = get_resp.json()
        # Verify every submitted field round-trips
        assert body["working_hours"]["start"] == "07:00"
        assert body["working_hours"]["end"] == "20:00"
        assert body["working_hours"]["timezone"] == "US/Pacific"
        assert body["briefing"]["enabled"] is False
        assert body["briefing"]["time"] == "06:30"
        assert body["proactive"]["priority_threshold"] == "HIGH"
        assert body["proactive"]["daily_cap"] == 10
        assert body["proactive"]["idle_nudge_minutes"] == 45
        assert body["personality"]["tone"] == "friendly"
        assert body["personality"]["name"] == "Max"
        assert body["connected_services"]["calendar"] is True
        assert body["connected_services"]["n8n"] is False

    async def test_settings_tenant_isolation(self, client, headers_a, headers_b):
        """customer_a's settings don't leak to customer_b."""
        custom = {
            "working_hours": {"start": "05:00", "end": "23:00", "timezone": "UTC"},
            "briefing": {"enabled": False, "time": "04:00"},
            "proactive": {
                "priority_threshold": "LOW",
                "daily_cap": 50,
                "idle_nudge_minutes": 120,
            },
            "personality": {
                "tone": "concise",
                "language": "es",
                "name": "Luna",
            },
            "connected_services": {"calendar": True, "n8n": True},
        }

        put_resp = await client.put("/v1/settings", json=custom, headers=headers_a)
        assert put_resp.status_code == 200

        # customer_b gets defaults, not A's settings
        resp = await client.get("/v1/settings", headers=headers_b)
        body = resp.json()
        assert body["working_hours"]["start"] == "09:00"
        assert body["personality"]["name"] == "Assistant"
        assert body["personality"]["tone"] == "professional"
        assert body["personality"]["language"] == "en"
        assert body["briefing"]["enabled"] is True
