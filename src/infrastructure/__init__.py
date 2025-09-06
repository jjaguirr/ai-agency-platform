"""
AI Agency Platform - Infrastructure Module
Phase 3: Port Allocation and Orchestration Logic

This module provides intelligent infrastructure orchestration with:
- Dynamic port allocation and conflict resolution  
- Customer environment isolation and provisioning
- Service orchestration and lifecycle management
- Performance monitoring and optimization
"""

from .port_allocator import (
    PortAllocator,
    ServiceType,
    PortRange,
    PortAllocation,
    create_port_allocator,
    allocate_customer_ports
)

from .infrastructure_orchestrator import (
    InfrastructureOrchestrator,
    CustomerEnvironment,
    ServiceInstance,
    DeploymentStatus,
    create_infrastructure_orchestrator
)

__version__ = "1.0.0"
__all__ = [
    "PortAllocator",
    "ServiceType", 
    "PortRange",
    "PortAllocation",
    "create_port_allocator",
    "allocate_customer_ports",
    "InfrastructureOrchestrator",
    "CustomerEnvironment",
    "ServiceInstance", 
    "DeploymentStatus",
    "create_infrastructure_orchestrator"
]