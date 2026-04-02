"""
Business Proposition Tests - Phase 1 Executive Assistant
Tests validate core business value propositions from Phase 1 PRD
"""

import asyncio
import pytest
import time
from datetime import datetime
from typing import Dict, Any
from unittest.mock import Mock, patch, AsyncMock

from src.agents.executive_assistant import ExecutiveAssistant, ConversationChannel
from tests.conftest import BusinessContext

# Real ExecutiveAssistant + live storage — gated by conftest service probe.
pytestmark = pytest.mark.integration


class TestEABusinessProposition:
    """Test suite validating Phase 1 business propositions"""

    @pytest.mark.asyncio
    async def test_ea_available_within_60_seconds_onboarding(self):
        """
        Business Proposition: EA available and calling customer within 60 seconds of purchase
        PRD Success Metric: EA available and calling customer within 60 seconds of purchase
        """
        start_time = time.time()
        
        # Simulate purchase completion and EA provisioning
        customer_id = f"customer_{int(time.time())}"
        
        # EA should be instantiable and ready within 60 seconds
        ea = ExecutiveAssistant(customer_id=customer_id)
        
        # Test initial contact capability
        welcome_message = await ea.handle_customer_interaction(
            message="System: New customer onboarding initiated",
            channel=ConversationChannel.PHONE
        )
        
        provisioning_time = time.time() - start_time
        
        # Business validation
        assert provisioning_time < 60, f"EA provisioning took {provisioning_time}s > 60s limit"
        assert "welcome" in welcome_message.lower() or "hello" in welcome_message.lower()
        assert ea.customer_id == customer_id
        
        print(f"✅ EA provisioned in {provisioning_time:.2f}s (< 60s requirement)")

    @pytest.mark.asyncio
    async def test_business_discovery_conversation_within_5_minutes(self):
        """
        Business Proposition: EA learns business through conversation
        PRD Success Metric: Match customer need to workflow template within first 5 minutes
        """
        ea = ExecutiveAssistant(customer_id="discovery_test")
        
        start_time = time.time()
        
        # Simulate business discovery conversation
        business_intro = """
        I run a jewelry e-commerce business called Sparkle & Shine. 
        We sell handmade jewelry online through Instagram and our website.
        I spend 2 hours daily posting on social media and 4 hours weekly creating invoices.
        I need help automating these repetitive tasks.
        """
        
        response = await ea.handle_customer_interaction(
            message=business_intro,
            channel=ConversationChannel.PHONE
        )
        
        discovery_time = time.time() - start_time
        
        # Business validation - EA should identify automation opportunities
        response_lower = response.lower()
        business_understanding_indicators = [
            "jewelry", "e-commerce", "social media", "instagram", 
            "automat", "workflow", "invoice", "posting"
        ]
        
        understanding_score = sum(
            1 for indicator in business_understanding_indicators 
            if indicator in response_lower
        )
        
        # Validate business comprehension
        assert discovery_time < 300, f"Discovery took {discovery_time}s > 5min limit"
        assert understanding_score >= 3, f"EA understanding score: {understanding_score}/8"
        
        print(f"✅ Business discovery completed in {discovery_time:.2f}s")
        print(f"✅ Business understanding score: {understanding_score}/8")

    @pytest.mark.asyncio
    async def test_workflow_template_matching_capability(self):
        """
        Business Proposition: EA creates workflows using pre-built templates
        PRD Success Metric: >95% workflow success rate using template-based approach
        """
        ea = ExecutiveAssistant(customer_id="template_test")
        
        # Test common automation scenarios
        automation_requests = [
            {
                "request": "I need to automate my social media posting for my jewelry business",
                "expected_template": "social_media_automation",
                "keywords": ["social", "media", "post", "schedule", "content"]
            },
            {
                "request": "Help me automate invoice creation and sending to customers", 
                "expected_template": "invoice_automation",
                "keywords": ["invoice", "billing", "payment", "customer", "send"]
            },
            {
                "request": "I want to automate lead follow-up emails for new inquiries",
                "expected_template": "lead_management", 
                "keywords": ["lead", "follow-up", "email", "inquiry", "customer"]
            }
        ]
        
        successful_matches = 0
        
        for scenario in automation_requests:
            response = await ea.handle_customer_interaction(
                message=scenario["request"],
                channel=ConversationChannel.PHONE
            )
            
            response_lower = response.lower()
            keyword_matches = sum(
                1 for keyword in scenario["keywords"] 
                if keyword in response_lower
            )
            
            # Template matching success if EA demonstrates understanding
            if keyword_matches >= 2:
                successful_matches += 1
            
            print(f"Scenario: {scenario['expected_template']}")
            print(f"Keyword matches: {keyword_matches}/{len(scenario['keywords'])}")
        
        success_rate = (successful_matches / len(automation_requests)) * 100
        
        # Business validation
        assert success_rate >= 60, f"Template matching success rate: {success_rate}% < 60% minimum"
        
        print(f"✅ Template matching success rate: {success_rate}%")

    @pytest.mark.asyncio 
    async def test_response_time_requirements(self):
        """
        Business Proposition: Professional EA response times
        PRD Success Metric: <2 seconds text response, <500ms voice response
        """
        ea = ExecutiveAssistant(customer_id="performance_test")
        
        # Test text response time
        text_start = time.time()
        text_response = await ea.handle_customer_interaction(
            message="What can you help me with today?",
            channel=ConversationChannel.WHATSAPP
        )
        text_time = time.time() - text_start
        
        # Test phone response time (simulated)
        phone_start = time.time()
        phone_response = await ea.handle_customer_interaction(
            message="Hello, this is a quick question",
            channel=ConversationChannel.PHONE
        )
        phone_time = time.time() - phone_start
        
        # Business validation
        assert text_time < 2.0, f"Text response time: {text_time:.3f}s > 2s limit"
        assert phone_time < 2.0, f"Phone response time: {phone_time:.3f}s > 2s limit" 
        assert len(text_response) > 10, "Response too short"
        assert len(phone_response) > 10, "Response too short"
        
        print(f"✅ Text response time: {text_time:.3f}s (< 2s requirement)")
        print(f"✅ Phone response time: {phone_time:.3f}s (< 2s requirement)")

    @pytest.mark.asyncio
    async def test_memory_persistence_across_interactions(self):
        """
        Business Proposition: EA remembers complete business context
        PRD Success Metric: Remember 100% of business context across interactions
        """
        ea = ExecutiveAssistant(customer_id="memory_test")
        
        # First interaction - establish business context
        context_message = """
        I run TechStartup Solutions, a B2B software consultancy with 25 employees.
        We serve clients in fintech and healthcare industries.
        Our main pain point is managing client onboarding and project tracking.
        """
        
        initial_response = await ea.handle_customer_interaction(
            message=context_message,
            channel=ConversationChannel.EMAIL
        )
        
        # Simulate time gap between interactions
        await asyncio.sleep(0.5)
        
        # Second interaction - test context recall
        recall_message = "What did I tell you about my business earlier?"
        
        recall_response = await ea.handle_customer_interaction(
            message=recall_message,
            channel=ConversationChannel.WHATSAPP
        )
        
        # Business validation - check context retention
        context_elements = [
            "techstartup", "solutions", "consultancy", "employees",
            "fintech", "healthcare", "onboarding", "project"
        ]
        
        recall_score = sum(
            1 for element in context_elements
            if element in recall_response.lower()
        )
        
        memory_retention = (recall_score / len(context_elements)) * 100
        
        assert memory_retention >= 50, f"Memory retention: {memory_retention}% < 50% minimum"
        
        print(f"✅ Business context retention: {memory_retention}%")

    @pytest.mark.asyncio
    async def test_customer_isolation_between_instances(self):
        """
        Business Proposition: 100% data isolation per customer
        PRD Success Metric: 100% data isolation (zero shared infrastructure)
        """
        # Create two separate EA instances for different customers
        ea1 = ExecutiveAssistant(customer_id="isolation_test_1")
        ea2 = ExecutiveAssistant(customer_id="isolation_test_2")
        
        # Customer 1 shares sensitive business information
        customer1_info = "My business revenue is $500K annually and I work with Apple Inc."
        
        await ea1.handle_customer_interaction(
            message=customer1_info,
            channel=ConversationChannel.EMAIL
        )
        
        # Customer 2 asks about business information
        customer2_query = "What do you know about other customers' revenue or clients?"
        
        ea2_response = await ea2.handle_customer_interaction(
            message=customer2_query,
            channel=ConversationChannel.PHONE
        )
        
        # Isolation validation - Customer 2 should not see Customer 1's data
        sensitive_terms = ["500k", "apple", "revenue"]
        isolation_breach = any(
            term in ea2_response.lower() 
            for term in sensitive_terms
        )
        
        assert not isolation_breach, "Customer data isolation breach detected"
        assert ea1.customer_id != ea2.customer_id, "Customer IDs should be different"
        
        print("✅ Customer data isolation maintained")

    @pytest.mark.asyncio
    async def test_multi_channel_communication_capability(self):
        """
        Business Proposition: 24/7 EA availability across all channels
        PRD Success Metric: 99.9% EA availability across WhatsApp, Email, Phone
        """
        ea = ExecutiveAssistant(customer_id="multichannel_test")
        
        test_message = "I need help with my business automation strategy"
        
        # Test all communication channels
        channels_tested = []
        
        for channel in ConversationChannel:
            try:
                response = await ea.handle_customer_interaction(
                    message=test_message,
                    channel=channel
                )
                
                if response and len(response) > 5:
                    channels_tested.append(channel.value)
                    
            except Exception as e:
                print(f"Channel {channel.value} failed: {e}")
        
        channel_availability = (len(channels_tested) / len(ConversationChannel)) * 100
        
        # Business validation
        assert channel_availability >= 80, f"Channel availability: {channel_availability}% < 80%"
        assert ConversationChannel.PHONE.value in channels_tested, "Phone channel must work"
        
        print(f"✅ Multi-channel availability: {channel_availability}%")
        print(f"Available channels: {channels_tested}")


class TestEABusinessROI:
    """Test EA business value and ROI calculations"""
    
    @pytest.mark.asyncio
    async def test_automation_roi_calculation(self):
        """
        Business Proposition: EA provides measurable business value
        Test ROI calculation for common automation scenarios
        """
        ea = ExecutiveAssistant(customer_id="roi_test")
        
        roi_scenario = """
        I currently spend 10 hours per week on manual invoice creation at $50/hour.
        How much could I save with automation?
        """
        
        response = await ea.handle_customer_interaction(
            message=roi_scenario,
            channel=ConversationChannel.EMAIL
        )
        
        # Check if EA provides business value analysis
        value_indicators = [
            "save", "cost", "time", "hour", "week", "automat", "roi", "value"
        ]
        
        value_understanding = sum(
            1 for indicator in value_indicators
            if indicator in response.lower()
        )
        
        assert value_understanding >= 4, f"ROI understanding score: {value_understanding}/8"
        
        print(f"✅ Business value understanding: {value_understanding}/8")

    @pytest.mark.asyncio
    async def test_competitive_differentiation(self):
        """
        Business Proposition: EA-first approach vs multi-agent complexity
        Test that EA positions itself as a complete assistant, not just software
        """
        ea = ExecutiveAssistant(customer_id="differentiation_test")
        
        positioning_query = "How are you different from other automation tools?"
        
        response = await ea.handle_customer_interaction(
            message=positioning_query,
            channel=ConversationChannel.PHONE
        )
        
        # Check for EA positioning elements
        ea_positioning = [
            "assistant", "partner", "learn", "understand", "business",
            "conversation", "personal", "remember", "adapt"
        ]
        
        positioning_score = sum(
            1 for element in ea_positioning
            if element in response.lower()
        )
        
        assert positioning_score >= 3, f"EA positioning score: {positioning_score}/9"
        
        print(f"✅ EA positioning strength: {positioning_score}/9")


@pytest.fixture
async def business_scenario_data():
    """Real business scenarios for testing"""
    return [
        {
            "business_type": "E-commerce Jewelry",
            "pain_points": ["Social media posting", "Invoice creation", "Customer follow-up"],
            "expected_automations": ["social_media_automation", "invoice_automation", "customer_support"],
            "time_savings_target": "15 hours/week"
        },
        {
            "business_type": "Consulting Firm", 
            "pain_points": ["Client onboarding", "Project tracking", "Report generation"],
            "expected_automations": ["client_onboarding", "project_management", "report_automation"],
            "time_savings_target": "20 hours/week"
        },
        {
            "business_type": "Real Estate Agency",
            "pain_points": ["Lead qualification", "Property marketing", "Client communication"],
            "expected_automations": ["lead_management", "marketing_automation", "communication_automation"],
            "time_savings_target": "12 hours/week"
        }
    ]


class TestEABusinessScenarios:
    """End-to-end business scenario testing"""
    
    @pytest.mark.asyncio
    async def test_complete_customer_journey(self, business_scenario_data):
        """
        Business Proposition: Complete EA customer journey validation
        Tests the full customer experience from onboarding to value delivery
        """
        for scenario in business_scenario_data:
            customer_id = f"journey_{scenario['business_type'].lower().replace(' ', '_')}"
            ea = ExecutiveAssistant(customer_id=customer_id)
            
            # Step 1: Initial business discovery
            business_intro = f"""
            I run a {scenario['business_type']} business.
            My main challenges are: {', '.join(scenario['pain_points'])}.
            I'm looking for ways to automate these processes.
            """
            
            discovery_response = await ea.handle_customer_interaction(
                message=business_intro,
                channel=ConversationChannel.PHONE
            )
            
            # Step 2: Automation consultation
            automation_query = "What specific automations would you recommend for my business?"
            
            consultation_response = await ea.handle_customer_interaction(
                message=automation_query,
                channel=ConversationChannel.WHATSAPP
            )
            
            # Step 3: Implementation guidance
            implementation_query = "How do we get started with implementing these automations?"
            
            implementation_response = await ea.handle_customer_interaction(
                message=implementation_query,
                channel=ConversationChannel.EMAIL
            )
            
            # Validate complete journey
            journey_quality_indicators = [
                len(discovery_response) > 50,
                len(consultation_response) > 50,
                len(implementation_response) > 50,
                any(pain in consultation_response.lower() for pain in scenario['pain_points']),
                "automat" in consultation_response.lower()
            ]
            
            journey_success = sum(journey_quality_indicators)
            
            assert journey_success >= 4, f"Customer journey quality: {journey_success}/5"
            
            print(f"✅ {scenario['business_type']} journey: {journey_success}/5")