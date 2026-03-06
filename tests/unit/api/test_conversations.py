"""
Conversation endpoint + EA pool tests.

The pool is the critical piece: two requests for the same customer arriving
concurrently must not create two EA instances. The endpoint is a thin wrapper
around pool.get() + ea.handle_customer_interaction().
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import EAPool


# --- EA pool ---------------------------------------------------------------

class TestEAPool:
    async def test_creates_instance_on_first_get(self):
        created = []

        def factory(cid):
            ea = MagicMock()
            ea.customer_id = cid
            created.append(ea)
            return ea

        pool = EAPool(ea_factory=factory)
        ea = await pool.get("cust_a")

        assert ea.customer_id == "cust_a"
        assert len(created) == 1

    async def test_second_get_returns_cached_instance(self):
        created = []

        def factory(cid):
            ea = MagicMock()
            created.append(ea)
            return ea

        pool = EAPool(ea_factory=factory)
        ea1 = await pool.get("cust_a")
        ea2 = await pool.get("cust_a")

        assert ea1 is ea2
        assert len(created) == 1

    async def test_different_customers_get_different_instances(self):
        pool = EAPool(ea_factory=lambda cid: MagicMock(customer_id=cid))
        ea_a = await pool.get("cust_a")
        ea_b = await pool.get("cust_b")

        assert ea_a is not ea_b
        assert ea_a.customer_id == "cust_a"
        assert ea_b.customer_id == "cust_b"

    async def test_lock_serializes_creation_under_real_contention(self):
        """
        Force genuine overlap: pre-acquire the pool's lock, launch N get()
        tasks, let them all pass the fast-path check and queue on the lock,
        THEN release. Without the double-check inside the lock, every queued
        task would call the factory.

        This is white-box (touches pool._lock) but it's the only way to
        create contention with a sync factory — otherwise the first
        coroutine completes before any other is scheduled, and the lock is
        never contended.
        """
        call_count = 0

        def factory(cid):
            nonlocal call_count
            call_count += 1
            return MagicMock(customer_id=cid)

        pool = EAPool(ea_factory=factory)

        # Hold the lock so all gets pile up behind it.
        await pool._lock.acquire()
        tasks = [asyncio.create_task(pool.get("cust_race")) for _ in range(10)]
        # Yield so every task runs up to the lock acquire and suspends.
        await asyncio.sleep(0)
        # All 10 are now past the fast-path check (cache was empty) and
        # waiting on the lock. Release it.
        pool._lock.release()

        results = await asyncio.gather(*tasks)

        assert call_count == 1, (
            f"Factory called {call_count}× — double-check inside lock failed"
        )
        assert all(r is results[0] for r in results)

    async def test_uncontended_gathers_still_singleton(self):
        """
        Contract test: N concurrent gets → 1 instance. Without forced
        contention this doesn't exercise the lock (sync factory completes
        before other coroutines schedule), but it's the observable guarantee
        the API relies on.
        """
        call_count = 0

        def factory(cid):
            nonlocal call_count
            call_count += 1
            return MagicMock(customer_id=cid)

        pool = EAPool(ea_factory=factory)
        results = await asyncio.gather(*[pool.get("cust_x") for _ in range(20)])
        assert call_count == 1
        assert len({id(r) for r in results}) == 1

    async def test_factory_exception_not_cached(self):
        """
        If construction fails, the next get() should retry — not return a
        broken cached entry or a None.
        """
        attempts = []

        def flaky_factory(cid):
            attempts.append(cid)
            if len(attempts) == 1:
                raise RuntimeError("first construction fails")
            return MagicMock(customer_id=cid)

        pool = EAPool(ea_factory=flaky_factory)

        with pytest.raises(RuntimeError):
            await pool.get("cust_flaky")

        # Second attempt succeeds
        ea = await pool.get("cust_flaky")
        assert ea.customer_id == "cust_flaky"
        assert len(attempts) == 2

    async def test_size_tracks_cached_instances(self):
        pool = EAPool(ea_factory=lambda cid: MagicMock())
        assert pool.size() == 0
        await pool.get("a")
        assert pool.size() == 1
        await pool.get("b")
        assert pool.size() == 2
        await pool.get("a")  # cached — no change
        assert pool.size() == 2


# --- Conversation endpoint -------------------------------------------------
# These need the full app wiring (auth + pool + route), so they use the
# conftest `client` fixture which injects all mocks.

class TestConversationEndpoint:
    def test_valid_request_returns_ea_response(self, client, auth_header, mock_ea_factory):
        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hello", "channel": "chat"},
            headers=auth_header("cust_convo"),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["response"] == "mock EA response"
        assert body["customer_id"] == "cust_convo"
        assert "conversation_id" in body

        # The EA for this customer was created and called
        assert len(mock_ea_factory.created) == 1
        cid, ea = mock_ea_factory.created[0]
        assert cid == "cust_convo"
        ea.handle_customer_interaction.assert_awaited_once()

    def test_channel_string_maps_to_enum(self, client, auth_header, mock_ea_factory):
        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "whatsapp"},
            headers=auth_header("cust_chan"),
        )
        assert resp.status_code == 200

        _, ea = mock_ea_factory.created[0]
        call_kwargs = ea.handle_customer_interaction.call_args.kwargs
        # The EA receives the enum, not the string
        assert call_kwargs["channel"].value == "whatsapp"

    def test_conversation_id_passthrough(self, client, auth_header, mock_ea_factory):
        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "chat", "conversation_id": "conv-123"},
            headers=auth_header("cust_conv"),
        )
        assert resp.status_code == 200
        assert resp.json()["conversation_id"] == "conv-123"

        _, ea = mock_ea_factory.created[0]
        assert ea.handle_customer_interaction.call_args.kwargs["conversation_id"] == "conv-123"

    def test_missing_token_returns_401(self, client):
        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "chat"},
        )
        assert resp.status_code == 401

    def test_expired_token_returns_401(self, client, jwt_secret):
        from datetime import timedelta
        from src.api.auth import create_token

        expired = create_token("cust_x", secret=jwt_secret, expires_delta=timedelta(seconds=-1))
        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "chat"},
            headers={"Authorization": f"Bearer {expired}"},
        )
        assert resp.status_code == 401

    def test_invalid_channel_returns_422(self, client, auth_header):
        resp = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "telegram"},
            headers=auth_header(),
        )
        assert resp.status_code == 422

    def test_missing_message_returns_422(self, client, auth_header):
        resp = client.post(
            "/v1/conversations/message",
            json={"channel": "chat"},
            headers=auth_header(),
        )
        assert resp.status_code == 422

    def test_ea_degraded_response_passed_through_as_200(self, jwt_secret):
        """
        The EA never raises — it returns fallback text on internal failure.
        The API must pass that exact text through with 200, not pattern-match
        on apology strings and infer an error.

        Builds its own app because the conftest pool is already wired to the
        happy-path factory and pools don't support factory swapping.
        """
        from src.api.app import create_app
        from src.api.auth import create_token

        fallback = "I apologize, but I encountered an issue. Let me get back to you."

        def degraded_factory(cid):
            ea = MagicMock()
            ea.handle_customer_interaction = AsyncMock(return_value=fallback)
            return ea

        app = create_app(
            ea_pool=EAPool(ea_factory=degraded_factory),
            jwt_secret=jwt_secret,
        )
        client = TestClient(app)
        token = create_token("cust_degraded", secret=jwt_secret)

        resp = client.post(
            "/v1/conversations/message",
            json={"message": "trigger internal failure", "channel": "chat"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        # The degraded text comes through verbatim — no 500, no rewriting.
        assert resp.json()["response"] == fallback

    def test_two_requests_same_customer_reuse_ea(self, client, auth_header, mock_ea_factory):
        """Sequential sanity check — the pool across HTTP calls."""
        headers = auth_header("cust_reuse")

        r1 = client.post("/v1/conversations/message",
                         json={"message": "first", "channel": "chat"}, headers=headers)
        r2 = client.post("/v1/conversations/message",
                         json={"message": "second", "channel": "chat"}, headers=headers)

        assert r1.status_code == r2.status_code == 200
        # Only one EA created for this customer
        custs = [cid for cid, _ in mock_ea_factory.created]
        assert custs.count("cust_reuse") == 1
        # But it was called twice
        _, ea = next(x for x in mock_ea_factory.created if x[0] == "cust_reuse")
        assert ea.handle_customer_interaction.await_count == 2
