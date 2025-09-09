"""
Unified Context Store - Unit Tests

Tests for the core context storage and retrieval system that enables
seamless multi-channel conversation context preservation.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.memory.unified_context_store import (
    UnifiedContextStore,
    ContextEntry,
    ConversationThread,
    CustomerContext,
    ContextStorageError,
    ContextNotFoundError
)


class TestUnifiedContextStore:
    """Test suite for UnifiedContextStore core functionality"""
    
    @pytest.fixture
    async def context_store(self):
        """Initialize UnifiedContextStore with test configuration"""
        store = UnifiedContextStore(
            database_url="postgresql://test:test@localhost:5432/test_context_db",
            performance_target_ms=500
        )
        await store.initialize()
        return store
    
    @pytest.fixture
    def sample_context_entry(self):
        """Sample context entry for testing"""
        return ContextEntry(
            customer_id="test_customer_001",
            channel="email",
            conversation_thread="board_meeting_prep",
            timestamp=datetime.now(),
            content="Preparing for board meeting presentation",
            metadata={
                "tone": "formal_professional",
                "urgency": "high",
                "stakeholders": ["board", "investors"]
            }
        )
    
    @pytest.mark.asyncio
    async def test_store_context_entry_success(self, context_store, sample_context_entry):
        """Test successful storage of context entry"""
        # Action
        result = await context_store.store_context(sample_context_entry)
        
        # Assertions
        assert result.success is True
        assert result.entry_id is not None
        assert result.timestamp is not None
        assert result.storage_time_ms < 500
    
    @pytest.mark.asyncio
    async def test_retrieve_context_by_customer_and_channel(self, context_store, sample_context_entry):
        """Test context retrieval by customer ID and channel"""
        # Setup
        await context_store.store_context(sample_context_entry)
        
        # Action
        start_time = time.time()
        retrieved_context = await context_store.get_context(
            customer_id="test_customer_001",
            channel="email"
        )
        retrieval_time = (time.time() - start_time) * 1000
        
        # Assertions
        assert retrieval_time < 500
        assert retrieved_context.customer_id == "test_customer_001"
        assert retrieved_context.channel == "email"
        assert retrieved_context.conversation_thread == "board_meeting_prep"
        assert retrieved_context.content == "Preparing for board meeting presentation"
    
    @pytest.mark.asyncio
    async def test_retrieve_nonexistent_context(self, context_store):
        """Test retrieval of non-existent context raises appropriate error"""
        # Action & Assertion
        with pytest.raises(ContextNotFoundError) as exc_info:
            await context_store.get_context(
                customer_id="nonexistent_customer",
                channel="email"
            )
        
        assert "nonexistent_customer" in str(exc_info.value)
        assert "email" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_update_context_entry(self, context_store, sample_context_entry):
        """Test updating an existing context entry"""
        # Setup
        store_result = await context_store.store_context(sample_context_entry)
        entry_id = store_result.entry_id
        
        # Action
        updates = {
            "content": "Updated board meeting preparation with financial projections",
            "metadata": {
                "tone": "formal_professional",
                "urgency": "critical",
                "stakeholders": ["board", "investors", "analysts"]
            }
        }
        
        update_result = await context_store.update_context(entry_id, updates)
        
        # Retrieve updated context
        updated_context = await context_store.get_context(
            customer_id="test_customer_001",
            channel="email"
        )
        
        # Assertions
        assert update_result.success is True
        assert updated_context.content == "Updated board meeting preparation with financial projections"
        assert updated_context.metadata["urgency"] == "critical"
        assert "analysts" in updated_context.metadata["stakeholders"]
    
    @pytest.mark.asyncio
    async def test_get_conversation_thread(self, context_store):
        """Test retrieval of complete conversation thread across channels"""
        # Setup: Create multiple context entries for same thread
        thread_id = "product_launch_discussion"
        contexts = [
            ContextEntry(
                customer_id="test_customer_001",
                channel="email",
                conversation_thread=thread_id,
                timestamp=datetime.now() - timedelta(hours=2),
                content="Let's discuss the product launch timeline."
            ),
            ContextEntry(
                customer_id="test_customer_001",
                channel="whatsapp",
                conversation_thread=thread_id,
                timestamp=datetime.now() - timedelta(hours=1),
                content="sounds good! what's our target date?"
            ),
            ContextEntry(
                customer_id="test_customer_001",
                channel="voice",
                conversation_thread=thread_id,
                timestamp=datetime.now(),
                content="I think we should aim for end of Q4 to capture holiday sales"
            )
        ]
        
        # Store all contexts
        for context in contexts:
            await context_store.store_context(context)
        
        # Action
        start_time = time.time()
        conversation_thread = await context_store.get_conversation_thread(
            customer_id="test_customer_001",
            thread_id=thread_id
        )
        retrieval_time = (time.time() - start_time) * 1000
        
        # Assertions
        assert retrieval_time < 500
        assert conversation_thread.thread_id == thread_id
        assert len(conversation_thread.entries) == 3
        assert conversation_thread.channels == ["email", "whatsapp", "voice"]
        
        # Verify chronological ordering
        assert conversation_thread.entries[0].channel == "email"
        assert conversation_thread.entries[1].channel == "whatsapp"
        assert conversation_thread.entries[2].channel == "voice"
    
    @pytest.mark.asyncio
    async def test_customer_context_aggregation(self, context_store):
        """Test aggregation of all context for a customer across channels"""
        customer_id = "test_customer_002"
        
        # Setup: Create contexts across multiple channels and threads
        contexts = [
            ContextEntry(
                customer_id=customer_id,
                channel="email",
                conversation_thread="quarterly_review",
                content="Quarterly business review preparation"
            ),
            ContextEntry(
                customer_id=customer_id,
                channel="whatsapp",
                conversation_thread="team_updates",
                content="Daily team standup discussion"
            ),
            ContextEntry(
                customer_id=customer_id,
                channel="voice",
                conversation_thread="strategy_session",
                content="Long-term strategic planning discussion"
            )
        ]
        
        for context in contexts:
            await context_store.store_context(context)
        
        # Action
        start_time = time.time()
        customer_context = await context_store.get_customer_context(customer_id)
        aggregation_time = (time.time() - start_time) * 1000
        
        # Assertions
        assert aggregation_time < 500
        assert customer_context.customer_id == customer_id
        assert len(customer_context.active_threads) == 3
        assert customer_context.channels_used == ["email", "whatsapp", "voice"]
        assert "quarterly_review" in customer_context.active_threads
        assert "team_updates" in customer_context.active_threads
        assert "strategy_session" in customer_context.active_threads
    
    @pytest.mark.asyncio
    async def test_context_search_by_content(self, context_store):
        """Test searching contexts by content keywords"""
        # Setup: Store contexts with searchable content
        contexts = [
            ContextEntry(
                customer_id="test_customer_003",
                channel="email",
                conversation_thread="marketing_campaign",
                content="Need to analyze marketing campaign performance and ROI metrics"
            ),
            ContextEntry(
                customer_id="test_customer_003",
                channel="whatsapp",
                conversation_thread="budget_review",
                content="Budget allocation for marketing initiatives next quarter"
            ),
            ContextEntry(
                customer_id="test_customer_003",
                channel="voice",
                conversation_thread="team_meeting",
                content="Team coordination and project status updates"
            )
        ]
        
        for context in contexts:
            await context_store.store_context(context)
        
        # Action: Search for marketing-related contexts
        start_time = time.time()
        search_results = await context_store.search_contexts(
            customer_id="test_customer_003",
            query="marketing",
            limit=10
        )
        search_time = (time.time() - start_time) * 1000
        
        # Assertions
        assert search_time < 500
        assert len(search_results) == 2
        
        # Verify marketing contexts found
        marketing_contexts = [r for r in search_results if "marketing" in r.content.lower()]
        assert len(marketing_contexts) == 2
        
        # Verify relevance scoring
        assert all(result.relevance_score > 0.5 for result in search_results)
    
    @pytest.mark.asyncio
    async def test_context_expiration_and_cleanup(self, context_store):
        """Test automatic cleanup of expired contexts"""
        # Setup: Create contexts with different ages
        old_context = ContextEntry(
            customer_id="test_customer_004",
            channel="email",
            conversation_thread="old_discussion",
            timestamp=datetime.now() - timedelta(days=90),  # 90 days old
            content="Old conversation that should be archived"
        )
        
        recent_context = ContextEntry(
            customer_id="test_customer_004",
            channel="email", 
            conversation_thread="recent_discussion",
            timestamp=datetime.now() - timedelta(days=1),  # 1 day old
            content="Recent conversation that should remain active"
        )
        
        await context_store.store_context(old_context)
        await context_store.store_context(recent_context)
        
        # Action: Run cleanup with 30-day retention policy
        cleanup_result = await context_store.cleanup_expired_contexts(
            retention_days=30
        )
        
        # Verify old context archived
        with pytest.raises(ContextNotFoundError):
            await context_store.get_context(
                customer_id="test_customer_004",
                channel="email",
                thread_id="old_discussion"
            )
        
        # Verify recent context still available
        recent_retrieved = await context_store.get_context(
            customer_id="test_customer_004",
            channel="email",
            thread_id="recent_discussion"
        )
        
        # Assertions
        assert cleanup_result.contexts_archived > 0
        assert recent_retrieved.content == "Recent conversation that should remain active"


class TestContextEntry:
    """Test suite for ContextEntry data model"""
    
    def test_context_entry_creation(self):
        """Test ContextEntry creation with required fields"""
        entry = ContextEntry(
            customer_id="test_customer",
            channel="email",
            conversation_thread="test_thread",
            timestamp=datetime.now(),
            content="Test content"
        )
        
        assert entry.customer_id == "test_customer"
        assert entry.channel == "email"
        assert entry.conversation_thread == "test_thread"
        assert entry.content == "Test content"
        assert entry.metadata == {}
    
    def test_context_entry_with_metadata(self):
        """Test ContextEntry creation with metadata"""
        metadata = {
            "tone": "professional",
            "urgency": "high",
            "participants": ["user", "assistant"]
        }
        
        entry = ContextEntry(
            customer_id="test_customer",
            channel="whatsapp",
            conversation_thread="test_thread",
            timestamp=datetime.now(),
            content="Test content with metadata",
            metadata=metadata
        )
        
        assert entry.metadata["tone"] == "professional"
        assert entry.metadata["urgency"] == "high"
        assert "user" in entry.metadata["participants"]
    
    def test_context_entry_serialization(self):
        """Test ContextEntry serialization to dictionary"""
        entry = ContextEntry(
            customer_id="test_customer",
            channel="voice",
            conversation_thread="test_thread", 
            timestamp=datetime.now(),
            content="Test content for serialization",
            metadata={"emotion": "excited"}
        )
        
        serialized = entry.to_dict()
        
        assert serialized["customer_id"] == "test_customer"
        assert serialized["channel"] == "voice"
        assert serialized["content"] == "Test content for serialization"
        assert serialized["metadata"]["emotion"] == "excited"
        assert "timestamp" in serialized
    
    def test_context_entry_deserialization(self):
        """Test ContextEntry creation from dictionary"""
        data = {
            "customer_id": "test_customer",
            "channel": "email",
            "conversation_thread": "test_thread",
            "timestamp": datetime.now().isoformat(),
            "content": "Deserialized content",
            "metadata": {"tone": "casual"}
        }
        
        entry = ContextEntry.from_dict(data)
        
        assert entry.customer_id == "test_customer"
        assert entry.channel == "email"
        assert entry.content == "Deserialized content"
        assert entry.metadata["tone"] == "casual"


class TestConversationThread:
    """Test suite for ConversationThread data model"""
    
    def test_conversation_thread_creation(self):
        """Test ConversationThread creation and management"""
        entries = [
            ContextEntry(
                customer_id="test_customer",
                channel="email",
                conversation_thread="test_thread",
                timestamp=datetime.now() - timedelta(hours=2),
                content="First message"
            ),
            ContextEntry(
                customer_id="test_customer",
                channel="whatsapp",
                conversation_thread="test_thread",
                timestamp=datetime.now() - timedelta(hours=1),
                content="Second message"
            )
        ]
        
        thread = ConversationThread(
            thread_id="test_thread",
            customer_id="test_customer",
            entries=entries
        )
        
        assert thread.thread_id == "test_thread"
        assert thread.customer_id == "test_customer"
        assert len(thread.entries) == 2
        assert thread.channels == ["email", "whatsapp"]
    
    def test_conversation_thread_chronological_ordering(self):
        """Test that conversation thread maintains chronological order"""
        # Create entries in non-chronological order
        entries = [
            ContextEntry(
                customer_id="test_customer",
                channel="whatsapp",
                conversation_thread="test_thread",
                timestamp=datetime.now() - timedelta(hours=1),
                content="Second message"
            ),
            ContextEntry(
                customer_id="test_customer",
                channel="email",
                conversation_thread="test_thread",
                timestamp=datetime.now() - timedelta(hours=2),
                content="First message"
            ),
            ContextEntry(
                customer_id="test_customer",
                channel="voice",
                conversation_thread="test_thread",
                timestamp=datetime.now(),
                content="Third message"
            )
        ]
        
        thread = ConversationThread(
            thread_id="test_thread",
            customer_id="test_customer",
            entries=entries
        )
        
        # Verify chronological ordering
        ordered_entries = thread.get_chronological_entries()
        assert ordered_entries[0].content == "First message"
        assert ordered_entries[1].content == "Second message"
        assert ordered_entries[2].content == "Third message"
    
    def test_conversation_thread_summary_generation(self):
        """Test conversation thread summary generation"""
        entries = [
            ContextEntry(
                customer_id="test_customer",
                channel="email",
                conversation_thread="product_planning",
                timestamp=datetime.now() - timedelta(hours=2),
                content="We need to finalize the product roadmap for Q4"
            ),
            ContextEntry(
                customer_id="test_customer",
                channel="whatsapp",
                conversation_thread="product_planning",
                timestamp=datetime.now() - timedelta(hours=1),
                content="agreed! what about the mobile app features?"
            ),
            ContextEntry(
                customer_id="test_customer",
                channel="voice",
                conversation_thread="product_planning",
                timestamp=datetime.now(),
                content="Mobile app should focus on core functionality first, then we can add advanced features"
            )
        ]
        
        thread = ConversationThread(
            thread_id="product_planning",
            customer_id="test_customer",
            entries=entries
        )
        
        summary = thread.generate_summary()
        
        assert "product roadmap" in summary.lower()
        assert "mobile app" in summary.lower()
        assert "Q4" in summary
        assert summary.word_count <= 50  # Summary should be concise


class TestPerformanceBenchmarks:
    """Performance benchmarks for context store operations"""
    
    @pytest.mark.asyncio
    async def test_bulk_context_storage_performance(self, context_store):
        """Test performance of bulk context storage operations"""
        # Setup: Generate 1000 context entries
        contexts = []
        for i in range(1000):
            context = ContextEntry(
                customer_id=f"perf_test_customer_{i % 10}",  # 10 customers
                channel=["email", "whatsapp", "voice"][i % 3],  # Rotate channels
                conversation_thread=f"thread_{i}",
                timestamp=datetime.now() - timedelta(minutes=i),
                content=f"Performance test message {i}"
            )
            contexts.append(context)
        
        # Action: Bulk storage
        start_time = time.time()
        results = await context_store.bulk_store_contexts(contexts)
        bulk_storage_time = (time.time() - start_time) * 1000
        
        # Assertions
        assert bulk_storage_time < 5000, f"Bulk storage took {bulk_storage_time}ms, exceeds 5s threshold"
        assert len(results.successful) == 1000
        assert len(results.failed) == 0
        assert results.average_storage_time_ms < 10
    
    @pytest.mark.asyncio
    async def test_concurrent_context_retrieval_performance(self, context_store):
        """Test performance under concurrent retrieval load"""
        # Setup: Store contexts for multiple customers
        customers = [f"concurrent_customer_{i}" for i in range(50)]
        for customer_id in customers:
            context = ContextEntry(
                customer_id=customer_id,
                channel="email",
                conversation_thread="concurrent_test",
                timestamp=datetime.now(),
                content=f"Concurrent test content for {customer_id}"
            )
            await context_store.store_context(context)
        
        # Action: Concurrent retrieval
        start_time = time.time()
        tasks = []
        for customer_id in customers:
            task = context_store.get_context(
                customer_id=customer_id,
                channel="email"
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        concurrent_retrieval_time = (time.time() - start_time) * 1000
        
        # Assertions
        assert concurrent_retrieval_time < 2000, f"Concurrent retrieval took {concurrent_retrieval_time}ms, exceeds 2s threshold"
        assert len([r for r in results if not isinstance(r, Exception)]) == 50
        
        # Verify all retrievals successful
        for i, result in enumerate(results):
            if not isinstance(result, Exception):
                assert result.customer_id == customers[i]