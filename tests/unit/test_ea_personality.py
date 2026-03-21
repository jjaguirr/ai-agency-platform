"""
Personality settings wiring — EA reads tone/language/name from the shared
Redis (db 0) instead of hardcoding "Sarah".

Settings live at Redis key `settings:{customer_id}` (written by the
/v1/settings route). The EA's own memory client is on a DIFFERENT Redis
db (customer_hash % 16), so it cannot see that key — the factory injects
the shared db-0 client as `ea.settings_redis`, same pattern as
`ea.audit_logger`.

Contract:
  - One GET per handle_customer_interaction call. Graph nodes read
    self._personality, not Redis.
  - Missing/partial/malformed → fall back to schema defaults.
  - Name replaces every hardcoded "Sarah" in prompts and fallbacks.
"""
import json

import pytest
import fakeredis.aioredis
from unittest.mock import AsyncMock, MagicMock, patch


DEFAULT = {"tone": "professional", "language": "en", "name": "Assistant"}


# --- Fixtures ---------------------------------------------------------------
# Mirror test_action_confirmation.py — patch the heavy deps so construction
# is cheap, force llm=None so we hit the deterministic paths.

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


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


# --- _load_personality: defaults & error tolerance --------------------------

class TestLoadPersonality:
    @pytest.mark.asyncio
    async def test_defaults_when_settings_redis_is_none(self, ea):
        """Legacy construction path — no injection → hardcoded defaults."""
        ea.settings_redis = None
        await ea._load_personality()
        assert ea._personality == DEFAULT

    @pytest.mark.asyncio
    async def test_defaults_when_key_missing(self, ea, fake_redis):
        """Customer never PUT /v1/settings — key absent."""
        ea.settings_redis = fake_redis
        await ea._load_personality()
        assert ea._personality == DEFAULT

    @pytest.mark.asyncio
    async def test_reads_stored_personality(self, ea, fake_redis):
        await fake_redis.set("settings:cust_test", json.dumps({
            "personality": {"tone": "friendly", "language": "es", "name": "Aria"},
        }))
        ea.settings_redis = fake_redis

        await ea._load_personality()

        assert ea._personality == {
            "tone": "friendly", "language": "es", "name": "Aria",
        }

    @pytest.mark.asyncio
    async def test_merges_partial_over_defaults(self, ea, fake_redis):
        """Only `name` stored → tone/language fall back to defaults."""
        await fake_redis.set("settings:cust_test", json.dumps({
            "personality": {"name": "Aria"},
        }))
        ea.settings_redis = fake_redis

        await ea._load_personality()

        assert ea._personality["name"] == "Aria"
        assert ea._personality["tone"] == "professional"
        assert ea._personality["language"] == "en"

    @pytest.mark.asyncio
    async def test_settings_blob_without_personality_key(self, ea, fake_redis):
        """Settings exist but personality sub-object doesn't."""
        await fake_redis.set("settings:cust_test", json.dumps({
            "working_hours": {"start": "09:00", "end": "17:00"},
        }))
        ea.settings_redis = fake_redis

        await ea._load_personality()

        assert ea._personality == DEFAULT

    @pytest.mark.asyncio
    async def test_malformed_json_falls_back_to_defaults(self, ea, fake_redis):
        """Corrupt value → don't crash the interaction, just use defaults."""
        await fake_redis.set("settings:cust_test", "}{not json")
        ea.settings_redis = fake_redis

        await ea._load_personality()

        assert ea._personality == DEFAULT

    @pytest.mark.asyncio
    async def test_redis_error_falls_back_to_defaults(self, ea):
        """Redis down → interaction continues with defaults."""
        broken = AsyncMock()
        broken.get = AsyncMock(side_effect=ConnectionError("redis unreachable"))
        ea.settings_redis = broken

        await ea._load_personality()

        assert ea._personality == DEFAULT


# --- Prompt assembly uses loaded personality --------------------------------

class TestPersonalityInPrompts:
    @pytest.mark.asyncio
    async def test_synthesize_prompt_uses_personality_name(self, ea):
        """_synthesize_specialist_result should address the LLM as the
        configured name, not hardcoded Sarah."""
        from src.agents.base.specialist import SpecialistResult, SpecialistStatus
        from src.agents.executive_assistant import BusinessContext

        ea._personality = {"tone": "friendly", "language": "en", "name": "Aria"}

        # Give the EA an LLM mock so the synthesis branch that builds a
        # prompt actually runs (with llm=None it just returns summary_for_ea).
        llm = AsyncMock()
        llm.ainvoke = AsyncMock(return_value=MagicMock(content="relayed"))
        ea.llm = llm

        result = SpecialistResult(
            status=SpecialistStatus.COMPLETED, domain="finance",
            payload={"balance": 1000}, confidence=0.9,
            summary_for_ea="Balance is $1000.",
        )
        await ea._synthesize_specialist_result(result, BusinessContext(business_name="Acme"))

        prompt = llm.ainvoke.call_args.args[0][0].content
        assert "Aria" in prompt
        assert "Sarah" not in prompt

    @pytest.mark.asyncio
    async def test_fallback_greeting_uses_personality_name(self, ea):
        """Empty-messages fallback in handle_customer_interaction
        introduces the EA by its configured name."""
        from src.agents.executive_assistant import ConversationChannel

        ea.settings_redis = None  # → defaults, name="Assistant"
        # Force the graph to produce no messages so the fallback greeting runs.
        ea.graph.ainvoke = AsyncMock(return_value={"messages": []})

        response = await ea.handle_customer_interaction(
            message="hi", channel=ConversationChannel.CHAT, conversation_id="c1",
        )

        assert "Assistant" in response
        assert "Sarah" not in response

    def test_tone_directive_maps_all_schema_tones(self, ea):
        """Every Tone literal from the schema has guidance text."""
        from src.agents.executive_assistant import _TONE_GUIDANCE
        # Matches PersonalitySettings.Tone in src/api/schemas.py
        for tone in ("professional", "friendly", "concise", "detailed"):
            assert tone in _TONE_GUIDANCE
            assert len(_TONE_GUIDANCE[tone]) > 0


# --- Integration with handle_customer_interaction ---------------------------

class TestPersonalityFetchCadence:
    @pytest.mark.asyncio
    async def test_loaded_once_per_interaction(self, ea, fake_redis):
        """One Redis GET per turn — graph nodes read self._personality,
        they don't each hit Redis."""
        from src.agents.executive_assistant import ConversationChannel

        await fake_redis.set("settings:cust_test", json.dumps({
            "personality": {"name": "Aria", "tone": "concise", "language": "en"},
        }))
        # Wrap the fake's get so we can count calls without losing behaviour.
        real_get = fake_redis.get
        fake_redis.get = AsyncMock(side_effect=real_get)
        ea.settings_redis = fake_redis

        # Short-circuit the graph so we only test the load path.
        ea.graph.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content="ok")],
        })

        await ea.handle_customer_interaction(
            message="hello", channel=ConversationChannel.CHAT, conversation_id="c1",
        )

        settings_gets = [
            c for c in fake_redis.get.call_args_list
            if c.args and c.args[0] == "settings:cust_test"
        ]
        assert len(settings_gets) == 1
        assert ea._personality["name"] == "Aria"

    @pytest.mark.asyncio
    async def test_reloaded_on_each_interaction(self, ea, fake_redis):
        """Settings PUT between turns → next turn sees the new name.
        No TTL cache; Redis is already fast."""
        from src.agents.executive_assistant import ConversationChannel

        ea.settings_redis = fake_redis
        ea.graph.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content="ok")],
        })

        await fake_redis.set("settings:cust_test", json.dumps({
            "personality": {"name": "Aria", "tone": "professional", "language": "en"},
        }))
        await ea.handle_customer_interaction(
            message="one", channel=ConversationChannel.CHAT, conversation_id="c1",
        )
        assert ea._personality["name"] == "Aria"

        await fake_redis.set("settings:cust_test", json.dumps({
            "personality": {"name": "Beacon", "tone": "professional", "language": "en"},
        }))
        await ea.handle_customer_interaction(
            message="two", channel=ConversationChannel.CHAT, conversation_id="c1",
        )
        assert ea._personality["name"] == "Beacon"


# --- Init contract ----------------------------------------------------------

class TestInitDefaults:
    def test_settings_redis_defaults_to_none(self, ea):
        """Same injection pattern as audit_logger — set by factory, not ctor."""
        # The fixture didn't set it, so the ctor default should be None.
        assert ea.settings_redis is None

    def test_personality_defaults_present_before_first_load(self, ea):
        """Graph nodes may run before handle_customer_interaction in tests
        that poke _delegate_to_specialist directly — they need a dict to
        read, not an AttributeError."""
        assert ea._personality["name"]  # non-empty default name
        assert ea._personality["tone"] in (
            "professional", "friendly", "concise", "detailed",
        )
