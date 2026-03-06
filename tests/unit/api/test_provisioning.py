"""
Customer provisioning: POST /v1/customers/provision

Wraps InfrastructureOrchestrator.provision_customer_environment. No auth
required — this *creates* the auth token. Request body is optional; if
customer_id is omitted we mint one. Response includes a JWT the customer
can use immediately.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from src.api.app import create_app
from src.api.auth import decode_token
from src.api.ea_registry import EARegistry


def _app(orchestrator):
    return create_app(
        ea_registry=EARegistry(factory=MagicMock()),
        orchestrator=orchestrator,
        whatsapp_manager=MagicMock(),
        redis_client=AsyncMock(),
    )


class TestProvisioningHappyPath:
    def test_returns_customer_id_and_token(self, mock_orchestrator):
        client = TestClient(_app(mock_orchestrator))

        resp = client.post("/v1/customers/provision",
                           json={"tier": "professional"})

        assert resp.status_code == 201
        body = resp.json()
        assert body["customer_id"]
        assert body["token"]
        assert body["tier"] == "professional"

    def test_returned_token_carries_customer_id(self, mock_orchestrator):
        client = TestClient(_app(mock_orchestrator))

        resp = client.post("/v1/customers/provision",
                           json={"tier": "basic"})

        body = resp.json()
        payload = decode_token(body["token"])
        assert payload["customer_id"] == body["customer_id"]

    def test_orchestrator_called_with_request_params(self, mock_orchestrator):
        client = TestClient(_app(mock_orchestrator))

        client.post("/v1/customers/provision",
                    json={"tier": "enterprise",
                          "customer_id": "cust_chosen"})

        call = mock_orchestrator.provision_customer_environment.call_args
        assert call.kwargs["customer_id"] == "cust_chosen"
        assert call.kwargs["tier"] == "enterprise"

    def test_customer_id_generated_when_omitted(self, mock_orchestrator):
        client = TestClient(_app(mock_orchestrator))

        resp = client.post("/v1/customers/provision", json={"tier": "basic"})

        body = resp.json()
        assert body["customer_id"]  # non-empty auto-generated
        # Verify orchestrator got the generated ID
        call = mock_orchestrator.provision_customer_environment.call_args
        assert call.kwargs["customer_id"] == body["customer_id"]

    def test_default_tier_when_body_empty(self, mock_orchestrator):
        client = TestClient(_app(mock_orchestrator))

        resp = client.post("/v1/customers/provision", json={})

        assert resp.status_code == 201
        # Default tier is orchestrator's default: professional
        assert resp.json()["tier"] == "professional"


class TestProvisioningValidation:
    def test_invalid_tier_returns_422(self, mock_orchestrator):
        client = TestClient(_app(mock_orchestrator))

        resp = client.post("/v1/customers/provision",
                           json={"tier": "ultra_premium_plus"})

        assert resp.status_code == 422

    @pytest.mark.parametrize("bad_id", [
        "../../../etc/passwd",       # path traversal
        "cust; rm -rf /",            # shell metachar
        "Cust_Upper",                # uppercase
        "ab",                        # too short
        "x" * 100,                   # too long
        "-starts-with-dash",         # leading special
        "has spaces in it",          # whitespace
    ])
    def test_malicious_customer_id_rejected(self, mock_orchestrator, bad_id):
        """
        customer_id flows into Docker network/container names and volume
        paths. Anything outside [a-z0-9_-]{3,48} must be rejected before
        it reaches the orchestrator.
        """
        client = TestClient(_app(mock_orchestrator))

        resp = client.post(
            "/v1/customers/provision",
            json={"tier": "basic", "customer_id": bad_id},
        )

        assert resp.status_code == 422
        # Orchestrator must NOT have been called with the bad input
        mock_orchestrator.provision_customer_environment.assert_not_called()

    def test_valid_customer_id_accepted(self, mock_orchestrator):
        client = TestClient(_app(mock_orchestrator))

        resp = client.post(
            "/v1/customers/provision",
            json={"tier": "basic", "customer_id": "acme-corp_2026"},
        )

        assert resp.status_code == 201


class TestProvisioningErrors:
    def test_orchestrator_value_error_returns_400_without_leak(self):
        """
        Orchestrator raises ValueError for bad input — map to 400.
        We do NOT echo the orchestrator's message: it wasn't written
        with a "safe for clients" contract and could carry internals.
        """
        orch = AsyncMock()
        orch.provision_customer_environment = AsyncMock(
            side_effect=ValueError("docker network customer-x-network exists at /var/lib/docker"))
        client = TestClient(_app(orch))

        resp = client.post("/v1/customers/provision",
                           json={"tier": "basic"})

        assert resp.status_code == 400
        body = resp.json()
        assert body["type"] == "bad_request"
        assert "/var/lib/docker" not in body["detail"]
        assert body["detail"] == "Provisioning request rejected. Check tier and parameters."

    def test_orchestrator_runtime_error_returns_503(self):
        """Deployment failure (Docker down, etc.) — map to 503."""
        orch = AsyncMock()
        orch.provision_customer_environment = AsyncMock(
            side_effect=RuntimeError("Deployment failed"))
        client = TestClient(_app(orch))

        resp = client.post("/v1/customers/provision",
                           json={"tier": "basic"})

        assert resp.status_code == 503
        body = resp.json()
        assert "Traceback" not in str(body)

    def test_provisioning_does_not_require_auth(self, mock_orchestrator):
        """You can't auth before you have a token — that's what this makes."""
        client = TestClient(_app(mock_orchestrator))

        resp = client.post("/v1/customers/provision",
                           json={"tier": "basic"})
        # No Authorization header, and that's fine.
        assert resp.status_code == 201
