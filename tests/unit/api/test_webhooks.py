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

        assert created_for == ["cust_specific"], \
            f"expected exactly one EA build for cust_specific, got {created_for}"


def _spy_manager() -> tuple[WhatsAppManager, list[str]]:
    """Empty manager that records every customer_id reaching get_channel()."""
    mgr = WhatsAppManager()
    seen: list[str] = []
    original = mgr.get_channel

    async def spy(cid: str):
        seen.append(cid)
        return await original(cid)

    mgr.get_channel = spy
    return mgr, seen


class TestWebhookCustomerIdValidation:
    """
    customer_id path parameter is validated against _CUSTOMER_ID_PATTERN.
    Invalid inputs must be rejected BEFORE manager.get_channel() sees
    them — the manager never observes the malicious string.
    """

    @pytest.mark.parametrize("bad_id", [
        "cust;rm%20-rf",     # shell metachar
        "a" * 100,           # oversized (pattern caps at 48)
        "UPPER_CASE",        # case violation
        "ab",                # too short (min 3)
        "valid.$(whoami)",   # command substitution
    ])
    def test_invalid_id_rejected_before_manager(self, bad_id):
        mgr, seen = _spy_manager()
        app = _app_with_manager(mgr)
        client = TestClient(app)

        r = client.post(f"/webhook/whatsapp/{bad_id}", content=b"x")

        assert r.status_code == 422, \
            f"{bad_id!r} should fail validation, got {r.status_code}"
        # Our custom validation handler fired (not FastAPI's default shape)
        assert r.json()["type"] == "validation_error"
        # CRITICAL: manager never saw the malicious string
        assert seen == [], \
            f"manager.get_channel was called with invalid id: {seen}"

    def test_path_traversal_rejected_at_router(self):
        # Encoded `/` decodes before route matching → multi-segment
        # path doesn't match /webhook/whatsapp/{customer_id}. Router
        # 404s. Still a rejection; manager still untouched.
        mgr, seen = _spy_manager()
        app = _app_with_manager(mgr)
        client = TestClient(app)

        r = client.post("/webhook/whatsapp/..%2F..%2Fetc%2Fpasswd", content=b"x")

        assert r.status_code == 404
        assert seen == [], \
            f"manager reached with traversal path: {seen}"

    def test_valid_id_reaches_manager(self):
        # Contrast: a valid-but-unknown id DOES reach the manager,
        # which then 404s. Proves validation isn't over-aggressive.
        mgr, seen = _spy_manager()
        app = _app_with_manager(mgr)
        client = TestClient(app)

        r = client.post("/webhook/whatsapp/valid_but_ghost", content=b"x")

        assert r.status_code == 404
        assert seen == ["valid_but_ghost"], \
            f"valid id should reach manager exactly once, got {seen}"


class TestWebhookTimeout:
    """
    EA calls are bounded by the same timeout as /v1/conversations/message.
    A hung LLM or mem0 connection returns 200 (not 503) — Twilio would
    retry on non-2xx, creating a storm.
    """

    def test_timeout_constant_shared_with_conversations(self):
        from src.api.routes.webhooks import _EA_CALL_TIMEOUT as wh_timeout
        from src.api.routes.conversations import _EA_CALL_TIMEOUT as conv_timeout
        assert wh_timeout is conv_timeout

    def test_hung_ea_returns_200_not_503(self, caplog):
        incoming = IncomingMessage(
            provider_message_id="SM_slow",
            from_number="+15551234567",
            to_number="+14155238886",
            body="hello",
        )
        mgr, provider = _manager_with_mock_provider(
            parse_result=[incoming], signature_valid=True,
        )

        # EA that never returns
        async def _hang(**_):
            await asyncio.sleep(1000)
        hung_ea = MagicMock()
        hung_ea.handle_customer_interaction = _hang

        app = _app_with_manager(mgr, ea_factory=lambda cid: hung_ea)
        # Patch the timeout to something tiny so the test is fast.
        # Patching the webhooks module's name works because the import
        # is `from .conversations import _EA_CALL_TIMEOUT` — a local
        # binding in webhooks' namespace.
        import src.api.routes.webhooks as webhooks_mod
        orig_timeout = webhooks_mod._EA_CALL_TIMEOUT
        webhooks_mod._EA_CALL_TIMEOUT = 0.05
        try:
            client = TestClient(app)
            with caplog.at_level(logging.ERROR):
                r = client.post("/webhook/whatsapp/cust_wa", content=b"x")
        finally:
            webhooks_mod._EA_CALL_TIMEOUT = orig_timeout

        assert r.status_code == 200  # NOT 503
        # Timeout was logged
        assert any("timed out" in rec.getMessage().lower()
                   for rec in caplog.records)
        # Fallback reply was sent — _handle_incoming's exception wrapper
        # fired and still called send_text.
        provider.send_text.assert_called_once()
