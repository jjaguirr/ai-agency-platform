"""
Multi-tenant WhatsApp channel manager.

Holds per-customer WhatsAppConfig, lazily builds WhatsAppChannel instances
with the configured provider. Optionally delegates config lookup to a
pluggable loader (e.g. DB-backed) when a customer isn't registered in memory.
"""
import logging
from typing import Callable, Optional

from .whatsapp import (
    InMemoryMessageStore, MessageStore, WhatsAppChannel,
    WhatsAppConfig, create_provider,
)

logger = logging.getLogger(__name__)

ConfigLoader = Callable[[str], Optional[WhatsAppConfig]]


class WhatsAppManager:
    """
    Manages WhatsApp channels for multiple customers.

    - In-memory registration for tests and API-driven onboarding
    - Optional `config_loader` for lazy loading (e.g. from database)
    - Shared MessageStore across all channels (inject DB-backed store in production)
    """

    def __init__(self, *,
                 store: MessageStore | None = None,
                 config_loader: ConfigLoader | None = None):
        self._configs: dict[str, WhatsAppConfig] = {}
        self._channels: dict[str, WhatsAppChannel] = {}
        self._store: MessageStore = store or InMemoryMessageStore()
        self._config_loader = config_loader

    @property
    def store(self) -> MessageStore:
        return self._store

    def register_customer(self, customer_id: str, config: WhatsAppConfig) -> None:
        self._configs[customer_id] = config
        # Drop cached channel so next get_channel() rebuilds with new config
        self._channels.pop(customer_id, None)

    def get_config(self, customer_id: str) -> WhatsAppConfig | None:
        return self._configs.get(customer_id)

    def has_customer(self, customer_id: str) -> bool:
        return customer_id in self._configs

    async def get_channel(self, customer_id: str) -> WhatsAppChannel | None:
        if customer_id in self._channels:
            return self._channels[customer_id]

        cfg = self._configs.get(customer_id)
        if cfg is None and self._config_loader is not None:
            cfg = self._config_loader(customer_id)
            if cfg is not None:
                self._configs[customer_id] = cfg

        if cfg is None:
            return None

        provider = create_provider(cfg.provider, cfg.credentials)
        channel = WhatsAppChannel(
            customer_id=customer_id,
            config={
                "from_number": cfg.from_number,
                "webhook_url": cfg.webhook_url_for(customer_id),
            },
            provider=provider,
            store=self._store,
        )
        await channel.initialize()
        self._channels[customer_id] = channel
        logger.info(
            "Built WhatsApp channel for customer=%s provider=%s",
            customer_id, cfg.provider,
        )
        return channel
