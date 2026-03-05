"""Unit tests for WhatsAppConfig."""
import pytest
from src.communication.whatsapp.config import WhatsAppConfig


class TestWhatsAppConfigFromEnv:
    def test_from_env_twilio(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_PROVIDER", "twilio")
        monkeypatch.setenv("WHATSAPP_FROM_NUMBER", "+14155238886")
        monkeypatch.setenv("WHATSAPP_WEBHOOK_BASE_URL", "https://example.com")
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACtest123")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "secret_token_abc")

        cfg = WhatsAppConfig.from_env()

        assert cfg.provider == "twilio"
        assert cfg.from_number == "+14155238886"
        assert cfg.webhook_base_url == "https://example.com"
        assert cfg.credentials == {
            "account_sid": "ACtest123",
            "auth_token": "secret_token_abc",
        }

    def test_from_env_defaults_when_unset(self, monkeypatch):
        for var in ("WHATSAPP_PROVIDER", "WHATSAPP_FROM_NUMBER",
                    "WHATSAPP_WEBHOOK_BASE_URL", "TWILIO_ACCOUNT_SID",
                    "TWILIO_AUTH_TOKEN"):
            monkeypatch.delenv(var, raising=False)

        cfg = WhatsAppConfig.from_env()

        assert cfg.provider == "twilio"
        assert cfg.from_number == ""
        assert cfg.webhook_base_url == ""
        assert cfg.credentials == {"account_sid": "", "auth_token": ""}

    def test_from_env_custom_prefix(self, monkeypatch):
        monkeypatch.setenv("TENANT_A_PROVIDER", "twilio")
        monkeypatch.setenv("TENANT_A_FROM_NUMBER", "+19998887777")
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACtenant_a")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok_a")

        cfg = WhatsAppConfig.from_env(prefix="TENANT_A_")

        assert cfg.from_number == "+19998887777"
        assert cfg.credentials["account_sid"] == "ACtenant_a"


class TestWhatsAppConfigFromDict:
    def test_from_dict_full(self):
        cfg = WhatsAppConfig.from_dict({
            "provider": "twilio",
            "from_number": "+14155238886",
            "credentials": {"account_sid": "AC1", "auth_token": "tok1"},
            "webhook_base_url": "https://x.example.com",
        })
        assert cfg.provider == "twilio"
        assert cfg.from_number == "+14155238886"
        assert cfg.credentials == {"account_sid": "AC1", "auth_token": "tok1"}
        assert cfg.webhook_base_url == "https://x.example.com"

    def test_from_dict_missing_optional(self):
        cfg = WhatsAppConfig.from_dict({
            "provider": "twilio",
            "from_number": "+14155238886",
            "credentials": {"account_sid": "AC1", "auth_token": "tok1"},
        })
        assert cfg.webhook_base_url == ""

    def test_webhook_url_for_customer(self):
        cfg = WhatsAppConfig(
            provider="twilio",
            from_number="+14155238886",
            credentials={"account_sid": "AC1", "auth_token": "tok1"},
            webhook_base_url="https://api.example.com",
        )
        assert cfg.webhook_url_for("cust_abc") == "https://api.example.com/webhook/whatsapp/cust_abc"
