"""Tests for FollowUpExtractor — commitment language parsing."""
import pytest
from datetime import datetime, timezone

from src.proactive.extractors import FollowUpExtractor, FollowUp

# Reference: Thursday 2026-03-19 10:00 UTC
_NOW = datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def extractor():
    return FollowUpExtractor()


class TestDetection:
    def test_remind_me_with_day(self, extractor):
        results = extractor.extract("Remind me to call John on Friday", _NOW)
        assert len(results) == 1
        assert "call John" in results[0].commitment
        # Friday = 2026-03-20
        assert results[0].deadline.weekday() == 4  # Friday

    def test_by_day(self, extractor):
        results = extractor.extract("Send the proposal by Wednesday", _NOW)
        assert len(results) == 1
        assert "proposal" in results[0].commitment.lower() or "send" in results[0].commitment.lower()

    def test_ill_verb_by_time(self, extractor):
        results = extractor.extract("I'll send the report by Friday", _NOW)
        assert len(results) == 1
        assert "report" in results[0].commitment.lower() or "send" in results[0].commitment.lower()

    def test_i_need_to_by(self, extractor):
        results = extractor.extract("I need to follow up with Acme by Friday", _NOW)
        assert len(results) == 1
        assert "acme" in results[0].commitment.lower() or "follow up" in results[0].commitment.lower()

    def test_tomorrow(self, extractor):
        results = extractor.extract("Remind me to check the deploy tomorrow", _NOW)
        assert len(results) == 1
        # tomorrow = 2026-03-20
        assert results[0].deadline.day == 20

    def test_next_week(self, extractor):
        results = extractor.extract("I'll have the budget ready by next Monday", _NOW)
        assert len(results) == 1
        assert results[0].deadline.weekday() == 0  # Monday


class TestRejection:
    def test_vague_without_deadline(self, extractor):
        results = extractor.extract(
            "I should probably call them sometime", _NOW
        )
        assert len(results) == 0

    def test_past_tense(self, extractor):
        results = extractor.extract("I reminded them yesterday", _NOW)
        assert len(results) == 0

    def test_no_commitment_language(self, extractor):
        results = extractor.extract("What's the weather today?", _NOW)
        assert len(results) == 0

    def test_empty_message(self, extractor):
        assert extractor.extract("", _NOW) == []


class TestExtractedData:
    def test_has_id(self, extractor):
        results = extractor.extract("Remind me to call John on Friday", _NOW)
        assert results[0].id  # non-empty string

    def test_has_deadline_as_datetime(self, extractor):
        results = extractor.extract("Remind me to call John on Friday", _NOW)
        assert isinstance(results[0].deadline, datetime)

    def test_has_source_message(self, extractor):
        msg = "Remind me to call John on Friday"
        results = extractor.extract(msg, _NOW)
        assert results[0].source_message == msg

    def test_unique_ids(self, extractor):
        r1 = extractor.extract("Remind me to call John on Friday", _NOW)
        r2 = extractor.extract("Remind me to email Sarah on Monday", _NOW)
        assert r1[0].id != r2[0].id
