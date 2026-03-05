"""
Unit tests for WhatsApp provider abstraction layer.

Covers:
- WhatsAppProvider ABC contract enforcement
- TwilioWhatsAppProvider: send, parse inbound, parse status, signature validation
- Provider registry / factory

No live API calls — httpx is mocked via respx or transport mocks.
"""
import base64
import hashlib
import hmac
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


# -------------------------------------------------------------------
# ABC contract
# -------------------------------------------------------------------

class TestWhatsAppProviderABC:
    def test_cannot_instantiate_abstract_base(self):
        from src.communication.providers.base_provider import WhatsAppProvider
        with pytest.raises(TypeError):
            WhatsAppProvider()  # type: ignore[abstract]

    def test_abc_declares_required_methods(self):
        from src.communication.providers.base_provider import WhatsAppProvider
        abstract = WhatsAppProvider.__abstractmethods__
        # Required seam: send, parse inbound, parse status, validate sig, fetch status
        assert "send_text" in abstract
        assert "parse_incoming_webhook" in abstract
        assert "parse_status_callback" in abstract
        assert "validate_signature" in abstract
        assert "fetch_message_status" in abstract

    def test_delivery_state_enum_values(self):
        from src.communication.providers.base_provider import DeliveryState
        assert DeliveryState.QUEUED.value == "queued"
        assert DeliveryState.SENT.value == "sent"
        assert DeliveryState.DELIVERED.value == "delivered"
        assert DeliveryState.READ.value == "read"
        assert DeliveryState.FAILED.value == "failed"
        assert DeliveryState.UNKNOWN.value == "unknown"

    def test_inbound_message_dataclass_fields(self):
        from src.communication.providers.base_provider import InboundMessage
        msg = InboundMessage(
            provider_message_id="SM123",
            from_phone="+15551234567",
            to_phone="+15559876543",
            body="hello",
            timestamp=datetime(2026, 3, 5, 12, 0, 0),
        )
        assert msg.provider_message_id == "SM123"
        assert msg.from_phone == "+15551234567"
        assert msg.body == "hello"
        assert msg.media_urls == []  # sensible default
        assert isinstance(msg.raw, dict)  # sensible default

    def test_message_status_dataclass_fields(self):
        from src.communication.providers.base_provider import (
            DeliveryState,
            MessageStatus,
        )
        status = MessageStatus(
            provider_message_id="SM123",
            state=DeliveryState.DELIVERED,
            timestamp=datetime(2026, 3, 5, 12, 0, 0),
        )
        assert status.state == DeliveryState.DELIVERED
        assert status.error_code is None
        assert status.error_message is None


# -------------------------------------------------------------------
# TwilioWhatsAppProvider — send_text
# -------------------------------------------------------------------

@pytest.fixture
def twilio_config():
    return {
        "account_sid": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "auth_token": "test_auth_token_secret",
        "whatsapp_number": "+14155238886",
    }


@pytest.fixture
def twilio_provider(twilio_config):
    from src.communication.providers.twilio_provider import TwilioWhatsAppProvider
    return TwilioWhatsAppProvider(**twilio_config)


class TestTwilioSendText:
    async def test_send_text_posts_to_correct_endpoint(self, twilio_provider, twilio_config):
        """Verify POST goes to Twilio Messages API with Basic auth + form-encoded body."""
        captured = {}

        async def handler(request: httpx.Request):
            captured["url"] = str(request.url)
            captured["auth"] = request.headers.get("authorization")
            captured["body"] = request.content.decode()
            return httpx.Response(
                201,
                json={"sid": "SMabc123def456", "status": "queued"},
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            twilio_provider._client = client
            msg_id = await twilio_provider.send_text("+15551234567", "Hello from test")

        assert msg_id == "SMabc123def456"
        assert twilio_config["account_sid"] in captured["url"]
        assert captured["url"].endswith("/Messages.json")
        # Basic auth header present
        assert captured["auth"].startswith("Basic ")
        # Form body contains WhatsApp-prefixed numbers
        assert "whatsapp%3A%2B15551234567" in captured["body"]
        assert "whatsapp%3A%2B14155238886" in captured["body"]
        assert "Hello+from+test" in captured["body"] or "Hello%20from%20test" in captured["body"]

    async def test_send_text_strips_existing_whatsapp_prefix(self, twilio_provider):
        """Phone numbers should not double-prefix."""
        captured = {}

        async def handler(request: httpx.Request):
            captured["body"] = request.content.decode()
            return httpx.Response(201, json={"sid": "SM999", "status": "queued"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            twilio_provider._client = client
            await twilio_provider.send_text("whatsapp:+15551234567", "hi")

        # Exactly one 'whatsapp:' prefix, not 'whatsapp:whatsapp:'
        assert "whatsapp%3Awhatsapp" not in captured["body"]

    async def test_send_text_raises_on_api_error(self, twilio_provider):
        from src.communication.providers.base_provider import ProviderError

        async def handler(request: httpx.Request):
            return httpx.Response(
                400,
                json={"code": 21211, "message": "Invalid 'To' phone number"},
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            twilio_provider._client = client
            with pytest.raises(ProviderError) as exc_info:
                await twilio_provider.send_text("+1invalid", "test")

        assert "21211" in str(exc_info.value) or "Invalid" in str(exc_info.value)

    async def test_send_text_without_credentials_raises(self):
        from src.communication.providers.twilio_provider import TwilioWhatsAppProvider
        from src.communication.providers.base_provider import ProviderError
        with pytest.raises((ValueError, ProviderError)):
            TwilioWhatsAppProvider(
                account_sid="", auth_token="", whatsapp_number=""
            )


# -------------------------------------------------------------------
# TwilioWhatsAppProvider — parse_incoming_webhook
# -------------------------------------------------------------------

class TestTwilioParseIncoming:
    def test_parse_basic_text_message(self, twilio_provider):
        form_data = {
            "MessageSid": "SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx01",
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+14155238886",
            "Body": "Hello, I need help with my order",
            "NumMedia": "0",
            "ProfileName": "Jane Doe",
            "WaId": "15551234567",
        }
        msg = twilio_provider.parse_incoming_webhook(form_data)

        assert msg.provider_message_id == "SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx01"
        assert msg.from_phone == "+15551234567"  # prefix stripped
        assert msg.to_phone == "+14155238886"
        assert msg.body == "Hello, I need help with my order"
        assert msg.media_urls == []
        assert msg.raw == form_data  # raw preserved for debugging

    def test_parse_media_message(self, twilio_provider):
        form_data = {
            "MessageSid": "MMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx02",
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+14155238886",
            "Body": "",
            "NumMedia": "2",
            "MediaUrl0": "https://api.twilio.com/media/abc123",
            "MediaContentType0": "image/jpeg",
            "MediaUrl1": "https://api.twilio.com/media/def456",
            "MediaContentType1": "application/pdf",
        }
        msg = twilio_provider.parse_incoming_webhook(form_data)
        assert len(msg.media_urls) == 2
        assert "https://api.twilio.com/media/abc123" in msg.media_urls
        assert "https://api.twilio.com/media/def456" in msg.media_urls

    def test_parse_missing_optional_fields(self, twilio_provider):
        """Minimal payload should not crash."""
        form_data = {
            "MessageSid": "SM_minimal",
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+14155238886",
            "Body": "minimal",
        }
        msg = twilio_provider.parse_incoming_webhook(form_data)
        assert msg.body == "minimal"
        assert msg.media_urls == []


# -------------------------------------------------------------------
# TwilioWhatsAppProvider — parse_status_callback
# -------------------------------------------------------------------

class TestTwilioParseStatus:
    def test_parse_delivered_status(self, twilio_provider):
        from src.communication.providers.base_provider import DeliveryState
        form_data = {
            "MessageSid": "SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx99",
            "MessageStatus": "delivered",
            "To": "whatsapp:+15551234567",
            "From": "whatsapp:+14155238886",
        }
        status = twilio_provider.parse_status_callback(form_data)
        assert status.provider_message_id == "SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx99"
        assert status.state == DeliveryState.DELIVERED
        assert status.error_code is None

    def test_parse_failed_status_with_error(self, twilio_provider):
        from src.communication.providers.base_provider import DeliveryState
        form_data = {
            "MessageSid": "SMfailed",
            "MessageStatus": "failed",
            "ErrorCode": "63016",
            "ErrorMessage": "Failed to send freeform message",
        }
        status = twilio_provider.parse_status_callback(form_data)
        assert status.state == DeliveryState.FAILED
        assert status.error_code == "63016"
        assert "freeform" in status.error_message

    def test_parse_unknown_status_maps_to_unknown(self, twilio_provider):
        from src.communication.providers.base_provider import DeliveryState
        form_data = {
            "MessageSid": "SMweird",
            "MessageStatus": "some_new_twilio_status",
        }
        status = twilio_provider.parse_status_callback(form_data)
        assert status.state == DeliveryState.UNKNOWN

    def test_parse_all_known_statuses(self, twilio_provider):
        from src.communication.providers.base_provider import DeliveryState
        mapping = {
            "queued": DeliveryState.QUEUED,
            "sent": DeliveryState.SENT,
            "delivered": DeliveryState.DELIVERED,
            "read": DeliveryState.READ,
            "failed": DeliveryState.FAILED,
            "undelivered": DeliveryState.FAILED,  # Twilio uses both
        }
        for twilio_status, expected_state in mapping.items():
            form_data = {"MessageSid": "SM1", "MessageStatus": twilio_status}
            status = twilio_provider.parse_status_callback(form_data)
            assert status.state == expected_state, f"{twilio_status} should map to {expected_state}"


# -------------------------------------------------------------------
# TwilioWhatsAppProvider — validate_signature (THE CRITICAL ONE)
# -------------------------------------------------------------------

def compute_twilio_signature(auth_token: str, url: str, params: dict) -> str:
    """
    Reference implementation of Twilio's signature algorithm for test verification.

    Algorithm:
    1. Start with the full URL
    2. Append each POST param key+value in alphabetical order by key
    3. HMAC-SHA1 with auth_token
    4. Base64-encode the digest
    """
    data = url
    for key in sorted(params.keys()):
        data += key + str(params[key])
    digest = hmac.new(
        auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


class TestTwilioSignatureValidation:
    def test_valid_signature_accepted(self, twilio_provider, twilio_config):
        url = "https://example.com/webhook/whatsapp/cust-001"
        params = {
            "MessageSid": "SM123",
            "From": "whatsapp:+15551234567",
            "Body": "test message",
        }
        valid_sig = compute_twilio_signature(twilio_config["auth_token"], url, params)
        assert twilio_provider.validate_signature(url, params, valid_sig) is True

    def test_invalid_signature_rejected(self, twilio_provider):
        url = "https://example.com/webhook/whatsapp/cust-001"
        params = {"MessageSid": "SM123", "Body": "test"}
        assert twilio_provider.validate_signature(url, params, "forged_signature") is False

    def test_signature_param_order_independence(self, twilio_provider, twilio_config):
        """Twilio sorts params alphabetically — input dict order must not matter."""
        url = "https://example.com/webhook/whatsapp/cust-001"
        params_a = {"Body": "x", "From": "y", "MessageSid": "z"}
        params_b = {"MessageSid": "z", "From": "y", "Body": "x"}

        sig = compute_twilio_signature(twilio_config["auth_token"], url, params_a)
        assert twilio_provider.validate_signature(url, params_b, sig) is True

    def test_tampered_body_rejected(self, twilio_provider, twilio_config):
        url = "https://example.com/webhook/whatsapp/cust-001"
        params = {"MessageSid": "SM123", "Body": "original"}
        sig = compute_twilio_signature(twilio_config["auth_token"], url, params)

        tampered = {"MessageSid": "SM123", "Body": "tampered!"}
        assert twilio_provider.validate_signature(url, tampered, sig) is False

    def test_wrong_url_rejected(self, twilio_provider, twilio_config):
        url = "https://example.com/webhook/whatsapp/cust-001"
        params = {"MessageSid": "SM123", "Body": "test"}
        sig = compute_twilio_signature(twilio_config["auth_token"], url, params)

        assert twilio_provider.validate_signature(
            "https://attacker.com/webhook", params, sig
        ) is False

    def test_empty_signature_rejected(self, twilio_provider):
        url = "https://example.com/webhook"
        params = {"Body": "test"}
        assert twilio_provider.validate_signature(url, params, "") is False

    def test_none_signature_rejected(self, twilio_provider):
        url = "https://example.com/webhook"
        params = {"Body": "test"}
        assert twilio_provider.validate_signature(url, params, None) is False


# -------------------------------------------------------------------
# TwilioWhatsAppProvider — fetch_message_status
# -------------------------------------------------------------------

class TestTwilioFetchStatus:
    async def test_fetch_message_status_parses_response(self, twilio_provider):
        from src.communication.providers.base_provider import DeliveryState

        async def handler(request: httpx.Request):
            return httpx.Response(
                200,
                json={
                    "sid": "SMqueried",
                    "status": "delivered",
                    "error_code": None,
                },
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            twilio_provider._client = client
            status = await twilio_provider.fetch_message_status("SMqueried")

        assert status.provider_message_id == "SMqueried"
        assert status.state == DeliveryState.DELIVERED

    async def test_fetch_message_status_handles_404(self, twilio_provider):
        from src.communication.providers.base_provider import ProviderError

        async def handler(request: httpx.Request):
            return httpx.Response(404, json={"code": 20404, "message": "Not found"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            twilio_provider._client = client
            with pytest.raises(ProviderError):
                await twilio_provider.fetch_message_status("SMnonexistent")


# -------------------------------------------------------------------
# Provider registry / factory
# -------------------------------------------------------------------

class TestProviderRegistry:
    def test_twilio_registered_by_name(self):
        from src.communication.providers import PROVIDER_REGISTRY
        assert "twilio" in PROVIDER_REGISTRY

    def test_create_provider_returns_twilio_instance(self, twilio_config):
        from src.communication.providers import create_provider
        from src.communication.providers.twilio_provider import TwilioWhatsAppProvider
        p = create_provider("twilio", twilio_config)
        assert isinstance(p, TwilioWhatsAppProvider)

    def test_create_provider_unknown_raises(self):
        from src.communication.providers import create_provider
        with pytest.raises((KeyError, ValueError)):
            create_provider("nonexistent_provider", {})

    def test_create_provider_case_insensitive(self, twilio_config):
        from src.communication.providers import create_provider
        from src.communication.providers.twilio_provider import TwilioWhatsAppProvider
        p = create_provider("Twilio", twilio_config)
        assert isinstance(p, TwilioWhatsAppProvider)
        assert p.account_sid == twilio_config["account_sid"]  # config propagated
        p2 = create_provider("TWILIO", twilio_config)
        assert isinstance(p2, TwilioWhatsAppProvider)
        assert p2.auth_token == twilio_config["auth_token"]

    def test_second_provider_addable_without_channel_changes(self):
        """
        Acceptance criterion: a second provider can be added by implementing
        the interface. This test registers a dummy provider and confirms
        the factory returns it — proving the seam works.
        """
        from src.communication.providers import (
            PROVIDER_REGISTRY,
            create_provider,
        )
        from src.communication.providers.base_provider import (
            DeliveryState,
            InboundMessage,
            MessageStatus,
            WhatsAppProvider,
        )

        class DummyProvider(WhatsAppProvider):
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            async def send_text(self, to, body):
                return "dummy-msg-id"

            def parse_incoming_webhook(self, form_data):
                return InboundMessage(
                    provider_message_id="d1",
                    from_phone="+1",
                    to_phone="+2",
                    body=form_data.get("body", ""),
                    timestamp=datetime.now(),
                )

            def parse_status_callback(self, form_data):
                return MessageStatus(
                    provider_message_id="d1",
                    state=DeliveryState.SENT,
                    timestamp=datetime.now(),
                )

            def validate_signature(self, url, form_data, signature):
                return True

            async def fetch_message_status(self, message_id):
                return MessageStatus(
                    provider_message_id=message_id,
                    state=DeliveryState.UNKNOWN,
                    timestamp=datetime.now(),
                )

        # Register and create
        PROVIDER_REGISTRY["dummy"] = DummyProvider
        try:
            p = create_provider("dummy", {"some_key": "some_val"})
            assert isinstance(p, DummyProvider)
            assert p.kwargs == {"some_key": "some_val"}
        finally:
            del PROVIDER_REGISTRY["dummy"]
