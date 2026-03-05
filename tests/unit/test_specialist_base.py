"""Unit tests for the specialist agent base contract."""
import pytest
from dataclasses import fields


class TestDelegationStatus:
    def test_enum_values(self):
        from src.agents.specialists.base import DelegationStatus

        assert DelegationStatus.COMPLETED.value == "completed"
        assert DelegationStatus.NEEDS_CLARIFICATION.value == "needs_clarification"
        assert DelegationStatus.FAILED.value == "failed"

    def test_exactly_three_statuses(self):
        from src.agents.specialists.base import DelegationStatus

        assert len(DelegationStatus) == 3


class TestSpecialistTask:
    def test_construction_with_required_fields(self):
        from src.agents.specialists.base import SpecialistTask
        from src.agents.executive_assistant import BusinessContext

        task = SpecialistTask(
            task_description="schedule a post",
            customer_id="cust_1",
            conversation_id="conv_1",
            business_context=BusinessContext(business_name="Acme"),
            domain_memories=[{"content": "x", "metadata": {"category": "social_media"}}],
            prior_clarifications={},
        )
        assert task.task_description == "schedule a post"
        assert task.customer_id == "cust_1"
        assert task.business_context.business_name == "Acme"
        assert len(task.domain_memories) == 1
        assert task.prior_clarifications == {}

    def test_prior_clarifications_defaults_empty(self):
        from src.agents.specialists.base import SpecialistTask
        from src.agents.executive_assistant import BusinessContext

        task = SpecialistTask(
            task_description="x",
            customer_id="c",
            conversation_id="v",
            business_context=BusinessContext(),
            domain_memories=[],
        )
        assert task.prior_clarifications == {}

    def test_does_not_carry_full_message_history(self):
        # Context scoping guarantee: the task contract has no field for
        # raw conversation messages — specialists see only scoped data.
        from src.agents.specialists.base import SpecialistTask

        field_names = {f.name for f in fields(SpecialistTask)}
        assert "messages" not in field_names
        assert "conversation_history" not in field_names


class TestSpecialistResult:
    def test_completed_result(self):
        from src.agents.specialists.base import SpecialistResult, DelegationStatus

        r = SpecialistResult(
            status=DelegationStatus.COMPLETED,
            content="done",
            confidence=0.9,
            structured_data={"engagement": 42},
        )
        assert r.status == DelegationStatus.COMPLETED
        assert r.content == "done"
        assert r.confidence == 0.9
        assert r.structured_data == {"engagement": 42}
        assert r.clarification_question is None
        assert r.error is None

    def test_needs_clarification_result(self):
        from src.agents.specialists.base import SpecialistResult, DelegationStatus

        r = SpecialistResult(
            status=DelegationStatus.NEEDS_CLARIFICATION,
            clarification_question="Which platform?",
        )
        assert r.status == DelegationStatus.NEEDS_CLARIFICATION
        assert r.clarification_question == "Which platform?"
        assert r.content is None

    def test_failed_result(self):
        from src.agents.specialists.base import SpecialistResult, DelegationStatus

        r = SpecialistResult(status=DelegationStatus.FAILED, error="boom")
        assert r.status == DelegationStatus.FAILED
        assert r.error == "boom"
        assert r.confidence == 0.0


class TestSpecialistAgentABC:
    def test_cannot_instantiate_abstract(self):
        from src.agents.specialists.base import SpecialistAgent

        with pytest.raises(TypeError):
            SpecialistAgent()

    def test_concrete_subclass_works(self):
        from src.agents.specialists.base import (
            SpecialistAgent,
            SpecialistTask,
            SpecialistResult,
            DelegationStatus,
        )

        class Dummy(SpecialistAgent):
            domain = "dummy"
            memory_categories = ["cat1"]

            def can_handle(self, task_description, intent):
                return 0.5

            async def execute(self, task):
                return SpecialistResult(status=DelegationStatus.COMPLETED)

        d = Dummy()
        assert d.domain == "dummy"
        assert d.memory_categories == ["cat1"]
        assert d.can_handle("anything", None) == 0.5
        assert d.llm is None

    def test_llm_injected_via_constructor(self):
        from src.agents.specialists.base import SpecialistAgent, SpecialistResult, DelegationStatus

        class Dummy(SpecialistAgent):
            domain = "d"
            memory_categories = []

            def can_handle(self, task_description, intent):
                return 0.0

            async def execute(self, task):
                return SpecialistResult(status=DelegationStatus.FAILED)

        fake_llm = object()
        d = Dummy(llm=fake_llm)
        assert d.llm is fake_llm


class TestPackageExports:
    def test_init_exports_core_types(self):
        from src.agents.specialists import (
            SpecialistAgent,
            SpecialistTask,
            SpecialistResult,
            DelegationStatus,
        )

        assert SpecialistAgent is not None
        assert SpecialistTask is not None
        assert SpecialistResult is not None
        assert DelegationStatus is not None
