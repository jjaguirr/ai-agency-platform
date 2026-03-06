"""Provider factory — maps config name to constructor."""
from typing import Callable

from ..provider import WhatsAppProvider
from .twilio import TwilioWhatsAppProvider


PROVIDER_REGISTRY: dict[str, Callable[[dict], WhatsAppProvider]] = {
    "twilio": lambda creds: TwilioWhatsAppProvider(
        account_sid=creds["account_sid"],
        auth_token=creds["auth_token"],
    ),
}


def create_provider(provider_name: str, credentials: dict) -> WhatsAppProvider:
    if provider_name not in PROVIDER_REGISTRY:
        raise ValueError(
            f"Unknown WhatsApp provider: {provider_name!r}. "
            f"Available: {list(PROVIDER_REGISTRY.keys())}"
        )
    return PROVIDER_REGISTRY[provider_name](credentials)
