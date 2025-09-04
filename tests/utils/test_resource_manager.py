"""
Test Resource Manager - Centralized resource cleanup and test isolation
"""

import asyncio
import logging
import uuid
from typing import List, Callable, Any, Optional
import redis
import psycopg2

logger = logging.getLogger(__name__)


class TestResourceManager:
    """Manages test resource cleanup and ensures test isolation."""
    
    def __init__(self):
        self.resources_to_cleanup: List[Callable] = []
        self.customer_ids_used: List[str] = []
        self.cleanup_errors: List[Exception] = []
    
    def register_cleanup(self, cleanup_func: Callable):
        """Register a cleanup function to be called during teardown."""
        self.resources_to_cleanup.append(cleanup_func)
    
    def register_customer_id(self, customer_id: str):
        """Track customer IDs used in tests for cleanup verification."""
        self.customer_ids_used.append(customer_id)
    
    async def cleanup_all(self):
        """Execute all registered cleanup functions with error tracking."""
        self.cleanup_errors = []
        
        # Execute cleanup functions in reverse order (LIFO)
        for cleanup_func in reversed(self.resources_to_cleanup):
            try:
                if asyncio.iscoroutinefunction(cleanup_func):
                    await cleanup_func()
                else:
                    cleanup_func()
            except Exception as e:
                logger.error(f"Cleanup function failed: {e}")
                self.cleanup_errors.append(e)
        
        # Fail fast if any cleanup failed
        if self.cleanup_errors:
            error_messages = [str(e) for e in self.cleanup_errors]
            raise Exception(f"Cleanup failures: {error_messages}")
    
    def generate_unique_customer_id(self, prefix: str = "test") -> str:
        """Generate unique customer ID with hex suffix."""
        hex_suffix = uuid.uuid4().hex[:8]
        return f"{prefix}_{hex_suffix}"
    
    def verify_test_isolation(self) -> bool:
        """Verify that test environment is clean and isolated."""
        try:
            # Check Redis isolation (if available)
            self._verify_redis_clean()
            
            # Check PostgreSQL isolation (if available) 
            self._verify_postgres_clean()
            
            return True
        except Exception as e:
            logger.error(f"Test isolation verification failed: {e}")
            return False
    
    def _verify_redis_clean(self):
        """Verify Redis test database is clean."""
        try:
            test_redis = redis.Redis(
                host='localhost', port=6379, db=15, decode_responses=True
            )
            keys = test_redis.keys("*")
            if len(keys) > 0:
                raise Exception(f"Redis test DB not clean - found keys: {keys}")
        except redis.ConnectionError:
            # Redis not available, skip verification
            logger.info("Redis not available for isolation verification")
    
    def _verify_postgres_clean(self):
        """Verify PostgreSQL test database is clean."""
        try:
            conn = psycopg2.connect(
                host="localhost",
                database="mcphub_test",
                user="mcphub", 
                password="mcphub_password"
            )
            
            with conn.cursor() as cursor:
                # Check for test data in customer tables
                cursor.execute(
                    "SELECT COUNT(*) FROM customer_business_context WHERE customer_id LIKE 'test_%'"
                )
                test_records = cursor.fetchone()[0]
                
                if test_records > 0:
                    raise Exception(f"PostgreSQL test DB not clean - found {test_records} test records")
            
            conn.close()
        except psycopg2.Error:
            # PostgreSQL not available, skip verification
            logger.info("PostgreSQL not available for isolation verification")


async def cleanup_ea_resources(ea, customer_id: str):
    """Comprehensive EA resource cleanup with error handling."""
    cleanup_errors = []
    
    try:
        # Redis cleanup
        if hasattr(ea, 'memory') and hasattr(ea.memory, 'redis_client'):
            ea.memory.redis_client.flushdb()
    except Exception as e:
        cleanup_errors.append(f"Redis cleanup failed: {e}")
    
    try:
        # Database cleanup
        if hasattr(ea, 'memory') and hasattr(ea.memory, 'db_connection') and ea.memory.db_connection:
            with ea.memory.db_connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM customer_business_context WHERE customer_id = %s",
                    (customer_id,)
                )
                ea.memory.db_connection.commit()
    except Exception as e:
        cleanup_errors.append(f"Database cleanup failed: {e}")
    
    try:
        # Mem0 cleanup (if available)
        if hasattr(ea, 'mem0_memory'):
            # Delete all memories for this customer
            memories = ea.mem0_memory.get_all(user_id=customer_id)
            for memory in memories:
                ea.mem0_memory.delete(memory_id=memory['id'])
    except Exception as e:
        cleanup_errors.append(f"Mem0 cleanup failed: {e}")
    
    # Fail fast on cleanup errors - don't hide them
    if cleanup_errors:
        raise Exception(f"EA resource cleanup failed for {customer_id}: {cleanup_errors}")


def create_isolated_business_context(**kwargs) -> Any:
    """Create BusinessContext with valid parameters only."""
    # Import here to avoid circular imports
    from src.agents.executive_assistant import BusinessContext
    
    # Filter out invalid parameters that don't exist in BusinessContext
    valid_params = {
        'business_name', 'business_type', 'industry', 'daily_operations',
        'pain_points', 'current_tools', 'automation_opportunities', 
        'communication_style', 'key_processes', 'customers', 'team_members', 'goals'
    }
    
    filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_params}
    
    return BusinessContext(**filtered_kwargs)


# Global instance for use in fixtures
test_resource_manager = TestResourceManager()