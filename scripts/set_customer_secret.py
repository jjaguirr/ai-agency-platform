#!/usr/bin/env python3
"""Seed a pre-shared login secret for a customer into Redis.

Usage:
    python scripts/set_customer_secret.py <customer_id> <secret>

The secret is stored at ``customer_secret:{customer_id}`` and used by
``POST /v1/auth/login`` to issue JWT tokens.

Environment:
    REDIS_HOST  (default: localhost)
    REDIS_PORT  (default: 6379)
    REDIS_DB    (default: 0)
"""
import os
import sys

import redis


def main():
    if len(sys.argv) != 3:
        print(__doc__.strip())
        sys.exit(1)

    customer_id, secret = sys.argv[1], sys.argv[2]
    host = os.environ.get("REDIS_HOST", "localhost")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    db = int(os.environ.get("REDIS_DB", "0"))

    r = redis.Redis(host=host, port=port, db=db)
    key = f"customer_secret:{customer_id}"
    r.set(key, secret)
    print(f"Set {key}")


if __name__ == "__main__":
    main()
