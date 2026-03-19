"""
Specialist registration at EA init.

The EA's __init__ must register both social_media and finance. The
finance import is guarded — if finance.py fails to import (missing
optional dep, syntax error), the EA degrades to having social_media
only. It does NOT crash.

Routing overlap: finance and social media share vocabulary ("Facebook
ads budget"). The DelegationRegistry.route() must produce ONE match or
None — never crash, never return two.
"""
import pytest
from unittest.mock import patch, AsyncMock


@pytest.fixture
def ea():
    """EA with infra mocked away. Same pattern as test_ea_delegation.py."""
    with patch("src.agents.executive_assistant.ExecutiveAssistantMemory") as MockMem, \
         patch("src.agents.executive_assistant.WorkflowCreator"), \
         patch("src.agents.executive_assistant.ChatOpenAI"):
        from src.agents.executive_assistant import ExecutiveAssistant, BusinessContext
        mem = MockMem.return_value
        mem.get_business_context = AsyncMock(return_value=BusinessContext())
        mem.search_business_knowledge = AsyncMock(return_value=[])
        mem.store_conversation_context = AsyncMock()
        mem.get_conversation_context = AsyncMock(return_value={})
        yield ExecutiveAssistant(customer_id="cust_reg")


@pytest.fixture
def retail_ctx():
    from src.agents.executive_assistant import BusinessContext
    return BusinessContext(
        business_name="Sparkle & Shine",
        industry="jewelry",
        current_tools=["Instagram", "Facebook", "QuickBooks"],
        pain_points=["manual expense tracking", "social media"],
    )


class TestSpecialistRegistration:
    def test_social_media_registered(self, ea):
        assert ea.delegation_registry.get("social_media") is not None

    def test_finance_registered(self, ea):
        assert ea.delegation_registry.get("finance") is not None

    def test_finance_import_failure_does_not_crash_ea(self):
        """
        If finance.py can't import (missing dep, syntax error),
        EA init still succeeds. Finance just isn't registered.
        """
        with patch("src.agents.executive_assistant.ExecutiveAssistantMemory"), \
             patch("src.agents.executive_assistant.WorkflowCreator"), \
             patch("src.agents.executive_assistant.ChatOpenAI"), \
             patch("src.agents.executive_assistant._FINANCE_AVAILABLE", False):
            from src.agents.executive_assistant import ExecutiveAssistant
            ea = ExecutiveAssistant(customer_id="cust_no_finance")
            # EA built, social media still there, finance absent
            assert ea.delegation_registry.get("social_media") is not None
            assert ea.delegation_registry.get("finance") is None


class TestRoutingWithFinance:
    def test_invoice_routes_to_finance(self, ea, retail_ctx):
        match = ea.delegation_registry.route(
            "Track this invoice: $2,400 from Acme Corp", retail_ctx,
        )
        assert match is not None
        assert match.specialist.domain == "finance"

    def test_engagement_still_routes_to_social(self, ea, retail_ctx):
        """
        Adding finance must not break social media routing.
        "Instagram engagement" has no finance signals.
        """
        match = ea.delegation_registry.route(
            "how's my Instagram engagement this week?", retail_ctx,
        )
        assert match is not None
        assert match.specialist.domain == "social_media"

    def test_facebook_roi_overlap_is_coherent(self, ea, retail_ctx):
        """
        "What's my ROI on the Facebook campaign?" is the overlap case.
        Facebook → social signal. ROI → finance signal.

        Acceptable outcomes: routes to exactly one registered specialist,
        or returns None (strategic — EA keeps it). Not acceptable:
        crash, exception, or routing to an unregistered domain.
        """
        match = ea.delegation_registry.route(
            "What's my ROI on the Facebook campaign?", retail_ctx,
        )
        # Unconditional: the outcome is one of the three valid states.
        # A None result is explicitly acceptable, not a vacuous pass.
        valid_domains = {"finance", "social_media"}
        actual = None if match is None else match.specialist.domain
        assert actual in (None, *valid_domains), \
            f"routed to unregistered domain: {actual!r}"
        if match is not None:
            # Confidence must be a proper probability.
            assert 0.0 <= match.assessment.confidence <= 1.0, \
                f"confidence out of range: {match.assessment.confidence}"


class TestFinanceDelegationPipeline:
    @pytest.mark.asyncio
    async def test_invoice_message_reaches_finance_via_delegate_node(self, retail_ctx):
        """
        Full delegation pipeline: message → delegation_registry.route →
        specialist.execute_task → EA weaves response. Mocked infra, no
        live services.
        """
        with patch("src.agents.executive_assistant.ExecutiveAssistantMemory") as MockMem, \
             patch("src.agents.executive_assistant.WorkflowCreator"), \
             patch("src.agents.executive_assistant.ChatOpenAI"):
            from src.agents.executive_assistant import (
                ExecutiveAssistant, ConversationState, ConversationIntent,
            )
            from langchain_core.messages import HumanMessage, AIMessage

            mem = MockMem.return_value
            mem.get_business_context = AsyncMock(return_value=retail_ctx)
            mem.search_business_knowledge = AsyncMock(return_value=[])

            ea = ExecutiveAssistant(customer_id="cust_pipeline")
            ea.llm = None

            # Spy on finance specialist
            finance = ea.delegation_registry.get("finance")
            assert finance is not None, "finance not registered"
            executed = []
            orig_exec = finance.execute_task
            async def spy_exec(task):
                executed.append(task)
                return await orig_exec(task)
            finance.execute_task = spy_exec

            state = ConversationState(
                messages=[HumanMessage(
                    content="Track this invoice: $2,400 from Acme Corp")],
                customer_id="cust_pipeline",
                conversation_id="conv_1",
                business_context=retail_ctx,
                current_intent=ConversationIntent.TASK_DELEGATION,
            )

            out = await ea._delegate_to_specialist(state)

            # Finance specialist was invoked
            assert len(executed) == 1
            assert "$2,400" in executed[0].description or \
                   "2400" in executed[0].description
            # EA produced a response
            assert isinstance(out.messages[-1], AIMessage)
            assert len(out.messages[-1].content) > 0
