"""Tests for the onboarding flow engine — pure functions, no I/O."""
import pytest

from src.onboarding.flow import (
    STEP_INTRODUCTION,
    STEP_BUSINESS_CONTEXT,
    STEP_PREFERENCES,
    STEP_QUICK_WIN,
    STEP_COMPLETION,
    generate_step_response,
    detect_real_request,
    parse_working_hours,
)

DEFAULT_PERSONALITY = {"tone": "professional", "language": "en", "name": "Assistant"}
CUSTOM_PERSONALITY = {"tone": "friendly", "language": "es", "name": "Aria"}


class TestStepIntroduction:
    def test_greeting_uses_personality_name(self):
        result = generate_step_response(
            STEP_INTRODUCTION, None, DEFAULT_PERSONALITY, {},
        )
        assert "Assistant" in result.response

    def test_greeting_uses_custom_name(self):
        result = generate_step_response(
            STEP_INTRODUCTION, None, CUSTOM_PERSONALITY, {},
        )
        assert "Aria" in result.response

    def test_greeting_mentions_capabilities(self):
        result = generate_step_response(
            STEP_INTRODUCTION, None, DEFAULT_PERSONALITY, {},
        )
        # Should mention at least some of what the EA can do
        response_lower = result.response.lower()
        assert any(word in response_lower for word in [
            "schedul", "financ", "workflow", "automat",
        ])

    def test_asks_about_business(self):
        result = generate_step_response(
            STEP_INTRODUCTION, None, DEFAULT_PERSONALITY, {},
        )
        assert "?" in result.response  # Contains a question

    def test_advance_is_true(self):
        result = generate_step_response(
            STEP_INTRODUCTION, None, DEFAULT_PERSONALITY, {},
        )
        assert result.advance is True

    def test_no_settings_update(self):
        result = generate_step_response(
            STEP_INTRODUCTION, None, DEFAULT_PERSONALITY, {},
        )
        assert result.settings_update is None


class TestStepBusinessContext:
    def test_parses_restaurant(self):
        result = generate_step_response(
            STEP_BUSINESS_CONTEXT, "I run a restaurant in downtown",
            DEFAULT_PERSONALITY, {},
        )
        assert result.collected is not None
        assert "business_type" in result.collected

    def test_parses_consulting(self):
        result = generate_step_response(
            STEP_BUSINESS_CONTEXT, "We're a consulting firm",
            DEFAULT_PERSONALITY, {},
        )
        assert result.collected["business_type"] is not None

    def test_stores_raw_description(self):
        result = generate_step_response(
            STEP_BUSINESS_CONTEXT, "I run a small bakery and café",
            DEFAULT_PERSONALITY, {},
        )
        assert "business_description" in result.collected

    def test_asks_about_preferences(self):
        result = generate_step_response(
            STEP_BUSINESS_CONTEXT, "I run a restaurant",
            DEFAULT_PERSONALITY, {},
        )
        response_lower = result.response.lower()
        assert any(word in response_lower for word in [
            "hours", "timezone", "time", "work",
        ])

    def test_advance_is_true(self):
        result = generate_step_response(
            STEP_BUSINESS_CONTEXT, "I have a retail store",
            DEFAULT_PERSONALITY, {},
        )
        assert result.advance is True


class TestStepPreferences:
    def test_parses_nine_to_five_eastern(self):
        result = generate_step_response(
            STEP_PREFERENCES, "9 to 5, Eastern time",
            DEFAULT_PERSONALITY, {"business_type": "restaurant"},
        )
        assert result.settings_update is not None
        wh = result.settings_update["working_hours"]
        assert wh["start"] == "09:00"
        assert wh["end"] == "17:00"

    def test_parses_8am_to_6pm(self):
        result = generate_step_response(
            STEP_PREFERENCES, "8am to 6pm",
            DEFAULT_PERSONALITY, {"business_type": "consulting"},
        )
        assert result.settings_update is not None
        wh = result.settings_update["working_hours"]
        assert wh["start"] == "08:00"
        assert wh["end"] == "18:00"

    def test_unparseable_uses_defaults(self):
        result = generate_step_response(
            STEP_PREFERENCES, "whenever really, I'm flexible",
            DEFAULT_PERSONALITY, {"business_type": "consulting"},
        )
        # Should still produce a settings_update with sensible defaults
        assert result.settings_update is not None
        wh = result.settings_update["working_hours"]
        assert wh["start"] == "09:00"
        assert wh["end"] == "18:00"

    def test_response_mentions_quick_win(self):
        """After collecting preferences, the response should suggest something."""
        result = generate_step_response(
            STEP_PREFERENCES, "9 to 5",
            DEFAULT_PERSONALITY, {"business_type": "restaurant"},
        )
        assert "?" in result.response  # Contains a suggestion/question

    def test_advance_is_true(self):
        result = generate_step_response(
            STEP_PREFERENCES, "9 to 5",
            DEFAULT_PERSONALITY, {"business_type": "consulting"},
        )
        assert result.advance is True


class TestStepQuickWin:
    def test_restaurant_gets_contextual_suggestion(self):
        result = generate_step_response(
            STEP_QUICK_WIN, "yes please",
            DEFAULT_PERSONALITY, {"business_type": "restaurant"},
        )
        response_lower = result.response.lower()
        assert any(word in response_lower for word in [
            "reservation", "daily", "summary",
        ])

    def test_consulting_gets_morning_briefing(self):
        result = generate_step_response(
            STEP_QUICK_WIN, "sure",
            DEFAULT_PERSONALITY, {"business_type": "consulting"},
        )
        response_lower = result.response.lower()
        assert "briefing" in response_lower or "morning" in response_lower

    def test_unknown_gets_morning_briefing_fallback(self):
        result = generate_step_response(
            STEP_QUICK_WIN, "ok",
            DEFAULT_PERSONALITY, {"business_type": "other"},
        )
        response_lower = result.response.lower()
        assert "briefing" in response_lower or "morning" in response_lower

    def test_yes_enables_feature_in_settings(self):
        result = generate_step_response(
            STEP_QUICK_WIN, "yes",
            DEFAULT_PERSONALITY, {"business_type": "consulting"},
        )
        assert result.settings_update is not None
        assert result.settings_update["briefing"]["enabled"] is True

    def test_no_does_not_enable_feature(self):
        result = generate_step_response(
            STEP_QUICK_WIN, "no thanks, maybe later",
            DEFAULT_PERSONALITY, {"business_type": "consulting"},
        )
        # No settings_update or briefing not enabled
        if result.settings_update:
            assert result.settings_update.get("briefing", {}).get("enabled") is not True

    def test_advance_is_true(self):
        result = generate_step_response(
            STEP_QUICK_WIN, "sure",
            DEFAULT_PERSONALITY, {"business_type": "consulting"},
        )
        assert result.advance is True


class TestStepCompletion:
    def test_mentions_dashboard(self):
        result = generate_step_response(
            STEP_COMPLETION, None,
            DEFAULT_PERSONALITY, {"business_type": "restaurant"},
        )
        assert "dashboard" in result.response.lower()

    def test_advance_is_true(self):
        result = generate_step_response(
            STEP_COMPLETION, None,
            DEFAULT_PERSONALITY, {},
        )
        assert result.advance is True

    def test_no_settings_update(self):
        result = generate_step_response(
            STEP_COMPLETION, None,
            DEFAULT_PERSONALITY, {},
        )
        assert result.settings_update is None


class TestDetectRealRequest:
    def test_scheduling_is_real(self):
        assert detect_real_request("can you schedule a meeting for tomorrow?") is True

    def test_help_with_task_is_real(self):
        assert detect_real_request("I need to send an invoice to my client") is True

    def test_business_description_is_not_real(self):
        assert detect_real_request("I run a restaurant") is False

    def test_yes_is_not_real(self):
        assert detect_real_request("yes") is False

    def test_ok_is_not_real(self):
        assert detect_real_request("ok") is False

    def test_empty_is_not_real(self):
        assert detect_real_request("") is False

    def test_hours_answer_is_not_real(self):
        assert detect_real_request("9am to 5pm Eastern") is False

    def test_check_my_finances_is_real(self):
        assert detect_real_request("check my finances") is True


class TestParseWorkingHours:
    def test_standard_format(self):
        result = parse_working_hours("9:00 to 17:00")
        assert result is not None
        assert result["start"] == "09:00"
        assert result["end"] == "17:00"

    def test_twelve_hour_format(self):
        result = parse_working_hours("8am to 6pm")
        assert result is not None
        assert result["start"] == "08:00"
        assert result["end"] == "18:00"

    def test_nine_to_five(self):
        result = parse_working_hours("9 to 5")
        assert result is not None
        assert result["start"] == "09:00"
        assert result["end"] == "17:00"

    def test_with_timezone(self):
        result = parse_working_hours("9am to 5pm Eastern")
        assert result is not None
        assert "eastern" in result.get("timezone", "").lower() or "east" in result.get("timezone", "").lower()

    def test_unparseable_returns_none(self):
        result = parse_working_hours("whenever really")
        assert result is None

    def test_just_a_number_returns_none(self):
        result = parse_working_hours("42")
        assert result is None
