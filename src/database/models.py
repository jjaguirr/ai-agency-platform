"""
Database Models for Multi-Channel Context Preservation

SQLAlchemy models for storing conversation context across channels
with high-performance indexing for <500ms retrieval targets.
"""

from datetime import datetime
from typing import Dict, Any, Optional
import json

from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Index, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

Base = declarative_base()


class ContextEntryModel(Base):
    """
    Core context entry model for storing individual conversation messages
    """
    __tablename__ = "context_entries"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(String(255), nullable=False, index=True)
    channel = Column(String(50), nullable=False, index=True)
    conversation_thread = Column(String(255), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    content = Column(Text, nullable=False)
    context_metadata = Column(JSON, nullable=True)
    
    # Performance optimization indexes
    __table_args__ = (
        Index('idx_customer_channel', 'customer_id', 'channel'),
        Index('idx_customer_thread', 'customer_id', 'conversation_thread'),
        Index('idx_customer_timestamp', 'customer_id', 'timestamp'),
        Index('idx_thread_timestamp', 'conversation_thread', 'timestamp'),
        Index('idx_customer_channel_thread', 'customer_id', 'channel', 'conversation_thread'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'customer_id': self.customer_id,
            'channel': self.channel,
            'conversation_thread': self.conversation_thread,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'content': self.content,
            'metadata': self.context_metadata or {}
        }


class ConversationThreadModel(Base):
    """
    Conversation thread model for cross-channel conversation tracking
    """
    __tablename__ = "conversation_threads"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    thread_id = Column(String(255), nullable=False, unique=True, index=True)
    customer_id = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    channels_involved = Column(JSON, nullable=True)  # List of channels in this thread
    summary = Column(Text, nullable=True)
    status = Column(String(50), default='active', index=True)
    
    # Relationships
    entries = relationship("ContextEntryModel", 
                          primaryjoin="ConversationThreadModel.thread_id == foreign(ContextEntryModel.conversation_thread)",
                          viewonly=True)
    
    __table_args__ = (
        Index('idx_customer_thread_id', 'customer_id', 'thread_id'),
        Index('idx_customer_status', 'customer_id', 'status'),
        Index('idx_updated_at', 'updated_at'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'thread_id': self.thread_id,
            'customer_id': self.customer_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'channels_involved': self.channels_involved or [],
            'summary': self.summary,
            'status': self.status
        }


class CustomerContextModel(Base):
    """
    Customer context model for storing aggregated customer information
    """
    __tablename__ = "customer_contexts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(String(255), nullable=False, unique=True, index=True)
    preferences = Column(JSON, nullable=True)
    business_context = Column(JSON, nullable=True)
    communication_style = Column(String(100), nullable=True)
    personality_profile = Column(JSON, nullable=True)
    active_threads_count = Column(Integer, default=0)
    last_interaction = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_last_interaction', 'last_interaction'),
        Index('idx_communication_style', 'communication_style'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'customer_id': self.customer_id,
            'preferences': self.preferences or {},
            'business_context': self.business_context or {},
            'communication_style': self.communication_style,
            'personality_profile': self.personality_profile or {},
            'active_threads_count': self.active_threads_count,
            'last_interaction': self.last_interaction.isoformat() if self.last_interaction else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class ChannelAdaptationLogModel(Base):
    """
    Log model for tracking channel adaptations and performance
    """
    __tablename__ = "channel_adaptation_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(String(255), nullable=False, index=True)
    from_channel = Column(String(50), nullable=False, index=True)
    to_channel = Column(String(50), nullable=False, index=True)
    conversation_thread = Column(String(255), nullable=False, index=True)
    adaptation_time_ms = Column(Integer, nullable=False)
    success = Column(String(10), nullable=False, index=True)  # 'success' or 'failure'
    error_message = Column(Text, nullable=True)
    personality_adapted = Column(String(10), nullable=False)  # 'true' or 'false'
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    __table_args__ = (
        Index('idx_customer_channels', 'customer_id', 'from_channel', 'to_channel'),
        Index('idx_success_timestamp', 'success', 'timestamp'),
        Index('idx_adaptation_performance', 'adaptation_time_ms', 'timestamp'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'customer_id': self.customer_id,
            'from_channel': self.from_channel,
            'to_channel': self.to_channel,
            'conversation_thread': self.conversation_thread,
            'adaptation_time_ms': self.adaptation_time_ms,
            'success': self.success,
            'error_message': self.error_message,
            'personality_adapted': self.personality_adapted,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }


class PerformanceMetricsModel(Base):
    """
    Model for storing system performance metrics
    """
    __tablename__ = "performance_metrics"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_type = Column(String(100), nullable=False, index=True)  # 'context_retrieval', 'adaptation', etc.
    metric_name = Column(String(100), nullable=False, index=True)
    metric_value = Column(String(255), nullable=False)
    customer_id = Column(String(255), nullable=True, index=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    context_metadata = Column(JSON, nullable=True)
    
    __table_args__ = (
        Index('idx_metric_type_timestamp', 'metric_type', 'timestamp'),
        Index('idx_metric_name_timestamp', 'metric_name', 'timestamp'),
        Index('idx_customer_metrics', 'customer_id', 'metric_type'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'metric_type': self.metric_type,
            'metric_name': self.metric_name,
            'metric_value': self.metric_value,
            'customer_id': self.customer_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'metadata': self.context_metadata or {}
        }


# Archive models for long-term storage

class ArchivedContextEntryModel(Base):
    """
    Archived context entries for long-term storage
    """
    __tablename__ = "archived_context_entries"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    original_id = Column(Integer, nullable=False, index=True)
    customer_id = Column(String(255), nullable=False, index=True)
    channel = Column(String(50), nullable=False, index=True)
    conversation_thread = Column(String(255), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    content = Column(Text, nullable=False)
    context_metadata = Column(JSON, nullable=True)
    archived_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    __table_args__ = (
        Index('idx_archived_customer', 'customer_id', 'archived_at'),
        Index('idx_archived_timestamp', 'timestamp', 'archived_at'),
    )


# Helper functions for database operations

def create_all_tables(engine):
    """Create all tables in the database"""
    Base.metadata.create_all(engine)


def get_context_entry_by_id(session, entry_id: int) -> Optional[ContextEntryModel]:
    """Get context entry by ID"""
    return session.query(ContextEntryModel).filter(ContextEntryModel.id == entry_id).first()


def get_context_entries_by_customer(
    session, 
    customer_id: str, 
    channel: Optional[str] = None,
    thread_id: Optional[str] = None,
    limit: int = 100
) -> list[ContextEntryModel]:
    """Get context entries for a customer"""
    query = session.query(ContextEntryModel).filter(ContextEntryModel.customer_id == customer_id)
    
    if channel:
        query = query.filter(ContextEntryModel.channel == channel)
    
    if thread_id:
        query = query.filter(ContextEntryModel.conversation_thread == thread_id)
    
    return query.order_by(ContextEntryModel.timestamp.desc()).limit(limit).all()


def get_conversation_thread(session, customer_id: str, thread_id: str) -> Optional[ConversationThreadModel]:
    """Get conversation thread"""
    return session.query(ConversationThreadModel).filter(
        ConversationThreadModel.customer_id == customer_id,
        ConversationThreadModel.thread_id == thread_id
    ).first()


def get_customer_context(session, customer_id: str) -> Optional[CustomerContextModel]:
    """Get customer context"""
    return session.query(CustomerContextModel).filter(
        CustomerContextModel.customer_id == customer_id
    ).first()


def create_or_update_customer_context(
    session,
    customer_id: str,
    preferences: Dict[str, Any] = None,
    business_context: Dict[str, Any] = None,
    communication_style: str = None,
    personality_profile: Dict[str, Any] = None
) -> CustomerContextModel:
    """Create or update customer context"""
    
    existing = get_customer_context(session, customer_id)
    
    if existing:
        # Update existing
        if preferences:
            existing.preferences = {**(existing.preferences or {}), **preferences}
        if business_context:
            existing.business_context = {**(existing.business_context or {}), **business_context}
        if communication_style:
            existing.communication_style = communication_style
        if personality_profile:
            existing.personality_profile = {**(existing.personality_profile or {}), **personality_profile}
        
        existing.updated_at = datetime.utcnow()
        return existing
    else:
        # Create new
        new_context = CustomerContextModel(
            customer_id=customer_id,
            preferences=preferences or {},
            business_context=business_context or {},
            communication_style=communication_style,
            personality_profile=personality_profile or {}
        )
        session.add(new_context)
        return new_context


def log_channel_adaptation(
    session,
    customer_id: str,
    from_channel: str,
    to_channel: str,
    conversation_thread: str,
    adaptation_time_ms: int,
    success: bool,
    error_message: str = None,
    personality_adapted: bool = False
):
    """Log channel adaptation for performance tracking"""
    
    log_entry = ChannelAdaptationLogModel(
        customer_id=customer_id,
        from_channel=from_channel,
        to_channel=to_channel,
        conversation_thread=conversation_thread,
        adaptation_time_ms=adaptation_time_ms,
        success='success' if success else 'failure',
        error_message=error_message,
        personality_adapted='true' if personality_adapted else 'false'
    )
    
    session.add(log_entry)


def record_performance_metric(
    session,
    metric_type: str,
    metric_name: str,
    metric_value: str,
    customer_id: str = None,
    metadata: Dict[str, Any] = None
):
    """Record performance metric"""
    
    metric = PerformanceMetricsModel(
        metric_type=metric_type,
        metric_name=metric_name,
        metric_value=metric_value,
        customer_id=customer_id,
        metadata=metadata or {}
    )
    
    session.add(metric)


def cleanup_old_metrics(session, days_to_keep: int = 30):
    """Clean up old performance metrics"""
    cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
    
    session.query(PerformanceMetricsModel).filter(
        PerformanceMetricsModel.timestamp < cutoff_date
    ).delete()


def archive_old_contexts(session, days_to_keep: int = 90):
    """Archive old context entries"""
    cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
    
    # Get old entries
    old_entries = session.query(ContextEntryModel).filter(
        ContextEntryModel.timestamp < cutoff_date
    ).all()
    
    # Move to archive
    for entry in old_entries:
        archived_entry = ArchivedContextEntryModel(
            original_id=entry.id,
            customer_id=entry.customer_id,
            channel=entry.channel,
            conversation_thread=entry.conversation_thread,
            timestamp=entry.timestamp,
            content=entry.content,
            context_metadata=entry.metadata
        )
        session.add(archived_entry)
    
    # Delete from main table
    session.query(ContextEntryModel).filter(
        ContextEntryModel.timestamp < cutoff_date
    ).delete()
    
    return len(old_entries)