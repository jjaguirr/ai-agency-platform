"""
Test Cross-Channel Conversation Continuity - Phone → WhatsApp → Email

Tests the specific Phase-1 requirement for conversation continuity across 
communication channels while maintaining business context and learning state.
"""

import os
import pytest
import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Any

# mem0_manager hard-imports mem0, asyncpg, redis at module level.
pytest.importorskip("mem0")
pytest.importorskip("asyncpg")

from tests.conftest import requires_live_services

pytestmark = [pytest.mark.integration, requires_live_services]

from src.agents.memory.ea_memory_integration import EAMemoryIntegration, ConversationContext
from src.memory.mem0_manager import maintain_conversation_continuity


class TestConversationContinuity:
    """Test cross-channel conversation continuity requirements"""
    
    @pytest.fixture
    async def customer_memory_integration(self):
        """Create memory integration for test customer"""
        customer_id = f"continuity_test_{uuid.uuid4().hex[:8]}"
        integration = EAMemoryIntegration(customer_id)
        
        yield integration
        
        # Cleanup
        await integration.close()
    
    @pytest.mark.asyncio
    async def test_phone_to_whatsapp_continuity(self, customer_memory_integration):
        """Test conversation continuity from phone to WhatsApp"""
        integration = customer_memory_integration
        conversation_id = str(uuid.uuid4())
        
        # Initial phone conversation about business automation
        phone_context = ConversationContext(
            customer_id=integration.customer_id,
            conversation_id=conversation_id,
            channel="phone",
            message_history=[
                {"role": "user", "content": "Hi Sarah! I run a jewelry store and need help with social media automation"},
                {"role": "assistant", "content": "I'd love to help! Tell me about your current social media process"}
            ],
            current_intent="business_discovery"
        )
        
        # Process phone conversation
        phone_results = await integration.process_business_conversation(phone_context)
        
        assert phone_results["memory_operations_successful"], "Phone conversation processing failed"
        assert len(phone_results["business_learnings"]) > 0, "No business learnings extracted from phone call"
        
        # Continue conversation via WhatsApp (different channel)
        whatsapp_message = "Following up on our phone call - can you show me the social media templates you mentioned?"
        
        continuity_result = await maintain_conversation_continuity(
            ea_memory=integration.memory_manager,
            channel="whatsapp",
            message=whatsapp_message,
            user_context={"previous_channel": "phone", "conversation_id": conversation_id}
        )
        
        # Verify continuity
        assert continuity_result["context_memories"], "No context memories retrieved for WhatsApp"
        assert len(continuity_result["context_memories"]) > 0, "Context not maintained from phone to WhatsApp"
        
        # Check that business context from phone is available in WhatsApp
        context_content = " ".join([
            memory.get("memory", "") for memory in continuity_result["context_memories"]
        ])
        
        assert "jewelry" in context_content.lower(), "Business context (jewelry store) not maintained"
        assert "social media" in context_content.lower(), "Topic context not maintained"
        
        # Verify response context includes channel switching
        response_context = continuity_result["response_context"]
        assert response_context["current_channel"] == "whatsapp", "Current channel not tracked"
        assert "phone" in response_context.get("previous_channels", []), "Previous channel not tracked"
    
    @pytest.mark.asyncio 
    async def test_multi_channel_business_learning_accumulation(self, customer_memory_integration):
        """Test that business learnings accumulate across channels"""
        integration = customer_memory_integration
        conversation_id = str(uuid.uuid4())
        
        # Phase 1: Phone - Initial business discovery
        phone_context = ConversationContext(
            customer_id=integration.customer_id,
            conversation_id=conversation_id,
            channel="phone",
            message_history=[
                {"role": "user", "content": "I run an e-commerce jewelry business. My main challenge is inventory management - I manually update stock levels daily across 3 platforms: Shopify, Etsy, and Amazon."}
            ],
            current_intent="business_discovery"
        )
        
        phone_results = await integration.process_business_conversation(phone_context)
        initial_learnings = len(phone_results["business_learnings"])
        
        # Phase 2: WhatsApp - Additional process details  
        whatsapp_context = ConversationContext(
            customer_id=integration.customer_id,
            conversation_id=conversation_id,
            channel="whatsapp", 
            message_history=[
                {"role": "user", "content": "Also, I spend 2 hours every morning posting new jewelry photos to Instagram and Pinterest. I use Canva for editing and Buffer for scheduling."}
            ],
            current_intent="process_documentation"
        )
        
        whatsapp_results = await integration.process_business_conversation(whatsapp_context)
        whatsapp_learnings = len(whatsapp_results["business_learnings"])
        
        # Phase 3: Email - Pain points and automation needs
        email_context = ConversationContext(
            customer_id=integration.customer_id,
            conversation_id=conversation_id,
            channel="email",
            message_history=[
                {"role": "user", "content": "Following up on our previous conversations - the inventory sync issue is getting worse. I had oversells on 3 items this week because stock wasn't updated in time. Can you help me automate this?"}
            ],
            current_intent="automation_request"
        )
        
        email_results = await integration.process_business_conversation(email_context)
        email_learnings = len(email_results["business_learnings"])
        
        # Verify business learning accumulation
        assert initial_learnings > 0, "No learnings from phone conversation"
        assert whatsapp_learnings > 0, "No learnings from WhatsApp conversation"  
        assert email_learnings > 0, "No learnings from email conversation"
        
        # Get comprehensive business intelligence
        business_intelligence = await integration.get_business_intelligence_summary()
        
        # Verify accumulated knowledge
        tools_discovered = business_intelligence.get("tools_discovered", [])
        expected_tools = ["shopify", "etsy", "amazon", "instagram", "pinterest", "canva", "buffer"]
        discovered_tool_count = sum(1 for tool in expected_tools if tool in [t.lower() for t in tools_discovered])
        
        assert discovered_tool_count >= 5, f"Expected at least 5 tools discovered, got {discovered_tool_count}: {tools_discovered}"
        
        # Verify automation opportunities identified
        automation_opportunities = business_intelligence.get("automation_opportunities_found", 0)
        assert automation_opportunities >= 2, "Expected at least 2 automation opportunities (inventory sync + social media)"
        
        # Verify pain points captured
        high_priority_opportunities = business_intelligence.get("high_priority_opportunities", [])
        assert len(high_priority_opportunities) > 0, "No high-priority opportunities identified"
        
        # Check for inventory management opportunity
        inventory_opportunity_found = any(
            "inventory" in opp.get("description", "").lower() for opp in high_priority_opportunities
        )
        assert inventory_opportunity_found, "Inventory management automation opportunity not identified"
    
    @pytest.mark.asyncio
    async def test_conversation_context_retrieval_performance(self, customer_memory_integration):
        """Test that conversation context retrieval meets <500ms SLA"""
        integration = customer_memory_integration
        
        # Populate memory with business context
        for i in range(10):
            context = ConversationContext(
                customer_id=integration.customer_id,
                conversation_id=f"perf_test_{i}",
                channel="phone",
                message_history=[
                    {"role": "user", "content": f"Business process {i}: I manually handle customer inquiries via email every morning. This takes about 30 minutes and involves checking inventory, pricing, and availability."}
                ],
                current_intent="business_process_documentation"
            )
            
            await integration.process_business_conversation(context)
        
        # Test context retrieval performance
        import time
        
        start_time = time.time()
        continuity_result = await maintain_conversation_continuity(
            ea_memory=integration.memory_manager,
            channel="whatsapp",
            message="Can you help me automate customer inquiry responses?",
            user_context={"performance_test": True}
        )
        retrieval_time = time.time() - start_time
        
        # Verify performance SLA
        assert retrieval_time < 0.5, f"Context retrieval took {retrieval_time:.3f}s, exceeds 500ms SLA"
        
        # Verify meaningful context was retrieved
        assert len(continuity_result["context_memories"]) > 0, "No context memories retrieved"
        assert continuity_result["response_context"], "No response context generated"
        
        # Verify relevant context
        context_content = " ".join([
            memory.get("memory", "") for memory in continuity_result["context_memories"]
        ])
        assert "customer inquiries" in context_content.lower() or "email" in context_content.lower(), \
            "Retrieved context not relevant to query"
    
    @pytest.mark.asyncio
    async def test_workflow_context_continuity(self, customer_memory_integration):
        """Test workflow creation context maintained across channels"""
        integration = customer_memory_integration
        conversation_id = str(uuid.uuid4())
        
        # Phone: Initial workflow discussion
        phone_context = ConversationContext(
            customer_id=integration.customer_id,
            conversation_id=conversation_id,
            channel="phone", 
            message_history=[
                {"role": "user", "content": "I want to automate my social media posting. I post to Instagram, Facebook, and LinkedIn daily using content from Canva."}
            ],
            current_intent="workflow_planning"
        )
        
        phone_results = await integration.process_business_conversation(phone_context)
        
        # WhatsApp: Template selection
        whatsapp_continuity = await maintain_conversation_continuity(
            ea_memory=integration.memory_manager,
            channel="whatsapp",
            message="Which social media automation template would work best for my setup?",
            user_context={"conversation_id": conversation_id}
        )
        
        # Email: Implementation confirmation
        email_continuity = await maintain_conversation_continuity(
            ea_memory=integration.memory_manager,
            channel="email",
            message="Let's proceed with the social media automation we discussed. Please set it up.",
            user_context={"conversation_id": conversation_id}
        )
        
        # Verify workflow context maintained
        whatsapp_context = " ".join([m.get("memory", "") for m in whatsapp_continuity["context_memories"]])
        email_context = " ".join([m.get("memory", "") for m in email_continuity["context_memories"]])
        
        # Check for workflow context continuity
        workflow_keywords = ["social media", "automation", "instagram", "facebook", "canva"]
        
        whatsapp_context_maintained = sum(1 for keyword in workflow_keywords if keyword.lower() in whatsapp_context.lower()) >= 3
        email_context_maintained = sum(1 for keyword in workflow_keywords if keyword.lower() in email_context.lower()) >= 3
        
        assert whatsapp_context_maintained, "Workflow context not maintained in WhatsApp"
        assert email_context_maintained, "Workflow context not maintained in email"
        
        # Verify template recommendations generated
        if phone_results.get("template_recommendations"):
            social_media_template_found = any(
                "social" in template.get("template_id", "").lower()
                for template in phone_results["template_recommendations"]
            )
            assert social_media_template_found, "Social media template not recommended"
    
    @pytest.mark.asyncio
    async def test_channel_specific_context_enhancement(self, customer_memory_integration):
        """Test that channel-specific context enhances responses appropriately"""
        integration = customer_memory_integration
        base_conversation_id = str(uuid.uuid4())
        
        # Same business query across different channels
        business_query = "I need help with customer follow-up automation"
        
        channels = ["phone", "whatsapp", "email"]
        channel_results = {}
        
        for channel in channels:
            conversation_id = f"{base_conversation_id}_{channel}"
            
            continuity_result = await maintain_conversation_continuity(
                ea_memory=integration.memory_manager,
                channel=channel,
                message=business_query,
                user_context={
                    "conversation_id": conversation_id,
                    "channel_preference": channel
                }
            )
            
            channel_results[channel] = continuity_result
        
        # Verify each channel maintains appropriate context
        for channel, result in channel_results.items():
            assert result["response_context"]["current_channel"] == channel, \
                f"Current channel not properly set for {channel}"
            
            # Verify continuity context structure
            response_context = result["response_context"]
            assert "business_context" in response_context, f"Business context missing for {channel}"
            assert "conversation_flow" in response_context, f"Conversation flow missing for {channel}"
            
            # Channel-specific verification
            if channel == "whatsapp":
                # WhatsApp should be optimized for quick, actionable responses
                assert "continuing conversation" in response_context["conversation_flow"].lower()
            elif channel == "email":
                # Email should maintain formal context
                assert response_context["conversation_flow"], "Email conversation flow empty"
    
    @pytest.mark.asyncio
    async def test_memory_isolation_across_conversations(self, customer_memory_integration):
        """Test that different conversation contexts don't cross-contaminate"""
        integration = customer_memory_integration
        
        # Create two separate conversation contexts
        jewelry_conversation = ConversationContext(
            customer_id=integration.customer_id,
            conversation_id="jewelry_conversation",
            channel="phone",
            message_history=[
                {"role": "user", "content": "I run a high-end jewelry store and need automation for inventory tracking across Shopify and physical store locations."}
            ],
            current_intent="inventory_automation"
        )
        
        restaurant_conversation = ConversationContext(
            customer_id=integration.customer_id,
            conversation_id="restaurant_conversation", 
            channel="whatsapp",
            message_history=[
                {"role": "user", "content": "I own a restaurant chain and want to automate online order processing from DoorDash, UberEats, and our website."}
            ],
            current_intent="order_automation"
        )
        
        # Process both conversations
        jewelry_results = await integration.process_business_conversation(jewelry_conversation)
        restaurant_results = await integration.process_business_conversation(restaurant_conversation)
        
        # Test context retrieval for each conversation
        jewelry_continuity = await maintain_conversation_continuity(
            ea_memory=integration.memory_manager,
            channel="email",
            message="Let's discuss the jewelry inventory automation further",
            user_context={"conversation_id": "jewelry_conversation"}
        )
        
        restaurant_continuity = await maintain_conversation_continuity(
            ea_memory=integration.memory_manager,
            channel="phone",
            message="Can we set up the restaurant order automation now?",
            user_context={"conversation_id": "restaurant_conversation"}
        )
        
        # Verify context isolation
        jewelry_context = " ".join([m.get("memory", "") for m in jewelry_continuity["context_memories"]])
        restaurant_context = " ".join([m.get("memory", "") for m in restaurant_continuity["context_memories"]])
        
        # Jewelry context should not contain restaurant terms
        restaurant_terms = ["restaurant", "doordash", "ubereats", "order processing"]
        jewelry_contamination = sum(1 for term in restaurant_terms if term.lower() in jewelry_context.lower())
        
        # Restaurant context should not contain jewelry terms  
        jewelry_terms = ["jewelry", "shopify", "physical store", "inventory tracking"]
        restaurant_contamination = sum(1 for term in jewelry_terms if term.lower() in restaurant_context.lower())
        
        assert jewelry_contamination == 0, f"Jewelry context contaminated with restaurant terms: {jewelry_context}"
        assert restaurant_contamination == 0, f"Restaurant context contaminated with jewelry terms: {restaurant_context}"
        
        # Verify appropriate context is maintained
        assert "jewelry" in jewelry_context.lower() or "inventory" in jewelry_context.lower(), \
            "Jewelry context not properly maintained"
        assert "restaurant" in restaurant_context.lower() or "order" in restaurant_context.lower(), \
            "Restaurant context not properly maintained"


if __name__ == "__main__":
    # Run specific continuity tests
    pytest.main([
        "-v", 
        "--tb=short",
        "tests/memory/test_conversation_continuity.py",
        "-k", "test_phone_to_whatsapp_continuity or test_multi_channel_business_learning_accumulation"
    ])