"""
Memory Layer Infrastructure for AI Agency Platform

Provides per-customer memory isolation with hybrid architecture:
- Mem0: Semantic memory for business knowledge and patterns
- Redis: Working memory for active conversation context  
- PostgreSQL: Persistent storage for audit logs and compliance

Key Features:
- Per-customer isolation via unique user_id/agent_id
- <500ms memory recall performance SLA
- Zero cross-customer memory access
- Support for 100+ concurrent customers
"""

from .mem0_manager import EAMemoryManager, OptimizedMemoryRouter
from .isolation_validator import MemoryIsolationValidator
from .performance_monitor import MemoryPerformanceMonitor

__all__ = [
    "EAMemoryManager",
    "OptimizedMemoryRouter", 
    "MemoryIsolationValidator",
    "MemoryPerformanceMonitor"
]