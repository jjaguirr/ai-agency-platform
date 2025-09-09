"""
Unified Context Store

Core context storage and retrieval system that enables seamless multi-channel
conversation context preservation with <500ms performance targets.

This module provides:
- Unified conversation context storage across all channels
- High-performance context retrieval and injection
- Cross-channel conversation threading
- Real-time context synchronization
- Customer isolation compliance
"""

import asyncio
import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager

import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update, delete, and_, or_
import redis.asyncio as redis

from ..database.models import (
    ContextEntryModel,
    ConversationThreadModel,
    CustomerContextModel
)
# Lazy import to avoid circular dependency
# from ..integrations.personality_engine_integration import PersonalityEngineConnector


logger = logging.getLogger(__name__)


class ContextStorageError(Exception):
    """Raised when context storage operations fail"""
    pass


class ContextNotFoundError(Exception):
    """Raised when requested context is not found"""
    pass


class ContextRetrievalTimeoutError(Exception):
    """Raised when context retrieval exceeds timeout threshold"""
    pass


@dataclass
class ContextEntry:
    """Data model for individual context entries"""
    customer_id: str
    channel: str
    conversation_thread: str
    timestamp: datetime
    content: str
    metadata: Dict[str, Any] = None
    entry_id: Optional[str] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContextEntry':
        """Create from dictionary"""
        if isinstance(data['timestamp'], str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


@dataclass
class ConversationThread:
    """Data model for conversation threads spanning multiple channels"""
    thread_id: str
    customer_id: str
    entries: List[ContextEntry]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    @property
    def channels(self) -> List[str]:
        """Get unique channels involved in this thread"""
        return list(set(entry.channel for entry in self.entries))
    
    def get_chronological_entries(self) -> List[ContextEntry]:
        """Get entries sorted chronologically"""
        return sorted(self.entries, key=lambda x: x.timestamp)
    
    def generate_summary(self, max_words: int = 50) -> str:
        """Generate concise summary of conversation thread"""
        entries = self.get_chronological_entries()
        if not entries:
            return ""
        
        # Combine content from all entries
        combined_content = " ".join(entry.content for entry in entries)
        
        # Extract key topics and themes (simplified implementation)
        words = combined_content.split()
        if len(words) <= max_words:
            return combined_content
        
        # Return first max_words with proper sentence ending
        truncated = " ".join(words[:max_words])
        last_period = truncated.rfind('.')
        if last_period > len(truncated) * 0.7:  # If sentence boundary is reasonable
            truncated = truncated[:last_period + 1]
        
        return truncated + "..." if len(words) > max_words else truncated


@dataclass
class CustomerContext:
    """Aggregated context for a customer across all channels"""
    customer_id: str
    active_threads: Dict[str, ConversationThread]
    channels_used: List[str]
    preferences: Dict[str, Any]
    business_context: Dict[str, Any]
    last_interaction: Optional[datetime] = None
    
    def get_recent_activity(self, hours: int = 24) -> List[ContextEntry]:
        """Get recent activity across all channels"""
        cutoff = datetime.now() - timedelta(hours=hours)
        recent_entries = []
        
        for thread in self.active_threads.values():
            recent_entries.extend([
                entry for entry in thread.entries
                if entry.timestamp >= cutoff
            ])
        
        return sorted(recent_entries, key=lambda x: x.timestamp, reverse=True)


@dataclass
class StorageResult:
    """Result of context storage operation"""
    success: bool
    entry_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    storage_time_ms: Optional[float] = None
    error: Optional[str] = None


@dataclass
class BulkStorageResult:
    """Result of bulk context storage operations"""
    successful: List[StorageResult]
    failed: List[StorageResult]
    total_time_ms: float
    average_storage_time_ms: float


@dataclass
class SearchResult:
    """Result of context search operation"""
    entry: ContextEntry
    relevance_score: float
    highlighted_content: str


class UnifiedContextStore:
    """
    High-performance unified context store for multi-channel conversations
    
    Features:
    - <500ms context retrieval and storage
    - Cross-channel conversation threading
    - Real-time context synchronization
    - Customer isolation compliance
    - Automatic context cleanup and archival
    """
    
    def __init__(
        self,
        database_url: str = None,
        redis_url: str = None,
        performance_target_ms: int = 500,
        cache_ttl_seconds: int = 3600
    ):
        self.database_url = database_url or "postgresql+asyncpg://context_user:context_pass@localhost:5432/context_db"
        self.redis_url = redis_url or "redis://localhost:6379"
        self.performance_target_ms = performance_target_ms
        self.cache_ttl = cache_ttl_seconds
        
        self.engine = None
        self.session_factory = None
        self.redis_client = None
        self.personality_connector = None
        
        # Performance tracking
        self.stats = {
            "storage_operations": 0,
            "retrieval_operations": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "average_storage_time_ms": 0,
            "average_retrieval_time_ms": 0
        }
    
    async def initialize(self):
        """Initialize database connections and cache"""
        try:
            # Initialize database
            self.engine = create_async_engine(
                self.database_url,
                pool_size=20,
                max_overflow=30,
                pool_pre_ping=True,
                echo=False
            )
            
            self.session_factory = sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            # Initialize Redis cache
            self.redis_client = redis.from_url(
                self.redis_url,
                max_connections=20,
                decode_responses=True
            )
            
            # Test connections
            async with self.session_factory() as session:
                await session.execute(select(1))
            
            await self.redis_client.ping()
            
            # Initialize personality engine connector (lazy import)
            try:
                from ..integrations.personality_engine_integration import PersonalityEngineConnector
                self.personality_connector = PersonalityEngineConnector()
                await self.personality_connector.initialize()
            except ImportError:
                self.personality_connector = None
                logger.warning("PersonalityEngineConnector not available")
            
            logger.info("UnifiedContextStore initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize UnifiedContextStore: {e}")
            raise ContextStorageError(f"Initialization failed: {e}")
    
    async def store_context(self, context_entry: ContextEntry) -> StorageResult:
        """
        Store context entry with <500ms performance target
        
        Args:
            context_entry: Context entry to store
            
        Returns:
            StorageResult with operation details
        """
        start_time = time.time()
        
        try:
            async with self.session_factory() as session:
                # Create database model
                db_entry = ContextEntryModel(
                    customer_id=context_entry.customer_id,
                    channel=context_entry.channel,
                    conversation_thread=context_entry.conversation_thread,
                    timestamp=context_entry.timestamp,
                    content=context_entry.content,
                    context_metadata=context_entry.metadata
                )
                
                session.add(db_entry)
                await session.commit()
                await session.refresh(db_entry)
                
                # Cache the entry for fast retrieval
                cache_key = self._get_cache_key(
                    context_entry.customer_id,
                    context_entry.channel,
                    context_entry.conversation_thread
                )
                
                await self.redis_client.setex(
                    cache_key,
                    self.cache_ttl,
                    json.dumps(context_entry.to_dict())
                )
                
                # Update conversation thread cache
                await self._update_thread_cache(context_entry)
                
                storage_time = (time.time() - start_time) * 1000
                
                # Update performance stats
                self.stats["storage_operations"] += 1
                self.stats["average_storage_time_ms"] = (
                    (self.stats["average_storage_time_ms"] * (self.stats["storage_operations"] - 1) + storage_time)
                    / self.stats["storage_operations"]
                )
                
                logger.debug(f"Context stored in {storage_time:.2f}ms for customer {context_entry.customer_id}")
                
                return StorageResult(
                    success=True,
                    entry_id=str(db_entry.id),
                    timestamp=context_entry.timestamp,
                    storage_time_ms=storage_time
                )
                
        except Exception as e:
            storage_time = (time.time() - start_time) * 1000
            logger.error(f"Context storage failed in {storage_time:.2f}ms: {e}")
            
            return StorageResult(
                success=False,
                storage_time_ms=storage_time,
                error=str(e)
            )
    
    async def get_context(
        self,
        customer_id: str,
        channel: str,
        thread_id: Optional[str] = None,
        timeout: float = None
    ) -> ContextEntry:
        """
        Retrieve context with <500ms performance target
        
        Args:
            customer_id: Customer identifier
            channel: Communication channel
            thread_id: Optional conversation thread ID
            timeout: Optional timeout in seconds
            
        Returns:
            ContextEntry with conversation context
            
        Raises:
            ContextNotFoundError: If context not found
            ContextRetrievalTimeoutError: If retrieval exceeds timeout
        """
        start_time = time.time()
        timeout = timeout or (self.performance_target_ms / 1000)
        
        try:
            # Try cache first
            cache_key = self._get_cache_key(customer_id, channel, thread_id)
            cached_data = await asyncio.wait_for(
                self.redis_client.get(cache_key),
                timeout=timeout / 2  # Use half timeout for cache
            )
            
            if cached_data:
                self.stats["cache_hits"] += 1
                retrieval_time = (time.time() - start_time) * 1000
                
                logger.debug(f"Context retrieved from cache in {retrieval_time:.2f}ms")
                return ContextEntry.from_dict(json.loads(cached_data))
            
            self.stats["cache_misses"] += 1
            
            # Fallback to database
            async with self.session_factory() as session:
                query = select(ContextEntryModel).where(
                    and_(
                        ContextEntryModel.customer_id == customer_id,
                        ContextEntryModel.channel == channel
                    )
                )
                
                if thread_id:
                    query = query.where(ContextEntryModel.conversation_thread == thread_id)
                
                query = query.order_by(ContextEntryModel.timestamp.desc()).limit(1)
                
                result = await asyncio.wait_for(
                    session.execute(query),
                    timeout=timeout - (time.time() - start_time)
                )
                
                db_entry = result.scalar_one_or_none()
                
                if not db_entry:
                    raise ContextNotFoundError(
                        f"Context not found for customer {customer_id}, channel {channel}"
                    )
                
                context_entry = ContextEntry(
                    customer_id=db_entry.customer_id,
                    channel=db_entry.channel,
                    conversation_thread=db_entry.conversation_thread,
                    timestamp=db_entry.timestamp,
                    content=db_entry.content,
                    metadata=db_entry.context_metadata or {},
                    entry_id=str(db_entry.id)
                )
                
                # Cache for future retrieval
                await self.redis_client.setex(
                    cache_key,
                    self.cache_ttl,
                    json.dumps(context_entry.to_dict())
                )
                
                retrieval_time = (time.time() - start_time) * 1000
                
                # Update performance stats
                self.stats["retrieval_operations"] += 1
                self.stats["average_retrieval_time_ms"] = (
                    (self.stats["average_retrieval_time_ms"] * (self.stats["retrieval_operations"] - 1) + retrieval_time)
                    / self.stats["retrieval_operations"]
                )
                
                logger.debug(f"Context retrieved from database in {retrieval_time:.2f}ms")
                return context_entry
                
        except asyncio.TimeoutError:
            retrieval_time = (time.time() - start_time) * 1000
            raise ContextRetrievalTimeoutError(
                f"Context retrieval timed out after {retrieval_time:.2f}ms"
            )
        except ContextNotFoundError:
            raise
        except Exception as e:
            retrieval_time = (time.time() - start_time) * 1000
            logger.error(f"Context retrieval failed in {retrieval_time:.2f}ms: {e}")
            raise ContextStorageError(f"Retrieval failed: {e}")
    
    async def get_conversation_thread(
        self,
        customer_id: str,
        thread_id: str
    ) -> ConversationThread:
        """
        Retrieve complete conversation thread across all channels
        
        Args:
            customer_id: Customer identifier
            thread_id: Conversation thread identifier
            
        Returns:
            ConversationThread with all entries
        """
        start_time = time.time()
        
        try:
            # Check thread cache first
            thread_cache_key = f"thread:{customer_id}:{thread_id}"
            cached_thread = await self.redis_client.get(thread_cache_key)
            
            if cached_thread:
                self.stats["cache_hits"] += 1
                thread_data = json.loads(cached_thread)
                entries = [ContextEntry.from_dict(entry_data) for entry_data in thread_data["entries"]]
                
                return ConversationThread(
                    thread_id=thread_id,
                    customer_id=customer_id,
                    entries=entries
                )
            
            self.stats["cache_misses"] += 1
            
            # Retrieve from database
            async with self.session_factory() as session:
                query = select(ContextEntryModel).where(
                    and_(
                        ContextEntryModel.customer_id == customer_id,
                        ContextEntryModel.conversation_thread == thread_id
                    )
                ).order_by(ContextEntryModel.timestamp.asc())
                
                result = await session.execute(query)
                db_entries = result.scalars().all()
                
                if not db_entries:
                    raise ContextNotFoundError(
                        f"Conversation thread {thread_id} not found for customer {customer_id}"
                    )
                
                entries = []
                for db_entry in db_entries:
                    entry = ContextEntry(
                        customer_id=db_entry.customer_id,
                        channel=db_entry.channel,
                        conversation_thread=db_entry.conversation_thread,
                        timestamp=db_entry.timestamp,
                        content=db_entry.content,
                        metadata=db_entry.context_metadata or {},
                        entry_id=str(db_entry.id)
                    )
                    entries.append(entry)
                
                thread = ConversationThread(
                    thread_id=thread_id,
                    customer_id=customer_id,
                    entries=entries
                )
                
                # Cache the thread
                thread_data = {
                    "entries": [entry.to_dict() for entry in entries]
                }
                await self.redis_client.setex(
                    thread_cache_key,
                    self.cache_ttl,
                    json.dumps(thread_data)
                )
                
                retrieval_time = (time.time() - start_time) * 1000
                logger.debug(f"Thread retrieved in {retrieval_time:.2f}ms with {len(entries)} entries")
                
                return thread
                
        except Exception as e:
            logger.error(f"Thread retrieval failed: {e}")
            raise ContextStorageError(f"Thread retrieval failed: {e}")
    
    async def get_customer_context(self, customer_id: str) -> CustomerContext:
        """
        Get aggregated context for customer across all channels
        
        Args:
            customer_id: Customer identifier
            
        Returns:
            CustomerContext with aggregated information
        """
        start_time = time.time()
        
        try:
            async with self.session_factory() as session:
                # Get all threads for customer
                query = select(ContextEntryModel).where(
                    ContextEntryModel.customer_id == customer_id
                ).order_by(ContextEntryModel.timestamp.desc())
                
                result = await session.execute(query)
                db_entries = result.scalars().all()
                
                if not db_entries:
                    raise ContextNotFoundError(f"No context found for customer {customer_id}")
                
                # Group entries by thread
                threads = {}
                channels_used = set()
                
                for db_entry in db_entries:
                    thread_id = db_entry.conversation_thread
                    channels_used.add(db_entry.channel)
                    
                    if thread_id not in threads:
                        threads[thread_id] = []
                    
                    entry = ContextEntry(
                        customer_id=db_entry.customer_id,
                        channel=db_entry.channel,
                        conversation_thread=db_entry.conversation_thread,
                        timestamp=db_entry.timestamp,
                        content=db_entry.content,
                        metadata=db_entry.context_metadata or {},
                        entry_id=str(db_entry.id)
                    )
                    threads[thread_id].append(entry)
                
                # Create ConversationThread objects
                conversation_threads = {}
                for thread_id, entries in threads.items():
                    conversation_threads[thread_id] = ConversationThread(
                        thread_id=thread_id,
                        customer_id=customer_id,
                        entries=entries
                    )
                
                # Get customer preferences and business context
                # (This would typically come from a separate customer profile store)
                preferences = {}
                business_context = {}
                last_interaction = max(entry.timestamp for entry in db_entries) if db_entries else None
                
                customer_context = CustomerContext(
                    customer_id=customer_id,
                    active_threads=conversation_threads,
                    channels_used=list(channels_used),
                    preferences=preferences,
                    business_context=business_context,
                    last_interaction=last_interaction
                )
                
                retrieval_time = (time.time() - start_time) * 1000
                logger.debug(f"Customer context retrieved in {retrieval_time:.2f}ms")
                
                return customer_context
                
        except Exception as e:
            logger.error(f"Customer context retrieval failed: {e}")
            raise ContextStorageError(f"Customer context retrieval failed: {e}")
    
    async def update_context(self, entry_id: str, updates: Dict[str, Any]) -> StorageResult:
        """
        Update existing context entry
        
        Args:
            entry_id: Context entry identifier
            updates: Fields to update
            
        Returns:
            StorageResult with operation details
        """
        start_time = time.time()
        
        try:
            async with self.session_factory() as session:
                query = update(ContextEntryModel).where(
                    ContextEntryModel.id == int(entry_id)
                ).values(**updates)
                
                result = await session.execute(query)
                await session.commit()
                
                if result.rowcount == 0:
                    raise ContextNotFoundError(f"Context entry {entry_id} not found")
                
                # Invalidate cache
                # (Would need to implement cache invalidation by entry_id)
                
                update_time = (time.time() - start_time) * 1000
                logger.debug(f"Context updated in {update_time:.2f}ms")
                
                return StorageResult(
                    success=True,
                    entry_id=entry_id,
                    timestamp=datetime.now(),
                    storage_time_ms=update_time
                )
                
        except Exception as e:
            update_time = (time.time() - start_time) * 1000
            logger.error(f"Context update failed in {update_time:.2f}ms: {e}")
            
            return StorageResult(
                success=False,
                storage_time_ms=update_time,
                error=str(e)
            )
    
    async def search_contexts(
        self,
        customer_id: str,
        query: str,
        limit: int = 10
    ) -> List[SearchResult]:
        """
        Search contexts by content keywords
        
        Args:
            customer_id: Customer identifier
            query: Search query
            limit: Maximum results to return
            
        Returns:
            List of SearchResult objects
        """
        start_time = time.time()
        
        try:
            async with self.session_factory() as session:
                # Simple text search (would use full-text search in production)
                search_query = select(ContextEntryModel).where(
                    and_(
                        ContextEntryModel.customer_id == customer_id,
                        ContextEntryModel.content.ilike(f"%{query}%")
                    )
                ).order_by(ContextEntryModel.timestamp.desc()).limit(limit)
                
                result = await session.execute(search_query)
                db_entries = result.scalars().all()
                
                search_results = []
                for db_entry in db_entries:
                    entry = ContextEntry(
                        customer_id=db_entry.customer_id,
                        channel=db_entry.channel,
                        conversation_thread=db_entry.conversation_thread,
                        timestamp=db_entry.timestamp,
                        content=db_entry.content,
                        metadata=db_entry.context_metadata or {},
                        entry_id=str(db_entry.id)
                    )
                    
                    # Simple relevance scoring
                    relevance_score = min(1.0, db_entry.content.lower().count(query.lower()) * 0.1 + 0.5)
                    
                    # Highlight query terms (simplified)
                    highlighted_content = db_entry.content.replace(
                        query,
                        f"**{query}**"
                    )
                    
                    search_results.append(SearchResult(
                        entry=entry,
                        relevance_score=relevance_score,
                        highlighted_content=highlighted_content
                    ))
                
                search_time = (time.time() - start_time) * 1000
                logger.debug(f"Context search completed in {search_time:.2f}ms, found {len(search_results)} results")
                
                return search_results
                
        except Exception as e:
            logger.error(f"Context search failed: {e}")
            raise ContextStorageError(f"Search failed: {e}")
    
    async def bulk_store_contexts(self, contexts: List[ContextEntry]) -> BulkStorageResult:
        """
        Store multiple contexts efficiently
        
        Args:
            contexts: List of context entries to store
            
        Returns:
            BulkStorageResult with operation summary
        """
        start_time = time.time()
        successful = []
        failed = []
        
        try:
            async with self.session_factory() as session:
                db_entries = []
                for context in contexts:
                    db_entry = ContextEntryModel(
                        customer_id=context.customer_id,
                        channel=context.channel,
                        conversation_thread=context.conversation_thread,
                        timestamp=context.timestamp,
                        content=context.content,
                        metadata=context.metadata
                    )
                    db_entries.append(db_entry)
                
                session.add_all(db_entries)
                await session.commit()
                
                # All successful if we reach here
                storage_time = (time.time() - start_time) * 1000
                avg_time = storage_time / len(contexts)
                
                for i, context in enumerate(contexts):
                    successful.append(StorageResult(
                        success=True,
                        entry_id=str(db_entries[i].id),
                        timestamp=context.timestamp,
                        storage_time_ms=avg_time
                    ))
                
                logger.info(f"Bulk stored {len(contexts)} contexts in {storage_time:.2f}ms")
                
        except Exception as e:
            storage_time = (time.time() - start_time) * 1000
            logger.error(f"Bulk storage failed: {e}")
            
            # Mark all as failed
            for context in contexts:
                failed.append(StorageResult(
                    success=False,
                    storage_time_ms=storage_time / len(contexts),
                    error=str(e)
                ))
        
        total_time = (time.time() - start_time) * 1000
        avg_time = total_time / len(contexts) if contexts else 0
        
        return BulkStorageResult(
            successful=successful,
            failed=failed,
            total_time_ms=total_time,
            average_storage_time_ms=avg_time
        )
    
    async def cleanup_expired_contexts(self, retention_days: int = 30) -> Dict[str, int]:
        """
        Clean up expired contexts based on retention policy
        
        Args:
            retention_days: Number of days to retain contexts
            
        Returns:
            Dictionary with cleanup statistics
        """
        start_time = time.time()
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        
        try:
            async with self.session_factory() as session:
                # Archive old contexts (simplified - would move to archive table)
                delete_query = delete(ContextEntryModel).where(
                    ContextEntryModel.timestamp < cutoff_date
                )
                
                result = await session.execute(delete_query)
                await session.commit()
                
                cleanup_time = (time.time() - start_time) * 1000
                contexts_archived = result.rowcount
                
                logger.info(f"Cleaned up {contexts_archived} expired contexts in {cleanup_time:.2f}ms")
                
                return {
                    "contexts_archived": contexts_archived,
                    "cleanup_time_ms": cleanup_time,
                    "retention_days": retention_days
                }
                
        except Exception as e:
            logger.error(f"Context cleanup failed: {e}")
            raise ContextStorageError(f"Cleanup failed: {e}")
    
    async def update_business_context(
        self,
        customer_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update business context for real-time synchronization
        
        Args:
            customer_id: Customer identifier
            updates: Business context updates
            
        Returns:
            True if successful
        """
        try:
            # Update cache immediately for real-time sync
            business_context_key = f"business_context:{customer_id}"
            
            # Get existing context
            existing_context = await self.redis_client.get(business_context_key)
            if existing_context:
                context_data = json.loads(existing_context)
            else:
                context_data = {}
            
            # Merge updates
            context_data.update(updates)
            context_data["updated_at"] = datetime.now().isoformat()
            
            # Store updated context
            await self.redis_client.setex(
                business_context_key,
                self.cache_ttl,
                json.dumps(context_data)
            )
            
            # Invalidate related context caches to force refresh
            pattern = f"context:{customer_id}:*"
            keys = await self.redis_client.keys(pattern)
            if keys:
                await self.redis_client.delete(*keys)
            
            logger.debug(f"Business context updated for customer {customer_id}")
            return True
            
        except Exception as e:
            logger.error(f"Business context update failed: {e}")
            return False
    
    def _get_cache_key(self, customer_id: str, channel: str, thread_id: Optional[str] = None) -> str:
        """Generate cache key for context entry"""
        if thread_id:
            return f"context:{customer_id}:{channel}:{thread_id}"
        return f"context:{customer_id}:{channel}"
    
    async def _update_thread_cache(self, context_entry: ContextEntry):
        """Update conversation thread cache with new entry"""
        try:
            thread_cache_key = f"thread:{context_entry.customer_id}:{context_entry.conversation_thread}"
            
            # Get existing thread data
            cached_thread = await self.redis_client.get(thread_cache_key)
            if cached_thread:
                thread_data = json.loads(cached_thread)
                entries = thread_data.get("entries", [])
            else:
                entries = []
            
            # Add new entry
            entries.append(context_entry.to_dict())
            
            # Sort by timestamp
            entries.sort(key=lambda x: x["timestamp"])
            
            # Update cache
            thread_data = {"entries": entries}
            await self.redis_client.setex(
                thread_cache_key,
                self.cache_ttl,
                json.dumps(thread_data)
            )
            
        except Exception as e:
            logger.warning(f"Failed to update thread cache: {e}")
    
    async def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for monitoring"""
        return {
            **self.stats,
            "cache_hit_rate": (
                self.stats["cache_hits"] / max(1, self.stats["cache_hits"] + self.stats["cache_misses"])
            ),
            "performance_target_ms": self.performance_target_ms,
            "performance_sla_met": (
                self.stats["average_retrieval_time_ms"] < self.performance_target_ms and
                self.stats["average_storage_time_ms"] < self.performance_target_ms
            )
        }
    
    async def close(self):
        """Clean shutdown of connections"""
        if self.redis_client:
            await self.redis_client.close()
        if self.engine:
            await self.engine.dispose()
        if self.personality_connector:
            await self.personality_connector.close()
        
        logger.info("UnifiedContextStore closed")