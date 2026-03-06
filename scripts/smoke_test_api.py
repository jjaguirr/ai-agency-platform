"""
Live HTTP smoke test for the API.

Boots a real uvicorn server (in-process, random port) with stubbed
EA + orchestrator, then drives it over actual HTTP with httpx:

    1. POST /v1/customers/provision  → get customer_id + JWT
    2. POST /v1/conversations/message with that JWT → get EA response
    3. GET  /healthz, /readyz

This is NOT a unit test — it exercises the full HTTP stack (routing,
auth middleware, serialization, error handlers) against a live socket.
The only mocks are the downstream services the API *calls*, not the
API itself.

Why not create_default_app()?
    That needs Docker + Redis + mem0 running. This script proves the
    HTTP layer is wired correctly without requiring local infra.

Run:
    JWT_SECRET=$(python -c 'import secrets; print(secrets.token_hex(32))') \
        .venv/bin/python scripts/smoke_test_api.py
"""
import asyncio
import os
import socket
import sys
import threading
import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import uvicorn


def _free_port() -> int:
    """Ask the OS for a free TCP port, return it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _build_test_app():
    """
    Production app factory (create_app) with stub dependencies.

    The EA stub echoes the message back so we can see the full
    round-trip in the output. The orchestrator stub returns a
    fake env so provisioning succeeds.
    """
    from src.api.app import create_app
    from src.api.ea_registry import EARegistry

    # --- EA stub: echoes the message + channel ---
    # Using a real class (not AsyncMock) so we can see per-customer state
    class EchoEA:
        def __init__(self, customer_id: str):
            self.customer_id = customer_id
            self.call_count = 0

        async def handle_customer_interaction(
            self, *, message: str, channel, conversation_id: str
        ) -> str:
            self.call_count += 1
            # Simulate a tiny bit of "thinking"
            await asyncio.sleep(0.01)
            return (
                f"[EA for {self.customer_id}] "
                f"Received '{message}' via {channel.value}. "
                f"This is call #{self.call_count} in conv {conversation_id[:8]}."
            )

    ea_registry = EARegistry(factory=EchoEA)

    # --- Orchestrator stub: returns a fake env ---
    orch = AsyncMock()

    async def fake_provision(*, customer_id, tier, **_):
        env = MagicMock()
        env.customer_id = customer_id
        env.tier = tier
        return env

    orch.provision_customer_environment = AsyncMock(side_effect=fake_provision)

    # --- WhatsApp manager stub: not exercised in this smoke test ---
    wa_manager = MagicMock()
    wa_manager.get_channel = AsyncMock(return_value=None)

    # --- Redis stub: ping succeeds so /readyz reports ready ---
    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True)

    return create_app(
        ea_registry=ea_registry,
        orchestrator=orch,
        whatsapp_manager=wa_manager,
        redis_client=redis,
    )


class ServerThread:
    """Run uvicorn in a background thread, stoppable."""

    def __init__(self, app, port: int):
        self.config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",  # keep output clean; we print our own
        )
        self.server = uvicorn.Server(self.config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.port = port

    def __enter__(self):
        self.thread.start()
        # Wait for server to come up (poll the started flag, not sleep)
        for _ in range(50):
            if self.server.started:
                return self
            time.sleep(0.05)
        raise RuntimeError("uvicorn did not start within 2.5s")

    def __exit__(self, *_):
        self.server.should_exit = True
        self.thread.join(timeout=3.0)


def _p(label: str, msg: str = "", *, indent: int = 0):
    """Formatted print with a consistent look."""
    prefix = "  " * indent
    if msg:
        print(f"{prefix}\033[36m{label:<24}\033[0m {msg}")
    else:
        print(f"{prefix}\033[1m{label}\033[0m")


def main() -> int:
    # Sanity: JWT_SECRET must be set and long enough, same as prod.
    # We DON'T set it here — forcing the caller to provide it mirrors
    # the real deployment check.
    if "JWT_SECRET" not in os.environ:
        print(
            "JWT_SECRET not set. Run:\n"
            "  JWT_SECRET=$(python -c 'import secrets; print(secrets.token_hex(32))') "
            "python scripts/smoke_test_api.py",
            file=sys.stderr,
        )
        return 1

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    app = _build_test_app()

    print(f"\033[1m== API smoke test — server on {base} ==\033[0m\n")

    with ServerThread(app, port):
        with httpx.Client(base_url=base, timeout=10.0) as client:
            # ----------------------------------------------------------------
            # Step 1: health endpoints — confirm server is alive
            # ----------------------------------------------------------------
            _p("[1] Health checks")

            resp = client.get("/healthz")
            _p("GET /healthz", f"→ {resp.status_code} {resp.json()}", indent=1)
            assert resp.status_code == 200, "liveness should always be 200"

            resp = client.get("/readyz")
            _p("GET /readyz", f"→ {resp.status_code} {resp.json()}", indent=1)
            assert resp.status_code == 200, "readiness should be 200 with stub redis"
            assert resp.json()["checks"]["redis"] == "ok"
            print()

            # ----------------------------------------------------------------
            # Step 2: provision — no auth, mints the token we'll use
            # ----------------------------------------------------------------
            _p("[2] Provision test customer")

            resp = client.post(
                "/v1/customers/provision",
                json={"tier": "professional", "customer_id": "smoke_test_cust"},
            )
            _p("POST /v1/customers/provision",
               f"→ {resp.status_code}", indent=1)
            _p("  body", str(resp.json()), indent=1)
            assert resp.status_code == 201

            body = resp.json()
            customer_id = body["customer_id"]
            token = body["token"]
            assert customer_id == "smoke_test_cust"
            assert token  # non-empty

            # Decode the token locally to show what's inside
            # (proves the auth round-trip contract)
            from src.api.auth import decode_token
            claims = decode_token(token)
            _p("  token claims", str(claims), indent=1)
            assert claims["customer_id"] == customer_id
            print()

            # ----------------------------------------------------------------
            # Step 3: send hello-world message using the minted token
            # ----------------------------------------------------------------
            _p("[3] Send 'hello world' to conversation endpoint")

            auth_headers = {"Authorization": f"Bearer {token}"}
            resp = client.post(
                "/v1/conversations/message",
                json={"message": "hello world", "channel": "chat"},
                headers=auth_headers,
            )
            _p("POST /v1/conversations/message",
               f"→ {resp.status_code}", indent=1)
            assert resp.status_code == 200

            msg_body = resp.json()
            conversation_id = msg_body["conversation_id"]
            _p("  conversation_id", conversation_id, indent=1)
            _p("  EA response", msg_body["response"], indent=1)
            # EA stub echoes the message — verify end-to-end data flow
            assert "hello world" in msg_body["response"]
            assert customer_id in msg_body["response"]
            print()

            # ----------------------------------------------------------------
            # Step 4: follow-up message — same conversation_id, prove EA
            # instance is cached (call_count should be 2)
            # ----------------------------------------------------------------
            _p("[4] Follow-up in same conversation — proves EA instance cached")

            resp = client.post(
                "/v1/conversations/message",
                json={
                    "message": "still there?",
                    "channel": "chat",
                    "conversation_id": conversation_id,
                },
                headers=auth_headers,
            )
            _p("POST /v1/conversations/message",
               f"→ {resp.status_code}", indent=1)
            _p("  EA response", resp.json()["response"], indent=1)
            # "#2" in the response means the SAME EA instance handled both
            # calls — registry caching works.
            assert "call #2" in resp.json()["response"], \
                "expected same EA instance (call count 2) — registry not caching?"
            assert resp.json()["conversation_id"] == conversation_id
            print()

            # ----------------------------------------------------------------
            # Step 5: auth enforcement — bad token, no token
            # ----------------------------------------------------------------
            _p("[5] Auth enforcement")

            resp = client.post(
                "/v1/conversations/message",
                json={"message": "sneaky", "channel": "chat"},
                # no Authorization header
            )
            _p("no token", f"→ {resp.status_code} {resp.json()}", indent=1)
            assert resp.status_code == 401

            resp = client.post(
                "/v1/conversations/message",
                json={"message": "sneaky", "channel": "chat"},
                headers={"Authorization": "Bearer not.a.real.jwt"},
            )
            _p("garbage token", f"→ {resp.status_code} {resp.json()}", indent=1)
            assert resp.status_code == 401
            print()

            # ----------------------------------------------------------------
            # Step 6: validation — bad channel, bad customer_id
            # ----------------------------------------------------------------
            _p("[6] Schema validation")

            resp = client.post(
                "/v1/conversations/message",
                json={"message": "hi", "channel": "smoke_signals"},
                headers=auth_headers,
            )
            _p("invalid channel", f"→ {resp.status_code}", indent=1)
            assert resp.status_code == 422

            resp = client.post(
                "/v1/customers/provision",
                json={"tier": "basic", "customer_id": "../../etc/passwd"},
            )
            _p("path-traversal customer_id",
               f"→ {resp.status_code}", indent=1)
            assert resp.status_code == 422
            print()

    print("\033[32m✓ All smoke checks passed.\033[0m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
