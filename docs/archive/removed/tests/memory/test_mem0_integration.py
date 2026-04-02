"""
Test-Driven Development for Mem0 Memory Layer Integration
Tests per-customer isolation, performance, and business memory operations
"""

import os
import pytest
import asyncio
import json
import uuid
import time
from datetime import datetime
from typing import Dict, List, Any

# mem0_manager hard-imports mem0, asyncpg, redis at module level.
pytest.importorskip("mem0")
pytest.importorskip("asyncpg")

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="requires live mem0/Redis/Postgres; set RUN_INTEGRATION_TESTS=1",
)

from src.memory.mem0_manager import EAMemoryManager, OptimizedMemoryRouter, maintain_conversation_continuity
from src.memory.isolation_validator import MemoryIsolationValidator
from src.memory.performance_monitor import MemoryPerformanceMonitor


class TestMem0Integration:
    """Test suite for Mem0 memory layer integration"""
    
    @pytest.fixture
    async def customer_memory_manager(self):
        """Create isolated customer memory manager for testing"""
        customer_id = f"test_customer_{uuid.uuid4().hex[:8]}"
        manager = EAMemoryManager(customer_id)
        
        yield manager
        
        # Cleanup test data
        await manager.cleanup_test_data()
    
    @pytest.fixture
    async def two_customer_managers(self):
        """Create two isolated customer memory managers"""
        customer_a = f"test_customer_a_{uuid.uuid4().hex[:8]}"
        customer_b = f"test_customer_b_{uuid.uuid4().hex[:8]}"
        
        manager_a = EAMemoryManager(customer_a)
        manager_b = EAMemoryManager(customer_b)
        
        yield manager_a, manager_b
        
        # Cleanup
        await manager_a.cleanup_test_data()
        await manager_b.cleanup_test_data()


class TestMemoryIsolation:
    """Test per-customer memory isolation requirements"""
    
    @pytest.mark.asyncio
    async def test_customer_isolation_boundary(self, two_customer_managers):
        """Test that customers cannot access each other's memories"""
        manager_a, manager_b = two_customer_managers
        
        # Store sensitive business data in customer A
        secret_data = {
            "business_description": f"Secret business process {uuid.uuid4()}",
            "revenue": "$1M annually",
            "competitive_advantage": "Proprietary algorithm"
        }
        
        result_a = await manager_a.store_business_context(
            context=secret_data,
            session_id=f"isolation_test_{uuid.uuid4().hex}"
        )
        
        assert result_a is not None, "Failed to store data in customer A memory"
        
        # Attempt to access customer A's data from customer B
        search_results_b = await manager_b.retrieve_business_context(
            query="Secret business process revenue algorithm",
            limit=10
        )
        
        # Critical assertion: Customer B should not see customer A's data
        assert len(search_results_b) == 0, \
            "CRITICAL FAILURE: Cross-customer memory access detected"
        
        # Verify customer A can access their own data
        search_results_a = await manager_a.retrieve_business_context(
            query="Secret business process",
            limit=10
        )
        
        assert len(search_results_a) > 0, \
            "Customer A cannot access their own memory"
        
        # Verify the retrieved data contains expected content
        found_secret = any(
            secret_data["business_description"] in memory["memory"] 
            for memory in search_results_a
        )
        assert found_secret, "Customer A's stored data not properly retrieved"
    
    @pytest.mark.asyncio
    async def test_agent_id_isolation(self, customer_memory_manager):
        """Test agent ID isolation within same customer"""
        # Create memories with different agent IDs for same customer
        ea_memory = await customer_memory_manager.store_business_context(
            context={"source": "EA", "data": "EA specific context"},
            session_id="ea_session"
        )
        
        # Simulate specialist agent memory (Phase 2)
        specialist_context = {
            "content": "Specialist agent context",
            "metadata": {
                "type": "specialist_context",
                "agent_type": "social_media_specialist"
            }
        }
        
        # Store with different agent_id
        specialist_result = customer_memory_manager.mem0_client.add(
            messages=[{"role": "assistant", "content": json.dumps(specialist_context)}],
            user_id=customer_memory_manager.user_id,
            agent_id=f"specialist_{customer_memory_manager.customer_id}",
            metadata=specialist_context["metadata"]
        )
        
        # Verify EA can access customer context but specialist context is isolated
        ea_results = await customer_memory_manager.retrieve_business_context(
            query="EA specific",
            limit=5
        )
        
        assert len(ea_results) > 0, "EA cannot access its own context"
        
        # Verify proper agent isolation in Phase 2 preparation
        all_customer_memories = customer_memory_manager.mem0_client.get_all(
            user_id=customer_memory_manager.user_id
        )
        
        ea_memories = [m for m in all_customer_memories.get("results", []) 
                      if m.get("agent_id") == customer_memory_manager.agent_id]
        specialist_memories = [m for m in all_customer_memories.get("results", [])
                             if m.get("agent_id") == f"specialist_{customer_memory_manager.customer_id}"]
        
        assert len(ea_memories) > 0, "EA memories not properly stored"
        assert len(specialist_memories) > 0, "Specialist memories not properly stored"


class TestBusinessMemoryOperations:
    """Test EA business learning and memory operations"""
    
    @pytest.mark.asyncio
    async def test_business_discovery_storage(self, customer_memory_manager):
        """Test storing and retrieving business discovery insights"""
        # Simulate business discovery conversation
        discovery_context = {
            "business_description": "E-commerce platform selling handmade jewelry",
            "phase": "discovery",
            "automation_opportunities": [
                "Social media posting automation",
                "Customer follow-up emails",
                "Inventory management alerts"
            ],
            "pain_points": [
                "Manual order processing",
                "Social media content creation",
                "Customer support response time"
            ]
        }
        
        # Store business context
        result = await customer_memory_manager.store_business_context(
            context=discovery_context,
            session_id="discovery_test"
        )
        
        assert result is not None, "Failed to store business discovery context"
        
        # Test semantic retrieval of business insights
        test_queries = [
            "automation opportunities for jewelry business",
            "e-commerce pain points manual processing",
            "social media content creation challenges"
        ]
        
        for query in test_queries:
            results = await customer_memory_manager.retrieve_business_context(
                query=query,
                limit=5
            )
            
            assert len(results) > 0, f"No results for query: {query}"
            
            # Verify semantic understanding
            relevant_found = any(
                any(keyword in memory["memory"].lower() 
                    for keyword in query.split())
                for memory in results
            )
            assert relevant_found, f"Semantic search failed for: {query}"
    
    @pytest.mark.asyncio
    async def test_workflow_memory_integration(self, customer_memory_manager):
        """Test storing and retrieving workflow creation memories"""
        # Simulate workflow creation during discovery call
        workflow_config = {
            "template_id": "social_media_automation",
            "customizations": {
                "platforms": ["Instagram", "Facebook"],
                "posting_schedule": "daily_at_9am",
                "content_types": ["product_photos", "behind_the_scenes"]
            },
            "deployment_status": "active",
            "performance_metrics": {
                "created_at": datetime.utcnow().isoformat(),
                "posts_scheduled": 0,
                "engagement_rate": 0.0
            }
        }
        
        result = await customer_memory_manager.store_workflow_memory(
            workflow_config=workflow_config,
            template_id="social_media_automation"
        )
        
        assert result is not None, "Failed to store workflow memory"
        
        # Test retrieval of workflow memories
        workflow_results = customer_memory_manager.mem0_client.search(
            query="social media automation workflow Instagram",
            user_id=customer_memory_manager.user_id,
            agent_id=customer_memory_manager.agent_id,
            filters={"type": "workflow_memory"}
        )
        
        assert len(workflow_results.get("results", [])) > 0, \
            "Workflow memory not properly retrieved"
        
        # Verify workflow details are preserved
        workflow_memory = workflow_results["results"][0]
        stored_config = json.loads(workflow_memory["memory"])
        
        assert stored_config["template_id"] == "social_media_automation", \
            "Workflow template ID not preserved"
    
    @pytest.mark.asyncio
    async def test_conversation_continuity(self, customer_memory_manager):
        """Test cross-channel conversation continuity"""
        # Simulate conversation across different channels
        phone_conversation = [
            {"role": "user", "content": "I need help setting up automation for my business"},
            {"role": "assistant", "content": "I'd love to help! Tell me about your business."},
            {"role": "user", "content": "I run a jewelry store and spend too much time on social media"}
        ]
        
        # Store phone conversation
        phone_result = customer_memory_manager.mem0_client.add(
            messages=phone_conversation,
            user_id=customer_memory_manager.user_id,
            agent_id=customer_memory_manager.agent_id,
            metadata={"channel": "phone", "session_type": "initial_discovery"}
        )
        
        # Simulate WhatsApp follow-up
        whatsapp_message = {
            "role": "user",
            "content": "Following up on our call - can you create that social media automation we discussed?"
        }
        
        # Test continuity retrieval
        continuity_result = await maintain_conversation_continuity(
            ea_memory=customer_memory_manager,
            channel="whatsapp",
            message=whatsapp_message["content"],
            user_context={"previous_channel": "phone"}
        )
        
        assert continuity_result["context_memories"], \
            "Failed to retrieve conversation context"
        
        # Verify phone context is available in WhatsApp interaction
        context_content = " ".join([
            m["memory"] for m in continuity_result["context_memories"]
        ])
        
        assert "jewelry store" in context_content.lower(), \
            "Cross-channel context not maintained"


class TestPerformanceRequirements:
    """Test memory performance against Phase 1 SLA requirements"""
    
    @pytest.mark.asyncio
    async def test_memory_recall_latency(self, customer_memory_manager):
        """Test <500ms memory recall requirement"""
        # Store test business context
        test_context = {
            "business_description": "Performance test business context",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await customer_memory_manager.store_business_context(
            context=test_context,
            session_id="performance_test"
        )
        
        # Test retrieval performance
        start_time = time.time()
        results = await customer_memory_manager.retrieve_business_context(
            query="Performance test business",
            limit=5
        )
        retrieval_time = time.time() - start_time
        
        assert retrieval_time < 0.5, \
            f"Memory retrieval exceeded 500ms SLA: {retrieval_time:.3f}s"
        
        assert len(results) > 0, "Performance test failed to retrieve data"
    
    @pytest.mark.asyncio
    async def test_concurrent_memory_operations(self, customer_memory_manager):
        """Test memory performance under concurrent load"""
        # Create multiple concurrent memory operations
        async def concurrent_operation(session_id: str):
            context = {
                "business_description": f"Concurrent test business {session_id}",
                "session_id": session_id
            }
            
            start_time = time.time()
            await customer_memory_manager.store_business_context(
                context=context,
                session_id=session_id
            )
            return time.time() - start_time
        
        # Run 10 concurrent operations
        tasks = [
            concurrent_operation(f"concurrent_{i}")
            for i in range(10)
        ]
        
        execution_times = await asyncio.gather(*tasks)
        
        # Verify all operations completed within SLA
        max_time = max(execution_times)
        avg_time = sum(execution_times) / len(execution_times)
        
        assert max_time < 1.0, \
            f"Concurrent operations exceeded 1s limit: {max_time:.3f}s"
        
        assert avg_time < 0.5, \
            f"Average concurrent operation time exceeded 500ms: {avg_time:.3f}s"
    
    @pytest.mark.asyncio
    async def test_memory_router_optimization(self, customer_memory_manager):
        """Test optimized memory routing for different query types"""
        router = OptimizedMemoryRouter(customer_memory_manager)
        
        # Test immediate context retrieval (should use Redis)
        start_time = time.time()
        immediate_result = await router.intelligent_memory_retrieval(
            query="current_session_context",
            query_type="immediate_context"
        )
        immediate_time = time.time() - start_time
        
        assert immediate_time < 0.01, \
            f"Immediate context retrieval too slow: {immediate_time:.3f}s"
        
        # Test semantic business knowledge (should use Mem0)
        start_time = time.time()
        semantic_result = await router.intelligent_memory_retrieval(
            query="business automation opportunities",
            query_type="business_knowledge"
        )
        semantic_time = time.time() - start_time
        
        assert semantic_time < 0.5, \
            f"Semantic retrieval exceeded SLA: {semantic_time:.3f}s"


class TestScalabilityRequirements:
    """Test system scalability for multiple customers"""
    
    @pytest.mark.asyncio
    async def test_multiple_customer_isolation(self):
        """Test isolation with multiple concurrent customers"""
        num_customers = 50  # Phase 1 target: 100+ customers
        customer_managers = []
        
        try:
            # Create multiple customer memory managers
            for i in range(num_customers):
                customer_id = f"scale_test_customer_{i}_{uuid.uuid4().hex[:6]}"
                manager = EAMemoryManager(customer_id)
                customer_managers.append(manager)
                
                # Store unique data per customer
                await manager.store_business_context(
                    context={
                        "business_description": f"Unique business {i}",
                        "customer_id": customer_id,
                        "test_data": f"secret_data_{uuid.uuid4()}"
                    },
                    session_id=f"scale_test_{i}"
                )
            
            # Verify each customer can only access their own data
            validation_results = []
            for i, manager in enumerate(customer_managers):
                results = await manager.retrieve_business_context(
                    query=f"Unique business {i}",
                    limit=10
                )
                
                # Should find own data
                own_data_found = any(
                    f"Unique business {i}" in memory["memory"]
                    for memory in results
                )
                
                # Should not find other customers' data
                other_data_found = any(
                    any(f"Unique business {j}" in memory["memory"] for j in range(num_customers) if j != i)
                    for memory in results
                )
                
                validation_results.append({
                    "customer": i,
                    "own_data_found": own_data_found,
                    "other_data_found": other_data_found
                })
            
            # Assert all validations passed
            for result in validation_results:
                assert result["own_data_found"], \
                    f"Customer {result['customer']} cannot access own data"
                assert not result["other_data_found"], \
                    f"Customer {result['customer']} can access other customer data"
                    
        finally:
            # Cleanup all test customers
            for manager in customer_managers:
                await manager.cleanup_test_data()


class TestFailureRecoveryScenarios:
    """Test memory system resilience and recovery"""
    
    @pytest.mark.asyncio
    async def test_mem0_fallback_to_redis(self, customer_memory_manager):
        """Test fallback to Redis when Mem0 is unavailable"""
        # Store context in Redis fallback
        fallback_context = {
            "business_description": "Fallback test business",
            "stored_in": "redis_fallback"
        }
        
        # Simulate Mem0 unavailability by using Redis directly
        customer_memory_manager.redis_client.setex(
            "fallback:business_context",
            3600,
            json.dumps(fallback_context)
        )
        
        # Test retrieval from Redis fallback
        router = OptimizedMemoryRouter(customer_memory_manager)
        result = await router._redis_retrieval("fallback:business_context")
        
        assert result is not None, "Redis fallback retrieval failed"
        assert result["stored_in"] == "redis_fallback", "Incorrect fallback data"
    
    @pytest.mark.asyncio
    async def test_memory_consistency_validation(self, customer_memory_manager):
        """Test memory consistency across storage layers"""
        # Store same context in multiple layers
        test_context = {
            "business_description": "Consistency test business",
            "validation_id": str(uuid.uuid4())
        }
        
        # Store in Mem0
        mem0_result = await customer_memory_manager.store_business_context(
            context=test_context,
            session_id="consistency_test"
        )
        
        # Store in Redis
        customer_memory_manager.redis_client.setex(
            f"consistency:{test_context['validation_id']}",
            3600,
            json.dumps(test_context)
        )
        
        # Verify consistency
        mem0_results = await customer_memory_manager.retrieve_business_context(
            query="Consistency test business"
        )
        
        redis_result = json.loads(
            customer_memory_manager.redis_client.get(
                f"consistency:{test_context['validation_id']}"
            )
        )
        
        assert len(mem0_results) > 0, "Mem0 consistency check failed"
        assert redis_result["validation_id"] == test_context["validation_id"], \
            "Redis consistency check failed"


if __name__ == "__main__":
    # Run specific test categories
    pytest.main([
        "-v",
        "--tb=short",
        "tests/memory/test_mem0_integration.py",
        "-k", "test_customer_isolation_boundary or test_memory_recall_latency"
    ])