"""Tests for GET /v1/analytics route."""
import os

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault(
    "JWT_SECRET", "test-secret-do-not-use-in-prod-32-chars-min-xxxxxxxx"
)

from src.api.app import create_app
from src.api.auth import create_token
from src.api.ea_registry import EARegistry


def _app(analytics_service=None):
    return create_app(
        ea_registry=EARegistry(factory=lambda cid: AsyncMock()),
        orchestrator=AsyncMock(),
        whatsapp_manager=MagicMock(),
        redis_client=AsyncMock(),
        analytics_service=analytics_service,
    )


class TestAnalyticsAuth:
    def test_401_without_token(self):
        client = TestClient(_app())
        resp = client.get("/v1/analytics")
        assert resp.status_code == 401

    def test_401_with_expired_token(self):
        client = TestClient(_app())
        tok = create_token("cust_a", expires_in=-1)
        resp = client.get(
            "/v1/analytics",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp.status_code == 401


class TestAnalyticsParams:
    def test_default_period_is_7d(self):
        svc = AsyncMock()
        svc.get_analytics = AsyncMock(return_value={
            "period": {"start": "2026-03-14T00:00:00Z", "end": "2026-03-21T00:00:00Z"},
            "overview": {
                "total_conversations": 0,
                "total_delegations": 0,
                "avg_messages_per_conversation": 0.0,
                "escalation_rate": 0.0,
                "unresolved_rate": 0.0,
            },
            "topics": {"breakdown": []},
            "specialist_performance": [],
            "trends": {"conversations_by_day": [], "delegations_by_day": []},
        })
        client = TestClient(_app(svc))
        tok = create_token("cust_a")

        resp = client.get(
            "/v1/analytics",
            headers={"Authorization": f"Bearer {tok}"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert "overview" in body
        assert "topics" in body
        assert "specialist_performance" in body
        assert "trends" in body

    def test_invalid_period_returns_422(self):
        client = TestClient(_app())
        tok = create_token("cust_a")

        resp = client.get(
            "/v1/analytics?period=invalid",
            headers={"Authorization": f"Bearer {tok}"},
        )

        assert resp.status_code == 422

    def test_custom_period_requires_dates(self):
        svc = AsyncMock()
        svc.get_analytics = AsyncMock(side_effect=ValueError("start and end required"))
        client = TestClient(_app(svc))
        tok = create_token("cust_a")

        resp = client.get(
            "/v1/analytics?period=custom",
            headers={"Authorization": f"Bearer {tok}"},
        )

        assert resp.status_code == 400


class TestAnalyticsNoService:
    def test_returns_503_when_service_unavailable(self):
        client = TestClient(_app(analytics_service=None))
        tok = create_token("cust_a")

        resp = client.get(
            "/v1/analytics",
            headers={"Authorization": f"Bearer {tok}"},
        )

        assert resp.status_code == 503
