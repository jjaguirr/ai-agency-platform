"""
Onboarding flow — the 5-step guided conversation.

The flow is stateful across turns via OnboardingStateStore. Each call
to ``handle()`` consumes one customer message and returns one EA reply.
The flow drives the conversation; the customer responds.

Personality (name, tone) comes from the same settings dict the EA uses
so onboarding feels like the rest of the product.
"""
import json

import pytest

from src.onboarding.flow import OnboardingFlow
from src.onboarding.state import OnboardingStateStore, OnboardingStep


@pytest.fixture
def store(fake_redis):
    return OnboardingStateStore(fake_redis)


@pytest.fixture
def flow(store, fake_redis):
    return OnboardingFlow(
        state_store=store,
        settings_redis=fake_redis,
        personality={"name": "Sarah", "tone": "friendly", "language": "en"},
    )


class TestIntroduction:
    async def test_first_message_introduces_ea_by_name(self, flow, store):
        reply = await flow.handle("cust_a", "hello")

        assert "Sarah" in reply
        state = await store.get("cust_a")
        assert state.step == OnboardingStep.BUSINESS_CONTEXT

    async def test_intro_mentions_capabilities(self, flow):
        reply = await flow.handle("cust_a", "hi")

        # Brief, not a wall of text
        assert len(reply) < 500
        # Mentions core specialist domains
        lowered = reply.lower()
        assert any(w in lowered for w in ["schedul", "calendar"])
        assert any(w in lowered for w in ["financ", "expense"])

    async def test_intro_asks_about_business(self, flow):
        reply = await flow.handle("cust_a", "hey")
        assert "?" in reply  # ends with a question


class TestBusinessContext:
    async def test_stores_business_answer(self, flow, store):
        await flow.handle("cust_a", "hi")  # intro → asks business

        await flow.handle("cust_a", "I run a small Italian restaurant")

        state = await store.get("cust_a")
        assert "restaurant" in state.collected["business_context"].lower()
        assert state.step == OnboardingStep.PREFERENCES

    async def test_free_text_accepted(self, flow, store):
        """No forced categories — whatever they say gets stored."""
        await flow.handle("cust_a", "hi")

        await flow.handle("cust_a", "uh, hard to explain, bit of everything")

        state = await store.get("cust_a")
        assert state.collected["business_context"]  # non-empty
        assert state.step == OnboardingStep.PREFERENCES

    async def test_asks_for_working_hours_next(self, flow):
        await flow.handle("cust_a", "hi")

        reply = await flow.handle("cust_a", "consulting firm")

        lowered = reply.lower()
        assert any(w in lowered for w in ["hours", "timezone", "work"])


class TestPreferences:
    async def test_parses_natural_language_hours(self, flow, fake_redis):
        await flow.handle("cust_a", "hi")
        await flow.handle("cust_a", "consulting")

        await flow.handle("cust_a", "I work 9 to 5 Eastern")

        raw = await fake_redis.get("settings:cust_a")
        settings = json.loads(raw)
        assert settings["working_hours"]["start"] == "09:00"
        assert settings["working_hours"]["end"] == "17:00"
        assert "Eastern" in settings["working_hours"]["timezone"] or \
               "New_York" in settings["working_hours"]["timezone"]

    async def test_parses_24h_format(self, flow, fake_redis):
        await flow.handle("cust_a", "hi")
        await flow.handle("cust_a", "tech startup")

        await flow.handle("cust_a", "08:30 to 18:00 UTC")

        settings = json.loads(await fake_redis.get("settings:cust_a"))
        assert settings["working_hours"]["start"] == "08:30"
        assert settings["working_hours"]["end"] == "18:00"

    async def test_unclear_answer_uses_defaults(self, flow, fake_redis):
        await flow.handle("cust_a", "hi")
        await flow.handle("cust_a", "retail")

        reply = await flow.handle("cust_a", "whenever really")

        settings = json.loads(await fake_redis.get("settings:cust_a"))
        assert settings["working_hours"]["start"] == "09:00"  # default
        assert "dashboard" in reply.lower()  # tells them they can change it

    async def test_advances_to_quick_win(self, flow, store):
        await flow.handle("cust_a", "hi")
        await flow.handle("cust_a", "law firm")

        await flow.handle("cust_a", "9 to 6")

        state = await store.get("cust_a")
        assert state.step == OnboardingStep.QUICK_WIN


class TestQuickWin:
    async def _run_to_quick_win(self, flow, business):
        await flow.handle("cust_a", "hi")
        await flow.handle("cust_a", business)
        return await flow.handle("cust_a", "9 to 5")

    async def test_restaurant_gets_reservation_suggestion(self, flow):
        reply = await self._run_to_quick_win(flow, "I run a restaurant")
        assert "reservation" in reply.lower()

    async def test_consulting_gets_briefing_suggestion(self, flow):
        reply = await self._run_to_quick_win(flow, "consulting firm")
        assert "briefing" in reply.lower() or "meeting" in reply.lower()

    async def test_unknown_business_gets_generic_briefing(self, flow):
        reply = await self._run_to_quick_win(flow, "something unusual")
        assert "briefing" in reply.lower() or "morning" in reply.lower()

    async def test_accepting_quick_win_enables_briefing(self, flow, fake_redis):
        await self._run_to_quick_win(flow, "consulting")

        await flow.handle("cust_a", "yes please")

        settings = json.loads(await fake_redis.get("settings:cust_a"))
        assert settings["briefing"]["enabled"] is True

    async def test_declining_quick_win_moves_on(self, flow, store):
        await self._run_to_quick_win(flow, "retail")

        reply = await flow.handle("cust_a", "not now")

        state = await store.get("cust_a")
        assert state.status == "completed"
        # Acknowledges gracefully
        assert any(w in reply.lower() for w in ["no problem", "anytime", "later"])


class TestCompletion:
    async def test_full_flow_completes(self, flow, store):
        await flow.handle("cust_a", "hi")
        await flow.handle("cust_a", "bakery")
        await flow.handle("cust_a", "6am to 2pm")
        await flow.handle("cust_a", "sure")

        state = await store.get("cust_a")
        assert state.status == "completed"

    async def test_completion_mentions_dashboard(self, flow):
        await flow.handle("cust_a", "hi")
        await flow.handle("cust_a", "bakery")
        await flow.handle("cust_a", "6am to 2pm")

        reply = await flow.handle("cust_a", "yes")

        assert "dashboard" in reply.lower()

    async def test_completed_flow_returns_none(self, flow, store):
        """Once complete, the flow hands back control — returns None to
        signal 'not my turn anymore, route normally'."""
        await store.complete("cust_a")

        result = await flow.handle("cust_a", "schedule a meeting")

        assert result is None


class TestResume:
    async def test_resumes_at_correct_step(self, flow, store, fake_redis):
        await flow.handle("cust_a", "hi")
        await flow.handle("cust_a", "restaurant")
        # Customer drops off here — state persisted in Redis

        # New flow instance, same Redis
        fresh_flow = OnboardingFlow(
            state_store=OnboardingStateStore(fake_redis),
            settings_redis=fake_redis,
            personality={"name": "Sarah", "tone": "friendly", "language": "en"},
        )
        reply = await fresh_flow.handle("cust_a", "10 to 6 Pacific")

        # Should process as PREFERENCES answer, not restart intro
        assert "Sarah" not in reply  # no re-introduction
        state = await store.get("cust_a")
        assert state.step == OnboardingStep.QUICK_WIN


class TestInterrupt:
    async def test_detects_real_request(self, flow):
        await flow.handle("cust_a", "hi")

        is_interrupt = flow.looks_like_real_request(
            "actually can you schedule a meeting for tomorrow at 3pm?"
        )
        assert is_interrupt

    async def test_onboarding_answer_not_interrupt(self, flow):
        assert not flow.looks_like_real_request("I run a restaurant")
        assert not flow.looks_like_real_request("9 to 5 eastern")
        assert not flow.looks_like_real_request("yes please")
