"""
Topic tagging from delegation history.

Deliberately trivial: if a specialist was invoked, tag with that
specialist's domain (mapped to the dashboard's topic vocabulary). No
specialist → "general". No LLM, no inference — the delegation metadata
IS the signal.

The domain→topic map handles the one naming mismatch: the `workflows`
specialist domain maps to the `workflow` topic tag (singular) per the
task's vocabulary. Everything else passes through.
"""
import pytest

from src.intelligence.tagging import tags_from_delegations, TOPIC_GENERAL


class TestTagsFromDelegations:
    def test_no_delegations_is_general(self):
        assert tags_from_delegations([]) == [TOPIC_GENERAL]

    def test_single_domain(self):
        assert tags_from_delegations(["finance"]) == ["finance"]

    def test_multiple_domains_preserved(self):
        # Order-independent but deterministic (sorted). A conversation
        # can touch calendar then invoices.
        tags = tags_from_delegations(["scheduling", "finance"])
        assert tags == ["finance", "scheduling"]

    def test_duplicates_collapsed(self):
        # Same specialist invoked three times in one conversation → one tag.
        assert tags_from_delegations(["finance", "finance", "finance"]) == ["finance"]

    def test_workflows_maps_to_workflow(self):
        # Specialist domain is "workflows" (plural, matches the module);
        # dashboard topic vocabulary uses "workflow" (singular).
        assert tags_from_delegations(["workflows"]) == ["workflow"]

    def test_mixed_with_workflows(self):
        tags = tags_from_delegations(["workflows", "finance", "workflows"])
        assert tags == ["finance", "workflow"]

    def test_all_known_domains(self):
        tags = tags_from_delegations(["finance", "scheduling", "social_media", "workflows"])
        assert tags == ["finance", "scheduling", "social_media", "workflow"]

    def test_unknown_domain_passes_through(self):
        # Future specialist, or a bug upstream — don't drop data silently.
        # The dashboard will render it as-is; better a weird tag than none.
        assert tags_from_delegations(["legal"]) == ["legal"]

    def test_general_constant(self):
        # The string literal is the contract with the dashboard filter.
        assert TOPIC_GENERAL == "general"

    def test_none_in_list_ignored(self):
        # Defensive: upstream might pass a None domain on a failed route.
        assert tags_from_delegations([None, "finance"]) == ["finance"]

    def test_only_nones_is_general(self):
        assert tags_from_delegations([None, None]) == [TOPIC_GENERAL]
