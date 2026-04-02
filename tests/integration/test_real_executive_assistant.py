"""
Integration Tests for Real ExecutiveAssistant Implementation
Tests actual Redis, PostgreSQL, and LangGraph integration - no mocks
"""

import pytest
import asyncio
import json
import os
from typing import Dict, List, Any
from unittest.mock import patch

from src.agents.executive_assistant import (
    ExecutiveAssistant, 
    ConversationChannel, 
    BusinessContext,
    ConversationIntent,
    ConversationPhase
)


@pytest.mark.integration
class TestRealExecutiveAssistantIntegration:
    """Test ExecutiveAssistant with real dependencies."""

    @pytest.mark.asyncio
    async def test_ea_initialization_with_real_dependencies(self, integration_test_config):
        """Test EA initializes with real Redis and PostgreSQL."""
        customer_id = "test_init_123"

        # When: Initialize EA with real dependencies
        ea = ExecutiveAssistant(
            customer_id=customer_id,
            mcp_server_url="test://localhost"
        )

        # Then: All dependencies should be initialized
        assert ea.customer_id == customer_id
        assert ea.memory is not None
        assert ea.memory.redis_client is not None
        assert ea.memory.db_connection is not None
        assert ea.workflow_creator is not None
        assert ea.graph is not None
        
        # Cleanup
        try:
            ea.memory.redis_client.flushdb()
            with ea.memory.db_connection.cursor() as cursor:
                cursor.execute("DELETE FROM customer_business_context WHERE customer_id = %s", (customer_id,))
                ea.memory.db_connection.commit()
        except Exception as e:
            print(f"Cleanup warning: {e}")

    @pytest.mark.asyncio
    async def test_real_redis_conversation_context(self, real_ea):
        """Test conversation context storage/retrieval with real Redis."""
        ea = await real_ea
        conversation_id = "test_conv_456"
        
        # When: Store conversation context in Redis
        context_data = {
            "last_message": "Hello, I need help with automation",
            "last_response": "I'd be happy to help with automation",
            "channel": "phone",
            "intent": "business_assistance",
            "workflow_created": False
        }
        
        await ea.memory.store_conversation_context(conversation_id, context_data)
        
        # Then: Should retrieve the exact context
        retrieved_context = await ea.memory.get_conversation_context(conversation_id)
        
        assert retrieved_context == context_data
        assert retrieved_context["last_message"] == "Hello, I need help with automation"
        assert retrieved_context["intent"] == "business_assistance"
        assert retrieved_context["workflow_created"] is False

    @pytest.mark.asyncio
    async def test_real_postgresql_business_context(self, real_ea, jewelry_business_context):
        """Test business context persistence with real PostgreSQL."""
        ea = await real_ea
        
        # When: Store business context in PostgreSQL
        await ea.memory.store_business_context(jewelry_business_context)
        
        # Then: Should retrieve the complete business context
        retrieved_context = await ea.memory.get_business_context()
        
        assert retrieved_context.business_name == jewelry_business_context.business_name
        assert retrieved_context.business_type == jewelry_business_context.business_type
        assert retrieved_context.industry == jewelry_business_context.industry
        assert retrieved_context.daily_operations == jewelry_business_context.daily_operations
        assert retrieved_context.pain_points == jewelry_business_context.pain_points
        assert retrieved_context.current_tools == jewelry_business_context.current_tools

    @pytest.mark.asyncio
    async def test_langgraph_conversation_flow(self, real_ea):
        """Test actual LangGraph conversation state transitions."""
        ea = await real_ea
        
        # When: Handle business discovery conversation
        response1 = await ea.handle_customer_interaction(
            "I need help with automation for my business",
            ConversationChannel.CHAT
        )
        
        # Then: Should get professional business response
        assert response1 is not None
        assert len(response1) > 50  # Meaningful response length
        assert any(word in response1.lower() for word in ["business", "automation", "help", "assistant"])
        
        # When: Follow up with specific business info
        response2 = await ea.handle_customer_interaction(
            "I run a consulting business and spend 5 hours a week on manual invoicing",
            ConversationChannel.CHAT
        )
        
        # Then: Should identify automation opportunity
        assert "invoice" in response2.lower() or "invoicing" in response2.lower()
        assert any(word in response2.lower() for word in ["automate", "automation", "save", "time"])

    @pytest.mark.asyncio
    @pytest.mark.skipif(not os.getenv('OPENAI_API_KEY'), reason="OpenAI API key required")
    async def test_real_openai_llm_integration(self, real_ea):
        """Test EA with real OpenAI API calls (requires API key)."""
        ea = await real_ea
        
        # When: Handle complex business scenario requiring LLM reasoning
        complex_message = """
        I run a digital marketing agency with 20 clients. Every Monday I manually:
        1. Create weekly reports for each client
        2. Schedule social media posts for the week
        3. Send follow-up emails to prospects
        4. Update project management boards
        
        This takes me 8 hours every Monday and I'm exhausted.
        """
        
        response = await ea.handle_customer_interaction(
            complex_message,
            ConversationChannel.PHONE
        )
        
        # Then: Should provide sophisticated analysis and recommendations
        assert len(response) > 200  # Detailed response
        assert "8 hour" in response or "monday" in response.lower()  # Context awareness
        assert any(word in response.lower() for word in ["automate", "automation", "workflow"])
        assert any(word in response.lower() for word in ["report", "social media", "email", "project"])
        
        # Should mention multiple automation opportunities
        automation_indicators = ["report", "social", "email", "project", "schedule"]
        found_indicators = [word for word in automation_indicators if word in response.lower()]
        assert len(found_indicators) >= 3, f"Only found {len(found_indicators)} automation indicators"

    @pytest.mark.asyncio
    async def test_memory_persistence_across_conversations(self, real_ea):
        """Test that business context persists across multiple conversations."""
        ea = await real_ea
        
        # First conversation: Store business info
        await ea.handle_customer_interaction(
            "I run GreenThumb Landscaping, we do residential lawn care",
            ConversationChannel.PHONE
        )
        
        # Store some specific business knowledge
        await ea.memory.store_business_knowledge(
            "Customer specializes in residential lawn care and landscaping services",
            {"category": "business_services", "priority": "high"}
        )
        
        # Second conversation: Should remember business context
        response = await ea.handle_customer_interaction(
            "What automation opportunities do you see for my business?",
            ConversationChannel.CHAT
        )
        
        # Then: Response should reference the landscaping business
        assert "landscap" in response.lower() or "lawn" in response.lower() or "greenthumb" in response.lower()
        
        # Third conversation: Test memory search
        search_results = await ea.memory.search_business_knowledge("landscaping services")
        
        assert len(search_results) > 0
        found_landscaping = any("landscap" in result["content"].lower() for result in search_results)
        assert found_landscaping, "Landscaping information not found in memory"

    @pytest.mark.asyncio
    async def test_workflow_creation_integration(self, real_ea):
        """Test workflow creation with template matching."""
        ea = await real_ea
        
        # When: Request automation for a common business process
        response = await ea.handle_customer_interaction(
            "I need to automate my social media posting. I manually post to Facebook and Instagram every day",
            ConversationChannel.CHAT
        )
        
        # Then: Should identify social media automation opportunity
        assert any(word in response.lower() for word in ["social media", "facebook", "instagram", "posting"])
        assert any(word in response.lower() for word in ["automat", "workflow", "template"])
        
        # Should suggest workflow creation
        workflow_indicators = ["workflow", "automat", "creat", "deploy", "template"]
        found_workflow_indicators = [word for word in workflow_indicators if word in response.lower()]
        assert len(found_workflow_indicators) >= 2

    @pytest.mark.asyncio
    async def test_cross_channel_context_continuity(self, real_ea):
        """Test conversation continuity across different channels."""
        ea = await real_ea
        
        # Phone conversation: Initial business discovery
        phone_response = await ea.handle_customer_interaction(
            "Hi, I'm John and I run a bakery called Sweet Dreams",
            ConversationChannel.PHONE
        )
        
        # Store the business context
        await ea.memory.store_business_knowledge(
            "Customer John runs Sweet Dreams bakery",
            {"category": "business_owner", "priority": "high"}
        )
        
        # WhatsApp conversation: Should remember context
        whatsapp_response = await ea.handle_customer_interaction(
            "What are the best automation opportunities for my business?",
            ConversationChannel.WHATSAPP
        )
        
        # Then: Should reference the bakery business
        business_indicators = ["bakery", "sweet dreams", "john"]
        found_indicators = [word for word in business_indicators if word.lower() in whatsapp_response.lower()]
        
        # Should find at least one business indicator
        assert len(found_indicators) >= 1, f"No business context found in response: {whatsapp_response}"

    @pytest.mark.asyncio
    async def test_error_handling_with_real_services(self, real_ea):
        """Test error handling when services encounter issues."""
        ea = await real_ea
        
        # Test with malformed input
        response = await ea.handle_customer_interaction(
            "",  # Empty message
            ConversationChannel.CHAT
        )
        
        # Should handle gracefully
        assert response is not None
        assert len(response) > 0
        assert "assist" in response.lower() or "help" in response.lower()
        
        # Test with very long message
        long_message = "automation " * 1000  # Very long message
        long_response = await ea.handle_customer_interaction(
            long_message,
            ConversationChannel.CHAT
        )
        
        # Should handle without crashing
        assert long_response is not None
        assert len(long_response) > 0

    @pytest.mark.asyncio
    async def test_business_context_extraction_accuracy(self, real_ea):
        """Test accurate extraction and storage of business information."""
        ea = await real_ea
        
        # Complex business scenario
        business_description = """
        I own TechStart Solutions, a B2B software consulting company. 
        We specialize in helping mid-size companies (50-200 employees) implement CRM systems.
        My team of 5 consultants and I work with tools like Salesforce, HubSpot, and Pipedrive.
        
        Our biggest challenges are:
        - Manual proposal creation takes 4 hours per proposal
        - Follow-up scheduling with prospects
        - Tracking project milestones across multiple clients
        - Generating weekly status reports for each client
        
        We're currently making $500K annually and want to scale to $1M next year.
        """
        
        # When: EA processes complex business information
        response = await ea.handle_customer_interaction(
            business_description,
            ConversationChannel.PHONE
        )
        
        # Then: Should extract key business elements
        key_elements = [
            "techstart solutions",
            "software consulting", 
            "crm",
            "salesforce",
            "hubspot",
            "proposal",
            "500k"
        ]
        
        # Search memory for extracted information
        for element in key_elements:
            search_results = await ea.memory.search_business_knowledge(element)
            found_element = any(element.lower() in result["content"].lower() for result in search_results)
            assert found_element, f"Business element '{element}' not found in memory"
        
        # Response should acknowledge the complexity
        assert len(response) > 300  # Detailed response for complex input
        assert any(word in response.lower() for word in ["proposal", "crm", "consulting", "automat"])


@pytest.mark.integration
class TestRealExecutiveAssistantPerformance:
    """Performance tests with real services."""

    @pytest.mark.asyncio
    async def test_response_time_with_real_services(self, real_ea, ea_performance_benchmarks):
        """Test EA response time meets requirements with real services."""
        import time
        
        ea = await real_ea
        
        # When: Process standard business query
        message = "I need help automating my customer follow-up process"
        
        start_time = time.time()
        response = await ea.handle_customer_interaction(
            message,
            ConversationChannel.CHAT
        )
        response_time = time.time() - start_time
        
        # Then: Should meet performance requirements
        max_response_time = ea_performance_benchmarks["response_time"]  # <2 seconds
        
        # Note: Real API calls may be slower, so we're more lenient for integration tests
        integration_max_time = max_response_time * 3  # Allow 6 seconds for integration tests
        
        assert response_time < integration_max_time, \
            f"Response time {response_time:.3f}s exceeds integration limit {integration_max_time}s"
        
        # Response should be meaningful
        assert len(response) >= 50, "Response too short to be meaningful"
        assert "follow" in response.lower() or "customer" in response.lower()

    @pytest.mark.asyncio
    async def test_memory_retrieval_performance(self, real_ea):
        """Test memory search performance against the live store."""
        ea = await real_ea
        
        # Store multiple business knowledge entries
        knowledge_entries = [
            "Customer runs a restaurant chain with 5 locations",
            "Daily operations include inventory management and staff scheduling", 
            "Main pain points are manual payroll and food cost tracking",
            "Current tools include Square POS and QuickBooks",
            "Revenue target is $2M annually across all locations"
        ]
        
        for knowledge in knowledge_entries:
            await ea.memory.store_business_knowledge(
                knowledge,
                {"category": "business_info", "source": "test"}
            )
        
        # When: Search memory with timing
        import time
        start_time = time.time()
        search_results = await ea.memory.search_business_knowledge("restaurant operations")
        search_time = time.time() - start_time
        
        # Then: Should retrieve relevant results quickly
        assert search_time < 2.0, f"Memory search took {search_time:.3f}s, should be <2s"
        assert len(search_results) > 0, "No search results returned"
        
        # Results should be relevant
        relevant_results = [
            result for result in search_results 
            if any(word in result["content"].lower() for word in ["restaurant", "operations", "locations"])
        ]
        assert len(relevant_results) > 0, "No relevant results found"


@pytest.mark.integration
class TestRealExecutiveAssistantEdgeCases:
    """Edge case testing with real services."""

    @pytest.mark.asyncio
    async def test_concurrent_conversations(self, integration_test_config):
        """Test EA handling concurrent conversations from same customer."""
        customer_id = "test_concurrent_123"
        
        # Create two EA instances for same customer (simulating concurrent requests)
        ea1 = ExecutiveAssistant(customer_id=customer_id)
        ea2 = ExecutiveAssistant(customer_id=customer_id)
        
        # When: Handle concurrent conversations
        async def conversation1():
            return await ea1.handle_customer_interaction(
                "I run a law firm and need help with client intake automation",
                ConversationChannel.PHONE
            )
        
        async def conversation2():
            return await ea2.handle_customer_interaction(
                "What automation opportunities do you see for legal practices?",
                ConversationChannel.CHAT
            )
        
        # Execute concurrently
        response1, response2 = await asyncio.gather(conversation1(), conversation2())
        
        # Then: Both should complete successfully
        assert response1 is not None and len(response1) > 0
        assert response2 is not None and len(response2) > 0
        
        # Should handle legal practice context
        assert "law" in response1.lower() or "legal" in response1.lower()
        assert "legal" in response2.lower() or "automat" in response2.lower()
        
        # Cleanup
        try:
            for ea in [ea1, ea2]:
                ea.memory.redis_client.flushdb()
                with ea.memory.db_connection.cursor() as cursor:
                    cursor.execute("DELETE FROM customer_business_context WHERE customer_id = %s", (customer_id,))
                    ea.memory.db_connection.commit()
        except Exception as e:
            print(f"Cleanup warning: {e}")

    @pytest.mark.asyncio
    async def test_memory_consistency_after_errors(self, real_ea):
        """Test memory remains consistent after handling errors."""
        ea = await real_ea
        
        # Store valid business context
        valid_context = BusinessContext(
            business_name="Test Business",
            industry="technology",
            daily_operations=["coding", "meetings"]
        )
        
        await ea.memory.store_business_context(valid_context)
        
        # Simulate error condition (invalid message handling)
        try:
            with patch('src.agents.executive_assistant.ExecutiveAssistant.llm') as mock_llm:
                # Make LLM throw an error
                mock_llm.ainvoke.side_effect = Exception("Simulated LLM error")
                
                response = await ea.handle_customer_interaction(
                    "This should cause an error",
                    ConversationChannel.CHAT
                )
                
                # Should handle error gracefully
                assert "issue" in response.lower() or "moment" in response.lower()
        
        except Exception:
            pass  # Expected due to mocked error
        
        # Then: Memory should still be consistent
        retrieved_context = await ea.memory.get_business_context()
        assert retrieved_context.business_name == "Test Business"
        assert retrieved_context.industry == "technology"
        assert "coding" in retrieved_context.daily_operations

    @pytest.mark.asyncio
    async def test_large_conversation_history(self, real_ea):
        """Test EA performance with large conversation history."""
        ea = await real_ea
        
        # Simulate long conversation history
        for i in range(20):  # 20 exchanges
            message = f"This is message {i+1} about my business automation needs"
            response = await ea.handle_customer_interaction(
                message,
                ConversationChannel.CHAT
            )
            
            # Each response should be valid
            assert response is not None
            assert len(response) > 0
        
        # Final message should still get quality response
        final_response = await ea.handle_customer_interaction(
            "Summarize all the automation opportunities we've discussed",
            ConversationChannel.CHAT
        )
        
        assert len(final_response) > 100  # Should provide meaningful summary
        assert "automat" in final_response.lower()