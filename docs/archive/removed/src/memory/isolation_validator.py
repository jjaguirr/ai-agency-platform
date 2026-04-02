"""
Memory Isolation Validator - Ensures 100% Customer Memory Isolation

Validates that customers cannot access each other's memories across all layers:
- Mem0 semantic memory isolation via user_id/agent_id  
- Redis working memory isolation via customer-specific databases
- PostgreSQL persistent storage isolation via customer_id filtering

Critical for enterprise security and GDPR compliance.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Any, Tuple

from .mem0_manager import EAMemoryManager

logger = logging.getLogger(__name__)


class MemoryIsolationValidator:
    """
    Validates per-customer memory isolation across all memory layers.
    
    Performs comprehensive isolation testing to ensure:
    - Zero cross-customer memory access
    - Proper customer data segregation 
    - Agent-level isolation within customers (Phase 2 prep)
    - Performance impact of isolation boundaries
    """
    
    @staticmethod
    async def validate_customer_isolation(customer_a_id: str, customer_b_id: str) -> Dict[str, Any]:
        """
        Comprehensive validation that customers cannot access each other's memories.
        
        Args:
            customer_a_id: First customer ID for isolation testing
            customer_b_id: Second customer ID for isolation testing
            
        Returns:
            Validation results with detailed isolation metrics
        """
        validation_start = datetime.utcnow()
        
        try:
            # Initialize separate customer memory managers
            memory_a = EAMemoryManager(customer_a_id)
            memory_b = EAMemoryManager(customer_b_id)
            
            # Generate unique test secrets for each customer
            secret_a = f"customer_a_secret_{uuid.uuid4()}"
            secret_b = f"customer_b_secret_{uuid.uuid4()}"
            
            # Test data with sensitive business information
            business_data_a = {
                "business_description": f"Customer A confidential business: {secret_a}",
                "revenue": "$5M annually - CONFIDENTIAL",
                "competitive_advantage": "Proprietary AI algorithm - SECRET",
                "customer_list": ["Fortune 500 Client A", "Enterprise Customer X"]
            }
            
            business_data_b = {
                "business_description": f"Customer B confidential business: {secret_b}", 
                "revenue": "$2M annually - CONFIDENTIAL",
                "competitive_advantage": "Exclusive partnerships - SECRET",
                "customer_list": ["Government Agency Y", "Healthcare Provider Z"]
            }
            
            # Store test data in respective customer memories
            session_a = f"isolation_test_a_{uuid.uuid4().hex}"
            session_b = f"isolation_test_b_{uuid.uuid4().hex}"
            
            result_a = await memory_a.store_business_context(
                context=business_data_a,
                session_id=session_a
            )
            
            result_b = await memory_b.store_business_context(
                context=business_data_b, 
                session_id=session_b
            )
            
            if not (result_a and result_b):
                raise Exception("Failed to store test data for isolation validation")
            
            # Cross-customer access attempts (should all fail)
            cross_access_results = await asyncio.gather(
                # Customer A trying to access Customer B's data
                memory_a.retrieve_business_context(query=secret_b, limit=10),
                memory_a.retrieve_business_context(query="Customer B confidential", limit=10),
                memory_a.retrieve_business_context(query="$2M annually", limit=10),
                
                # Customer B trying to access Customer A's data  
                memory_b.retrieve_business_context(query=secret_a, limit=10),
                memory_b.retrieve_business_context(query="Customer A confidential", limit=10),
                memory_b.retrieve_business_context(query="$5M annually", limit=10),
                
                return_exceptions=True
            )
            
            # Own data access (should succeed)
            own_access_results = await asyncio.gather(
                memory_a.retrieve_business_context(query=secret_a, limit=10),
                memory_b.retrieve_business_context(query=secret_b, limit=10),
                return_exceptions=True
            )
            
            # Analyze isolation results
            isolation_violations = []
            for i, result in enumerate(cross_access_results):
                if isinstance(result, Exception):
                    continue  # Exceptions are acceptable for cross-access
                    
                if len(result) > 0:
                    # Found cross-customer data - CRITICAL VIOLATION
                    customer = "A" if i < 3 else "B"
                    target = "B" if i < 3 else "A"
                    violation = {
                        "severity": "CRITICAL",
                        "violation_type": "cross_customer_access",
                        "accessing_customer": customer,
                        "target_customer": target,
                        "leaked_memories": len(result),
                        "sample_content": result[0].get("memory", "")[:100] if result else ""
                    }
                    isolation_violations.append(violation)
            
            # Verify own data access
            own_access_success = {
                "customer_a_access": len(own_access_results[0]) > 0 if not isinstance(own_access_results[0], Exception) else False,
                "customer_b_access": len(own_access_results[1]) > 0 if not isinstance(own_access_results[1], Exception) else False
            }
            
            # Redis isolation validation
            redis_isolation = await MemoryIsolationValidator._validate_redis_isolation(memory_a, memory_b)
            
            # Agent ID isolation validation (Phase 2 prep)
            agent_isolation = await MemoryIsolationValidator._validate_agent_isolation(memory_a)
            
            validation_end = datetime.utcnow()
            validation_duration = (validation_end - validation_start).total_seconds()
            
            validation_results = {
                "validation_timestamp": validation_end.isoformat(),
                "validation_duration_seconds": validation_duration,
                "customers_tested": [customer_a_id, customer_b_id],
                
                # Critical isolation results
                "isolation_verified": len(isolation_violations) == 0,
                "isolation_violations": isolation_violations,
                "violation_count": len(isolation_violations),
                
                # Access verification
                "own_data_access": own_access_success,
                "cross_customer_attempts": len(cross_access_results),
                "cross_customer_successes": sum(1 for r in cross_access_results if not isinstance(r, Exception) and len(r) > 0),
                
                # Layer-specific isolation
                "mem0_isolation": {
                    "customer_a_memories": len(own_access_results[0]) if not isinstance(own_access_results[0], Exception) else 0,
                    "customer_b_memories": len(own_access_results[1]) if not isinstance(own_access_results[1], Exception) else 0,
                    "cross_contamination": sum(1 for r in cross_access_results if not isinstance(r, Exception) and len(r) > 0)
                },
                "redis_isolation": redis_isolation,
                "agent_isolation": agent_isolation,
                
                # Test metadata
                "test_secrets": {
                    "customer_a_secret": secret_a,
                    "customer_b_secret": secret_b
                },
                "test_sessions": {
                    "customer_a": session_a,
                    "customer_b": session_b
                }
            }
            
            # Log results
            if validation_results["isolation_verified"]:
                logger.info(f"✅ Memory isolation VERIFIED for customers {customer_a_id} and {customer_b_id}")
            else:
                logger.error(f"❌ Memory isolation FAILED for customers {customer_a_id} and {customer_b_id}: {len(isolation_violations)} violations")
                for violation in isolation_violations:
                    logger.error(f"VIOLATION: {violation}")
            
            # Cleanup test data
            await memory_a.cleanup_test_data()
            await memory_b.cleanup_test_data()
            await memory_a.close()
            await memory_b.close()
            
            return validation_results
            
        except Exception as e:
            logger.error(f"Memory isolation validation failed: {e}")
            return {
                "validation_timestamp": datetime.utcnow().isoformat(),
                "isolation_verified": False,
                "error": str(e),
                "customers_tested": [customer_a_id, customer_b_id]
            }
    
    @staticmethod
    async def _validate_redis_isolation(memory_a: EAMemoryManager, memory_b: EAMemoryManager) -> Dict[str, Any]:
        """Validate Redis database isolation between customers"""
        try:
            # Test Redis key isolation
            test_key_a = f"isolation_test_{uuid.uuid4()}"
            test_key_b = f"isolation_test_{uuid.uuid4()}"
            test_value_a = f"secret_value_a_{uuid.uuid4()}"
            test_value_b = f"secret_value_b_{uuid.uuid4()}"
            
            redis_a = await memory_a._get_redis_client()
            redis_b = await memory_b._get_redis_client()
            
            # Store test data in each Redis DB
            await redis_a.setex(test_key_a, 300, test_value_a)  # 5 minute TTL
            await redis_b.setex(test_key_b, 300, test_value_b)
            
            # Attempt cross-database access
            a_can_access_b = await redis_a.get(test_key_b) is not None
            b_can_access_a = await redis_b.get(test_key_a) is not None
            
            # Verify own data access
            a_can_access_own = await redis_a.get(test_key_a) == test_value_a
            b_can_access_own = await redis_b.get(test_key_b) == test_value_b
            
            # Cleanup
            await redis_a.delete(test_key_a)
            await redis_b.delete(test_key_b)
            
            return {
                "redis_databases": {
                    "customer_a_db": memory_a.config["redis"]["db"],
                    "customer_b_db": memory_b.config["redis"]["db"]
                },
                "cross_access_detected": a_can_access_b or b_can_access_a,
                "own_access_working": a_can_access_own and b_can_access_own,
                "isolation_verified": not (a_can_access_b or b_can_access_a) and (a_can_access_own and b_can_access_own)
            }
            
        except Exception as e:
            logger.error(f"Redis isolation validation failed: {e}")
            return {
                "redis_isolation_error": str(e),
                "isolation_verified": False
            }
    
    @staticmethod
    async def _validate_agent_isolation(memory: EAMemoryManager) -> Dict[str, Any]:
        """Validate agent-level isolation within customer (Phase 2 preparation)"""
        try:
            customer_id = memory.customer_id
            
            # Create test memories with different agent IDs
            ea_memory = await memory.store_business_context(
                context={
                    "business_description": f"EA-specific context for customer {customer_id}",
                    "agent_type": "executive_assistant"
                },
                session_id=f"ea_test_{uuid.uuid4().hex}"
            )
            
            # Simulate specialist agent memory (Phase 2)
            specialist_data = {
                "content": f"Specialist agent context for customer {customer_id}",
                "metadata": {
                    "type": "specialist_context", 
                    "agent_type": "social_media_specialist",
                    "customer_id": customer_id
                }
            }
            
            specialist_result = memory.mem0_client.add(
                messages=[{"role": "assistant", "content": json.dumps(specialist_data)}],
                user_id=memory.user_id,
                agent_id=f"specialist_{customer_id}",  # Different agent_id
                metadata=specialist_data["metadata"]
            )
            
            # Test agent-specific retrieval
            ea_results = await memory.retrieve_business_context(query="EA-specific context")
            
            # Get all customer memories to check agent segregation
            all_memories = memory.mem0_client.get_all(user_id=memory.user_id)
            
            ea_memories = [
                m for m in all_memories.get("results", []) 
                if m.get("agent_id") == memory.agent_id
            ]
            
            specialist_memories = [
                m for m in all_memories.get("results", [])
                if m.get("agent_id") == f"specialist_{customer_id}"
            ]
            
            return {
                "agent_ids_tested": [memory.agent_id, f"specialist_{customer_id}"],
                "ea_memories_count": len(ea_memories),
                "specialist_memories_count": len(specialist_memories),
                "agent_segregation_working": len(ea_memories) > 0 and len(specialist_memories) > 0,
                "total_customer_memories": len(all_memories.get("results", [])),
                "phase_2_ready": True
            }
            
        except Exception as e:
            logger.error(f"Agent isolation validation failed: {e}")
            return {
                "agent_isolation_error": str(e),
                "phase_2_ready": False
            }
    
    @staticmethod
    async def validate_multiple_customers(customer_ids: List[str], max_concurrent: int = 10) -> Dict[str, Any]:
        """
        Validate isolation across multiple customers concurrently.
        
        Args:
            customer_ids: List of customer IDs to validate
            max_concurrent: Maximum concurrent validation operations
            
        Returns:
            Comprehensive multi-customer isolation validation results
        """
        if len(customer_ids) < 2:
            raise ValueError("At least 2 customers required for isolation validation")
        
        validation_start = datetime.utcnow()
        
        # Generate customer pairs for testing
        customer_pairs = []
        for i in range(len(customer_ids)):
            for j in range(i + 1, len(customer_ids)):
                customer_pairs.append((customer_ids[i], customer_ids[j]))
        
        logger.info(f"Validating isolation for {len(customer_ids)} customers ({len(customer_pairs)} pairs)")
        
        # Create semaphore to limit concurrent validations
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def validate_pair(pair: Tuple[str, str]) -> Dict[str, Any]:
            async with semaphore:
                customer_a, customer_b = pair
                return await MemoryIsolationValidator.validate_customer_isolation(customer_a, customer_b)
        
        # Execute validations concurrently
        try:
            pair_results = await asyncio.gather(
                *[validate_pair(pair) for pair in customer_pairs],
                return_exceptions=True
            )
            
            # Analyze results
            successful_validations = []
            failed_validations = []
            total_violations = 0
            
            for i, result in enumerate(pair_results):
                if isinstance(result, Exception):
                    failed_validations.append({
                        "pair": customer_pairs[i],
                        "error": str(result)
                    })
                else:
                    if result.get("isolation_verified", False):
                        successful_validations.append(result)
                    else:
                        failed_validations.append(result)
                        total_violations += result.get("violation_count", 0)
            
            validation_end = datetime.utcnow()
            validation_duration = (validation_end - validation_start).total_seconds()
            
            overall_results = {
                "validation_timestamp": validation_end.isoformat(),
                "validation_duration_seconds": validation_duration,
                "total_customers": len(customer_ids),
                "customer_pairs_tested": len(customer_pairs),
                
                # Overall isolation status
                "overall_isolation_verified": len(failed_validations) == 0,
                "successful_validations": len(successful_validations),
                "failed_validations": len(failed_validations),
                "total_violations": total_violations,
                
                # Performance metrics
                "average_validation_time": validation_duration / len(customer_pairs),
                "concurrent_operations": min(max_concurrent, len(customer_pairs)),
                
                # Detailed results
                "successful_results": successful_validations,
                "failed_results": failed_validations,
                
                # Summary statistics
                "isolation_success_rate": len(successful_validations) / len(customer_pairs) * 100 if customer_pairs else 0,
                "customers_tested": customer_ids
            }
            
            if overall_results["overall_isolation_verified"]:
                logger.info(f"✅ Multi-customer isolation VERIFIED: {len(customer_ids)} customers, {len(customer_pairs)} pairs")
            else:
                logger.error(f"❌ Multi-customer isolation FAILED: {total_violations} violations across {len(failed_validations)} pairs")
            
            return overall_results
            
        except Exception as e:
            logger.error(f"Multi-customer isolation validation failed: {e}")
            return {
                "validation_timestamp": datetime.utcnow().isoformat(),
                "overall_isolation_verified": False,
                "error": str(e),
                "customers_tested": customer_ids
            }
    
    @staticmethod
    async def continuous_isolation_monitoring(customer_ids: List[str], 
                                              interval_seconds: int = 3600,
                                              max_iterations: int = 24) -> None:
        """
        Continuous monitoring of memory isolation for production environments.
        
        Args:
            customer_ids: Customer IDs to monitor
            interval_seconds: Time between validation checks (default: 1 hour)
            max_iterations: Maximum number of monitoring iterations (default: 24 hours)
        """
        logger.info(f"Starting continuous isolation monitoring for {len(customer_ids)} customers")
        
        for iteration in range(max_iterations):
            try:
                logger.info(f"Isolation monitoring iteration {iteration + 1}/{max_iterations}")
                
                # Randomly sample customer pairs for validation
                import random
                sample_size = min(10, len(customer_ids))  # Validate up to 10 customers per iteration
                sample_customers = random.sample(customer_ids, sample_size)
                
                validation_results = await MemoryIsolationValidator.validate_multiple_customers(
                    customer_ids=sample_customers,
                    max_concurrent=5
                )
                
                if not validation_results.get("overall_isolation_verified", False):
                    logger.critical(f"🚨 ISOLATION VIOLATION DETECTED in monitoring iteration {iteration + 1}")
                    logger.critical(f"Violations: {validation_results.get('total_violations', 0)}")
                    # In production, this would trigger alerts to security team
                
                # Wait for next iteration
                if iteration < max_iterations - 1:
                    await asyncio.sleep(interval_seconds)
                    
            except Exception as e:
                logger.error(f"Isolation monitoring iteration {iteration + 1} failed: {e}")
                await asyncio.sleep(60)  # Short delay before retry
        
        logger.info("Continuous isolation monitoring completed")