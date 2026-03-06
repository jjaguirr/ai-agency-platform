"""Unit tests for provider registry."""
import pytest
from src.communication.whatsapp.providers._registry import (
    create_provider, PROVIDER_REGISTRY
)
from src.communication.whatsapp.providers.twilio import TwilioWhatsAppProvider


class TestProviderRegistry:
    def test_twilio_registered(self):
        assert "twilio" in PROVIDER_REGISTRY

    def test_create_twilio_provider(self):
        p = create_provider("twilio", {
            "account_sid": "ACtest", "auth_token": "tok123"
        })
        assert isinstance(p, TwilioWhatsAppProvider)
        assert p.provider_name == "twilio"

    def test_unknown_provider_raises_value_error(self):
        with pytest.raises(ValueError) as exc_info:
            create_provider("nonexistent_provider", {})
        assert "nonexistent_provider" in str(exc_info.value)
        assert "Unknown WhatsApp provider" in str(exc_info.value)

    def test_missing_credential_raises_key_error(self):
        with pytest.raises(KeyError):
            create_provider("twilio", {"account_sid": "ACtest"})  # no auth_token
