"""
Analytics endpoint: GET /v1/analytics

Aggregates derived conversation intelligence for a time window.
IntelligenceRepository does the heavy lifting — each field in the
response maps to one repo method. The route's own job is window
arithmetic (range=7d → since/until) and trend comparison (current
vs. the preceding window of equal length).

Repo is mocked; IntelligenceRepository unit tests already cover the
SQL.
"""
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from src.api.app import create_app
from src.api.auth import create_token
from src.api.ea_registry import EARegistry


def _app(intel_repo):
    return create_app(
        ea_registry=EARegistry(factory=lambda cid: AsyncMock()),
        orchestrator=AsyncMock(),
        whatsapp_manager=MagicMock(),
        redis_client=AsyncMock(),
        intelligence_repo=intel_repo,
    )


@pytest.fixture
def intel_repo():
    r = AsyncMock()
    r.topic_breakdown = AsyncMock(return_value=[])
    r.specialist_metrics = AsyncMock(return_value=[])
    r.quality_counts = AsyncMock(return_value={})
    r.conversation_count = AsyncMock(return_value=0)
    return r


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {create_token('cust_ana')}"}


# ─── auth + tenant ─────────────────────────────────────────────────────────

class TestAuth:
    def test_401_without_token(self, intel_repo):
        client = TestClient(_app(intel_repo))
        resp = client.get("/v1/analytics")
        assert resp.status_code == 401

    def test_repo_called_with_token_customer_id(self, intel_repo):
        client = TestClient(_app(intel_repo))
        tok = create_token("cust_from_jwt")

        client.get(
            "/v1/analytics?range=7d",
            headers={"Authorization": f"Bearer {tok}"},
        )

        # Every repo method must receive the JWT customer_id, not
        # anything from the request body or query string.
        for m in (intel_repo.topic_breakdown, intel_repo.specialist_metrics,
                  intel_repo.quality_counts):
            assert m.await_args.kwargs["customer_id"] == "cust_from_jwt"


# ─── time window ───────────────────────────────────────────────────────────

class TestWindow:
    def test_range_7d(self, intel_repo, auth_headers):
        client = TestClient(_app(intel_repo))
        before = datetime.now(timezone.utc)

        client.get("/v1/analytics?range=7d", headers=auth_headers)

        after = datetime.now(timezone.utc)
        kw = intel_repo.topic_breakdown.await_args.kwargs
        # until ≈ now
        assert before <= kw["until"] <= after
        # since = until - 7 days
        assert kw["until"] - kw["since"] == timedelta(days=7)

    def test_range_24h(self, intel_repo, auth_headers):
        client = TestClient(_app(intel_repo))
        client.get("/v1/analytics?range=24h", headers=auth_headers)
        kw = intel_repo.topic_breakdown.await_args.kwargs
        assert kw["until"] - kw["since"] == timedelta(hours=24)

    def test_range_30d(self, intel_repo, auth_headers):
        client = TestClient(_app(intel_repo))
        client.get("/v1/analytics?range=30d", headers=auth_headers)
        kw = intel_repo.topic_breakdown.await_args.kwargs
        assert kw["until"] - kw["since"] == timedelta(days=30)

    def test_default_range_is_7d(self, intel_repo, auth_headers):
        client = TestClient(_app(intel_repo))
        client.get("/v1/analytics", headers=auth_headers)
        kw = intel_repo.topic_breakdown.await_args.kwargs
        assert kw["until"] - kw["since"] == timedelta(days=7)

    def test_custom_since_until(self, intel_repo, auth_headers):
        client = TestClient(_app(intel_repo))
        client.get(
            "/v1/analytics"
            "?since=2026-03-01T00:00:00Z"
            "&until=2026-03-15T00:00:00Z",
            headers=auth_headers,
        )
        kw = intel_repo.topic_breakdown.await_args.kwargs
        assert kw["since"] == datetime(2026, 3, 1, tzinfo=timezone.utc)
        assert kw["until"] == datetime(2026, 3, 15, tzinfo=timezone.utc)

    def test_invalid_range_422(self, intel_repo, auth_headers):
        client = TestClient(_app(intel_repo))
        resp = client.get("/v1/analytics?range=bogus", headers=auth_headers)
        assert resp.status_code == 422

    def test_window_echoed_in_response(self, intel_repo, auth_headers):
        client = TestClient(_app(intel_repo))
        resp = client.get("/v1/analytics?range=7d", headers=auth_headers)
        body = resp.json()
        assert "window" in body
        assert "since" in body["window"]
        assert "until" in body["window"]
        # Dashboard wants a human label for the picker
        assert body["window"]["label"] == "7d"


# ─── response shape ────────────────────────────────────────────────────────

class TestShape:
    def test_topics_pass_through(self, intel_repo, auth_headers):
        intel_repo.topic_breakdown.return_value = [
            {"label": "finance", "value": 12},
            {"label": "scheduling", "value": 5},
        ]
        client = TestClient(_app(intel_repo))

        resp = client.get("/v1/analytics?range=7d", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["topics"] == [
            {"label": "finance", "value": 12},
            {"label": "scheduling", "value": 5},
        ]

    def test_specialists_pass_through(self, intel_repo, auth_headers):
        intel_repo.specialist_metrics.return_value = [
            {"domain": "finance", "delegation_count": 20,
             "success_rate": 0.9, "avg_turns": 1.5, "confirmation_rate": 0.75},
        ]
        client = TestClient(_app(intel_repo))

        resp = client.get("/v1/analytics?range=7d", headers=auth_headers)

        spec = resp.json()["specialists"][0]
        assert spec["domain"] == "finance"
        assert spec["delegation_count"] == 20
        assert spec["success_rate"] == 0.9
        assert spec["avg_turns"] == 1.5
        assert spec["confirmation_rate"] == 0.75

    def test_quality_wraps_counts_and_total(self, intel_repo, auth_headers):
        intel_repo.quality_counts.return_value = {
            "escalation": 3, "unresolved": 7, "long": 2,
        }
        intel_repo.conversation_count.return_value = 50
        client = TestClient(_app(intel_repo))

        resp = client.get("/v1/analytics?range=7d", headers=auth_headers)

        q = resp.json()["quality"]
        assert q["total"] == 50
        assert q["flags"] == {"escalation": 3, "unresolved": 7, "long": 2}

    def test_empty_sections_are_empty_not_missing(self, intel_repo, auth_headers):
        # No data in the window → chart sections render empty, not explode.
        client = TestClient(_app(intel_repo))
        resp = client.get("/v1/analytics?range=7d", headers=auth_headers)
        body = resp.json()
        assert body["topics"] == []
        assert body["specialists"] == []
        assert body["quality"]["flags"] == {}
        assert body["quality"]["total"] == 0


# ─── trend ─────────────────────────────────────────────────────────────────

class TestTrend:
    def test_trend_compares_with_preceding_window(self, intel_repo, auth_headers):
        # conversation_count is called twice: current window, then the
        # window of equal length immediately before it.
        intel_repo.conversation_count = AsyncMock(side_effect=[10, 8])
        client = TestClient(_app(intel_repo))

        client.get("/v1/analytics?range=7d", headers=auth_headers)

        assert intel_repo.conversation_count.await_count == 2
        cur_kw = intel_repo.conversation_count.await_args_list[0].kwargs
        prev_kw = intel_repo.conversation_count.await_args_list[1].kwargs
        # Previous window abuts current: prev.until == cur.since
        assert prev_kw["until"] == cur_kw["since"]
        # Same width
        assert (prev_kw["until"] - prev_kw["since"]) == (cur_kw["until"] - cur_kw["since"])

    def test_trend_delta_pct(self, intel_repo, auth_headers):
        intel_repo.conversation_count = AsyncMock(side_effect=[10, 8])
        client = TestClient(_app(intel_repo))

        resp = client.get("/v1/analytics?range=7d", headers=auth_headers)

        t = resp.json()["trend"]["conversations"]
        assert t["current"] == 10
        assert t["previous"] == 8
        assert t["delta_pct"] == pytest.approx(25.0)  # (10-8)/8 * 100

    def test_trend_previous_zero_delta_none(self, intel_repo, auth_headers):
        intel_repo.conversation_count = AsyncMock(side_effect=[5, 0])
        client = TestClient(_app(intel_repo))

        resp = client.get("/v1/analytics?range=7d", headers=auth_headers)

        t = resp.json()["trend"]["conversations"]
        assert t["current"] == 5
        assert t["previous"] == 0
        assert t["delta_pct"] is None

    def test_trend_negative(self, intel_repo, auth_headers):
        intel_repo.conversation_count = AsyncMock(side_effect=[4, 10])
        client = TestClient(_app(intel_repo))

        resp = client.get("/v1/analytics?range=7d", headers=auth_headers)

        assert resp.json()["trend"]["conversations"]["delta_pct"] == pytest.approx(-60.0)


# ─── degraded ──────────────────────────────────────────────────────────────

class TestDegraded:
    def test_no_intel_repo_empty_response(self, auth_headers):
        # intelligence_repo not wired (pre-intelligence deployments,
        # tests that don't care) → empty shell, not 500.
        app = create_app(
            ea_registry=EARegistry(factory=lambda cid: AsyncMock()),
            orchestrator=AsyncMock(),
            whatsapp_manager=MagicMock(),
            redis_client=AsyncMock(),
            intelligence_repo=None,
        )
        client = TestClient(app)

        resp = client.get("/v1/analytics?range=7d", headers=auth_headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["topics"] == []
        assert body["specialists"] == []
