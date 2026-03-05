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
