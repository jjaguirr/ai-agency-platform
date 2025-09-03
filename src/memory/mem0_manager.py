"""
EA Memory Manager - Mem0 Integration for Executive Assistant Agents

Provides per-customer memory isolation with hybrid architecture combining:
- Mem0: Semantic business knowledge and cross-conversation learning
- Redis: Active conversation context for <2s access
- PostgreSQL: Persistent audit logs and compliance data

Implements the architecture defined in docs/architecture/Mem0-Integration-Architecture.md
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, Union

import redis.asyncio as redis
from mem0 import Memory
from mem0.client.main import MemoryClient
import asyncpg

logger = logging.getLogger(__name__)


class EAMemoryManager:
    """
    Executive Assistant Memory Manager with per-customer isolation.
    
    Orchestrates hybrid memory architecture for optimal performance:
    - Working Memory (Redis): <2s access for active conversation context
    - Semantic Memory (Mem0): <500ms for business knowledge retrieval
    - Persistent Storage (PostgreSQL): Complete audit history
    """
    
    def __init__(self, customer_id: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize per-customer memory manager.
        
        Args:
            customer_id: Unique customer identifier for isolation
            config: Optional configuration override
        """
        self.customer_id = customer_id
        self.user_id = f"customer_{customer_id}"
        self.agent_id = f"ea_{customer_id}"
        
        # Configuration
        self.config = config or self._default_config()
        
        # Initialize memory layers
        self.mem0_client = self._initialize_mem0()
        self.redis_client = None  # Lazy initialization
        self.postgres_pool = None  # Lazy initialization
        
        logger.info(f"Initialized EA Memory Manager for customer {customer_id}")
    
    def _default_config(self) -> Dict[str, Any]:
        """Default configuration for memory layers"""
        return {
            "mem0": {
                "vector_store": {
                    "provider": "qdrant",
                    "config": {
                        "host": "localhost",
                        "port": 6333,
                        "collection_name": f"customer_{self.customer_id}_memories"
                    }
                },
                "graph_store": {
                    "provider": "neo4j", 
                    "config": {
                        "url": "neo4j://localhost:7687",
                        "username": "neo4j",
                        "password": "password",
                        "database": f"customer_{self.customer_id}_graph"
                    }
                },
                "llm": {
                    "provider": "openai",
                    "config": {
                        "model": "gpt-4o-mini",
                        "temperature": 0.1
                    }
                },
                "embedder": {
                    "provider": "openai", 
                    "config": {
                        "model": "text-embedding-3-small"
                    }
                }
            },
            "redis": {
                "host": "localhost",
                "port": 6379,
                "db": int(self.customer_id[-4:], 16) % 16,  # Customer-specific DB 0-15
                "decode_responses": True
            },
            "postgres": {
                "host": "localhost",
                "port": 5432,
                "database": "mcphub",
                "user": "mcphub", 
                "password": "mcphub_password"
            },
            "performance": {
                "redis_timeout": 0.002,  # 2ms
                "mem0_timeout": 0.5,     # 500ms SLA
                "postgres_timeout": 0.1   # 100ms
            }
        }
    
    def _initialize_mem0(self) -> Memory:
        """Initialize Mem0 client with per-customer isolation"""
        try:
            memory_config = self.config["mem0"]
            
            # Ensure collection name includes customer ID for isolation
            vector_config = memory_config["vector_store"]["config"]
            vector_config["collection_name"] = f"customer_{self.customer_id}_memories"
            
            # Ensure Neo4j database is customer-specific
            if "graph_store" in memory_config:
                graph_config = memory_config["graph_store"]["config"]  
                graph_config["database"] = f"customer_{self.customer_id}_graph"
            
            mem0_client = Memory.from_config(
                config=memory_config,
                user_id=self.user_id,
                metadata={
                    "customer_id": self.customer_id,
                    "agent_type": "executive_assistant",
                    "created_at": datetime.utcnow().isoformat(),
                    "isolation_boundary": "per_customer"
                }
            )
            
            logger.info(f"Initialized Mem0 client for customer {self.customer_id}")
            return mem0_client
            
        except Exception as e:
            logger.error(f"Failed to initialize Mem0 for customer {self.customer_id}: {e}")
            raise
    
    async def _get_redis_client(self) -> redis.Redis:
        """Get or create Redis client with customer isolation"""
        if self.redis_client is None:
            try:
                redis_config = self.config["redis"]
                self.redis_client = redis.Redis(**redis_config)
                
                # Test connection
                await self.redis_client.ping()
                logger.info(f"Connected to Redis DB {redis_config['db']} for customer {self.customer_id}")
                
            except Exception as e:
                logger.error(f"Failed to connect to Redis for customer {self.customer_id}: {e}")
                raise
        
        return self.redis_client
    
    async def _get_postgres_pool(self) -> asyncpg.Pool:
        """Get or create PostgreSQL connection pool"""
        if self.postgres_pool is None:
            try:
                postgres_config = self.config["postgres"]
                self.postgres_pool = await asyncpg.create_pool(
                    host=postgres_config["host"],
                    port=postgres_config["port"], 
                    database=postgres_config["database"],
                    user=postgres_config["user"],
                    password=postgres_config["password"],
                    min_size=1,
                    max_size=5,
                    command_timeout=self.config["performance"]["postgres_timeout"]
                )
                
                logger.info(f"Connected to PostgreSQL for customer {self.customer_id}")
                
            except Exception as e:
                logger.error(f"Failed to connect to PostgreSQL for customer {self.customer_id}: {e}")
                raise
        
        return self.postgres_pool
    
    async def store_business_context(self, context: Dict[str, Any], session_id: str) -> Optional[str]:
        """
        Store business discovery insights in Mem0 for semantic retrieval.
        
        Args:
            context: Business context data from discovery conversation
            session_id: Unique session identifier
            
        Returns:
            Memory ID if successful, None if failed
        """
        try:
            # Prepare memory data with rich metadata
            memory_data = {
                "content": context.get("business_description", ""),
                "metadata": {
                    "type": "business_context",
                    "customer_id": self.customer_id,
                    "session_id": session_id, 
                    "discovery_phase": context.get("phase", "initial"),
                    "automation_opportunities": context.get("opportunities", []),
                    "pain_points": context.get("pain_points", []),
                    "timestamp": datetime.utcnow().isoformat(),
                    "source": "business_discovery"
                }
            }
            
            # Store in Mem0 for semantic retrieval
            result = self.mem0_client.add(
                messages=[{
                    "role": "system",
                    "content": json.dumps(memory_data)
                }],
                user_id=self.user_id,
                agent_id=self.agent_id,
                metadata=memory_data["metadata"]
            )
            
            # Store in Redis for immediate access
            redis_client = await self._get_redis_client()
            redis_key = f"business_context:{session_id}"
            await redis_client.setex(
                redis_key,
                3600,  # 1 hour TTL
                json.dumps(context)
            )
            
            # Store in PostgreSQL for audit trail
            await self._store_audit_log({
                "action": "store_business_context",
                "customer_id": self.customer_id,
                "session_id": session_id,
                "data_summary": context.get("business_description", "")[:200],
                "mem0_result": str(result),
                "timestamp": datetime.utcnow().isoformat()
            })
            
            memory_id = result.get("id") if result else str(uuid.uuid4())
            logger.info(f"Stored business context {memory_id} for customer {self.customer_id}")
            
            return memory_id
            
        except Exception as e:
            logger.error(f"Failed to store business context for customer {self.customer_id}: {e}")
            return None
    
    async def retrieve_business_context(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieve relevant business context from Mem0 using semantic search.
        
        Args:
            query: Search query for business context
            limit: Maximum number of results
            
        Returns:
            List of relevant memories with metadata
        """
        try:
            start_time = time.time()
            
            # Search semantic memory
            results = self.mem0_client.search(
                query=query,
                user_id=self.user_id,
                agent_id=self.agent_id, 
                limit=limit,
                filters={"type": "business_context"}
            )
            
            retrieval_time = time.time() - start_time
            
            # Check performance SLA
            if retrieval_time > self.config["performance"]["mem0_timeout"]:
                logger.warning(f"Mem0 retrieval exceeded SLA: {retrieval_time:.3f}s > {self.config['performance']['mem0_timeout']}s")
            
            memories = results.get("results", [])
            
            # Log audit entry for retrieval
            await self._store_audit_log({
                "action": "retrieve_business_context", 
                "customer_id": self.customer_id,
                "query": query,
                "results_count": len(memories),
                "retrieval_time": retrieval_time,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            logger.info(f"Retrieved {len(memories)} business memories for customer {self.customer_id} in {retrieval_time:.3f}s")
            return memories
            
        except Exception as e:
            logger.error(f"Failed to retrieve business context for customer {self.customer_id}: {e}")
            return []
    
    async def store_workflow_memory(self, workflow_config: Dict[str, Any], template_id: str) -> Optional[str]:
        """
        Store workflow creation and performance data in memory.
        
        Args:
            workflow_config: n8n workflow configuration
            template_id: Template used for workflow creation
            
        Returns:
            Memory ID if successful
        """
        try:
            workflow_memory = {
                "content": f"Created workflow using template {template_id}",
                "metadata": {
                    "type": "workflow_memory",
                    "customer_id": self.customer_id,
                    "template_id": template_id,
                    "workflow_config": workflow_config,
                    "created_at": datetime.utcnow().isoformat(),
                    "performance_metrics": workflow_config.get("performance_metrics", {}),
                    "deployment_status": workflow_config.get("deployment_status", "unknown")
                }
            }
            
            # Store workflow memory in Mem0
            result = self.mem0_client.add(
                messages=[{
                    "role": "assistant", 
                    "content": json.dumps(workflow_memory)
                }],
                user_id=self.user_id,
                agent_id=self.agent_id,
                metadata=workflow_memory["metadata"]
            )
            
            memory_id = result.get("id") if result else str(uuid.uuid4())
            logger.info(f"Stored workflow memory {memory_id} for customer {self.customer_id}")
            
            return memory_id
            
        except Exception as e:
            logger.error(f"Failed to store workflow memory for customer {self.customer_id}: {e}")
            return None
    
    async def _store_audit_log(self, audit_data: Dict[str, Any]) -> bool:
        """Store audit log entry in PostgreSQL"""
        try:
            pool = await self._get_postgres_pool()
            
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO customer_memory_audit (
                        customer_id, action, data, timestamp
                    ) VALUES ($1, $2, $3, $4)
                    ON CONFLICT DO NOTHING
                """, 
                    audit_data["customer_id"],
                    audit_data["action"],
                    json.dumps(audit_data),
                    datetime.utcnow()
                )
            
            return True
            
        except Exception as e:
            logger.warning(f"Failed to store audit log: {e}")
            return False
    
    async def cleanup_test_data(self):
        """Cleanup test data for testing purposes"""
        try:
            # Clean up Redis test data
            if self.redis_client:
                redis_client = await self._get_redis_client()
                keys = await redis_client.keys(f"*test*")
                if keys:
                    await redis_client.delete(*keys)
            
            # Note: Mem0 and PostgreSQL cleanup would require specific cleanup logic
            # For now, we rely on test isolation via customer_id prefixes
            
            logger.info(f"Cleaned up test data for customer {self.customer_id}")
            
        except Exception as e:
            logger.warning(f"Failed to cleanup test data: {e}")
    
    async def close(self):
        """Close all connections"""
        try:
            if self.redis_client:
                await self.redis_client.aclose()
                
            if self.postgres_pool:
                await self.postgres_pool.close()
                
            logger.info(f"Closed all connections for customer {self.customer_id}")
            
        except Exception as e:
            logger.error(f"Error closing connections: {e}")


class OptimizedMemoryRouter:
    """
    Optimized memory router for intelligent query routing across memory layers.
    
    Routes queries to optimal memory layer based on query type and performance requirements:
    - immediate_context: Redis (<2ms)
    - business_knowledge: Mem0 (<500ms) 
    - historical_audit: PostgreSQL (<100ms)
    - hybrid_context: Multiple sources combined
    """
    
    def __init__(self, ea_memory: EAMemoryManager):
        self.ea_memory = ea_memory
        self.performance_targets = ea_memory.config["performance"]
    
    async def intelligent_memory_retrieval(self, query: str, query_type: str) -> Union[Dict[str, Any], List[Dict[str, Any]], None]:
        """
        Route queries to optimal memory layer based on type and performance requirements.
        
        Args:
            query: Query string
            query_type: Type of query (immediate_context, business_knowledge, historical_audit, hybrid_context)
            
        Returns:
            Query results from appropriate memory layer
        """
        start_time = time.time()
        
        try:
            if query_type == "immediate_context":
                result = await self._redis_retrieval(query)
            elif query_type == "business_knowledge":
                result = await self._mem0_retrieval(query)
            elif query_type == "historical_audit":
                result = await self._postgres_retrieval(query)
            elif query_type == "hybrid_context":
                result = await self._hybrid_retrieval(query)
            else:
                logger.warning(f"Unknown query type: {query_type}")
                result = await self._mem0_retrieval(query)  # Default to Mem0
            
            elapsed = time.time() - start_time
            logger.info(f"Memory retrieval ({query_type}) completed in {elapsed:.3f}s")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed memory retrieval for query_type {query_type}: {e}")
            return None
    
    async def _redis_retrieval(self, query: str) -> Optional[Dict[str, Any]]:
        """Retrieve from Redis working memory"""
        start_time = time.time()
        
        try:
            redis_client = await self.ea_memory._get_redis_client()
            result = await redis_client.get(f"context:{query}")
            
            elapsed = time.time() - start_time
            if elapsed > self.performance_targets["redis_timeout"]:
                logger.warning(f"Redis access exceeded target: {elapsed:.3f}s > {self.performance_targets['redis_timeout']}s")
            
            return json.loads(result) if result else None
            
        except Exception as e:
            logger.error(f"Redis retrieval failed: {e}")
            return None
    
    async def _mem0_retrieval(self, query: str) -> List[Dict[str, Any]]:
        """Retrieve from Mem0 semantic memory"""
        start_time = time.time()
        
        try:
            results = await self.ea_memory.retrieve_business_context(query)
            
            elapsed = time.time() - start_time
            if elapsed > self.performance_targets["mem0_timeout"]:
                logger.warning(f"Mem0 access exceeded target: {elapsed:.3f}s > {self.performance_targets['mem0_timeout']}s")
            
            return results
            
        except Exception as e:
            logger.error(f"Mem0 retrieval failed: {e}")
            return []
    
    async def _postgres_retrieval(self, query: str) -> List[Dict[str, Any]]:
        """Retrieve from PostgreSQL persistent storage"""
        start_time = time.time()
        
        try:
            pool = await self.ea_memory._get_postgres_pool()
            
            async with pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT * FROM customer_memory_audit 
                    WHERE customer_id = $1 
                    AND data::text ILIKE $2
                    ORDER BY timestamp DESC
                    LIMIT 10
                """, self.ea_memory.customer_id, f"%{query}%")
            
            elapsed = time.time() - start_time
            if elapsed > self.performance_targets["postgres_timeout"]:
                logger.warning(f"PostgreSQL access exceeded target: {elapsed:.3f}s > {self.performance_targets['postgres_timeout']}s")
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"PostgreSQL retrieval failed: {e}")
            return []
    
    async def _hybrid_retrieval(self, query: str) -> Dict[str, Any]:
        """Retrieve from multiple sources for comprehensive context"""
        try:
            # Execute retrieval from multiple sources concurrently
            redis_task = asyncio.create_task(self._redis_retrieval(f"context:{query}"))
            mem0_task = asyncio.create_task(self._mem0_retrieval(query))
            postgres_task = asyncio.create_task(self._postgres_retrieval(query))
            
            # Wait for all results
            redis_result, mem0_results, postgres_results = await asyncio.gather(
                redis_task, mem0_task, postgres_task,
                return_exceptions=True
            )
            
            return {
                "immediate_context": redis_result if not isinstance(redis_result, Exception) else None,
                "semantic_memories": mem0_results if not isinstance(mem0_results, Exception) else [],
                "audit_history": postgres_results if not isinstance(postgres_results, Exception) else [],
                "hybrid_timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Hybrid retrieval failed: {e}")
            return {}


async def maintain_conversation_continuity(ea_memory: EAMemoryManager, 
                                          channel: str, 
                                          message: str,
                                          user_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Maintain conversation continuity across phone, WhatsApp, and email channels.
    
    Args:
        ea_memory: EA memory manager instance
        channel: Communication channel (phone, whatsapp, email)
        message: User message content
        user_context: Additional user context
        
    Returns:
        Dictionary with stored memory, context memories, and response context
    """
    try:
        # Retrieve relevant conversation history from Mem0
        relevant_memories = await ea_memory.retrieve_business_context(
            query=f"recent conversations {message}",
            limit=5
        )
        
        # Create enhanced message with channel context
        enhanced_message = {
            "role": "user",
            "content": message,
            "channel": channel,
            "context": user_context,
            "timestamp": datetime.utcnow().isoformat(),
            "continuity_context": [m.get("memory", "") for m in relevant_memories]
        }
        
        # Store with cross-channel continuity metadata
        result = ea_memory.mem0_client.add(
            messages=[enhanced_message],
            user_id=ea_memory.user_id,
            agent_id=ea_memory.agent_id,
            metadata={
                "type": "conversation",
                "channel": channel,
                "continuity_enabled": True,
                "previous_context_count": len(relevant_memories)
            }
        )
        
        # Build response context for EA
        response_context = {
            "current_channel": channel,
            "previous_channels": list(set(m.get("metadata", {}).get("channel", "unknown") for m in relevant_memories)),
            "business_context": [m.get("memory", "") for m in relevant_memories],
            "conversation_flow": f"Continuing conversation from {channel}"
        }
        
        return {
            "stored_memory": result,
            "context_memories": relevant_memories,
            "response_context": response_context
        }
        
    except Exception as e:
        logger.error(f"Failed to maintain conversation continuity: {e}")
        return {
            "stored_memory": None,
            "context_memories": [],
            "response_context": {}
        }