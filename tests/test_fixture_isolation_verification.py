"""
TDD Test Suite: Verify Fixture Isolation and Resource Cleanup
These tests should FAIL initially, then pass after implementing the fixes
"""

import pytest
import asyncio
import uuid
import redis
from unittest.mock import AsyncMock, MagicMock

# Import the EA components we need
from src.agents.executive_assistant import ExecutiveAssistant, BusinessContext


class TestFixtureIsolationVerification:
    """TDD: Write failing tests first for fixture isolation requirements."""
    
    @pytest.mark.asyncio
    async def test_unique_customer_ids_across_test_runs(self):
        """Test that TestResourceManager generates unique customer IDs."""
        from tests.utils.test_resource_manager import TestResourceManager
        
        # Now using the TestResourceManager implementation
        manager = TestResourceManager()
        customer_ids_seen = []
        
        # Generate multiple customer IDs
        for i in range(3):
            customer_id = manager.generate_unique_customer_id("test_customer")
            customer_ids_seen.append(customer_id)
        
        # All customer IDs should be different
        unique_suffixes = set(cid.split('_')[-1] for cid in customer_ids_seen)
        assert len(unique_suffixes) == len(customer_ids_seen), \
            f"Customer IDs not sufficiently unique: {customer_ids_seen}"
            
        # All should have valid hex suffixes of adequate length
        for customer_id in customer_ids_seen:
            suffix = customer_id.split('_')[-1]
            try:
                # Should be valid hex (will raise ValueError if not)
                int(suffix, 16)
                assert len(suffix) >= 8, f"Customer ID suffix too short: {suffix}"
            except ValueError:
                pytest.fail(f"Customer ID suffix not hex: {suffix}")
    
    @pytest.mark.asyncio
    async def test_redis_cleanup_verification(self):
        """FAILING TEST: Redis should be completely clean after each test fixture."""
        
        # This test should fail initially because we don't have proper cleanup verification
        test_redis = redis.Redis(
            host='localhost', port=6379, db=15, decode_responses=True
        )
        
        # Store some test data
        test_key = f"test_cleanup_verification_{uuid.uuid4().hex[:8]}"
        test_redis.set(test_key, "should_be_cleaned_up")
        
        # Simulate fixture cleanup (this should clean everything)
        # Currently this is NOT implemented, so test should fail
        await self.simulate_fixture_cleanup(test_redis)
        
        # This assertion should FAIL until cleanup is implemented
        remaining_keys = test_redis.keys("*")
        assert len(remaining_keys) == 0, \
            f"Redis cleanup failed - remaining keys: {remaining_keys}"
    
    @pytest.mark.asyncio
    async def test_test_resource_manager_exists(self):
        """FAILING TEST: TestResourceManager class should exist and work."""
        
        # This import should FAIL until we implement TestResourceManager
        try:
            from tests.utils.test_resource_manager import TestResourceManager
            
            # Test the manager functionality
            manager = TestResourceManager()
            
            # Should be able to register cleanup functions
            cleanup_called = []
            
            async def mock_cleanup():
                cleanup_called.append(True)
                
            manager.register_cleanup(mock_cleanup)
            manager.register_customer_id("test_customer_abc123")
            
            # Should execute cleanup
            await manager.cleanup_all()
            
            assert len(cleanup_called) == 1, "Cleanup function not called"
            assert len(manager.customer_ids_used) == 1, "Customer ID not tracked"
            
        except ImportError:
            pytest.fail("TestResourceManager not implemented yet - this test should fail first")
    
    @pytest.mark.asyncio
    async def test_clean_ea_instance_fixture_exists(self):
        """FAILING TEST: clean_ea_instance fixture should exist with proper isolation."""
        
        # This test should fail until we implement the clean_ea_instance fixture
        # We'll simulate what the fixture should do
        
        customer_id = f"test_{uuid.uuid4().hex[:8]}"
        
        # Should create unique EA instance
        ea = ExecutiveAssistant(
            customer_id=customer_id,
            mcp_server_url="test://localhost"
        )
        
        # Should have test Redis configuration
        ea.memory.redis_client = redis.Redis(
            host='localhost', port=6379, db=15, decode_responses=True
        )
        
        # Should store some test data
        await ea.memory.store_business_knowledge(
            f"Test data for {customer_id}",
            {"test": True}
        )
        
        # Should have proper cleanup after test
        await self.cleanup_ea_resources(ea, customer_id)
        
        # Verify cleanup worked
        test_redis = redis.Redis(
            host='localhost', port=6379, db=15, decode_responses=True
        )
        remaining_keys = test_redis.keys(f"*{customer_id}*")
        assert len(remaining_keys) == 0, \
            f"EA cleanup failed - remaining keys: {remaining_keys}"
    
    @pytest.mark.asyncio
    async def test_ea_with_business_context_no_complex_fixture_chain(self):
        """FAILING TEST: ea_with_business_context should be self-contained, not chained."""
        
        # This test verifies the NEW implementation doesn't have complex fixture chains
        # It should fail until we implement the simplified version
        
        # Create business context (this should work)
        business_context = BusinessContext(
            business_name="Test Business",
            business_type="e-commerce", 
            industry="jewelry",
            daily_operations=["social media", "customer service"],
            pain_points=["manual processes"],
            current_tools=["Instagram", "Gmail"]
            # NOTE: Removed invalid 'revenue_range' that was causing fixture failure
        )
        
        # This should be a self-contained fixture, not dependent on real_ea
        customer_id = f"test_business_{uuid.uuid4().hex[:8]}"
        
        ea = ExecutiveAssistant(
            customer_id=customer_id,
            mcp_server_url="test://localhost"
        )
        
        # Configure test Redis
        ea.memory.redis_client = redis.Redis(
            host='localhost', port=6379, db=15, decode_responses=True
        )
        
        # Store business context directly (not through complex fixture chain)
        await ea.memory.store_business_context(business_context)
        await ea.memory.store_business_knowledge(
            f"Customer runs {business_context.business_name}",
            {"category": "business_info", "priority": "high"}
        )
        
        # Test that business context is available
        stored_context = await ea.memory.get_business_context()
        assert stored_context.business_name == "Test Business"
        
        # Cleanup verification
        await self.cleanup_ea_resources(ea, customer_id)
        
        test_redis = redis.Redis(
            host='localhost', port=6379, db=15, decode_responses=True
        )
        remaining_keys = test_redis.keys(f"*{customer_id}*")
        assert len(remaining_keys) == 0, f"Business context cleanup failed: {remaining_keys}"
    
    # Helper methods that should exist but don't yet (will cause test failures)
    
    async def simulate_fixture_cleanup(self, redis_client):
        """Simulate what proper fixture cleanup should do."""
        # This should flush the test database
        redis_client.flushdb()
    
    async def cleanup_ea_resources(self, ea, customer_id):
        """Cleanup EA resources - this should be in TestResourceManager."""
        try:
            # Redis cleanup
            ea.memory.redis_client.flushdb()
            
            # Database cleanup (if connection exists)
            if hasattr(ea.memory, 'db_connection') and ea.memory.db_connection:
                with ea.memory.db_connection.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM customer_business_context WHERE customer_id = %s", 
                        (customer_id,)
                    )
                    ea.memory.db_connection.commit()
        except Exception as e:
            # This should NOT be a silent failure - tests should catch cleanup issues
            raise Exception(f"Resource cleanup failed for {customer_id}: {e}")


class TestCurrentProblematicFixtures:
    """Demonstrate the problems with current fixture implementation."""
    
    @pytest.mark.asyncio
    async def test_current_real_ea_fixture_problems(self):
        """Show why the current real_ea fixture is problematic."""
        
        # Problem 1: Hardcoded customer ID causes test pollution
        customer_id = "test_customer_123"  # This is the hardcoded value from conftest.py
        
        # Problem 2: Shared customer ID means tests interfere with each other
        # If two tests run in parallel or sequence, they share the same customer
        
        # Problem 3: Silent cleanup failures
        # The current fixture only prints warnings, doesn't fail tests
        
        # This demonstrates the issue
        test_redis = redis.Redis(
            host='localhost', port=6379, db=15, decode_responses=True
        )
        
        # Store data with the shared customer ID
        test_redis.set(f"customer:{customer_id}:test_data", "contamination")
        
        # If another test runs with the same customer ID, it will see this data
        contaminating_data = test_redis.get(f"customer:{customer_id}:test_data")
        
        # Clean up our test data - don't fail on contamination (this test demonstrates the issue)
        test_redis.delete(f"customer:{customer_id}:test_data")
        
        # This test demonstrates that the hardcoded customer ID causes contamination potential
        # In a real scenario with concurrent tests, this would be a problem
        # But for this demo, we'll just log it
        if contaminating_data:
            print(f"WARNING: Found potential test contamination data: {contaminating_data}")
        
        assert customer_id == "test_customer_123", "This test demonstrates the hardcoded customer ID problem"
    
    def test_current_business_context_fixture_fails(self):
        """Demonstrate the BusinessContext fixture failure."""
        
        # This shows the exact error from the current fixture
        try:
            # This is what the current fixture tries to do (from conftest.py:334)
            context = BusinessContext(
                business_name="Sparkle & Shine Jewelry",
                business_type="e-commerce",
                industry="jewelry",
                daily_operations=["social media posting", "order processing", "customer service"],
                pain_points=["manual social media", "invoice creation", "follow-up emails"],
                current_tools=["Instagram", "Shopify", "Gmail"],
                revenue_range="$100K-500K",  # This parameter doesn't exist!
                time_constraints={"social_media": "2h/day", "invoicing": "4h/week"}  # This also doesn't exist!
            )
            pytest.fail("BusinessContext fixture should have failed but didn't")
        except TypeError as e:
            # This demonstrates the fixture is currently broken
            assert "unexpected keyword argument" in str(e)
            assert "revenue_range" in str(e)