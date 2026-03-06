"""Per-customer WhatsApp configuration following src/utils/config.py convention."""
import os
from dataclasses import dataclass, field


@dataclass
class WhatsAppConfig:
    provider: str                               # "twilio", "meta_cloud", ...
    from_number: str                            # E.164 WhatsApp sender number
    credentials: dict[str, str] = field(default_factory=dict)
    webhook_base_url: str = ""

    def webhook_url_for(self, customer_id: str) -> str:
        base = self.webhook_base_url.rstrip("/")
        return f"{base}/webhook/whatsapp/{customer_id}"

    @classmethod
    def from_env(cls, prefix: str = "WHATSAPP_") -> "WhatsAppConfig":
        provider = os.getenv(f"{prefix}PROVIDER", "twilio")
        from_number = os.getenv(f"{prefix}FROM_NUMBER", "")
        webhook_base_url = os.getenv(f"{prefix}WEBHOOK_BASE_URL", "")

        credentials: dict[str, str] = {}
        if provider == "twilio":
            credentials = {
                "account_sid": os.getenv("TWILIO_ACCOUNT_SID", ""),
                "auth_token": os.getenv("TWILIO_AUTH_TOKEN", ""),
            }

        return cls(
            provider=provider,
            from_number=from_number,
            credentials=credentials,
            webhook_base_url=webhook_base_url,
        )

    @classmethod
    def from_dict(cls, d: dict) -> "WhatsAppConfig":
        return cls(
            provider=d["provider"],
            from_number=d["from_number"],
            credentials=dict(d.get("credentials", {})),
            webhook_base_url=d.get("webhook_base_url", ""),
        )
