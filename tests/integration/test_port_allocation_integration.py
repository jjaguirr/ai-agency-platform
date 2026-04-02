#!/usr/bin/env python3
"""
AI Agency Platform - Port Allocation Integration Tests
Phase 3: Comprehensive Integration Testing

Tests the complete port allocation and infrastructure orchestration system
including conflict resolution, customer isolation, and performance validation.
"""

import asyncio
import os
import pytest
import time
import logging
from typing import Dict, List
from unittest.mock import Mock, patch

# port_allocator and infrastructure_orchestrator hard-import asyncpg/redis.
pytest.importorskip("asyncpg")
pytest.importorskip("redis")

from tests.conftest import requires_live_services

pytestmark = [pytest.mark.integration, requires_live_services]

from src.infrastructure.port_allocator import (
    PortAllocator, ServiceType, create_port_allocator, allocate_customer_ports
)
from src.infrastructure.infrastructure_orchestrator import (
    InfrastructureOrchestrator, create_infrastructure_orchestrator
)
from src.infrastructure.docker_compose_generator import DockerComposeGenerator

# Configure test logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestPortAllocationIntegration:
    """Integration tests for port allocation system"""
    
    @pytest.fixture
    async def port_allocator(self):
        """Create test port allocator with in-memory storage"""
        # Use test database URLs
        redis_url = "redis://localhost:6379/15"  # Test database
        postgres_url = "postgresql://mcphub:mcphub_password@localhost:5432/mcphub_test"
        
        allocator = await create_port_allocator(redis_url=redis_url, postgres_url=postgres_url)
        yield allocator
        await allocator.close()
    
    @pytest.mark.asyncio
    async def test_basic_port_allocation(self, port_allocator):
        """Test basic port allocation functionality"""
        customer_id = "test_customer_001"
        service_type = ServiceType.POSTGRES
        
        # Allocate port
        allocation = await port_allocator.allocate_port(customer_id, service_type)
        
        assert allocation.customer_id == customer_id
        assert allocation.service_type == service_type
        assert 31000 <= allocation.port <= 31999  # PostgreSQL range
        assert allocation.allocated_at is not None
    
    @pytest.mark.asyncio
    async def test_multiple_service_allocation(self, port_allocator):
        """Test allocating ports for multiple services"""
        customer_id = "test_customer_002"
        services = [ServiceType.POSTGRES, ServiceType.REDIS, ServiceType.QDRANT]
        
        # Allocate ports for all services
        allocated_ports = await allocate_customer_ports(port_allocator, customer_id, services)
        
        assert len(allocated_ports) == 3
        assert ServiceType.POSTGRES in allocated_ports
        assert ServiceType.REDIS in allocated_ports
        assert ServiceType.QDRANT in allocated_ports
        
        # Verify port ranges
        assert 31000 <= allocated_ports[ServiceType.POSTGRES] <= 31999
        assert 32000 <= allocated_ports[ServiceType.REDIS] <= 32999
        assert 33000 <= allocated_ports[ServiceType.QDRANT] <= 33999
        
        # Verify all ports are unique
        ports = list(allocated_ports.values())
        assert len(ports) == len(set(ports))
    
    @pytest.mark.asyncio
    async def test_port_conflict_resolution(self, port_allocator):
        """Test port conflict detection and resolution"""
        customer1 = "test_customer_003a"
        customer2 = "test_customer_003b"
        service_type = ServiceType.POSTGRES
        
        # Allocate port for first customer
        allocation1 = await port_allocator.allocate_port(customer1, service_type)
        
        # Try to allocate preferred port (should be taken)
        preferred_port = allocation1.port
        allocation2 = await port_allocator.allocate_port(
            customer2, service_type, preferred_port=preferred_port
        )
        
        # Should get different port due to conflict
        assert allocation1.port != allocation2.port
        assert allocation2.port != preferred_port
        assert 31000 <= allocation2.port <= 31999
    
    @pytest.mark.asyncio
    async def test_customer_isolation(self, port_allocator):
        """Test complete customer isolation with dedicated ports"""
        customers = ["customer_isolation_001", "customer_isolation_002", "customer_isolation_003"]
        services = [ServiceType.POSTGRES, ServiceType.REDIS, ServiceType.QDRANT, ServiceType.MCP_SERVER]
        
        all_allocations = {}
        
        # Allocate ports for multiple customers
        for customer_id in customers:
            customer_ports = await allocate_customer_ports(port_allocator, customer_id, services)
            all_allocations[customer_id] = customer_ports
        
        # Verify complete isolation - no port conflicts
        all_ports = []
        for customer_ports in all_allocations.values():
            all_ports.extend(customer_ports.values())
        
        # All ports should be unique
        assert len(all_ports) == len(set(all_ports))
        
        # Each customer should have all required services
        for customer_id in customers:
            customer_ports = all_allocations[customer_id]
            assert len(customer_ports) == len(services)
            for service_type in services:
                assert service_type in customer_ports
    
    @pytest.mark.asyncio
    async def test_port_deallocation(self, port_allocator):
        """Test port deallocation and cleanup"""
        customer_id = "test_customer_004"
        service_type = ServiceType.REDIS
        
        # Allocate port
        allocation = await port_allocator.allocate_port(customer_id, service_type)
        allocated_port = allocation.port
        
        # Verify allocation exists
        customer_ports = await port_allocator.get_customer_ports(customer_id)
        assert service_type in customer_ports
        assert customer_ports[service_type] == allocated_port
        
        # Deallocate port
        success = await port_allocator.deallocate_port(customer_id, service_type)
        assert success
        
        # Verify deallocation
        customer_ports = await port_allocator.get_customer_ports(customer_id)
        assert service_type not in customer_ports
        
        # Port should be available for reallocation
        new_allocation = await port_allocator.allocate_port(
            "test_customer_005", service_type, preferred_port=allocated_port
        )
        assert new_allocation.port == allocated_port
    
    @pytest.mark.asyncio
    async def test_performance_benchmarks(self, port_allocator):
        """Test port allocation performance meets SLA requirements"""
        num_customers = 50
        services_per_customer = 3
        max_allocation_time_ms = 100  # SLA requirement
        
        allocation_times = []
        
        for i in range(num_customers):
            customer_id = f"perf_test_customer_{i:03d}"
            services = [ServiceType.POSTGRES, ServiceType.REDIS, ServiceType.QDRANT]
            
            start_time = time.time()
            allocated_ports = await allocate_customer_ports(port_allocator, customer_id, services)
            allocation_time = (time.time() - start_time) * 1000
            
            allocation_times.append(allocation_time)
            
            # Verify successful allocation
            assert len(allocated_ports) == services_per_customer
        
        # Performance validation
        avg_allocation_time = sum(allocation_times) / len(allocation_times)
        max_allocation_time = max(allocation_times)
        
        logger.info(f"Performance Results:")
        logger.info(f"  Average allocation time: {avg_allocation_time:.2f}ms")
        logger.info(f"  Maximum allocation time: {max_allocation_time:.2f}ms")
        logger.info(f"  Total customers processed: {num_customers}")
        
        # Validate SLA compliance
        assert avg_allocation_time < max_allocation_time_ms, f"Average allocation time {avg_allocation_time:.2f}ms exceeds SLA"
        assert max_allocation_time < max_allocation_time_ms * 2, f"Maximum allocation time {max_allocation_time:.2f}ms exceeds tolerance"
    
    @pytest.mark.asyncio
    async def test_port_utilization_monitoring(self, port_allocator):
        """Test port utilization tracking and metrics"""
        # Allocate some ports
        customers = [f"util_test_customer_{i:02d}" for i in range(5)]
        service_type = ServiceType.POSTGRES
        
        for customer_id in customers:
            await port_allocator.allocate_port(customer_id, service_type)
        
        # Get utilization metrics
        utilization = await port_allocator.get_port_utilization()
        
        assert "postgres" in utilization
        postgres_util = utilization["postgres"]
        
        assert postgres_util["allocated_ports"] == len(customers)
        assert postgres_util["total_ports"] == 1000  # PostgreSQL range size
        assert postgres_util["available_ports"] == postgres_util["total_ports"] - postgres_util["allocated_ports"]
        assert 0 <= postgres_util["utilization_percentage"] <= 100
        
        # Verify metrics structure
        metrics = port_allocator.get_allocation_metrics()
        assert "total_allocations" in metrics
        assert "successful_allocations" in metrics
        assert "active_allocations" in metrics
        assert "port_ranges" in metrics
    
    @pytest.mark.asyncio
    async def test_allocation_persistence(self, port_allocator):
        """Test allocation persistence across restarts"""
        customer_id = "persistence_test_001"
        services = [ServiceType.POSTGRES, ServiceType.REDIS]
        
        # Allocate ports
        original_ports = await allocate_customer_ports(port_allocator, customer_id, services)
        
        # Simulate restart by creating new allocator instance
        await port_allocator.close()
        
        redis_url = "redis://localhost:6379/15"
        postgres_url = "postgresql://mcphub:mcphub_password@localhost:5432/mcphub_test"
        new_allocator = await create_port_allocator(redis_url=redis_url, postgres_url=postgres_url)
        
        try:
            # Load existing allocations
            restored_ports = await new_allocator.get_customer_ports(customer_id)
            
            # Verify allocations were restored
            assert len(restored_ports) == len(original_ports)
            for service_type, port in original_ports.items():
                assert service_type in restored_ports
                assert restored_ports[service_type] == port
        
        finally:
            await new_allocator.close()


class TestInfrastructureOrchestrationIntegration:
    """Integration tests for infrastructure orchestration"""
    
    @pytest.fixture
    async def orchestrator(self):
        """Create test infrastructure orchestrator"""
        # Mock Docker client for testing
        mock_docker = Mock()
        mock_docker.ping.return_value = True
        mock_docker.containers.list.return_value = []
        
        with patch('docker.from_env', return_value=mock_docker):
            orchestrator = await create_infrastructure_orchestrator(
                redis_url="redis://localhost:6379/15",
                postgres_url="postgresql://mcphub:mcphub_password@localhost:5432/mcphub_test",
                docker_client=mock_docker
            )
            yield orchestrator
            await orchestrator.port_allocator.close()
    
    @pytest.mark.asyncio
    async def test_orchestrator_initialization(self, orchestrator):
        """Test orchestrator initialization"""
        assert orchestrator.port_allocator is not None
        assert orchestrator.docker_client is not None
        assert len(orchestrator.environments) >= 0
        
        # Test metrics
        metrics = orchestrator.get_orchestration_metrics()
        assert "environments_created" in metrics
        assert "active_environments" in metrics
    
    @pytest.mark.asyncio
    async def test_environment_provisioning_workflow(self, orchestrator):
        """Test complete environment provisioning workflow"""
        customer_id = "integration_test_001"
        tier = "professional"
        ai_model = "claude-3.5-sonnet"
        
        # Mock the actual Docker operations
        with patch.object(orchestrator, 'create_customer_network'), \
             patch.object(orchestrator, 'deploy_service') as mock_deploy, \
             patch.object(orchestrator, 'perform_health_check') as mock_health:
            
            # Configure mocks
            mock_deploy.return_value = Mock(
                service_type=ServiceType.POSTGRES,
                container_name=f"postgres-{customer_id}",
                port=31001,
                status="running"
            )
            mock_health.return_value = {
                "healthy_services": 5,
                "unhealthy_services": 0
            }
            
            # Provision environment
            environment = await orchestrator.provision_customer_environment(
                customer_id=customer_id,
                tier=tier,
                ai_model=ai_model
            )
            
            # Verify environment
            assert environment.customer_id == customer_id
            assert environment.tier == tier
            assert environment.status.value in ["healthy", "provisioning"]
            
            # Verify ports were allocated
            customer_ports = await orchestrator.port_allocator.get_customer_ports(customer_id)
            assert len(customer_ports) > 0


class TestDockerComposeIntegration:
    """Integration tests for Docker Compose generation"""
    
    @pytest.fixture
    async def compose_generator(self):
        """Create test Docker Compose generator"""
        port_allocator = await create_port_allocator(
            redis_url="redis://localhost:6379/15",
            postgres_url="postgresql://mcphub:mcphub_password@localhost:5432/mcphub_test"
        )
        
        generator = DockerComposeGenerator(
            port_allocator=port_allocator,
            output_dir="./tests/tmp/compose"
        )
        
        yield generator
        await port_allocator.close()
    
    @pytest.mark.asyncio
    async def test_compose_generation(self, compose_generator):
        """Test Docker Compose configuration generation"""
        customer_id = "compose_test_001"
        tier = "professional"
        ai_model = "claude-3.5-sonnet"
        
        # Allocate ports
        services = [ServiceType.POSTGRES, ServiceType.REDIS, ServiceType.QDRANT,
                   ServiceType.MCP_SERVER, ServiceType.MEMORY_MONITOR]
        allocated_ports = {}
        
        for service_type in services:
            allocation = await compose_generator.port_allocator.allocate_port(customer_id, service_type)
            allocated_ports[service_type] = allocation.port
        
        # Generate credentials
        credentials = {
            "postgres_password": "test_postgres_pass_123",
            "jwt_secret": "test_jwt_secret_456", 
            "encryption_key": "test_encryption_key_789"
        }
        
        # Generate compose configuration
        compose_file = await compose_generator.generate_customer_compose(
            customer_id=customer_id,
            tier=tier,
            ai_model=ai_model,
            credentials=credentials,
            allocated_ports=allocated_ports
        )
        
        # Verify file was created
        assert compose_file.exists()
        assert f"docker-compose.{customer_id}.yml" in str(compose_file)
        
        # Verify environment file was created
        env_file = compose_file.parent / f".env.{customer_id}"
        assert env_file.exists()
        
        # Basic content verification
        with open(compose_file, 'r') as f:
            content = f.read()
            assert customer_id in content
            assert "postgres" in content
            assert "redis" in content
    
    @pytest.mark.asyncio
    async def test_deployment_script_generation(self, compose_generator):
        """Test deployment script generation"""
        customer_id = "script_test_001"
        
        # Mock compose file
        compose_file = compose_generator.output_dir / f"docker-compose.{customer_id}.yml"
        compose_file.parent.mkdir(parents=True, exist_ok=True)
        compose_file.touch()
        
        # Generate deployment script
        script_file = compose_generator.generate_deployment_script(customer_id, compose_file)
        
        # Verify script was created
        assert script_file.exists()
        assert script_file.stat().st_mode & 0o111  # Check executable bit
        
        # Basic content verification
        with open(script_file, 'r') as f:
            content = f.read()
            assert customer_id in content
            assert "docker-compose" in content
            assert "#!/bin/bash" in content


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v", "--tb=short"])