"""
MCP Memory Service Client - HTTP API Client for doobidoo/mcp-memory-service

This client replaces the QdrantClient in ExecutiveAssistantMemory with HTTP API calls
to the MCP Memory Service, leveraging ChromaDB backend and autonomous consolidation.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
import aiohttp
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class MemorySearchResult:
    """Search result from MCP Memory Service"""
    content: str
    score: float
    metadata: Dict[str, Any]
    id: str = ""
    timestamp: Optional[str] = None

class MCPMemoryServiceClient:
    """
    HTTP API client for MCP Memory Service with ChromaDB backend.
    
    Provides the same interface as QdrantClient for seamless integration
    with ExecutiveAssistantMemory while leveraging advanced features like:
    - Autonomous memory consolidation
    - Built-in embedding generation
    - Semantic search optimization
    """
    
    def __init__(self, base_url: str, customer_id: str, api_key: Optional[str] = None):
        """
        Initialize MCP Memory Service client.
        
        Args:
            base_url: MCP Memory Service endpoint (e.g., http://localhost:40000)
            customer_id: Customer identifier for memory isolation
            api_key: Optional API key for authentication
        """
        self.base_url = base_url.rstrip('/')
        self.customer_id = customer_id
        self.api_key = api_key
        self.collection_name = f"customer_{customer_id}_memory"
        
        # HTTP session for connection pooling and performance
        self.session: Optional[aiohttp.ClientSession] = None
        
        logger.info(f"Initialized MCP Memory Service client for customer {customer_id} at {base_url}")
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self._close_session()
    
    async def _ensure_session(self):
        """Ensure HTTP session is created"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers=self._get_headers(),
                connector=aiohttp.TCPConnector(limit=10, limit_per_host=5)
            )
    
    async def _close_session(self):
        """Close HTTP session"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
    
    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for API requests"""
        headers = {
            'Content-Type': 'application/json',
            'X-Customer-ID': self.customer_id
        }
        
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        
        return headers
    
    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """
        Make HTTP request to MCP Memory Service.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            data: Optional request payload
            
        Returns:
            Response JSON data
            
        Raises:
            aiohttp.ClientError: For HTTP errors
            asyncio.TimeoutError: For timeout errors
        """
        await self._ensure_session()
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            async with self.session.request(
                method, 
                url, 
                json=data,
                headers=self._get_headers()
            ) as response:
                response.raise_for_status()
                
                # Handle different content types
                content_type = response.headers.get('content-type', '').lower()
                if 'application/json' in content_type:
                    return await response.json()
                else:
                    text = await response.text()
                    return {'response': text}
                    
        except aiohttp.ClientError as e:
            logger.error(f"MCP Memory Service request failed: {e}")
            raise
        except asyncio.TimeoutError:
            logger.error(f"MCP Memory Service request timeout for {url}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in MCP Memory Service request: {e}")
            raise
    
    async def ensure_collection(self) -> bool:
        """
        Ensure customer's memory collection exists.
        
        Replaces _ensure_vector_collection() from QdrantClient.
        
        Returns:
            True if collection exists or was created successfully
        """
        try:
            # Check if collection exists
            collections_response = await self._make_request('GET', '/api/v1/collections')
            existing_collections = collections_response.get('collections', [])
            
            if self.collection_name in existing_collections:
                logger.info(f"Memory collection {self.collection_name} already exists")
                return True
            
            # Create collection if it doesn't exist
            collection_data = {
                'name': self.collection_name,
                'customer_id': self.customer_id,
                'metadata': {
                    'created_at': datetime.now().isoformat(),
                    'customer_isolation': True,
                    'auto_consolidation': True
                }
            }
            
            await self._make_request('POST', '/api/v1/collections', collection_data)
            logger.info(f"Created memory collection: {self.collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to ensure collection {self.collection_name}: {e}")
            return False
    
    async def store_memory(
        self, 
        content: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Store business knowledge in memory with automatic embedding generation.
        
        Replaces store_business_knowledge() from Qdrant implementation.
        
        Args:
            content: Text content to store
            metadata: Optional metadata dictionary
            
        Returns:
            Memory ID for the stored content
        """
        try:
            # Ensure collection exists
            await self.ensure_collection()
            
            memory_id = str(uuid.uuid4())
            memory_data = {
                'id': memory_id,
                'content': content,
                'collection': self.collection_name,
                'metadata': {
                    'customer_id': self.customer_id,
                    'timestamp': datetime.now().isoformat(),
                    'source': 'executive_assistant',
                    **(metadata or {})
                }
            }
            
            # Store memory - MCP Memory Service handles embedding generation
            response = await self._make_request('POST', '/api/v1/memories', memory_data)
            
            stored_id = response.get('id', memory_id)
            logger.info(f"Stored memory {stored_id}: {content[:100]}...")
            
            return stored_id
            
        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            raise
    
    async def search_memories(
        self, 
        query: str, 
        limit: int = 10,
        score_threshold: float = 0.0
    ) -> List[MemorySearchResult]:
        """
        Search business knowledge using semantic similarity.
        
        Replaces search_business_knowledge() from Qdrant implementation.
        
        Args:
            query: Search query string
            limit: Maximum number of results
            score_threshold: Minimum similarity score
            
        Returns:
            List of search results with content, scores, and metadata
        """
        try:
            search_data = {
                'query': query,
                'collection': self.collection_name,
                'limit': limit,
                'score_threshold': score_threshold,
                'customer_id': self.customer_id
            }
            
            response = await self._make_request('POST', '/api/v1/search', search_data)
            
            results = []
            for item in response.get('results', []):
                result = MemorySearchResult(
                    id=item.get('id', ''),
                    content=item.get('content', ''),
                    score=float(item.get('score', 0.0)),
                    metadata=item.get('metadata', {}),
                    timestamp=item.get('metadata', {}).get('timestamp')
                )
                results.append(result)
            
            logger.info(f"Found {len(results)} memories for query: {query[:50]}...")
            return results
            
        except Exception as e:
            logger.error(f"Failed to search memories: {e}")
            return []
    
    async def delete_memory(self, memory_id: str) -> bool:
        """
        Delete a specific memory by ID.
        
        Args:
            memory_id: ID of memory to delete
            
        Returns:
            True if deletion was successful
        """
        try:
            await self._make_request('DELETE', f'/api/v1/memories/{memory_id}')
            logger.info(f"Deleted memory {memory_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete memory {memory_id}: {e}")
            return False
    
    async def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get statistics about customer's memory collection.
        
        Returns:
            Dictionary with memory statistics
        """
        try:
            stats_data = {
                'collection': self.collection_name,
                'customer_id': self.customer_id
            }
            
            response = await self._make_request('POST', '/api/v1/stats', stats_data)
            return response.get('stats', {})
            
        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return {}
    
    async def trigger_consolidation(self) -> Dict[str, Any]:
        """
        Trigger autonomous memory consolidation for the customer.
        
        This is a unique feature of MCP Memory Service that automatically
        organizes and optimizes stored memories.
        
        Returns:
            Consolidation results and statistics
        """
        try:
            consolidation_data = {
                'collection': self.collection_name,
                'customer_id': self.customer_id,
                'mode': 'business_knowledge'
            }
            
            response = await self._make_request('POST', '/api/v1/consolidate', consolidation_data)
            
            logger.info(f"Memory consolidation triggered for customer {self.customer_id}")
            return response
            
        except Exception as e:
            logger.error(f"Failed to trigger consolidation: {e}")
            return {'error': str(e)}
    
    async def health_check(self) -> bool:
        """
        Check if MCP Memory Service is healthy and responsive.
        
        Returns:
            True if service is healthy
        """
        try:
            response = await self._make_request('GET', '/health')
            return response.get('status') == 'healthy'
            
        except Exception as e:
            logger.warning(f"MCP Memory Service health check failed: {e}")
            return False

# Backwards compatibility alias
MCPMemoryClient = MCPMemoryServiceClient