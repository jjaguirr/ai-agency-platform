"""
N8n connection configuration.

Per-customer config stored in Redis. Falls back to environment variables
for single-instance / development setups.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class N8nConfig:
    base_url: str
    api_key: str

    # --- Redis persistence ---------------------------------------------------

    @staticmethod
    def _key(customer_id: str) -> str:
        return f"n8n:{customer_id}:config"

    async def save(self, redis, customer_id: str) -> None:
        payload = json.dumps({"base_url": self.base_url, "api_key": self.api_key})
        await redis.set(self._key(customer_id), payload)

    @classmethod
    async def load(cls, redis, customer_id: str) -> Optional["N8nConfig"]:
        raw = await redis.get(cls._key(customer_id))
        if raw is None:
            return None
        data = json.loads(raw if isinstance(raw, str) else raw.decode())
        return cls(base_url=data["base_url"], api_key=data["api_key"])

    # --- Environment ---------------------------------------------------------

    @classmethod
    def from_env(cls) -> "N8nConfig":
        return cls(
            base_url=os.environ.get("N8N_BASE_URL", "http://localhost:5678"),
            api_key=os.environ.get("N8N_API_KEY", ""),
        )
