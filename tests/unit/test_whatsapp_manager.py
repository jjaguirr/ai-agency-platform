"""Unit tests for WhatsAppManager."""
import pytest
from unittest.mock import Mock

from src.communication.whatsapp_manager import WhatsAppManager
from src.communication.whatsapp import WhatsAppConfig, WhatsAppChannel


class TestWhatsAppManagerRegistration:
    def test_register_and_get_config(self):
        mgr = WhatsAppManager()
        cfg = WhatsAppConfig(
            provider="twilio", from_number="+14155238886",
            credentials={"account_sid": "ACtest", "auth_token": "tok"},
        )
        mgr.register_customer("cust_a", cfg)
        assert mgr.get_config("cust_a") == cfg

    def test_get_config_unknown_returns_none(self):
        mgr = WhatsAppManager()
        assert mgr.get_config("unknown") is None

    def test_has_customer(self):
        mgr = WhatsAppManager()
        assert mgr.has_customer("x") is False
        mgr.register_customer("x", WhatsAppConfig(
            provider="twilio", from_number="+1",
            credentials={"account_sid": "a", "auth_token": "b"},
        ))
        assert mgr.has_customer("x") is True


class TestWhatsAppManagerChannelBuilding:
    async def test_get_channel_builds_from_config(self):
        mgr = WhatsAppManager()
        mgr.register_customer("cust_a", WhatsAppConfig(
            provider="twilio", from_number="+14155238886",
            credentials={"account_sid": "ACtest", "auth_token": "tok"},
            webhook_base_url="https://api.example.com",
        ))

        channel = await mgr.get_channel("cust_a")

        assert isinstance(channel, WhatsAppChannel)
        assert channel.customer_id == "cust_a"
        assert channel.provider.provider_name == "twilio"
        assert channel.config["from_number"] == "+14155238886"
        assert channel.config["webhook_url"] == "https://api.example.com/webhook/whatsapp/cust_a"

    async def test_get_channel_caches_instance(self):
        mgr = WhatsAppManager()
        mgr.register_customer("cust_a", WhatsAppConfig(
            provider="twilio", from_number="+1",
            credentials={"account_sid": "a", "auth_token": "b"},
        ))
        ch1 = await mgr.get_channel("cust_a")
        ch2 = await mgr.get_channel("cust_a")
        assert ch1 is ch2

    async def test_get_channel_unknown_returns_none(self):
        mgr = WhatsAppManager()
        assert await mgr.get_channel("unknown") is None

    async def test_get_channel_with_config_loader_fallback(self):
        loader = Mock(return_value=WhatsAppConfig(
            provider="twilio", from_number="+1",
            credentials={"account_sid": "AC_loaded", "auth_token": "tok_loaded"},
        ))
        mgr = WhatsAppManager(config_loader=loader)

        channel = await mgr.get_channel("cust_lazy")

        assert channel is not None
        loader.assert_called_once_with("cust_lazy")
        assert channel.customer_id == "cust_lazy"

    async def test_config_loader_returns_none(self):
        loader = Mock(return_value=None)
        mgr = WhatsAppManager(config_loader=loader)
        assert await mgr.get_channel("unknown") is None


class TestWhatsAppManagerStoreSharing:
    async def test_channels_use_shared_store(self):
        """All channels share the manager's MessageStore."""
        mgr = WhatsAppManager()
        mgr.register_customer("cust_a", WhatsAppConfig(
            provider="twilio", from_number="+1",
            credentials={"account_sid": "a", "auth_token": "b"},
        ))
        mgr.register_customer("cust_b", WhatsAppConfig(
            provider="twilio", from_number="+2",
            credentials={"account_sid": "c", "auth_token": "d"},
        ))

        ch_a = await mgr.get_channel("cust_a")
        ch_b = await mgr.get_channel("cust_b")
        assert ch_a.store is ch_b.store
        assert ch_a.store is mgr.store
