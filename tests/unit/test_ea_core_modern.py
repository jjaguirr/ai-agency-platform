"""
Modern Executive Assistant Core Tests
Combines traditional TDD with 2024 AI agent testing frameworks
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, List, Any

# AI Agent Testing Frameworks (mock implementations)
# from any_agent.evaluation import LlmJudge, AgentJudge
from pydantic import BaseModel
from typing import Optional

# Mock implementations for testing
class MockLlmJudge:
    def __init__(self, model_id="gpt-4o-mini", output_type=None):
        self.model_id = model_id
        self.output_type = output_type
    
    def run(self, context, question, **kwargs):
        mock_result = MagicMock()
        mock_result.passed = True
        mock_result.reasoning = "Mock evaluation passed"
        return mock_result

# Real EA Core - fail fast if imports don't work
from src.agents.executive_assistant import ExecutiveAssistant, ConversationChannel, BusinessContext


class EAResponseQuality(BaseModel):
    """Structured evaluation schema for EA responses."""
    passed: bool
    professionalism_score: float  # 0-10
    business_relevance_score: float  # 0-10
    automation_identification: bool
    roi_communication: bool
    confidence_score: float  # 0-1
    suggestions: List[str]


class TestEABasicConversation:
    """Test EA's basic conversation capabilities using modern evaluation."""

    @pytest.mark.asyncio
    async def test_ea_responds_to_greeting_with_evaluation(self, real_ea, conversation_evaluator):
        """EA should respond professionally to basic greetings - evaluated by AI."""
        ea = real_ea  # No await needed - fixture returns EA directly
        
        # Given: A basic greeting message
        message = "Hello, I need help with my business"
        
        # When: EA processes the message
        response = await ea.handle_customer_interaction(message, ConversationChannel.PHONE)
        
        # Then: Traditional assertions
        assert response is not None
        assert len(response) > 0
        assert "Executive Assistant" in response or "help" in response.lower()
        
        # And: AI evaluation for conversation quality
        evaluation_questions = [
            "Did the response demonstrate professional business communication?",
            "Did the response acknowledge the business context mentioned?",
            "Was the tone appropriate for a business executive assistant?",
            "Did the response invite further business discussion?"
        ]
        
        evaluation_results = []
        for question in evaluation_questions:
            result = conversation_evaluator.run(
                context=f"User: {message}\nAssistant: {response}",
                question=question
            )
            evaluation_results.append(result)
        
        # AI evaluation should pass all criteria
        passed_evaluations = [r.passed for r in evaluation_results]
        assert sum(passed_evaluations) >= 3, f"Only {sum(passed_evaluations)}/4 evaluations passed"

    @pytest.mark.asyncio 
    async def test_ea_maintains_professional_tone(self, real_ea):
        """EA should maintain professional tone using structured evaluation."""
        ea = real_ea  # No await needed - fixture returns EA directly
        
        # Given: An urgent/emotional user message
        urgent_message = "This is super urgent!!! I'm totally overwhelmed with my business!"
        
        # When: EA responds
        response = await ea.handle_customer_interaction(urgent_message, ConversationChannel.PHONE)
        
        # Then: Structured evaluation with custom schema
        judge = LlmJudge(
            model_id="gpt-4o-mini",
            output_type=EAResponseQuality
        )
        
        evaluation = judge.run(
            context=f"User: {urgent_message}\nAssistant: {response}",
            question="Evaluate the assistant's response for professionalism, business relevance, and communication quality"
        )
        
        # Professional communication requirements
        assert evaluation.passed, f"Evaluation failed: {evaluation.suggestions}"
        assert evaluation.professionalism_score >= 8.0, f"Professionalism score too low: {evaluation.professionalism_score}"
        assert evaluation.confidence_score >= 0.8, f"Confidence score too low: {evaluation.confidence_score}"
        
        # Response should not contain casual language
        casual_phrases = ["super", "totally", "awesome", "cool", "no worries"]
        response_lower = response.lower()
        found_casual = [phrase for phrase in casual_phrases if phrase in response_lower]
        assert len(found_casual) == 0, f"Found casual language: {found_casual}"

    @pytest.mark.asyncio
    async def test_ea_asks_business_discovery_questions(self, real_ea, agent_evaluator):
        """EA should proactively ask questions to understand business - trace evaluation."""
        ea = real_ea  # No await needed - fixture returns EA directly
        
        # Given: Initial business context
        messages = [
            "I run a jewelry business",
            "I need automation help"
        ]
        
        # When: EA processes messages
        responses = []
        for message in messages:
            response = await ea.handle_customer_interaction(message, ConversationChannel.PHONE)
            responses.append(response)
        
        # Then: Evaluate using AgentJudge with trace analysis
        conversation_trace = self._create_mock_trace(messages, responses)
        
        evaluation_questions = [
            "Did the assistant ask clarifying questions about the business?",
            "Did the assistant inquire about daily tasks or pain points?",
            "Were the follow-up questions relevant to business automation?",
            "Did the assistant maintain context about the jewelry business?"
        ]
        
        for question in evaluation_questions:
            result = agent_evaluator.run(
                trace=conversation_trace,
                question=question
            )
            assert result.passed, f"Failed evaluation: {question} - {result.reasoning}"

    @pytest.mark.asyncio
    async def test_ea_remembers_business_context(self, ea_with_business_context, jewelry_business_context):
        """EA should remember and reference business context throughout conversation."""
        # Given: EA with established business context
        ea = ea_with_business_context  # No await needed - fixture returns EA directly
        
        # When: Multiple messages reference different aspects
        messages_and_responses = [
            ("I spend too much time on social media", None),
            ("Can you help with that?", None),
            ("What about my customer service issues?", None)
        ]
        
        for i, (message, _) in enumerate(messages_and_responses):
            response = await ea.handle_customer_interaction(message, ConversationChannel.PHONE)
            messages_and_responses[i] = (message, response)
        
        # Then: Each response should reference jewelry business context
        for message, response in messages_and_responses:
            assert "jewelry" in response.lower() or "sparkle" in response.lower(), \
                f"Response didn't reference jewelry business: {response}"
        
        # And: Final response should maintain full context
        final_response = messages_and_responses[-1][1]
        context_elements = ["jewelry", "social media", "customer service"]
        referenced_elements = [elem for elem in context_elements if elem.lower() in final_response.lower()]
        assert len(referenced_elements) >= 2, f"Only {len(referenced_elements)}/3 context elements referenced"

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_ea_meets_response_time_requirements(self, real_ea, ea_performance_benchmarks):
        """EA should meet Phase-1 PRD response time requirements (<2 seconds)."""
        ea = real_ea  # No await needed - fixture returns EA directly
        import time
        
        # Given: A standard business message
        message = "Tell me about automation opportunities for my business"
        
        # When: EA processes with timing
        start_time = time.time()
        response = await ea.handle_customer_interaction(message, ConversationChannel.PHONE)
        response_time = time.time() - start_time
        
        # Then: Response time meets benchmark
        max_response_time = ea_performance_benchmarks["response_time"]
        assert response_time < max_response_time, \
            f"Response time {response_time:.3f}s exceeds {max_response_time}s requirement"
        
        # And: Response is meaningful (not just fast but empty)
        assert len(response) >= 50, "Response too short to be meaningful"
        assert "automation" in response.lower(), "Response doesn't address automation"

    def _create_mock_trace(self, messages: List[str], responses: List[str]):
        """Create mock trace object for AgentJudge evaluation."""
        # Mock trace structure for evaluation
        # In real implementation, this would be an actual AgentTrace
        mock_trace = MagicMock()
        
        # Create conversation messages
        conversation_messages = []
        for msg, resp in zip(messages, responses):
            conversation_messages.extend([
                {"role": "user", "content": msg},
                {"role": "assistant", "content": resp}
            ])
        
        mock_trace.spans_to_messages.return_value = [
            MagicMock(role=msg["role"], content=msg["content"]) 
            for msg in conversation_messages
        ]
        mock_trace.final_output = responses[-1] if responses else ""
        
        return mock_trace


class TestEAAutomationIdentification:
    """Test EA's ability to identify and prioritize automation opportunities."""

    @pytest.mark.asyncio
    @pytest.mark.evaluation
    async def test_ea_identifies_automation_opportunities_with_ai_scoring(self, real_ea, agent_evaluator):
        """EA should identify multiple automation opportunities from business description."""
        ea = real_ea  # No await needed - fixture returns EA directly
        
        # Given: A consulting business scenario with multiple automation opportunities
        conversation = [
            "I run a consulting business",
            "I manually send follow-up emails to every client", 
            "I create the same reports every week",
            "I post on LinkedIn daily but sometimes forget"
        ]
        
        # When: EA processes conversation
        responses = []
        for message in conversation:
            response = await ea.handle_customer_interaction(message, ConversationChannel.PHONE)
            responses.append(response)
        
        # Then: AI evaluation for automation identification
        full_conversation = ""
        for msg, resp in zip(conversation, responses):
            full_conversation += f"User: {msg}\nAssistant: {resp}\n\n"
        
        automation_evaluation = agent_evaluator.run(
            trace=self._create_conversation_trace(conversation, responses),
            question="Did the assistant identify email automation, report generation, and social media scheduling opportunities from the conversation?",
            additional_tools=[]  # Could add custom tools for automation analysis
        )
        
        assert automation_evaluation.passed, f"Automation identification failed: {automation_evaluation.reasoning}"
        
        # Traditional assertions for specific automation types
        final_response = responses[-1]
        automation_types = ["email", "report", "social media", "linkedin"]
        identified_types = [atype for atype in automation_types if atype in final_response.lower()]
        assert len(identified_types) >= 2, f"Only {len(identified_types)} automation types identified"

    @pytest.mark.asyncio
    async def test_ea_prioritizes_automations_by_impact(self, real_ea):
        """EA should prioritize automations by business impact (time saved, cost reduction)."""
        ea = real_ea  # No await needed - fixture returns EA directly
        
        # Given: Pain points with different time impacts
        pain_points = [
            "I spend 10 hours a week on manual invoicing",  # High impact
            "I forget to follow up with 1-2 leads per month",  # Medium impact  
            "I manually backup files once a week"  # Low impact
        ]
        
        # When: EA analyzes pain points
        responses = []
        for pain_point in pain_points:
            response = await ea.handle_customer_interaction(pain_point, ConversationChannel.PHONE)
            responses.append(response)
        
        # Ask for prioritization
        prioritization_request = "Which of these automations should I implement first?"
        priority_response = await ea.handle_customer_interaction(prioritization_request, ConversationChannel.PHONE)
        
        # Then: Invoicing (10 hrs/week) should be mentioned first/most prominently
        assert "invoicing" in priority_response.lower(), "Invoicing automation not prioritized"
        assert "10 hour" in priority_response.lower() or "time" in priority_response.lower(), \
            "Time savings not mentioned in prioritization"
        
        # Structured evaluation of prioritization logic
        judge = LlmJudge(model_id="gpt-4o-mini")
        prioritization_eval = judge.run(
            context=priority_response,
            question="Did the assistant correctly prioritize the 10-hour weekly invoicing task as the highest impact automation opportunity?"
        )
        
        assert prioritization_eval.passed, f"Prioritization logic failed: {prioritization_eval.reasoning}"

    def _create_conversation_trace(self, messages: List[str], responses: List[str]):
        """Helper to create conversation trace for evaluation."""
        # Mock implementation - in real system would use actual trace
        mock_trace = MagicMock()
        mock_trace.final_output = responses[-1] if responses else ""
        
        conversation_messages = []
        for msg, resp in zip(messages, responses):
            conversation_messages.extend([
                MagicMock(role="user", content=msg),
                MagicMock(role="assistant", content=resp)
            ])
        
        mock_trace.spans_to_messages.return_value = conversation_messages
        return mock_trace


class TestEAROICommunication:
    """Test EA's ROI calculation and communication capabilities."""

    @pytest.mark.asyncio
    async def test_ea_calculates_roi_projections(self, real_ea):
        """EA should calculate and communicate ROI for automation recommendations."""
        ea = real_ea  # No await needed - fixture returns EA directly
        
        # Given: A business problem with quantifiable time investment
        problem = "I spend 5 hours per week on social media posting for my consulting business, and my billable rate is $150/hour"
        
        # When: EA analyzes and responds
        response = await ea.handle_customer_interaction(problem, ConversationChannel.PHONE)
        
        # Then: Response should include ROI calculations
        roi_keywords = ["$", "save", "hour", "week", "month", "cost", "return"]
        found_roi_terms = [term for term in roi_keywords if term in response.lower()]
        assert len(found_roi_terms) >= 3, f"Insufficient ROI communication: {found_roi_terms}"
        
        # AI evaluation of ROI communication quality
        judge = LlmJudge(model_id="gpt-4o-mini")
        roi_evaluation = judge.run(
            context=f"Business problem: {problem}\nEA response: {response}",
            question="Did the assistant calculate specific time savings (5 hours/week), cost savings ($750/week = $3000/month), and communicate clear ROI for social media automation?"
        )
        
        assert roi_evaluation.passed, f"ROI calculation evaluation failed: {roi_evaluation.reasoning}"

    @pytest.mark.asyncio
    async def test_ea_provides_specific_implementation_guidance(self, real_ea):
        """EA should provide specific, step-by-step implementation guidance."""
        ea = real_ea  # No await needed - fixture returns EA directly
        
        # Given: A request for solution implementation
        request = "How do I set up social media automation for my jewelry business?"
        
        # When: EA provides guidance
        response = await ea.handle_customer_interaction(request, ConversationChannel.PHONE)
        
        # Then: Response should contain implementation steps
        step_indicators = ["1.", "first", "step", "then", "next", "finally"]
        found_steps = [indicator for indicator in step_indicators if indicator in response.lower()]
        assert len(found_steps) >= 2, f"Insufficient step-by-step guidance: {found_steps}"
        
        # Evaluation for implementation quality
        judge = LlmJudge(
            model_id="gpt-4o-mini", 
            output_type=EAResponseQuality
        )
        
        implementation_eval = judge.run(
            context=response,
            question="Evaluate whether this response provides clear, actionable implementation steps for social media automation in the jewelry business"
        )
        
        assert implementation_eval.passed, f"Implementation guidance failed evaluation"
        assert implementation_eval.business_relevance_score >= 7.0, \
            f"Business relevance too low: {implementation_eval.business_relevance_score}"


@pytest.mark.integration
class TestEAIntegrationWithServices:
    """Integration tests requiring actual services (Redis, PostgreSQL, etc.)."""

    @pytest.mark.asyncio
    async def test_ea_with_real_memory_persistence(self, integration_test_config):
        """Test EA with real Redis/PostgreSQL for memory persistence."""
        if not integration_test_config["use_real_services"]:
            pytest.skip("Integration testing disabled")
        
        # This would test with real services
        # Implementation depends on Docker services being available
        pass

    @pytest.mark.asyncio  
    async def test_ea_performance_with_real_llm(self, integration_test_config):
        """Test EA performance with real LLM calls."""
        if not integration_test_config["use_real_services"]:
            pytest.skip("Integration testing disabled")
        
        # This would make real OpenAI API calls
        # Implementation for performance benchmarking
        pass


# === Helper Functions ===

def assert_conversation_quality(messages: List[str], responses: List[str], min_quality_score: float = 0.8):
    """Helper function to assert overall conversation quality using AI evaluation."""
    # Combine conversation for evaluation
    conversation_text = ""
    for msg, resp in zip(messages, responses):
        conversation_text += f"User: {msg}\nAssistant: {resp}\n\n"
    
    # Evaluate conversation quality
    judge = LlmJudge(model_id="gpt-4o-mini")
    quality_eval = judge.run(
        context=conversation_text,
        question=f"Rate the overall conversation quality, professionalism, and business relevance on a scale of 0-1. The conversation should score at least {min_quality_score}."
    )
    
    assert quality_eval.passed, f"Conversation quality below threshold: {quality_eval.reasoning}"


def calculate_response_metrics(response: str) -> Dict[str, float]:
    """Calculate objective metrics for EA responses."""
    import re
    from collections import Counter
    
    return {
        "word_count": len(response.split()),
        "sentence_count": len(re.findall(r'[.!?]+', response)),
        "business_terms": len(re.findall(r'\b(business|automation|process|workflow|efficiency|ROI|save|cost|revenue)\b', response.lower())),
        "question_count": response.count('?'),
        "professional_score": 1.0 if any(term in response.lower() for term in ['professional', 'business', 'assist', 'help']) else 0.0
    }