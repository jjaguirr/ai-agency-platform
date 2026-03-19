"""
WhatsApp webhook mounted into the main API.

Reuses the provider abstraction from src/communication/whatsapp/ — we're
NOT reimplementing signature validation or message parsing. The test
verifies the main API forwards webhook POSTs into that existing machinery.
"""
import asyncio
import logging

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, Mock, MagicMock

from src.api.app import create_app
from src.api.constants import EA_CALL_TIMEOUT
from src.api.ea_registry import EARegistry
from src.communication.whatsapp_manager import WhatsAppManager
from src.communication.whatsapp import (
    IncomingMessage, MessageStatus, SendResult, WhatsAppConfig,
)


def _manager_with_mock_provider(
    customer_id: str = "cust_wa",
    parse_result: list | None = None,
    signature_valid: bool = True,
) -> tuple[WhatsAppManager, Mock]:
    cfg = WhatsAppConfig(
        provider="twilio", from_number="+14155238886",
        credentials={"account_sid": "ACtest", "auth_token": "tok"},
        webhook_base_url="http://testserver",
    )
    mgr = WhatsAppManager()
    mgr.register_customer(customer_id, cfg)

    mock_provider = Mock()
    mock_provider.provider_name = "mock"
    mock_provider.validate_signature = Mock(return_value=signature_valid)
    mock_provider.parse_webhook = Mock(return_value=parse_result or [])
    mock_provider.send_text = AsyncMock(return_value=SendResult(
        provider_message_id="SM_reply", status=MessageStatus.QUEUED,
    ))
    mock_provider.fetch_status = AsyncMock(return_value=MessageStatus.UNKNOWN)

    original = mgr.get_channel

    async def patched(cid):
        ch = await original(cid)
        if ch is not None:
            ch._provider = mock_provider
        return ch

    mgr.get_channel = patched
    return mgr, mock_provider


def _app_with_manager(manager, ea_factory=None):
    factory = ea_factory or (lambda cid: MagicMock(
        handle_customer_interaction=AsyncMock(return_value="EA reply"),
    ))
    return create_app(
        ea_registry=EARegistry(factory=factory),
        orchestrator=AsyncMock(),
        whatsapp_manager=manager,
        redis_client=AsyncMock(),
    )


class TestWebhookRouting:
    def test_unknown_customer_404(self):
        mgr = WhatsAppManager()  # empty
        app = _app_with_manager(mgr)
        client = TestClient(app)

        resp = client.post("/webhook/whatsapp/ghost", content=b"x")
        assert resp.status_code == 404

    def test_invalid_signature_403_before_parse(self):
        mgr, provider = _manager_with_mock_provider(signature_valid=False)
        app = _app_with_manager(mgr)
        client = TestClient(app)

        resp = client.post(
            "/webhook/whatsapp/cust_wa",
            content=b"Body=hello",
            headers={"X-Twilio-Signature": "bad"},
        )

        assert resp.status_code == 403
        # parse_webhook must not have been called — signature check first
        assert provider.parse_webhook.call_count == 0

    def test_valid_signature_parses_and_invokes_ea(self):
        incoming = IncomingMessage(
            provider_message_id="SM123",
            from_number="+15551234567",
            to_number="+14155238886",
            body="Hello from WhatsApp",
        )
        mgr, provider = _manager_with_mock_provider(
            parse_result=[incoming], signature_valid=True,
        )

        # Track EA invocation
        ea_mock = AsyncMock()
        ea_mock.handle_customer_interaction = AsyncMock(
            return_value="Hi there!")
        app = _app_with_manager(mgr, ea_factory=lambda cid: ea_mock)
        client = TestClient(app)

        resp = client.post(
            "/webhook/whatsapp/cust_wa",
            content=b"Body=Hello+from+WhatsApp",
            headers={"X-Twilio-Signature": "valid_sig"},
        )

        assert resp.status_code == 200
        # Provider parse was hit
        provider.parse_webhook.assert_called_once()
        # EA was invoked with the incoming text
        ea_mock.handle_customer_interaction.assert_called_once()
        call_kwargs = ea_mock.handle_customer_interaction.call_args.kwargs
        assert call_kwargs["message"] == "Hello from WhatsApp"
        # Reply was sent
        provider.send_text.assert_called_once()

    def test_webhook_uses_per_customer_ea(self):
        """
        Webhook for cust_A uses cust_A's EA, not some shared/default one.
        This is the multi-tenant isolation check.
        """
        incoming = IncomingMessage(
            provider_message_id="SM1", from_number="+1555", to_number="+1415",
            body="hi",
        )
        mgr, _ = _manager_with_mock_provider(
            customer_id="cust_specific", parse_result=[incoming],
        )

        created_for: list[str] = []

        def spy_factory(cid):
            created_for.append(cid)
            m = AsyncMock()
            m.handle_customer_interaction = AsyncMock(return_value="ok")
            return m

        app = _app_with_manager(mgr, ea_factory=spy_factory)
        client = TestClient(app)

        client.post("/webhook/whatsapp/cust_specific", content=b"x")

        assert "cust_specific" in created_for


class TestWebhookTimeout:
    def test_timeout_returns_200_not_503(self):
        """
        Timed-out webhook must return 200 — Twilio interprets non-2xx
        as failure and retries, creating duplicate message storms.
        """
        incoming = IncomingMessage(
            provider_message_id="SM_slow", from_number="+1555",
            to_number="+1415", body="hello",
        )
        mgr, _ = _manager_with_mock_provider(parse_result=[incoming])

        async def hung_ea(*, message, channel, conversation_id):
            await asyncio.sleep(999)
            return "never"

        ea_mock = AsyncMock()
        ea_mock.handle_customer_interaction = AsyncMock(side_effect=hung_ea)
        app = _app_with_manager(mgr, ea_factory=lambda cid: ea_mock)
        client = TestClient(app)

        resp = client.post("/webhook/whatsapp/cust_wa", content=b"x")
        assert resp.status_code == 200  # NOT 503

    def test_timeout_is_logged(self, caplog):
        incoming = IncomingMessage(
            provider_message_id="SM_slow", from_number="+1555",
            to_number="+1415", body="hello",
        )
        mgr, _ = _manager_with_mock_provider(parse_result=[incoming])

        async def hung_ea(*, message, channel, conversation_id):
            await asyncio.sleep(999)
            return "never"

        ea_mock = AsyncMock()
        ea_mock.handle_customer_interaction = AsyncMock(side_effect=hung_ea)
        app = _app_with_manager(mgr, ea_factory=lambda cid: ea_mock)
        client = TestClient(app)

        with caplog.at_level(logging.ERROR):
            client.post("/webhook/whatsapp/cust_wa", content=b"x")

        assert any("timeout" in r.message.lower() or "timed out" in r.message.lower()
                    for r in caplog.records)

    def test_timeout_uses_shared_constant(self):
        """Timeout must match the conversations endpoint — shared constant."""
        assert EA_CALL_TIMEOUT == 60.0


class TestWebhookCustomerIdValidation:
    def test_path_traversal_rejected(self):
        """
        Starlette normalizes ../ sequences before routing, so this
        resolves to /etc/passwd → 404 (no route). The customer_id
        pattern validator never fires. Either 404 or 422 is acceptable
        — the important thing is the request never reaches the handler.
        """
        mgr = WhatsAppManager()
        app = _app_with_manager(mgr)
        client = TestClient(app)

        resp = client.post(
            "/webhook/whatsapp/../../etc/passwd",
            content=b"x",
        )
        assert resp.status_code in (404, 422)

    def test_empty_customer_id_rejected(self):
        """Empty string doesn't match the pattern."""
        mgr = WhatsAppManager()
        app = _app_with_manager(mgr)
        client = TestClient(app)

        resp = client.post("/webhook/whatsapp/", content=b"x")
        # FastAPI returns 404 for empty path segment, or 405 — either is fine
        assert resp.status_code in (404, 405, 422)

    def test_overlong_customer_id_rejected(self):
        mgr = WhatsAppManager()
        app = _app_with_manager(mgr)
        client = TestClient(app)

        resp = client.post(
            f"/webhook/whatsapp/{'a' * 100}",
            content=b"x",
        )
        assert resp.status_code == 422

    def test_valid_unprovisioned_customer_still_404(self):
        """Pattern-valid but unknown customer → 404 (existing behavior)."""
        mgr = WhatsAppManager()  # empty, no customers registered
        app = _app_with_manager(mgr)
        client = TestClient(app)

        resp = client.post("/webhook/whatsapp/cust_valid_but_unknown", content=b"x")
        assert resp.status_code == 404
