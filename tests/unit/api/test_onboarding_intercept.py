"""Tests for the onboarding intercept in the conversation message pipeline."""
import json
import os

import pytest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault(
    "JWT_SECRET", "test-secret-do-not-use-in-prod-32-chars-min-xxxxxxxx"
)

import fakeredis.aioredis
import httpx

from src.api.app import create_app
from src.api.auth import create_token
from src.api.ea_registry import EARegistry
from src.api.schemas import Settings
from src.onboarding.state import OnboardingStateStore

CID = "cust_onb_intercept"


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def onboarding_store(fake_redis):
    return OnboardingStateStore(fake_redis)


@pytest.fixture
def mock_ea():
    ea = AsyncMock()
    ea.customer_id = CID
    ea.handle_customer_interaction = AsyncMock(return_value="EA reply")
    ea.last_specialist_domain = None
    return ea


@pytest.fixture
def mock_ea_registry(mock_ea):
    registry = MagicMock()
    registry.get = AsyncMock(return_value=mock_ea)
    return registry


@pytest.fixture
def app(mock_ea_registry, fake_redis, onboarding_store):
    return create_app(
        ea_registry=mock_ea_registry,
        orchestrator=AsyncMock(),
        whatsapp_manager=MagicMock(),
        redis_client=fake_redis,
        onboarding_state_store=onboarding_store,
    )


@pytest.fixture
async def aclient(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers():
    token = create_token(CID)
    return {"Authorization": f"Bearer {token}"}


class TestOnboardingIntercept:
    @pytest.mark.asyncio
    async def test_first_message_triggers_introduction(
        self, aclient, auth_headers, onboarding_store, mock_ea,
    ):
        await onboarding_store.initialize(CID)
        # Seed default settings so personality loads
        resp = await aclient.post(
            "/v1/conversations/message",
            headers=auth_headers,
            json={"message": "hello", "channel": "whatsapp"},
        )
        assert resp.status_code == 200
        body = resp.json()
        # Should get an onboarding intro, not the EA
        assert "Assistant" in body["response"]
        mock_ea.handle_customer_interaction.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_second_message_collects_business(
        self, aclient, auth_headers, onboarding_store, fake_redis, mock_ea,
    ):
        await onboarding_store.initialize(CID)
        # First message → intro (step 0→1)
        await aclient.post(
            "/v1/conversations/message",
            headers=auth_headers,
            json={"message": "hi", "channel": "whatsapp"},
        )
        # Second message → business context (step 1→2)
        resp = await aclient.post(
            "/v1/conversations/message",
            headers=auth_headers,
            json={"message": "I run a restaurant downtown", "channel": "whatsapp"},
        )
        assert resp.status_code == 200
        # Should ask about hours/timezone
        assert "hours" in resp.json()["response"].lower() or "time" in resp.json()["response"].lower()
        mock_ea.handle_customer_interaction.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_preferences_writes_to_settings(
        self, aclient, auth_headers, onboarding_store, fake_redis, mock_ea,
    ):
        await onboarding_store.initialize(CID)
        # Step 0→1: intro
        await aclient.post(
            "/v1/conversations/message",
            headers=auth_headers,
            json={"message": "hi", "channel": "whatsapp"},
        )
        # Step 1→2: business
        await aclient.post(
            "/v1/conversations/message",
            headers=auth_headers,
            json={"message": "consulting firm", "channel": "whatsapp"},
        )
        # Step 2→3: preferences
        await aclient.post(
            "/v1/conversations/message",
            headers=auth_headers,
            json={"message": "9am to 5pm Eastern", "channel": "whatsapp"},
        )

        # Settings should now have working hours written
        raw = await fake_redis.get(f"settings:{CID}")
        assert raw is not None, "preferences step must write settings to Redis"
        settings = json.loads(raw)
        assert settings["working_hours"]["start"] == "09:00"
        assert settings["working_hours"]["end"] == "17:00"

    @pytest.mark.asyncio
    async def test_full_flow_completes_onboarding(
        self, aclient, auth_headers, onboarding_store, mock_ea,
    ):
        await onboarding_store.initialize(CID)
        messages = ["hi", "I run a restaurant", "9 to 5", "yes please"]
        for msg in messages:
            await aclient.post(
                "/v1/conversations/message",
                headers=auth_headers,
                json={"message": msg, "channel": "whatsapp"},
            )

        state = await onboarding_store.get(CID)
        assert state.status == "completed"

    @pytest.mark.asyncio
    async def test_completed_onboarding_routes_to_ea(
        self, aclient, auth_headers, onboarding_store, mock_ea,
    ):
        await onboarding_store.initialize(CID)
        await onboarding_store.mark_completed(CID)

        resp = await aclient.post(
            "/v1/conversations/message",
            headers=auth_headers,
            json={"message": "hello", "channel": "whatsapp"},
        )
        assert resp.status_code == 200
        assert resp.json()["response"] == "EA reply"
        mock_ea.handle_customer_interaction.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_onboarding_store_routes_to_ea(
        self, mock_ea_registry, fake_redis, mock_ea,
    ):
        """Backward compat: apps without onboarding_state_store skip intercept."""
        app = create_app(
            ea_registry=mock_ea_registry,
            orchestrator=AsyncMock(),
            whatsapp_manager=MagicMock(),
            redis_client=fake_redis,
            # No onboarding_state_store
        )
        transport = httpx.ASGITransport(app=app)
        headers = {"Authorization": f"Bearer {create_token(CID)}"}
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/v1/conversations/message",
                headers=headers,
                json={"message": "hello", "channel": "whatsapp"},
            )
        assert resp.status_code == 200
        assert resp.json()["response"] == "EA reply"
        mock_ea.handle_customer_interaction.assert_awaited_once()


class TestOnboardingInterrupt:
    @pytest.mark.asyncio
    async def test_real_request_falls_through_to_ea(
        self, aclient, auth_headers, onboarding_store, mock_ea,
    ):
        await onboarding_store.initialize(CID)
        # First turn starts onboarding (step 0→1)
        await aclient.post(
            "/v1/conversations/message",
            headers=auth_headers,
            json={"message": "hi", "channel": "whatsapp"},
        )
        # Real request during onboarding
        resp = await aclient.post(
            "/v1/conversations/message",
            headers=auth_headers,
            json={"message": "can you schedule a meeting for tomorrow?", "channel": "whatsapp"},
        )
        assert resp.status_code == 200
        assert resp.json()["response"] == "EA reply"
        mock_ea.handle_customer_interaction.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resumes_onboarding_after_interrupt(
        self, aclient, auth_headers, onboarding_store, mock_ea,
    ):
        await onboarding_store.initialize(CID)
        # Step 0→1
        await aclient.post(
            "/v1/conversations/message",
            headers=auth_headers,
            json={"message": "hi", "channel": "whatsapp"},
        )
        # Interrupt with real request
        await aclient.post(
            "/v1/conversations/message",
            headers=auth_headers,
            json={"message": "can you schedule a meeting for tomorrow?", "channel": "whatsapp"},
        )
        mock_ea.handle_customer_interaction.reset_mock()

        # Next message should resume onboarding (still at step 1)
        resp = await aclient.post(
            "/v1/conversations/message",
            headers=auth_headers,
            json={"message": "I run a consulting firm", "channel": "whatsapp"},
        )
        # Should get onboarding response, not EA
        mock_ea.handle_customer_interaction.assert_not_awaited()
        assert "hours" in resp.json()["response"].lower() or "time" in resp.json()["response"].lower()


class TestOnboardingResponseShape:
    @pytest.mark.asyncio
    async def test_onboarding_response_includes_conversation_id(
        self, aclient, auth_headers, onboarding_store,
    ):
        await onboarding_store.initialize(CID)
        resp = await aclient.post(
            "/v1/conversations/message",
            headers=auth_headers,
            json={"message": "hello", "channel": "whatsapp"},
        )
        body = resp.json()
        assert "conversation_id" in body
        assert isinstance(body["conversation_id"], str)
        assert len(body["conversation_id"]) > 0


class TestOnboardingPersonality:
    @pytest.mark.asyncio
    async def test_uses_configured_name(
        self, aclient, auth_headers, onboarding_store, fake_redis, mock_ea,
    ):
        await onboarding_store.initialize(CID)
        # Seed custom personality
        await fake_redis.set(
            f"settings:{CID}",
            Settings(
                personality={"tone": "friendly", "language": "en", "name": "Aria"},
            ).model_dump_json(),
        )

        resp = await aclient.post(
            "/v1/conversations/message",
            headers=auth_headers,
            json={"message": "hello", "channel": "whatsapp"},
        )
        assert "Aria" in resp.json()["response"]
