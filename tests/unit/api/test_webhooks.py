"""
WhatsApp webhook route tests.

The route forwards to the WhatsApp channel abstraction — signature validation,
webhook parsing, and message sending all live in src/communication/whatsapp/.
The difference from the standalone webhook server: the EA is fetched from the
customer-scoped pool, not a hardcoded "default" instance.

Fixture pattern mirrors tests/unit/test_webhook_server.py: real WhatsAppManager
with a registered customer, mock provider injected into the built channel.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import EAPool
from src.communication.whatsapp import (
    IncomingMessage, MessageStatus, SendResult, StatusUpdate, WhatsAppConfig,
)
from src.communication.whatsapp_manager import WhatsAppManager


# --- Fixtures --------------------------------------------------------------

def _manager_with_mock_provider(
    customer_id: str = "cust_wa",
    *,
    parse_result: list | None = None,
    signature_valid: bool = True,
) -> tuple[WhatsAppManager, Mock]:
    """
    WhatsAppManager with one registered customer and a mocked provider.
    Same pattern as test_webhook_server.py — we test the route wiring, not
    Twilio's HMAC.
    """
    cfg = WhatsAppConfig(
        provider="twilio",
        from_number="+14155238886",
        credentials={"account_sid": "ACtest", "auth_token": "tok"},
        webhook_base_url="http://testserver",
    )
    mgr = WhatsAppManager()
    mgr.register_customer(customer_id, cfg)

    mock_provider = Mock()
    mock_provider.provider_name = "mock"
    mock_provider.validate_signature = Mock(return_value=signature_valid)
    mock_provider.parse_webhook = Mock(return_value=parse_result or [])
    mock_provider.send_text = AsyncMock(
        return_value=SendResult(provider_message_id="SM_reply", status=MessageStatus.QUEUED)
    )

    original_get_channel = mgr.get_channel

    async def get_channel_with_mock(cid):
        ch = await original_get_channel(cid)
        if ch is not None:
            ch._provider = mock_provider
        return ch

    mgr.get_channel = get_channel_with_mock
    return mgr, mock_provider


def _app_with(manager: WhatsAppManager, ea_factory) -> TestClient:
    app = create_app(
        ea_pool=EAPool(ea_factory=ea_factory),
        whatsapp_manager=manager,
        jwt_secret="test-secret",
    )
    return TestClient(app)


# --- Signature & routing ---------------------------------------------------

class TestWebhookAuth:
    def test_unknown_customer_returns_404(self, mock_ea_factory):
        mgr = WhatsAppManager()  # no customers registered
        client = _app_with(mgr, mock_ea_factory)

        resp = client.post("/v1/webhooks/whatsapp/ghost", content=b"x")
        assert resp.status_code == 404

    def test_invalid_signature_returns_403_before_parsing(self, mock_ea_factory):
        mgr, provider = _manager_with_mock_provider(signature_valid=False)
        client = _app_with(mgr, mock_ea_factory)

        resp = client.post(
            "/v1/webhooks/whatsapp/cust_wa",
            content=b"Body=hello",
            headers={"X-Twilio-Signature": "bad"},
        )

        assert resp.status_code == 403
        provider.parse_webhook.assert_not_called()
        assert len(mock_ea_factory.created) == 0  # never touched the pool

    def test_valid_signature_no_events_returns_200(self, mock_ea_factory):
        mgr, _ = _manager_with_mock_provider(signature_valid=True, parse_result=[])
        client = _app_with(mgr, mock_ea_factory)

        resp = client.post(
            "/v1/webhooks/whatsapp/cust_wa",
            content=b"x",
            headers={"X-Twilio-Signature": "sig"},
        )
        assert resp.status_code == 200

    def test_signature_validated_against_configured_url_not_request_url(self, mock_ea_factory):
        """
        Behind a proxy, request.url is the internal address — Twilio signed
        the public URL. The channel's configured webhook_url must be used.

        Use a webhook_base_url that DIFFERS from TestClient's http://testserver
        so the assertion actually discriminates. (Previously both were
        "testserver" so the test couldn't tell them apart.)
        """
        cfg = WhatsAppConfig(
            provider="twilio",
            from_number="+14155238886",
            credentials={"account_sid": "ACtest", "auth_token": "tok"},
            webhook_base_url="https://public.example.com",  # NOT testserver
        )
        mgr = WhatsAppManager()
        mgr.register_customer("cust_proxy", cfg)

        mock_provider = Mock()
        mock_provider.validate_signature = Mock(return_value=True)
        mock_provider.parse_webhook = Mock(return_value=[])

        original = mgr.get_channel

        async def inject(cid):
            ch = await original(cid)
            if ch:
                ch._provider = mock_provider
            return ch

        mgr.get_channel = inject
        client = _app_with(mgr, mock_ea_factory)

        client.post(
            "/v1/webhooks/whatsapp/cust_proxy",
            content=b"x",
            headers={"X-Twilio-Signature": "sig"},
        )

        url = mock_provider.validate_signature.call_args.kwargs["url"]
        assert url.startswith("https://public.example.com"), url
        assert "testserver" not in url  # proves we did NOT use request.url


# --- Incoming message flow -------------------------------------------------

class TestIncomingMessage:
    def test_routes_to_customer_scoped_ea_and_replies(self, mock_ea_factory):
        incoming = IncomingMessage(
            provider_message_id="SM_in",
            from_number="+15551234567",
            to_number="+14155238886",
            body="I need help with orders",
        )
        mgr, provider = _manager_with_mock_provider(
            customer_id="cust_scoped",
            parse_result=[incoming],
        )
        client = _app_with(mgr, mock_ea_factory)

        resp = client.post(
            "/v1/webhooks/whatsapp/cust_scoped",
            content=b"From=whatsapp%3A%2B15551234567&Body=I+need+help",
            headers={"X-Twilio-Signature": "sig"},
        )

        assert resp.status_code == 200

        # EA pool created exactly one instance for THIS customer — not "default"
        assert len(mock_ea_factory.created) == 1
        cid, ea = mock_ea_factory.created[0]
        assert cid == "cust_scoped"

        # EA was called with the message body and WHATSAPP channel
        ea.handle_customer_interaction.assert_awaited_once()
        call = ea.handle_customer_interaction.call_args
        assert call.kwargs["message"] == "I need help with orders"
        assert call.kwargs["channel"].value == "whatsapp"
        assert call.kwargs["conversation_id"] is not None

        # Reply went out via the provider
        provider.send_text.assert_called_once()
        assert provider.send_text.call_args.kwargs["to"] == "+15551234567"
        assert provider.send_text.call_args.kwargs["body"] == "mock EA response"

    def test_ea_exception_sends_fallback_returns_200(self, mock_ea_factory):
        """
        If the EA pool's instance raises (shouldn't happen — EA catches
        internally — but defend anyway), send a fallback and still ack 200.
        Twilio retries on 5xx; we don't want that storm.
        """
        incoming = IncomingMessage(
            provider_message_id="SM_err",
            from_number="+15551234567",
            to_number="+14155238886",
            body="trigger",
        )
        mgr, provider = _manager_with_mock_provider(parse_result=[incoming])

        def raising_factory(cid):
            ea = Mock()
            ea.handle_customer_interaction = AsyncMock(side_effect=RuntimeError("boom"))
            return ea

        client = _app_with(mgr, raising_factory)

        resp = client.post(
            "/v1/webhooks/whatsapp/cust_wa",
            content=b"x",
            headers={"X-Twilio-Signature": "sig"},
        )

        assert resp.status_code == 200
        provider.send_text.assert_called_once()
        # A fallback was sent (not empty, not the exception message)
        sent = provider.send_text.call_args.kwargs["body"]
        assert sent
        assert "boom" not in sent

    def test_send_failure_still_returns_200(self, mock_ea_factory):
        """
        The EA must have run BEFORE the send attempt. A short-circuit that
        skips the EA on send-setup failure would also return 200 — so assert
        on the call order, not just the status code.
        """
        incoming = IncomingMessage(
            provider_message_id="SM_send_fail",
            from_number="+15551234567",
            to_number="+14155238886",
            body="hi",
        )
        mgr, provider = _manager_with_mock_provider(parse_result=[incoming])
        provider.send_text = AsyncMock(side_effect=Exception("twilio api down"))
        client = _app_with(mgr, mock_ea_factory)

        resp = client.post(
            "/v1/webhooks/whatsapp/cust_wa",
            content=b"x",
            headers={"X-Twilio-Signature": "sig"},
        )

        assert resp.status_code == 200
        # EA was fetched and called — the send failure happened AFTER.
        assert len(mock_ea_factory.created) == 1
        _, ea = mock_ea_factory.created[0]
        ea.handle_customer_interaction.assert_awaited_once()
        # Send was attempted with the EA's response.
        provider.send_text.assert_awaited_once()
        assert provider.send_text.call_args.kwargs["body"] == "mock EA response"


# --- Status callbacks ------------------------------------------------------

class TestStatusCallback:
    def test_status_update_recorded_in_store_ea_untouched(self, mock_ea_factory):
        import asyncio

        update = StatusUpdate(
            provider_message_id="SM_out_42",
            status=MessageStatus.DELIVERED,
        )
        mgr, _ = _manager_with_mock_provider(parse_result=[update])
        client = _app_with(mgr, mock_ea_factory)

        resp = client.post(
            "/v1/webhooks/whatsapp/cust_wa",
            content=b"x",
            headers={"X-Twilio-Signature": "sig"},
        )

        assert resp.status_code == 200
        # The status actually landed in the shared store — not just "didn't crash".
        stored = asyncio.run(mgr.store.get_status("SM_out_42"))
        assert stored == MessageStatus.DELIVERED
        # And the EA pool was never touched.
        assert len(mock_ea_factory.created) == 0
