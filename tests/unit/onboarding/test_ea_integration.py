"""
EA ↔ onboarding integration.

At the top of handle_customer_interaction, the EA checks onboarding
state. If incomplete, the onboarding flow handles the turn instead of
the normal LangGraph. If complete, the onboarding check is a single
Redis GET and normal processing continues.

Interrupt handling: if the customer sends a real task request
mid-onboarding, the EA handles it normally, then prompts to resume.
"""
import json

import pytest
import fakeredis.aioredis
from unittest.mock import AsyncMock, patch

from src.onboarding.state import OnboardingStateStore, OnboardingStep


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def ea(fake_redis):
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

        instance = ExecutiveAssistant(customer_id="cust_onboard")
        instance.llm = None
        instance.settings_redis = fake_redis
        yield instance


class TestOnboardingRouting:
    async def test_new_customer_gets_intro(self, ea, fake_redis):
        from src.agents.executive_assistant import ConversationChannel

        reply = await ea.handle_customer_interaction(
            "hello", ConversationChannel.WHATSAPP
        )

        assert "Assistant" in reply  # default personality name
        assert "business" in reply.lower()

    async def test_completed_customer_skips_onboarding(self, ea, fake_redis):
        """After completion, normal EA flow runs — onboarding never
        re-introduces itself."""
        from src.agents.executive_assistant import ConversationChannel

        store = OnboardingStateStore(fake_redis)
        await store.complete("cust_onboard")

        reply = await ea.handle_customer_interaction(
            "hello", ConversationChannel.WHATSAPP
        )

        # No re-introduction
        assert "what kind of business" not in reply.lower()

    async def test_onboarding_progresses_across_turns(self, ea, fake_redis):
        from src.agents.executive_assistant import ConversationChannel

        await ea.handle_customer_interaction("hi", ConversationChannel.WHATSAPP)
        await ea.handle_customer_interaction(
            "consulting firm", ConversationChannel.WHATSAPP
        )

        store = OnboardingStateStore(fake_redis)
        state = await store.get("cust_onboard")
        assert state.step == OnboardingStep.PREFERENCES
        assert "consulting" in state.collected["business_context"]

    async def test_full_onboarding_completes(self, ea, fake_redis):
        from src.agents.executive_assistant import ConversationChannel
        ch = ConversationChannel.WHATSAPP

        await ea.handle_customer_interaction("hi", ch)
        await ea.handle_customer_interaction("restaurant", ch)
        await ea.handle_customer_interaction("9 to 5 eastern", ch)
        await ea.handle_customer_interaction("yes", ch)

        store = OnboardingStateStore(fake_redis)
        assert await store.is_complete("cust_onboard")

        # Settings were written
        raw = await fake_redis.get("settings:cust_onboard")
        settings = json.loads(raw)
        assert settings["working_hours"]["start"] == "09:00"

    async def test_no_settings_redis_skips_onboarding(self, ea):
        """Legacy construction path — no settings_redis → can't check
        state → skip onboarding entirely rather than crash."""
        from src.agents.executive_assistant import ConversationChannel

        ea.settings_redis = None
        reply = await ea.handle_customer_interaction(
            "hello", ConversationChannel.WHATSAPP
        )
        # Doesn't crash, doesn't run onboarding
        assert "what kind of business" not in reply.lower()


class TestInterruptHandling:
    async def test_real_request_interrupts_onboarding(self, ea, fake_redis):
        from src.agents.executive_assistant import ConversationChannel
        ch = ConversationChannel.WHATSAPP

        await ea.handle_customer_interaction("hi", ch)  # intro

        # Customer interrupts with a real request
        reply = await ea.handle_customer_interaction(
            "actually can you schedule a meeting for tomorrow at 3pm?", ch
        )

        # EA handled the real request (not asking about business type)
        assert "working hours" not in reply.lower()
        # And onboarding state didn't advance past where it was
        store = OnboardingStateStore(fake_redis)
        state = await store.get("cust_onboard")
        # Still at business_context (the step after intro) OR completed
        # if EA decided to skip remaining steps
        assert state.step in (OnboardingStep.BUSINESS_CONTEXT, OnboardingStep.DONE)

    async def test_interrupt_mentions_returning_to_setup(self, ea, fake_redis):
        from src.agents.executive_assistant import ConversationChannel
        ch = ConversationChannel.WHATSAPP

        await ea.handle_customer_interaction("hi", ch)
        reply = await ea.handle_customer_interaction(
            "actually schedule a meeting tomorrow at 2pm", ch
        )

        # Reply references returning to setup or finishing later
        lowered = reply.lower()
        assert any(w in lowered for w in ["setup", "onboarding", "later", "back to"])


class TestPersonalityAppliedDuringOnboarding:
    async def test_configured_name_used_in_intro(self, ea, fake_redis):
        from src.agents.executive_assistant import ConversationChannel

        await fake_redis.set("settings:cust_onboard", json.dumps({
            "personality": {"name": "Aria", "tone": "friendly", "language": "en"}
        }))

        reply = await ea.handle_customer_interaction(
            "hello", ConversationChannel.WHATSAPP
        )

        assert "Aria" in reply
