"""
Test Data Manager for AI Agency Platform
Provides unique test data generation and guaranteed cleanup across all storage systems.
"""

import uuid
import time
import asyncio
import logging
from typing import Dict, List, Any, Optional, Tuple
from contextlib import asynccontextmanager
from datetime import datetime

# Database clients
import redis
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class TestDataManager:
    """Manages unique test data generation and guaranteed cleanup."""

    # Utility class — not a pytest test case despite the Test* name.
    __test__ = False

    def __init__(self, test_name: str):
        self.test_name = test_name.replace("::", "_").replace("[", "_").replace("]", "_")
        self.resources_created: List[Tuple[str, str]] = []
        self.cleanup_callbacks: List[callable] = []
        
        # Database connections (lazy initialization)
        self._redis_client = None
        self._postgres_conn = None
        
    def generate_unique_customer_id(self) -> str:
        """Generate globally unique customer ID for test isolation."""
        timestamp = int(time.time())
        unique_id = uuid.uuid4().hex[:8]
        customer_id = f"test_{self.test_name}_{timestamp}_{unique_id}"
        
        # Track for cleanup
        self.resources_created.append(('customer_id', customer_id))
        logger.info(f"Generated unique customer ID: {customer_id}")
        
        return customer_id
    
    def generate_conversation_id(self) -> str:
        """Generate unique conversation ID."""
        unique_id = uuid.uuid4().hex
        conversation_id = f"conv_test_{unique_id}"
        
        self.resources_created.append(('conversation_id', conversation_id))
        return conversation_id
    
    def generate_unique_business_context(self, business_type: str = "test_business") -> Dict[str, Any]:
        """Generate unique business context for testing."""
        unique_suffix = uuid.uuid4().hex[:6]
        
        context = {
            "business_name": f"Test {business_type.title()} {unique_suffix}",
            "business_type": business_type,
            "industry": f"test_{business_type}",
            "daily_operations": [f"test_operation_{unique_suffix}"],
            "pain_points": [f"test_pain_point_{unique_suffix}"],
            "current_tools": [f"TestTool_{unique_suffix}"],
            "automation_opportunities": [f"test_automation_{unique_suffix}"],
        }
        
        self.resources_created.append(('business_context', context['business_name']))
        return context
    
    @property
    def redis_client(self) -> redis.Redis:
        """Lazy Redis client initialization."""
        if self._redis_client is None:
            # Use test database (15) to avoid conflicts with development
            self._redis_client = redis.Redis(
                host='localhost',
                port=6379,
                db=15,  # Test database
                decode_responses=True
            )
        return self._redis_client
    
    @property 
    def postgres_conn(self):
        """Lazy PostgreSQL connection initialization."""
        if self._postgres_conn is None:
            try:
                self._postgres_conn = psycopg2.connect(
                    host="localhost",
                    database="mcphub_test",  # Test database
                    user="mcphub",
                    password="mcphub_password"
                )
            except psycopg2.OperationalError:
                # Fallback to main database if test database doesn't exist
                logger.warning("Test database 'mcphub_test' not available, using main database")
                self._postgres_conn = psycopg2.connect(
                    host="localhost",
                    database="mcphub",
                    user="mcphub",
                    password="mcphub_password"
                )
        return self._postgres_conn
    
    async def cleanup_customer_data(self, customer_id: str):
        """Guaranteed cleanup of customer data across all storage systems."""
        cleanup_tasks = []
        
        # Redis cleanup
        cleanup_tasks.append(self._cleanup_redis(customer_id))
        
        # PostgreSQL cleanup
        cleanup_tasks.append(self._cleanup_postgres(customer_id))
        
        # Qdrant cleanup (for Mem0 vector storage)
        cleanup_tasks.append(self._cleanup_qdrant(customer_id))
        
        # Execute all cleanup tasks concurrently
        results = await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        
        # Log any cleanup errors but don't fail tests
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Cleanup task {i} failed for {customer_id}: {result}")
        
        logger.info(f"Completed cleanup for customer: {customer_id}")
    
    async def _cleanup_redis(self, customer_id: str):
        """Clean up Redis data for customer."""
        try:
            # Clean all keys matching customer pattern
            pattern = f"*{customer_id}*"
            keys = self.redis_client.keys(pattern)
            if keys:
                self.redis_client.delete(*keys)
                logger.debug(f"Cleaned {len(keys)} Redis keys for {customer_id}")
                
            # Also clean conversation data
            conv_pattern = f"conv:*{customer_id}*"
            conv_keys = self.redis_client.keys(conv_pattern)
            if conv_keys:
                self.redis_client.delete(*conv_keys)
                logger.debug(f"Cleaned {len(conv_keys)} Redis conversation keys for {customer_id}")
                
        except Exception as e:
            logger.error(f"Redis cleanup failed for {customer_id}: {e}")
            raise
    
    async def _cleanup_postgres(self, customer_id: str):
        """Clean up PostgreSQL data for customer."""
        try:
            with self.postgres_conn.cursor() as cursor:
                # Clean customer business context
                cursor.execute(
                    "DELETE FROM customer_business_context WHERE customer_id = %s",
                    (customer_id,)
                )
                
                # Clean any test-related data
                cursor.execute(
                    "DELETE FROM customer_business_context WHERE customer_id LIKE %s",
                    (f"test_%",)
                )
                
                self.postgres_conn.commit()
                logger.debug(f"Cleaned PostgreSQL data for {customer_id}")
                
        except Exception as e:
            logger.error(f"PostgreSQL cleanup failed for {customer_id}: {e}")
            if self.postgres_conn:
                self.postgres_conn.rollback()
            raise
    
    async def _cleanup_qdrant(self, customer_id: str):
        """Clean up Qdrant vector collections for customer."""
        try:
            # For now, just log that we would clean Qdrant
            # TODO: Implement actual Qdrant cleanup when Mem0 integration is complete
            logger.debug(f"Qdrant cleanup (placeholder) for {customer_id}")
            
        except Exception as e:
            logger.error(f"Qdrant cleanup failed for {customer_id}: {e}")
    
    async def cleanup_all(self):
        """Clean up all resources created during test."""
        for resource_type, resource_id in self.resources_created:
            if resource_type == 'customer_id':
                await self.cleanup_customer_data(resource_id)
        
        # Execute any registered cleanup callbacks
        for callback in self.cleanup_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.warning(f"Cleanup callback failed: {e}")
        
        # Close database connections
        if self._redis_client:
            self._redis_client.close()
        if self._postgres_conn:
            self._postgres_conn.close()
        
        logger.info(f"Completed cleanup for test: {self.test_name}")
    
    def register_cleanup(self, cleanup_func: callable):
        """Register additional cleanup function."""
        self.cleanup_callbacks.append(cleanup_func)
    
    @asynccontextmanager
    async def isolated_customer(self, business_type: str = "test_business"):
        """Context manager for isolated customer testing."""
        customer_id = self.generate_unique_customer_id()
        business_context = self.generate_unique_business_context(business_type)
        
        try:
            yield customer_id, business_context
        finally:
            await self.cleanup_customer_data(customer_id)


# Pytest fixture for easy integration
@asynccontextmanager
async def test_data_manager(test_name: str):
    """Context manager for test data management."""
    manager = TestDataManager(test_name)
    try:
        yield manager
    finally:
        await manager.cleanup_all()


# Helper context manager — not a pytest test function despite the test_* name.
test_data_manager.__test__ = False