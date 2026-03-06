"""
Customer provisioning endpoint tests.

The endpoint wraps InfrastructureOrchestrator.provision_customer_environment.
On success it mints a JWT for the new customer and returns it — that's the
"something the customer can use to authenticate subsequent requests."

The orchestrator touches Docker, filesystem, Postgres. All mocked here.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


# --- Happy path ------------------------------------------------------------

class TestProvisionSuccess:
    def test_returns_201_with_customer_id_and_token(self, client, mock_orchestrator):
        resp = client.post(
            "/v1/customers",
            json={"customer_id": "cust_new", "tier": "professional"},
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["customer_id"] == "cust_new"
        assert body["tier"] == "professional"
        assert body["status"] == "healthy"
        assert body["token"]
        assert body["created_at"]

    def test_calls_orchestrator_with_request_params(self, client, mock_orchestrator):
        client.post(
            "/v1/customers",
            json={"customer_id": "cust_xyz", "tier": "enterprise"},
        )

        mock_orchestrator.provision_customer_environment.assert_awaited_once()
        call = mock_orchestrator.provision_customer_environment.call_args
        assert call.kwargs["customer_id"] == "cust_xyz"
        assert call.kwargs["tier"] == "enterprise"

    def test_returned_token_is_usable_for_conversation_endpoint(self, client):
        """
        The real test: provision → get token → use token → EA responds.
        Closes the loop on "something the customer can use to authenticate."
        """
        prov_resp = client.post(
            "/v1/customers",
            json={"customer_id": "cust_loop", "tier": "basic"},
        )
        assert prov_resp.status_code == 201
        token = prov_resp.json()["token"]

        # Use the token on the authenticated conversation endpoint
        conv_resp = client.post(
            "/v1/conversations/message",
            json={"message": "hello", "channel": "chat"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert conv_resp.status_code == 200
        # The token's sub claim matches the provisioned customer
        assert conv_resp.json()["customer_id"] == "cust_loop"

    def test_token_is_scoped_to_provisioned_customer_not_request_body(self, client, mock_orchestrator):
        """
        The token's subject must come from what the orchestrator actually
        provisioned — not what the client asked for. If the orchestrator
        normalizes the ID, the token must reflect that.
        """
        env = MagicMock()
        env.customer_id = "cust_normalized"  # orchestrator changed it
        env.tier = "basic"
        env.status = MagicMock(value="healthy")
        env.created_at = MagicMock(isoformat=MagicMock(return_value="2026-01-01T00:00:00"))
        mock_orchestrator.provision_customer_environment.side_effect = None
        mock_orchestrator.provision_customer_environment.return_value = env

        resp = client.post("/v1/customers", json={"customer_id": "CUST_RAW", "tier": "basic"})
        assert resp.status_code == 201
        assert resp.json()["customer_id"] == "cust_normalized"

        from src.api.auth import decode_token
        token_cust = decode_token(
            resp.json()["token"],
            secret=client.app.state.jwt_secret,
        )
        assert token_cust == "cust_normalized"

    def test_tier_defaults_to_professional(self, client, mock_orchestrator):
        client.post("/v1/customers", json={"customer_id": "cust_default"})
        call = mock_orchestrator.provision_customer_environment.call_args
        assert call.kwargs["tier"] == "professional"


# --- Failure paths ---------------------------------------------------------

class TestProvisionFailure:
    def test_orchestrator_exception_returns_503(self, client, mock_orchestrator):
        mock_orchestrator.provision_customer_environment.side_effect = RuntimeError(
            "docker daemon unreachable"
        )

        resp = client.post("/v1/customers", json={"customer_id": "cust_fail"})

        assert resp.status_code == 503
        # The error envelope is ours — errors.py wraps HTTPException.detail
        # as {"error": ...}. No `or` escape hatch for format drift.
        assert resp.json() == {"error": "Provisioning failed"}

    def test_orchestrator_error_does_not_leak_internals(self, client, mock_orchestrator):
        mock_orchestrator.provision_customer_environment.side_effect = RuntimeError(
            "failed to bind /var/run/docker.sock"
        )

        resp = client.post("/v1/customers", json={"customer_id": "cust_x"})

        assert resp.status_code == 503
        assert "docker.sock" not in resp.text

    def test_failed_environment_status_returns_503(self, client, mock_orchestrator):
        """
        Orchestrator didn't raise, but returned status=failed. We must not
        mint a token for a broken environment.
        """
        env = MagicMock()
        env.customer_id = "cust_broken"
        env.tier = "basic"
        env.status = MagicMock(value="failed")
        env.created_at = MagicMock(isoformat=MagicMock(return_value="2026-01-01T00:00:00"))
        mock_orchestrator.provision_customer_environment.side_effect = None
        mock_orchestrator.provision_customer_environment.return_value = env

        resp = client.post("/v1/customers", json={"customer_id": "cust_broken"})
        assert resp.status_code == 503
        assert "token" not in resp.json()

    def test_missing_customer_id_returns_422(self, client):
        resp = client.post("/v1/customers", json={"tier": "basic"})
        assert resp.status_code == 422

    def test_invalid_tier_returns_422(self, client):
        resp = client.post("/v1/customers", json={"customer_id": "c", "tier": "platinum"})
        assert resp.status_code == 422

    def test_no_orchestrator_configured_returns_503(self, jwt_secret, mock_ea_factory):
        """If orchestrator isn't wired, provisioning is unavailable."""
        from src.api.app import create_app
        from src.api.dependencies import EAPool

        app = create_app(
            ea_pool=EAPool(ea_factory=mock_ea_factory),
            orchestrator=None,
            jwt_secret=jwt_secret,
        )
        client = TestClient(app)

        resp = client.post("/v1/customers", json={"customer_id": "cust_x"})
        assert resp.status_code == 503
