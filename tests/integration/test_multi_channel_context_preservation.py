"""
Multi-Channel Context Preservation System - Integration Tests

Tests for seamless context handoffs between communication channels
(email, WhatsApp, voice) with unified customer understanding.

Requirements:
- Context preserved across all channel transitions (100% target)
- <500ms context retrieval time
- Conversation threading across channels
- Personal preferences maintained in all contexts
- Business context carried forward seamlessly
- Integration with personality engine complete
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from src.communication.multi_channel_context import (
    MultiChannelContextManager,
    ContextTransitionError,
    ContextRetrievalTimeoutError
)
from src.communication.channel_adapters import (
    EmailChannelAdapter,
    WhatsAppChannelAdapter, 
    VoiceChannelAdapter
)
from src.memory.unified_context_store import UnifiedContextStore
from src.integrations.personality_engine_integration import PersonalityEngineConnector


class TestMultiChannelContextPreservation:
    """Test suite for multi-channel context preservation system"""
    
    @pytest.fixture
    async def context_manager(self):
        """Initialize MultiChannelContextManager with test configuration"""
        manager = MultiChannelContextManager(
            context_store=UnifiedContextStore(),
            personality_connector=PersonalityEngineConnector(),
            performance_target_ms=500
        )
        await manager.initialize()
        return manager
    
    @pytest.fixture
    def customer_context(self):
        """Sample customer context for testing"""
        return {
            "customer_id": "test_customer_001",
            "preferences": {
                "communication_style": "premium_casual",
                "formality_level": "approachable_professional",
                "response_length": "concise_detailed"
            },
            "business_context": {
                "company": "TechStartup Inc",
                "role": "CEO",
                "industry": "SaaS",
                "goals": ["scale_team", "raise_series_a", "expand_market"]
            },
            "conversation_history": [
                {
                    "channel": "email",
                    "timestamp": datetime.now() - timedelta(hours=2),
                    "content": "I need help preparing for our board meeting next week.",
                    "sentiment": "professional_urgent"
                }
            ]
        }
    
    @pytest.mark.asyncio
    async def test_email_to_whatsapp_context_transition(self, context_manager, customer_context):
        """Test Email → WhatsApp transition with formal to casual adaptation"""
        # Setup: Email conversation with formal context
        email_context = {
            "channel": "email",
            "customer_id": customer_context["customer_id"],
            "conversation_thread": "board_meeting_prep",
            "tone": "formal_professional",
            "content": "Thank you for your assistance with the board presentation. Could you please review the financial projections?"
        }
        
        # Store email context
        await context_manager.store_conversation_context(email_context)
        
        # Action: Transition to WhatsApp
        start_time = time.time()
        whatsapp_context = await context_manager.transition_channel(
            customer_id=customer_context["customer_id"],
            from_channel="email",
            to_channel="whatsapp",
            new_message="hey, quick question about those numbers"
        )
        transition_time = (time.time() - start_time) * 1000
        
        # Assertions
        assert transition_time < 500, f"Context transition took {transition_time}ms, exceeds 500ms target"
        assert whatsapp_context["conversation_thread"] == "board_meeting_prep"
        assert whatsapp_context["channel"] == "whatsapp"
        assert whatsapp_context["tone"] == "casual_friendly"
        assert "board presentation" in str(whatsapp_context["context_summary"])
        assert whatsapp_context["customer_preferences"] == customer_context["preferences"]
    
    @pytest.mark.asyncio
    async def test_voice_to_whatsapp_context_transition(self, context_manager, customer_context):
        """Test Voice → WhatsApp transition with spoken to text adaptation"""
        # Setup: Voice conversation context
        voice_context = {
            "channel": "voice",
            "customer_id": customer_context["customer_id"],
            "conversation_thread": "weekly_checkin",
            "tone": "conversational_natural",
            "transcript": "So I was thinking about our marketing strategy and I'm not sure if we're targeting the right audience segment",
            "speech_patterns": ["filler_words", "informal_structure"],
            "emotion": "thoughtful_uncertainty"
        }
        
        # Store voice context
        await context_manager.store_conversation_context(voice_context)
        
        # Action: Transition to WhatsApp
        start_time = time.time()
        whatsapp_context = await context_manager.transition_channel(
            customer_id=customer_context["customer_id"],
            from_channel="voice",
            to_channel="whatsapp",
            new_message="Can you send me some data on our current audience?"
        )
        transition_time = (time.time() - start_time) * 1000
        
        # Assertions
        assert transition_time < 500, f"Context transition took {transition_time}ms, exceeds 500ms target"
        assert whatsapp_context["conversation_thread"] == "weekly_checkin"
        assert "marketing strategy" in str(whatsapp_context["context_summary"])
        assert "audience segment" in str(whatsapp_context["context_summary"])
        assert whatsapp_context["emotion_continuity"] == "thoughtful_uncertainty"
    
    @pytest.mark.asyncio
    async def test_whatsapp_to_email_context_transition(self, context_manager, customer_context):
        """Test WhatsApp → Email transition with casual to formal adaptation"""
        # Setup: WhatsApp conversation context  
        whatsapp_context = {
            "channel": "whatsapp",
            "customer_id": customer_context["customer_id"],
            "conversation_thread": "team_hiring",
            "tone": "casual_friendly",
            "content": "btw found a great developer, want to move fast on this one 🚀",
            "emojis": ["🚀"],
            "urgency": "high"
        }
        
        # Store WhatsApp context
        await context_manager.store_conversation_context(whatsapp_context)
        
        # Action: Transition to Email
        start_time = time.time()
        email_context = await context_manager.transition_channel(
            customer_id=customer_context["customer_id"],
            from_channel="whatsapp",
            to_channel="email",
            new_message="Please draft an offer letter for the developer position."
        )
        transition_time = (time.time() - start_time) * 1000
        
        # Assertions
        assert transition_time < 500, f"Context transition took {transition_time}ms, exceeds 500ms target"
        assert email_context["conversation_thread"] == "team_hiring"
        assert email_context["tone"] == "formal_professional"
        assert "developer" in str(email_context["context_summary"])
        assert email_context["urgency"] == "high"
        assert "emojis" not in email_context or len(email_context.get("emojis", [])) == 0
    
    @pytest.mark.asyncio
    async def test_concurrent_multi_channel_conversations(self, context_manager, customer_context):
        """Test concurrent conversations across multiple channels with context isolation"""
        customer_id = customer_context["customer_id"]
        
        # Setup: Start conversations on different channels
        contexts = {
            "email": {
                "channel": "email",
                "customer_id": customer_id,
                "conversation_thread": "partnership_proposal",
                "content": "Let's discuss the strategic partnership opportunity."
            },
            "whatsapp": {
                "channel": "whatsapp", 
                "customer_id": customer_id,
                "conversation_thread": "daily_standup",
                "content": "team update - sarah finished the api integration"
            },
            "voice": {
                "channel": "voice",
                "customer_id": customer_id,
                "conversation_thread": "brainstorm_session",
                "transcript": "I have this idea for a new feature that could really differentiate us"
            }
        }
        
        # Store all contexts
        for context in contexts.values():
            await context_manager.store_conversation_context(context)
        
        # Action: Retrieve contexts for each channel
        start_time = time.time()
        retrieved_contexts = {}
        for channel in ["email", "whatsapp", "voice"]:
            retrieved_contexts[channel] = await context_manager.get_channel_context(
                customer_id=customer_id,
                channel=channel
            )
        retrieval_time = (time.time() - start_time) * 1000
        
        # Assertions
        assert retrieval_time < 500, f"Context retrieval took {retrieval_time}ms, exceeds 500ms target"
        
        # Verify context isolation
        assert retrieved_contexts["email"]["conversation_thread"] == "partnership_proposal"
        assert retrieved_contexts["whatsapp"]["conversation_thread"] == "daily_standup"
        assert retrieved_contexts["voice"]["conversation_thread"] == "brainstorm_session"
        
        # Verify no cross-contamination
        email_content = str(retrieved_contexts["email"]["context_summary"])
        assert "sarah finished" not in email_content
        assert "new feature" not in email_content
    
    @pytest.mark.asyncio
    async def test_context_retrieval_performance_sla(self, context_manager, customer_context):
        """Test <500ms context retrieval and injection performance requirement"""
        customer_id = customer_context["customer_id"]
        
        # Setup: Store context with significant conversation history
        large_context = {
            "channel": "email",
            "customer_id": customer_id,
            "conversation_thread": "performance_test",
            "conversation_history": [
                {"timestamp": datetime.now() - timedelta(minutes=i), "content": f"Message {i}"}
                for i in range(100)  # 100 message history
            ],
            "business_context": customer_context["business_context"],
            "preferences": customer_context["preferences"]
        }
        
        await context_manager.store_conversation_context(large_context)
        
        # Action: Measure retrieval performance
        performance_results = []
        for _ in range(10):  # Run 10 iterations
            start_time = time.time()
            context = await context_manager.get_channel_context(
                customer_id=customer_id,
                channel="email"
            )
            retrieval_time = (time.time() - start_time) * 1000
            performance_results.append(retrieval_time)
        
        # Assertions
        avg_retrieval_time = sum(performance_results) / len(performance_results)
        max_retrieval_time = max(performance_results)
        
        assert avg_retrieval_time < 500, f"Average retrieval time {avg_retrieval_time}ms exceeds 500ms target"
        assert max_retrieval_time < 750, f"Max retrieval time {max_retrieval_time}ms exceeds acceptable threshold"
        assert all(t < 1000 for t in performance_results), "All retrievals must complete within 1 second"
    
    @pytest.mark.asyncio
    async def test_personality_engine_integration(self, context_manager, customer_context):
        """Test integration with personality engine for context-aware transformations"""
        # Setup: Context with specific personality requirements
        context_with_personality = {
            "channel": "email",
            "customer_id": customer_context["customer_id"],
            "conversation_thread": "personality_test",
            "content": "I need help with a sensitive client situation.",
            "personality_requirements": {
                "tone": "empathetic_professional", 
                "approach": "diplomatic_solution_oriented",
                "formality": "respectful_approachable"
            }
        }
        
        await context_manager.store_conversation_context(context_with_personality)
        
        # Action: Transition with personality adaptation
        start_time = time.time()
        adapted_context = await context_manager.transition_channel(
            customer_id=customer_context["customer_id"],
            from_channel="email",
            to_channel="whatsapp",
            new_message="Quick update on that client issue",
            personality_adaptation=True
        )
        adaptation_time = (time.time() - start_time) * 1000
        
        # Assertions
        assert adaptation_time < 500, f"Personality adaptation took {adaptation_time}ms, exceeds 500ms target"
        assert adapted_context["personality_applied"]["tone"] == "empathetic_casual"
        assert adapted_context["personality_applied"]["approach"] == "supportive_solution_oriented"
        assert "client situation" in str(adapted_context["context_summary"])
    
    @pytest.mark.asyncio
    async def test_context_preservation_failure_recovery(self, context_manager, customer_context):
        """Test graceful handling of context preservation failures"""
        customer_id = customer_context["customer_id"]
        
        # Setup: Store valid context
        valid_context = {
            "channel": "email",
            "customer_id": customer_id,
            "conversation_thread": "failure_test",
            "content": "Important business discussion"
        }
        
        await context_manager.store_conversation_context(valid_context)
        
        # Action: Simulate context retrieval failure
        with pytest.raises(ContextRetrievalTimeoutError):
            await context_manager.get_channel_context(
                customer_id="nonexistent_customer",
                channel="email",
                timeout=0.1  # Force timeout
            )
        
        # Verify original context still accessible
        recovered_context = await context_manager.get_channel_context(
            customer_id=customer_id,
            channel="email"
        )
        
        assert recovered_context["conversation_thread"] == "failure_test"
        assert "Important business discussion" in str(recovered_context["context_summary"])
    
    @pytest.mark.asyncio
    async def test_cross_channel_conversation_threading(self, context_manager, customer_context):
        """Test conversation threading across multiple channels"""
        customer_id = customer_context["customer_id"]
        thread_id = "product_launch_planning"
        
        # Setup: Create conversation thread across channels
        contexts = [
            {
                "channel": "email",
                "customer_id": customer_id,
                "conversation_thread": thread_id,
                "message_id": "msg_001",
                "content": "Let's plan the product launch strategy."
            },
            {
                "channel": "whatsapp",
                "customer_id": customer_id,
                "conversation_thread": thread_id,
                "message_id": "msg_002",
                "content": "great idea! when should we start?"
            },
            {
                "channel": "voice", 
                "customer_id": customer_id,
                "conversation_thread": thread_id,
                "message_id": "msg_003",
                "transcript": "I think we should focus on the enterprise market first"
            }
        ]
        
        # Store all contexts
        for context in contexts:
            await context_manager.store_conversation_context(context)
        
        # Action: Retrieve threaded conversation
        start_time = time.time()
        threaded_conversation = await context_manager.get_conversation_thread(
            customer_id=customer_id,
            thread_id=thread_id
        )
        threading_time = (time.time() - start_time) * 1000
        
        # Assertions
        assert threading_time < 500, f"Conversation threading took {threading_time}ms, exceeds 500ms target"
        assert len(threaded_conversation["messages"]) == 3
        assert threaded_conversation["thread_id"] == thread_id
        assert threaded_conversation["channels_involved"] == ["email", "whatsapp", "voice"]
        
        # Verify chronological ordering
        messages = threaded_conversation["messages"]
        assert messages[0]["message_id"] == "msg_001"
        assert messages[1]["message_id"] == "msg_002" 
        assert messages[2]["message_id"] == "msg_003"


class TestContextStorePerformance:
    """Performance-focused tests for context storage and retrieval"""
    
    @pytest.mark.asyncio
    async def test_high_volume_context_storage(self, context_manager):
        """Test context storage under high volume load"""
        customer_ids = [f"customer_{i:03d}" for i in range(100)]
        
        # Action: Store contexts for 100 customers simultaneously
        start_time = time.time()
        tasks = []
        for customer_id in customer_ids:
            context = {
                "channel": "email",
                "customer_id": customer_id,
                "conversation_thread": f"thread_{customer_id}",
                "content": f"Business discussion for {customer_id}"
            }
            tasks.append(context_manager.store_conversation_context(context))
        
        await asyncio.gather(*tasks)
        storage_time = (time.time() - start_time) * 1000
        
        # Assertions
        assert storage_time < 5000, f"High volume storage took {storage_time}ms, exceeds 5s threshold"
        
        # Verify all contexts stored successfully
        for customer_id in customer_ids[:10]:  # Sample verification
            context = await context_manager.get_channel_context(
                customer_id=customer_id,
                channel="email"
            )
            assert context["conversation_thread"] == f"thread_{customer_id}"
    
    @pytest.mark.asyncio
    async def test_concurrent_channel_transitions(self, context_manager):
        """Test multiple simultaneous channel transitions"""
        customer_id = "concurrent_test_customer"
        
        # Setup: Prepare contexts for transition
        initial_contexts = [
            {
                "channel": "email",
                "customer_id": customer_id,
                "conversation_thread": f"thread_{i}",
                "content": f"Email conversation {i}"
            }
            for i in range(20)
        ]
        
        for context in initial_contexts:
            await context_manager.store_conversation_context(context)
        
        # Action: Perform concurrent transitions
        start_time = time.time()
        transition_tasks = []
        for i in range(20):
            task = context_manager.transition_channel(
                customer_id=customer_id,
                from_channel="email",
                to_channel="whatsapp",
                new_message=f"Transition message {i}",
                thread_id=f"thread_{i}"
            )
            transition_tasks.append(task)
        
        results = await asyncio.gather(*transition_tasks)
        concurrent_time = (time.time() - start_time) * 1000
        
        # Assertions
        assert concurrent_time < 2000, f"Concurrent transitions took {concurrent_time}ms, exceeds 2s threshold"
        assert len(results) == 20
        assert all(result["channel"] == "whatsapp" for result in results)


@pytest.mark.integration
class TestRealTimeContextSynchronization:
    """Test real-time context synchronization capabilities"""
    
    @pytest.mark.asyncio
    async def test_real_time_context_updates(self, context_manager):
        """Test real-time synchronization of context updates across channels"""
        customer_id = "realtime_test_customer"
        
        # Setup: Initialize context
        initial_context = {
            "channel": "email",
            "customer_id": customer_id,
            "conversation_thread": "realtime_sync",
            "content": "Initial message",
            "status": "active"
        }
        
        await context_manager.store_conversation_context(initial_context)
        
        # Action: Update context and verify real-time sync
        start_time = time.time()
        
        # Update business context
        await context_manager.update_business_context(
            customer_id=customer_id,
            updates={
                "current_priority": "quarterly_review",
                "urgency_level": "high",
                "stakeholders": ["board", "investors"]
            }
        )
        
        # Retrieve context from different channel
        updated_context = await context_manager.get_channel_context(
            customer_id=customer_id,
            channel="whatsapp"  # Different channel
        )
        
        sync_time = (time.time() - start_time) * 1000
        
        # Assertions
        assert sync_time < 500, f"Real-time sync took {sync_time}ms, exceeds 500ms target"
        assert updated_context["business_context"]["current_priority"] == "quarterly_review"
        assert updated_context["business_context"]["urgency_level"] == "high"
        assert "board" in updated_context["business_context"]["stakeholders"]
    
    @pytest.mark.asyncio
    async def test_context_consistency_across_channels(self, context_manager):
        """Test context consistency maintained across all channels"""
        customer_id = "consistency_test_customer"
        
        # Setup: Create context with shared business information
        shared_context = {
            "customer_id": customer_id,
            "business_context": {
                "active_project": "Q4_campaign",
                "budget": "$50000",
                "deadline": "2025-12-31"
            },
            "preferences": {
                "update_frequency": "daily",
                "detail_level": "comprehensive"
            }
        }
        
        # Store contexts across multiple channels
        channels = ["email", "whatsapp", "voice"]
        for channel in channels:
            context = {
                **shared_context,
                "channel": channel,
                "conversation_thread": f"{channel}_thread",
                "content": f"Message via {channel}"
            }
            await context_manager.store_conversation_context(context)
        
        # Action: Retrieve and verify consistency
        start_time = time.time()
        retrieved_contexts = {}
        for channel in channels:
            retrieved_contexts[channel] = await context_manager.get_channel_context(
                customer_id=customer_id,
                channel=channel
            )
        consistency_check_time = (time.time() - start_time) * 1000
        
        # Assertions
        assert consistency_check_time < 500, f"Consistency check took {consistency_check_time}ms, exceeds 500ms target"
        
        # Verify business context consistency
        for channel in channels:
            context = retrieved_contexts[channel]
            assert context["business_context"]["active_project"] == "Q4_campaign"
            assert context["business_context"]["budget"] == "$50000"
            assert context["preferences"]["update_frequency"] == "daily"