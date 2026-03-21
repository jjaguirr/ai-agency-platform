"""Safety layer configuration.

All thresholds and limits are env-overridable (SAFETY_* prefix).
Defaults are tuned for a multi-tenant business assistant handling
scheduling, finance, and social-media operations.
"""
import os
from dataclasses import dataclass


@dataclass
class SafetyConfig:
    """Configurable safety thresholds and limits.

    Follows the from_env() pattern used by DatabaseConfig and RedisConfig
    in src/utils/config.py. Every field can be overridden via an
    environment variable (see ``from_env``).
    """

    # Max characters per inbound message. WhatsApp caps at ~4096;
    # 4000 leaves room for encoding overhead.
    max_input_length: int = 4000

    # PromptGuard risk score thresholds (0.0–1.0 scale).
    # >= high → reject outright.  >= medium → log WARNING, allow through.
    injection_high_threshold: float = 0.7
    injection_medium_threshold: float = 0.3

    # Rate limits — sized for a single-worker deployment. Scale by
    # adjusting per-worker or fronting with a shared Redis counter.
    per_customer_per_minute: int = 30    # prevents automated flooding
    per_customer_per_day: int = 500      # prevents runaway integrations
    global_rps: int = 200                # protects the worker process

    # WhatsApp Business API hard limit per message segment.
    whatsapp_max_length: int = 1600

    # Audit event retention. 30 days balances compliance visibility
    # with Redis memory cost. Adjust via SAFETY_AUDIT_TTL.
    audit_ttl_seconds: int = 2_592_000  # 30 days
    audit_page_size: int = 50

    @classmethod
    def from_env(cls) -> "SafetyConfig":
        """Build config from SAFETY_* environment variables, falling
        back to dataclass defaults for any variable not set."""
        return cls(
            max_input_length=int(os.getenv("SAFETY_MAX_INPUT_LENGTH", "4000")),
            injection_high_threshold=float(os.getenv("SAFETY_INJECTION_HIGH_THRESHOLD", "0.7")),
            injection_medium_threshold=float(os.getenv("SAFETY_INJECTION_MEDIUM_THRESHOLD", "0.3")),
            per_customer_per_minute=int(os.getenv("SAFETY_RATE_PER_MINUTE", "30")),
            per_customer_per_day=int(os.getenv("SAFETY_RATE_PER_DAY", "500")),
            global_rps=int(os.getenv("SAFETY_RATE_GLOBAL_RPS", "200")),
            whatsapp_max_length=int(os.getenv("SAFETY_WHATSAPP_MAX_LENGTH", "1600")),
            audit_ttl_seconds=int(os.getenv("SAFETY_AUDIT_TTL", "2592000")),
            audit_page_size=int(os.getenv("SAFETY_AUDIT_PAGE_SIZE", "50")),
        )
