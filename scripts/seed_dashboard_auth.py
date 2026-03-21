#!/usr/bin/env python3
"""
Seed a dashboard login secret for a customer.

    uv run scripts/seed_dashboard_auth.py <customer_id> [secret]

Omitting the secret generates a random one and prints it. The value is
written to Redis at auth:{customer_id}:secret — the same key the
POST /v1/auth/login endpoint checks. This is the MVP pre-shared-key
auth scheme; replace when OAuth lands.
"""
import asyncio
import secrets
import sys

import redis.asyncio as aioredis

from src.utils.config import RedisConfig


async def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: seed_dashboard_auth.py <customer_id> [secret]")

    customer_id = sys.argv[1]
    secret = sys.argv[2] if len(sys.argv) > 2 else secrets.token_urlsafe(24)

    cfg = RedisConfig.from_env()
    client = aioredis.from_url(cfg.url)
    try:
        key = f"auth:{customer_id}:secret"
        await client.set(key, secret)
        print(f"  {key}  →  {secret}")
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
