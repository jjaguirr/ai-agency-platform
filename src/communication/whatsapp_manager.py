"""
Multi-tenant WhatsApp channel manager.

Responsible for:
- Per-customer channel caching
- Loading per-customer provider config (via callback or env-var fallback)
- Wiring the message handler (EA integration point) into each channel

Deliberately free of I/O at construction time — no DB, no Redis, no globals.
Safe to import without side effects.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, Optional

from .providers import create_provider
from .providers.base_provider import WhatsAppProvider
from .whatsapp_channel import MessageHandler, WhatsAppChannel

logger = logging.getLogger(__name__)

# Loads provider config for a given customer. Return None to fall through to env vars.
ConfigLoader = Callable[[str], Optional[Dict[str, Any]]]

# Builds a message handler for a given customer.
# Typically wraps ExecutiveAssistant.handle_customer_interaction.
HandlerFactory = Callable[[str], MessageHandler]

# Default provider when config doesn't specify one
_DEFAULT_PROVIDER = "twilio"

# Env var prefix for fallback config
_ENV_PREFIX = "WHATSAPP_"

# Signature-validator callable: (url, form_data, signature) -> bool
SignatureValidator = Callable[[str, Dict[str, Any], Optional[str]], bool]


class WhatsAppManager:
    """Caches and constructs WhatsAppChannel instances per customer.

    Args:
        config_loader: Optional callback `(customer_id) -> config_dict | None`.
            Config dict must contain at minimum the provider-specific credentials.
            A "provider" key selects the backend (defaults to "twilio").
            If the loader returns None (or is not provided), falls back to
            WHATSAPP_* environment variables.
        handler_factory: Optional callback `(customer_id) -> async handler`.
            The handler is attached to each channel as its message_handler.
            This is the seam where you plug in the Executive Assistant.

    Config dict shape::

        {
            "provider": "twilio",               # optional, default "twilio"
            "account_sid": "ACxxx...",          # provider-specific keys
            "auth_token": "...",
            "whatsapp_number": "+14155238886",
        }

    Env-var fallback (all prefixed WHATSAPP_)::

        WHATSAPP_PROVIDER=twilio
        WHATSAPP_ACCOUNT_SID=ACxxx...
        WHATSAPP_AUTH_TOKEN=...
        WHATSAPP_NUMBER=+14155238886
    """

    def __init__(
        self,
        config_loader: Optional[ConfigLoader] = None,
        handler_factory: Optional[HandlerFactory] = None,
    ):
        self._config_loader = config_loader
        self._handler_factory = handler_factory
        # Providers cached separately from channels so the webhook can validate
        # signatures WITHOUT building a full channel (pre-auth → lightweight).
        self._providers: Dict[str, WhatsAppProvider] = {}
        self._channels: Dict[str, WhatsAppChannel] = {}

    def get_validator(self, customer_id: str) -> SignatureValidator:
        """Return the signature-validator callable for a customer.

        Does NOT build a channel, does NOT call handler_factory. This is the
        cheap path the webhook uses before authenticating a request — so a
        forged signature never triggers channel construction.

        Raises RuntimeError if no config is found (caller maps to 404).
        """
        provider = self._get_or_build_provider(customer_id)
        return provider.validate_signature

    async def get_channel(self, customer_id: str) -> WhatsAppChannel:
        """Get or create the WhatsAppChannel for a customer.

        Reuses a provider previously built by get_validator() so config is
        loaded at most once per customer.
        """
        if customer_id in self._channels:
            return self._channels[customer_id]

        provider = self._get_or_build_provider(customer_id)
        handler = self._handler_factory(customer_id) if self._handler_factory else None

        channel = WhatsAppChannel(
            customer_id=customer_id,
            provider=provider,
            message_handler=handler,
        )
        await channel.initialize()

        self._channels[customer_id] = channel
        logger.info(
            "WhatsApp channel ready: customer=%s provider=%s",
            customer_id,
            type(provider).__name__,
        )
        return channel

    def _get_or_build_provider(self, customer_id: str) -> WhatsAppProvider:
        if customer_id in self._providers:
            return self._providers[customer_id]

        config = self._resolve_config(customer_id)
        provider_name = config.pop("provider", _DEFAULT_PROVIDER)
        provider = create_provider(provider_name, config)
        self._providers[customer_id] = provider
        return provider

    def invalidate(self, customer_id: str) -> None:
        """Drop cached provider + channel for a customer (e.g. config change)."""
        self._channels.pop(customer_id, None)
        self._providers.pop(customer_id, None)

    # ------------------------------------------------------------------
    # Config resolution
    # ------------------------------------------------------------------

    def _resolve_config(self, customer_id: str) -> Dict[str, Any]:
        # Try loader first
        if self._config_loader is not None:
            cfg = self._config_loader(customer_id)
            if cfg is not None:
                return dict(cfg)  # shallow copy so caller's dict isn't mutated

        # Fall through to env vars
        env_cfg = self._config_from_env()
        if env_cfg:
            return env_cfg

        raise RuntimeError(
            f"No WhatsApp config for customer '{customer_id}': "
            f"no config_loader result and no {_ENV_PREFIX}* env vars set"
        )

    @staticmethod
    def _config_from_env() -> Optional[Dict[str, Any]]:
        """Build a provider config dict from WHATSAPP_* env vars.

        Returns None if no relevant env vars are set.
        """
        provider = os.getenv(f"{_ENV_PREFIX}PROVIDER", _DEFAULT_PROVIDER)

        # Collect all WHATSAPP_* vars, lowercase the suffix as config keys
        config: Dict[str, Any] = {}
        for env_key, value in os.environ.items():
            if not env_key.startswith(_ENV_PREFIX):
                continue
            if env_key == f"{_ENV_PREFIX}PROVIDER":
                continue  # handled separately
            # WHATSAPP_ACCOUNT_SID → account_sid, WHATSAPP_NUMBER → whatsapp_number
            suffix = env_key[len(_ENV_PREFIX):].lower()
            if suffix == "number":
                suffix = "whatsapp_number"
            config[suffix] = value

        if not config:
            return None

        config["provider"] = provider
        return config
