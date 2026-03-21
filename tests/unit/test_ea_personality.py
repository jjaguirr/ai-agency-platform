"""
Personality settings wiring — EA reads tone/name/language from Redis.

Settings live in Redis at `settings:{customer_id}` as JSON. The EA
fetches them once at the start of handle_customer_interaction, caches
for the request, and uses them in prompts instead of hard-coded values.

When no settings exist (first-time customer), defaults apply.
"""
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.base.specialist import DelegationRegistry


# --- Lightweight EA fixture (same pattern as test_action_confirmation) ------

@pytest.fixture
def ea():
    with patch("src.agents.executive_assistant.ExecutiveAssistantMemory") as MockMem, \
         patch("src.agents.executive_assistant.WorkflowCreator"), \
         patch("src.agents.executive_assistant.ChatOpenAI"):
        from src.agents.executive_assistant import ExecutiveAssistant, BusinessContext

        mem = MockMem.return_value
        mem.get_business_context = AsyncMock(return_value=BusinessContext(
            business_name="Test Co",
        ))
        mem.search_business_knowledge = AsyncMock(return_value=[])
        mem.store_conversation_context = AsyncMock()
        mem.get_conversation_context = AsyncMock(return_value={})
        mem.store_business_context = AsyncMock()

        instance = ExecutiveAssistant(customer_id="cust_test")
        instance.llm = None
        yield instance


def _settings_json(*, tone="friendly", name="Alex", language="es"):
    return json.dumps({
        "working_hours": {"start": "09:00", "end": "18:00", "timezone": "UTC"},
        "briefing": {"enabled": True, "time": "08:00"},
        "proactive": {"priority_threshold": "MEDIUM", "daily_cap": 5, "idle_nudge_minutes": 120},
        "personality": {"tone": tone, "name": name, "language": language},
        "connected_services": {"calendar": False, "n8n": False},
    })


class TestPersonalityFromRedis:
    @pytest.mark.asyncio
    async def test_ea_uses_custom_name_from_settings(self, ea):
        """When Redis returns settings with name='Alex', the EA response
        should NOT contain 'Sarah' — it should use 'Alex'."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=_settings_json(name="Alex"))
        ea.settings_redis = mock_redis

        from src.agents.executive_assistant import ConversationChannel
        response = await ea.handle_customer_interaction(
            message="hello",
            channel=ConversationChannel.CHAT,
            conversation_id="conv_personality",
        )

        # EA should identify as Alex, not Sarah
        assert ea.name == "Alex"

    @pytest.mark.asyncio
    async def test_ea_uses_custom_tone(self, ea):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=_settings_json(tone="concise"))
        ea.settings_redis = mock_redis

        from src.agents.executive_assistant import ConversationChannel
        await ea.handle_customer_interaction(
            message="hi",
            channel=ConversationChannel.CHAT,
            conversation_id="conv_tone",
        )

        assert ea.personality == "concise"

    @pytest.mark.asyncio
    async def test_ea_uses_custom_language(self, ea):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=_settings_json(language="es"))
        ea.settings_redis = mock_redis

        from src.agents.executive_assistant import ConversationChannel
        await ea.handle_customer_interaction(
            message="hola",
            channel=ConversationChannel.CHAT,
            conversation_id="conv_lang",
        )

        assert ea.language == "es"


class TestPersonalityDefaults:
    @pytest.mark.asyncio
    async def test_no_settings_redis_uses_defaults(self, ea):
        """When settings_redis is None (tests, old construction),
        defaults apply — no crash."""
        assert ea.settings_redis is None

        from src.agents.executive_assistant import ConversationChannel
        response = await ea.handle_customer_interaction(
            message="hello",
            channel=ConversationChannel.CHAT,
            conversation_id="conv_default",
        )

        assert ea.name == "Assistant"
        assert ea.personality == "professional"
        assert response  # non-empty response

    @pytest.mark.asyncio
    async def test_empty_redis_value_uses_defaults(self, ea):
        """Redis returns None (key doesn't exist) → defaults."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        ea.settings_redis = mock_redis

        from src.agents.executive_assistant import ConversationChannel
        await ea.handle_customer_interaction(
            message="hello",
            channel=ConversationChannel.CHAT,
            conversation_id="conv_empty",
        )

        assert ea.name == "Assistant"
        assert ea.personality == "professional"

    @pytest.mark.asyncio
    async def test_redis_failure_uses_defaults(self, ea):
        """Redis GET raises → fallback to defaults, no crash."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=Exception("Redis down"))
        ea.settings_redis = mock_redis

        from src.agents.executive_assistant import ConversationChannel
        response = await ea.handle_customer_interaction(
            message="hello",
            channel=ConversationChannel.CHAT,
            conversation_id="conv_fail",
        )

        assert ea.name == "Assistant"
        assert ea.personality == "professional"
        assert response

    @pytest.mark.asyncio
    async def test_redis_called_once_per_interaction(self, ea):
        """Personality is fetched once per handle_customer_interaction call."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=_settings_json(name="Alex"))
        ea.settings_redis = mock_redis

        from src.agents.executive_assistant import ConversationChannel
        await ea.handle_customer_interaction(
            message="hello",
            channel=ConversationChannel.CHAT,
            conversation_id="conv_once",
        )

        # Only one GET for the settings key
        settings_calls = [
            c for c in mock_redis.get.await_args_list
            if "settings:" in str(c)
        ]
        assert len(settings_calls) == 1
