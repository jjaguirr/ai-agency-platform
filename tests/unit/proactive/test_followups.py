"""
Commitment extraction — turning "I'll send the proposal by Thursday" into
a tracked follow-up with a deadline.

Scope: explicit patterns only. False negatives are fine (customer can
always ask explicitly); false positives that spam the customer are not.

Patterns:
  - "remind me to X [by/on/at Y]"
  - "I'll / I will <verb> ... by/on <day|date>"
  - "let me get back to <person> <timeframe>"

Non-patterns (vague, no deadline — do NOT extract):
  - "I should probably call them sometime"
  - "I need to think about it"
  - "maybe next week we could..."
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.agents.proactive.followups import Commitment, extract_commitments


@pytest.fixture
def ref():
    # Wednesday 2026-03-18 09:00 UTC — reference for relative day parsing
    return datetime(2026, 3, 18, 9, 0, tzinfo=ZoneInfo("UTC"))


class TestRemindMe:
    def test_remind_me_with_day(self, ref):
        c = extract_commitments("Remind me to call John by Thursday", ref=ref)
        assert len(c) == 1
        assert "call John" in c[0].text
        # Thursday after Wed 2026-03-18 is 2026-03-19
        assert c[0].due.date() == datetime(2026, 3, 19).date()

    def test_remind_me_with_tomorrow(self, ref):
        c = extract_commitments("remind me to send the deck tomorrow", ref=ref)
        assert len(c) == 1
        assert c[0].due.date() == (ref + timedelta(days=1)).date()

    def test_remind_me_no_deadline_defaults_to_tomorrow(self, ref):
        """
        Explicit "remind me to X" with no time → default tomorrow. This is
        the one pattern where a missing deadline doesn't kill extraction,
        because the imperative "remind me" is unambiguous intent.
        """
        c = extract_commitments("remind me to chase the invoice", ref=ref)
        assert len(c) == 1
        assert c[0].due.date() == (ref + timedelta(days=1)).date()


class TestIllDoX:
    def test_ill_verb_by_day(self, ref):
        c = extract_commitments("I'll send the proposal by Thursday", ref=ref)
        assert len(c) == 1
        assert "send the proposal" in c[0].text
        assert c[0].due.date() == datetime(2026, 3, 19).date()

    def test_i_will_verb_on_day(self, ref):
        c = extract_commitments("I will follow up with them on Monday", ref=ref)
        assert len(c) == 1
        # Next Monday after Wed 18th is Mon 23rd
        assert c[0].due.date() == datetime(2026, 3, 23).date()

    def test_ill_without_deadline_not_extracted(self, ref):
        """No deadline anchor → skip. 'I'll think about it' isn't a commitment."""
        c = extract_commitments("I'll think about it", ref=ref)
        assert c == []


class TestGetBackTo:
    def test_get_back_to_them_tomorrow(self, ref):
        c = extract_commitments("Let me get back to them tomorrow", ref=ref)
        assert len(c) == 1
        assert c[0].due.date() == (ref + timedelta(days=1)).date()

    def test_get_back_no_timeframe_not_extracted(self, ref):
        c = extract_commitments("I need to get back to them at some point", ref=ref)
        assert c == []


class TestNonMatches:
    @pytest.mark.parametrize("text", [
        "I should probably call them sometime",
        "maybe next week we could sync",
        "I've been meaning to do that",
        "we might want to consider that",
        "hello how are you",
        "",
    ])
    def test_vague_language_not_extracted(self, text, ref):
        assert extract_commitments(text, ref=ref) == []


class TestCommitmentIdentity:
    def test_commitment_has_stable_id(self, ref):
        """Two commitments with identical fields get the same id —
        lets us dedupe if the customer says the same thing twice."""
        c1 = extract_commitments("remind me to call John by Thursday", ref=ref)[0]
        c2 = extract_commitments("remind me to call John by Thursday", ref=ref)[0]
        assert c1.id == c2.id

    def test_commitment_roundtrips_json(self, ref):
        c = extract_commitments("remind me to call John by Thursday", ref=ref)[0]
        d = c.to_dict()
        back = Commitment.from_dict(d)
        assert back == c


class TestTriggerGeneration:
    """
    A Commitment becomes a ProactiveTrigger when its deadline approaches.
    """
    def test_due_commitment_yields_trigger(self, ref):
        from src.agents.proactive.followups import commitment_to_trigger

        c = Commitment(text="call John", due=ref, raw="remind me to call John")
        t = commitment_to_trigger(c, now=ref + timedelta(minutes=5))
        assert t is not None
        assert t.trigger_type == "follow_up"
        assert "call John" in t.suggested_message
        assert t.cooldown_key is not None  # so it doesn't fire every tick

    def test_not_yet_due_yields_none(self, ref):
        from src.agents.proactive.followups import commitment_to_trigger
        c = Commitment(text="x", due=ref + timedelta(days=1), raw="r")
        assert commitment_to_trigger(c, now=ref) is None
