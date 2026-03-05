"""Unit tests for TwilioWhatsAppProvider."""
import base64
import hashlib
import hmac
from urllib.parse import urlencode, parse_qsl

import httpx
import pytest

from src.communication.whatsapp.providers.twilio import TwilioWhatsAppProvider
from src.communication.whatsapp.provider import (
    MessageStatus, SendResult, IncomingMessage, StatusUpdate, WhatsAppSendError
)


# --- Helpers ---------------------------------------------------------------

def _twilio_signature(auth_token: str, url: str, params: dict[str, str]) -> str:
    """Compute the Twilio signature per their official algorithm."""
    s = url
    for key in sorted(params.keys()):
        s += key + params[key]
    mac = hmac.new(auth_token.encode("utf-8"), s.encode("utf-8"), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode("ascii")


def _form_body(params: dict[str, str]) -> bytes:
    return urlencode(params).encode("utf-8")


# --- Signature validation tests -------------------------------------------

class TestTwilioSignatureValidation:
    AUTH_TOKEN = "test_auth_token_12345"
    WEBHOOK_URL = "https://example.com/webhook/whatsapp/cust_a"

    def _provider(self) -> TwilioWhatsAppProvider:
        return TwilioWhatsAppProvider(
            account_sid="ACtest", auth_token=self.AUTH_TOKEN
        )

    def test_valid_signature_accepted(self):
        params = {
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+14155238886",
            "Body": "hello world",
            "MessageSid": "SM1234567890abcdef",
        }
        sig = _twilio_signature(self.AUTH_TOKEN, self.WEBHOOK_URL, params)
        body = _form_body(params)

        result = self._provider().validate_signature(
            url=self.WEBHOOK_URL, body=body,
            headers={"X-Twilio-Signature": sig},
        )
        assert result is True

    def test_tampered_body_rejected(self):
        params = {"From": "whatsapp:+15551234567", "Body": "original"}
        sig = _twilio_signature(self.AUTH_TOKEN, self.WEBHOOK_URL, params)
        tampered = {"From": "whatsapp:+15551234567", "Body": "tampered"}

        result = self._provider().validate_signature(
            url=self.WEBHOOK_URL, body=_form_body(tampered),
            headers={"X-Twilio-Signature": sig},
        )
        assert result is False

    def test_wrong_url_rejected(self):
        params = {"Body": "hello"}
        sig = _twilio_signature(self.AUTH_TOKEN, self.WEBHOOK_URL, params)

        result = self._provider().validate_signature(
            url="https://evil.example.com/webhook", body=_form_body(params),
            headers={"X-Twilio-Signature": sig},
        )
        assert result is False

    def test_missing_signature_header_rejected(self):
        params = {"Body": "hello"}
        result = self._provider().validate_signature(
            url=self.WEBHOOK_URL, body=_form_body(params), headers={},
        )
        assert result is False

    def test_wrong_auth_token_rejected(self):
        params = {"Body": "hello"}
        sig = _twilio_signature("different_token", self.WEBHOOK_URL, params)

        result = self._provider().validate_signature(
            url=self.WEBHOOK_URL, body=_form_body(params),
            headers={"X-Twilio-Signature": sig},
        )
        assert result is False

    def test_case_insensitive_header_lookup(self):
        params = {"Body": "hello"}
        sig = _twilio_signature(self.AUTH_TOKEN, self.WEBHOOK_URL, params)

        result = self._provider().validate_signature(
            url=self.WEBHOOK_URL, body=_form_body(params),
            headers={"x-twilio-signature": sig},  # lowercase
        )
        assert result is True


# --- Webhook parsing tests ------------------------------------------------

class TestTwilioParseWebhook:
    def _provider(self) -> TwilioWhatsAppProvider:
        return TwilioWhatsAppProvider(account_sid="ACtest", auth_token="tok")

    def test_parse_incoming_text_message(self):
        params = {
            "MessageSid": "SMabcdef1234567890",
            "SmsMessageSid": "SMabcdef1234567890",
            "AccountSid": "ACtest",
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+14155238886",
            "Body": "hello there",
            "NumMedia": "0",
            "ProfileName": "Alice Example",
        }
        events = self._provider().parse_webhook(
            _form_body(params), "application/x-www-form-urlencoded"
        )

        assert len(events) == 1
        msg = events[0]
        assert isinstance(msg, IncomingMessage)
        assert msg.provider_message_id == "SMabcdef1234567890"
        assert msg.from_number == "+15551234567"   # whatsapp: prefix stripped
        assert msg.to_number == "+14155238886"
        assert msg.body == "hello there"
        assert msg.profile_name == "Alice Example"
        assert msg.media == []
        assert msg.raw == params

    def test_parse_incoming_message_with_media(self):
        params = {
            "MessageSid": "SMmedia123",
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+14155238886",
            "Body": "",
            "NumMedia": "2",
            "MediaContentType0": "image/jpeg",
            "MediaUrl0": "https://api.twilio.com/media/img1.jpg",
            "MediaContentType1": "image/png",
            "MediaUrl1": "https://api.twilio.com/media/img2.png",
        }
        events = self._provider().parse_webhook(
            _form_body(params), "application/x-www-form-urlencoded"
        )

        assert len(events) == 1
        msg = events[0]
        assert isinstance(msg, IncomingMessage)
        assert msg.provider_message_id == "SMmedia123"
        assert msg.body == ""
        assert len(msg.media) == 2
        assert msg.media[0].content_type == "image/jpeg"
        assert msg.media[0].url == "https://api.twilio.com/media/img1.jpg"
        assert msg.media[1].content_type == "image/png"
        assert msg.media[1].url == "https://api.twilio.com/media/img2.png"

    def test_parse_status_callback_delivered(self):
        params = {
            "MessageSid": "SMout456",
            "MessageStatus": "delivered",
            "To": "whatsapp:+15551234567",
            "From": "whatsapp:+14155238886",
        }
        events = self._provider().parse_webhook(
            _form_body(params), "application/x-www-form-urlencoded"
        )

        assert len(events) == 1
        upd = events[0]
        assert isinstance(upd, StatusUpdate)
        assert upd.provider_message_id == "SMout456"
        assert upd.status == MessageStatus.DELIVERED
        assert upd.error_code is None
        assert upd.raw == params

    def test_parse_status_callback_failed_with_error_code(self):
        params = {
            "MessageSid": "SMfail789",
            "MessageStatus": "failed",
            "ErrorCode": "30008",
        }
        events = self._provider().parse_webhook(
            _form_body(params), "application/x-www-form-urlencoded"
        )

        assert len(events) == 1
        upd = events[0]
        assert isinstance(upd, StatusUpdate)
        assert upd.provider_message_id == "SMfail789"
        assert upd.status == MessageStatus.FAILED
        assert upd.error_code == "30008"

    def test_parse_status_callback_read(self):
        params = {"MessageSid": "SMread1", "MessageStatus": "read"}
        events = self._provider().parse_webhook(
            _form_body(params), "application/x-www-form-urlencoded"
        )
        assert len(events) == 1
        assert isinstance(events[0], StatusUpdate)
        assert events[0].status == MessageStatus.READ

    def test_parse_unknown_status_maps_to_unknown(self):
        params = {"MessageSid": "SMx", "MessageStatus": "some_new_state"}
        events = self._provider().parse_webhook(
            _form_body(params), "application/x-www-form-urlencoded"
        )
        assert len(events) == 1
        assert isinstance(events[0], StatusUpdate)
        assert events[0].status == MessageStatus.UNKNOWN

    def test_parse_incoming_without_profile_name(self):
        params = {
            "MessageSid": "SM_noprofile",
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+14155238886",
            "Body": "hi",
            "NumMedia": "0",
        }
        events = self._provider().parse_webhook(
            _form_body(params), "application/x-www-form-urlencoded"
        )
        assert len(events) == 1
        msg = events[0]
        assert isinstance(msg, IncomingMessage)
        assert msg.profile_name is None

    def test_parse_empty_body_returns_empty_list(self):
        events = self._provider().parse_webhook(
            b"", "application/x-www-form-urlencoded"
        )
        assert events == []


# --- send_text tests ------------------------------------------------------

class TestTwilioSendText:
    ACCOUNT_SID = "ACtest123"
    AUTH_TOKEN = "secret_tok"

    def _provider_with_transport(self, handler) -> TwilioWhatsAppProvider:
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(
            transport=transport,
            auth=(self.ACCOUNT_SID, self.AUTH_TOKEN),
        )
        return TwilioWhatsAppProvider(
            account_sid=self.ACCOUNT_SID,
            auth_token=self.AUTH_TOKEN,
            http_client=client,
        )

    async def test_send_text_success(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["url"] = str(request.url)
            captured["form"] = dict(parse_qsl(request.content.decode("utf-8")))
            captured["auth"] = request.headers.get("authorization")
            return httpx.Response(201, json={
                "sid": "SM_sent_abc123",
                "status": "queued",
                "to": "whatsapp:+15551234567",
                "from": "whatsapp:+14155238886",
            })

        provider = self._provider_with_transport(handler)
        result = await provider.send_text(
            to="+15551234567", body="hello!", from_="+14155238886"
        )

        # Returned SendResult
        assert isinstance(result, SendResult)
        assert result.provider_message_id == "SM_sent_abc123"
        assert result.status == MessageStatus.QUEUED
        assert result.raw["sid"] == "SM_sent_abc123"

        # Outbound request shape
        assert captured["method"] == "POST"
        assert captured["url"] == (
            f"https://api.twilio.com/2010-04-01/Accounts/{self.ACCOUNT_SID}/Messages.json"
        )
        assert captured["form"] == {
            "To": "whatsapp:+15551234567",
            "From": "whatsapp:+14155238886",
            "Body": "hello!",
        }
        # Basic auth header = base64(sid:token)
        expected_auth = "Basic " + base64.b64encode(
            f"{self.ACCOUNT_SID}:{self.AUTH_TOKEN}".encode()
        ).decode("ascii")
        assert captured["auth"] == expected_auth

    async def test_send_text_status_mapping(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(201, json={"sid": "SM1", "status": "sent"})

        provider = self._provider_with_transport(handler)
        result = await provider.send_text(
            to="+15551234567", body="x", from_="+14155238886"
        )
        assert result.status == MessageStatus.SENT

    async def test_send_text_api_error_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={
                "code": 21211,
                "message": "Invalid 'To' Phone Number",
                "more_info": "https://www.twilio.com/docs/errors/21211",
            })

        provider = self._provider_with_transport(handler)
        with pytest.raises(WhatsAppSendError) as exc_info:
            await provider.send_text(
                to="invalid", body="x", from_="+14155238886"
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.error_code == "21211"
        assert "Invalid 'To' Phone Number" in str(exc_info.value)

    async def test_send_text_5xx_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"message": "Service Unavailable"})

        provider = self._provider_with_transport(handler)
        with pytest.raises(WhatsAppSendError) as exc_info:
            await provider.send_text(to="+15551234567", body="x", from_="+14155238886")
        assert exc_info.value.status_code == 503

    async def test_send_text_unknown_status_maps_to_unknown(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(201, json={"sid": "SM2", "status": "weird_new_state"})

        provider = self._provider_with_transport(handler)
        result = await provider.send_text(
            to="+15551234567", body="x", from_="+14155238886"
        )
        assert result.status == MessageStatus.UNKNOWN


# --- fetch_status tests ---------------------------------------------------

class TestTwilioFetchStatus:
    ACCOUNT_SID = "ACfetch"

    def _provider_with_transport(self, handler) -> TwilioWhatsAppProvider:
        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(
            transport=transport, auth=(self.ACCOUNT_SID, "tok")
        )
        return TwilioWhatsAppProvider(
            account_sid=self.ACCOUNT_SID, auth_token="tok", http_client=client
        )

    async def test_fetch_status_delivered(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["url"] = str(request.url)
            return httpx.Response(200, json={
                "sid": "SM_fetch_1", "status": "delivered"
            })

        provider = self._provider_with_transport(handler)
        status = await provider.fetch_status("SM_fetch_1")

        assert status == MessageStatus.DELIVERED
        assert captured["method"] == "GET"
        assert captured["url"] == (
            f"https://api.twilio.com/2010-04-01/Accounts/{self.ACCOUNT_SID}/Messages/SM_fetch_1.json"
        )

    async def test_fetch_status_read(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"sid": "SM2", "status": "read"})

        provider = self._provider_with_transport(handler)
        assert await provider.fetch_status("SM2") == MessageStatus.READ

    async def test_fetch_status_not_found_returns_unknown(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"code": 20404, "message": "Not Found"})

        provider = self._provider_with_transport(handler)
        assert await provider.fetch_status("SM_missing") == MessageStatus.UNKNOWN
