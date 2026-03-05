"""
Unit tests for WhatsAppManager (multi-tenant channel factory).

Covers:
- Per-customer channel caching
- Config loading: callback vs env-var fallback
- Handler factory wiring (EA integration point)
- Provider selection via config

No live services — providers and handlers are all mocked.
"""
import os
from unittest.mock import AsyncMock, patch

import pytest

from src.communication.base_channel import BaseMessage, ChannelType


# -------------------------------------------------------------------
# Basic construction + caching
# -------------------------------------------------------------------

class TestManagerBasics:
    def test_manager_constructs_without_side_effects(self):
        """Importing/constructing must not connect to Postgres/Redis/anything."""
        from src.communication.whatsapp_manager import WhatsAppManager
        m = WhatsAppManager()
        # Empty channel cache on construction — no eager channel creation
        assert len(m._channels) == 0
        # No config_loader/handler_factory set when not provided
        assert m._config_loader is None
        assert m._handler_factory is None

    def test_manager_no_module_level_global(self):
        """Importing the module must not create a global instance."""
        import src.communication.whatsapp_manager as mod
        # Ensure no 'whatsapp_manager' or similar global at module level
        globals_ = [
            name for name in dir(mod)
            if not name.startswith("_")
            and isinstance(getattr(mod, name), mod.WhatsAppManager)
        ]
        assert globals_ == [], f"Found module-level manager instance(s): {globals_}"


# -------------------------------------------------------------------
# Config loading: callback > env vars > error
# -------------------------------------------------------------------

class TestConfigLoading:
    async def test_config_loader_callback_used_and_config_reaches_provider(self):
        from src.communication.whatsapp_manager import WhatsAppManager

        loaded_for = []

        def loader(customer_id: str):
            loaded_for.append(customer_id)
            return {
                "provider": "twilio",
                "account_sid": "ACtest_from_loader",
                "auth_token": "token_xyz_from_loader",
                "whatsapp_number": "+14155238886",
            }

        m = WhatsAppManager(config_loader=loader)
        ch = await m.get_channel("cust-42")

        # Loader called exactly once with the right customer_id
        assert loaded_for == ["cust-42"]
        assert ch.customer_id == "cust-42"
        assert ch.channel_type == ChannelType.WHATSAPP
        # Critical: config values actually propagated to the provider
        assert ch.provider.account_sid == "ACtest_from_loader"
        assert ch.provider.auth_token == "token_xyz_from_loader"
        assert ch.provider.whatsapp_number == "+14155238886"

    async def test_env_var_fallback_when_no_loader(self):
        from src.communication.whatsapp_manager import WhatsAppManager

        env = {
            "WHATSAPP_PROVIDER": "twilio",
            "WHATSAPP_ACCOUNT_SID": "ACenvsid",
            "WHATSAPP_AUTH_TOKEN": "envtoken",
            "WHATSAPP_NUMBER": "+14155000000",
        }
        with patch.dict(os.environ, env, clear=False):
            m = WhatsAppManager()
            ch = await m.get_channel("cust-env")

        assert ch.customer_id == "cust-env"
        # Provider was created from env vars
        assert type(ch.provider).__name__ == "TwilioWhatsAppProvider"
        assert ch.provider.account_sid == "ACenvsid"

    async def test_config_loader_returning_none_falls_through_to_env(self):
        from src.communication.whatsapp_manager import WhatsAppManager

        def loader(customer_id: str):
            return None  # customer not configured

        env = {
            "WHATSAPP_PROVIDER": "twilio",
            "WHATSAPP_ACCOUNT_SID": "ACfallback",
            "WHATSAPP_AUTH_TOKEN": "fallbacktoken",
            "WHATSAPP_NUMBER": "+14155111111",
        }
        with patch.dict(os.environ, env, clear=False):
            m = WhatsAppManager(config_loader=loader)
            ch = await m.get_channel("unknown-cust")

        assert ch.provider.account_sid == "ACfallback"

    async def test_no_config_and_no_env_raises(self):
        from src.communication.whatsapp_manager import WhatsAppManager

        # Clear relevant env vars
        clear_keys = [
            "WHATSAPP_PROVIDER", "WHATSAPP_ACCOUNT_SID",
            "WHATSAPP_AUTH_TOKEN", "WHATSAPP_NUMBER",
        ]
        env_snapshot = {k: os.environ.pop(k) for k in clear_keys if k in os.environ}
        try:
            m = WhatsAppManager()
            with pytest.raises((ValueError, RuntimeError)):
                await m.get_channel("cust-noconfig")
        finally:
            os.environ.update(env_snapshot)

    async def test_provider_defaults_to_twilio_when_unspecified(self):
        from src.communication.whatsapp_manager import WhatsAppManager

        def loader(customer_id):
            return {
                # no "provider" key
                "account_sid": "ACx",
                "auth_token": "tok",
                "whatsapp_number": "+14155000000",
            }

        m = WhatsAppManager(config_loader=loader)
        ch = await m.get_channel("cust-default")
        assert type(ch.provider).__name__ == "TwilioWhatsAppProvider"


# -------------------------------------------------------------------
# Channel caching
# -------------------------------------------------------------------

class TestChannelCaching:
    async def test_same_customer_returns_cached_channel(self):
        from src.communication.whatsapp_manager import WhatsAppManager

        def loader(cid):
            return {
                "provider": "twilio",
                "account_sid": "AC1", "auth_token": "t1",
                "whatsapp_number": "+14155000000",
            }

        m = WhatsAppManager(config_loader=loader)
        ch1 = await m.get_channel("cust-A")
        ch2 = await m.get_channel("cust-A")
        assert ch1 is ch2

    async def test_different_customers_get_different_channels(self):
        from src.communication.whatsapp_manager import WhatsAppManager

        configs = {
            "cust-A": {
                "provider": "twilio", "account_sid": "AC_A",
                "auth_token": "tA", "whatsapp_number": "+1111",
            },
            "cust-B": {
                "provider": "twilio", "account_sid": "AC_B",
                "auth_token": "tB", "whatsapp_number": "+2222",
            },
        }
        m = WhatsAppManager(config_loader=lambda cid: configs[cid])
        chA = await m.get_channel("cust-A")
        chB = await m.get_channel("cust-B")

        assert chA is not chB
        assert chA.provider.account_sid == "AC_A"
        assert chB.provider.account_sid == "AC_B"

    async def test_invalidate_removes_from_cache(self):
        from src.communication.whatsapp_manager import WhatsAppManager

        def loader(cid):
            return {
                "provider": "twilio", "account_sid": "AC1",
                "auth_token": "t1", "whatsapp_number": "+1",
            }

        m = WhatsAppManager(config_loader=loader)
        ch1 = await m.get_channel("cust-X")
        m.invalidate("cust-X")
        ch2 = await m.get_channel("cust-X")
        assert ch1 is not ch2


# -------------------------------------------------------------------
# Handler factory — EA integration point
# -------------------------------------------------------------------

class TestHandlerFactory:
    async def test_handler_factory_wires_channel_message_handler(self):
        """The handler produced by the factory must be THE handler attached
        to the channel — not just any callable. Verify by invoking it."""
        from src.communication.whatsapp_manager import WhatsAppManager
        from datetime import datetime

        handler_calls = []
        factory_calls = []

        async def fake_ea_handler(msg: BaseMessage) -> str:
            handler_calls.append((msg.customer_id, msg.content))
            return f"EA says: got '{msg.content}'"

        def handler_factory(customer_id: str):
            factory_calls.append(customer_id)
            return fake_ea_handler

        def loader(cid):
            return {
                "provider": "twilio", "account_sid": "AC1",
                "auth_token": "t1", "whatsapp_number": "+1",
            }

        m = WhatsAppManager(config_loader=loader, handler_factory=handler_factory)
        ch = await m.get_channel("cust-handler-test")

        # Factory was called with the customer_id
        assert factory_calls == ["cust-handler-test"]

        # The attached handler IS the one from the factory — prove by invoking
        test_msg = BaseMessage(
            content="probe message",
            from_number="+1555",
            to_number="+1444",
            channel=ChannelType.WHATSAPP,
            message_id="test-1",
            conversation_id="conv-1",
            timestamp=datetime.now(),
            customer_id="cust-handler-test",
        )
        reply = await ch.message_handler(test_msg)
        assert reply == "EA says: got 'probe message'"
        assert handler_calls == [("cust-handler-test", "probe message")]

    async def test_no_handler_factory_leaves_handler_none(self):
        from src.communication.whatsapp_manager import WhatsAppManager

        def loader(cid):
            return {
                "provider": "twilio", "account_sid": "AC1",
                "auth_token": "t1", "whatsapp_number": "+1",
            }

        m = WhatsAppManager(config_loader=loader)
        ch = await m.get_channel("cust-nohandler")
        assert ch.message_handler is None


# -------------------------------------------------------------------
# get_validator — lightweight pre-auth validator access
# -------------------------------------------------------------------

class TestGetValidator:
    """get_validator(customer_id) must return a signature-validator callable
    WITHOUT building the full channel (no handler_factory, no initialize).

    This is the seam that lets the webhook server check signatures BEFORE
    doing expensive per-customer work."""

    def test_returns_working_validator(self):
        """Validator must actually validate — not just be callable."""
        from src.communication.whatsapp_manager import WhatsAppManager
        import base64, hashlib, hmac

        def loader(cid):
            return {
                "provider": "twilio", "account_sid": "ACx",
                "auth_token": "sekret_token_123", "whatsapp_number": "+1",
            }

        m = WhatsAppManager(config_loader=loader)
        validate = m.get_validator("cust-V")

        # Compute a REAL Twilio signature using the configured auth_token.
        # If validate() accepts this, it IS the provider's validate_signature.
        url = "https://example.com/webhook"
        params = {"Body": "hello", "MessageSid": "SM1"}
        data = url + "".join(k + v for k, v in sorted(params.items()))
        good_sig = base64.b64encode(
            hmac.new(b"sekret_token_123", data.encode(), hashlib.sha1).digest()
        ).decode()

        assert validate(url, params, good_sig) is True
        assert validate(url, params, "garbage") is False
        assert validate(url, params, None) is False

    def test_does_not_call_handler_factory(self):
        """Critical pre-auth guarantee: getting a validator must NOT build
        the full channel. handler_factory untouched, _channels untouched."""
        from src.communication.whatsapp_manager import WhatsAppManager

        factory_calls = []

        def handler_factory(cid):
            factory_calls.append(cid)
            async def h(msg): return "reply"
            return h

        def loader(cid):
            return {
                "provider": "twilio", "account_sid": "ACx",
                "auth_token": "t", "whatsapp_number": "+1",
            }

        m = WhatsAppManager(config_loader=loader, handler_factory=handler_factory)
        _ = m.get_validator("cust-V")

        # No channel built → no handler factory call, no cache entry
        assert factory_calls == []
        assert "cust-V" not in m._channels

    async def test_get_channel_after_get_validator_reuses_provider(self):
        """Provider built once by get_validator; get_channel wraps the SAME
        instance. Proves config_loader runs once, not twice."""
        from src.communication.whatsapp_manager import WhatsAppManager

        loader_calls = []

        def loader(cid):
            loader_calls.append(cid)
            return {
                "provider": "twilio", "account_sid": "ACx",
                "auth_token": "t", "whatsapp_number": "+1",
            }

        m = WhatsAppManager(config_loader=loader)
        validate = m.get_validator("cust-reuse")
        ch = await m.get_channel("cust-reuse")

        # ONE config load, not two
        assert loader_calls == ["cust-reuse"]
        # Channel's provider is the SAME instance the validator is bound to
        assert validate.__self__ is ch.provider

    async def test_get_validator_after_get_channel_reuses_channel_provider(self):
        """Inverse order: channel first, then validator — same provider."""
        from src.communication.whatsapp_manager import WhatsAppManager

        loader_calls = []

        def loader(cid):
            loader_calls.append(cid)
            return {
                "provider": "twilio", "account_sid": "ACx",
                "auth_token": "t", "whatsapp_number": "+1",
            }

        m = WhatsAppManager(config_loader=loader)
        ch = await m.get_channel("cust-inv")
        validate = m.get_validator("cust-inv")

        assert loader_calls == ["cust-inv"]
        assert validate.__self__ is ch.provider

    def test_raises_for_unconfigured_customer(self):
        """No config → RuntimeError. Caller (webhook) turns this into 404."""
        from src.communication.whatsapp_manager import WhatsAppManager

        def loader(cid):
            return None

        clear_keys = [
            "WHATSAPP_PROVIDER", "WHATSAPP_ACCOUNT_SID",
            "WHATSAPP_AUTH_TOKEN", "WHATSAPP_NUMBER",
        ]
        env_snapshot = {k: os.environ.pop(k) for k in clear_keys if k in os.environ}
        try:
            m = WhatsAppManager(config_loader=loader)
            with pytest.raises(RuntimeError):
                m.get_validator("unknown")
        finally:
            os.environ.update(env_snapshot)

    async def test_invalidate_clears_provider_cache(self):
        """invalidate() must clear the provider cache too — otherwise
        config changes don't take effect for signature validation."""
        from src.communication.whatsapp_manager import WhatsAppManager

        loader_calls = []

        def loader(cid):
            loader_calls.append(cid)
            return {
                "provider": "twilio", "account_sid": "ACx",
                "auth_token": "t", "whatsapp_number": "+1",
            }

        m = WhatsAppManager(config_loader=loader)
        v1 = m.get_validator("cust-inval")
        m.invalidate("cust-inval")
        v2 = m.get_validator("cust-inval")

        # Two separate loader calls → two separate provider builds
        assert loader_calls == ["cust-inval", "cust-inval"]
        # Different provider INSTANCES (not just different bound methods)
        assert v1.__self__ is not v2.__self__


# -------------------------------------------------------------------
# Per-customer provider selection
# -------------------------------------------------------------------

class TestMultiProvider:
    async def test_different_customers_can_use_different_providers(self):
        """Acceptance criterion: channel instantiated with different provider
        configurations per customer."""
        from src.communication.whatsapp_manager import WhatsAppManager
        from src.communication.providers import PROVIDER_REGISTRY
        from src.communication.providers.base_provider import (
            DeliveryState, InboundMessage, MessageStatus, WhatsAppProvider,
        )
        from datetime import datetime

        # Register a second dummy provider
        class AltProvider(WhatsAppProvider):
            def __init__(self, **kw):
                self.kw = kw
            async def send_text(self, to, body):
                return "alt-id"
            def parse_incoming_webhook(self, d):
                return InboundMessage("a", "+1", "+2", "", datetime.now())
            def parse_status_callback(self, d):
                return MessageStatus("a", DeliveryState.SENT, datetime.now())
            def validate_signature(self, u, d, s):
                return True
            async def fetch_message_status(self, m):
                return MessageStatus(m, DeliveryState.SENT, datetime.now())

        PROVIDER_REGISTRY["alt"] = AltProvider
        try:
            configs = {
                "cust-twilio": {
                    "provider": "twilio", "account_sid": "ACx",
                    "auth_token": "t", "whatsapp_number": "+1",
                },
                "cust-alt": {
                    "provider": "alt", "foo": "bar",
                },
            }
            m = WhatsAppManager(config_loader=lambda c: configs[c])
            ch_twilio = await m.get_channel("cust-twilio")
            ch_alt = await m.get_channel("cust-alt")

            assert type(ch_twilio.provider).__name__ == "TwilioWhatsAppProvider"
            assert type(ch_alt.provider).__name__ == "AltProvider"
        finally:
            del PROVIDER_REGISTRY["alt"]
