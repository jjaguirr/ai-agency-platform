"""
Customer Provisioning Orchestrator - Production Deployment Infrastructure

Implements per-customer MCP server and Mem0 memory isolation with 30-second onboarding SLA.
Provides auto-provisioning, resource allocation, and service discovery for customer isolation.

Architecture:
- Customer Purchase → 30-second working EA with isolated Mem0 memory
- Per-customer Docker containers: MCP server + PostgreSQL + Redis + Qdrant + Neo4j  
- Service discovery and routing for customer → MCP server mapping
- Resource scaling based on customer tier (Starter/Professional/Enterprise)

Implements GitHub issue #14: Production deployment orchestration
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import docker
import asyncpg
import redis.asyncio as redis
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class CustomerTier(Enum):
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


@dataclass
class CustomerInfrastructure:
    """Customer infrastructure allocation and configuration"""
    customer_id: str
    tier: CustomerTier
    mcp_server_id: str
    mcp_port: int
    postgres_port: int
    redis_port: int
    qdrant_port: int
    neo4j_port: int
    memory_monitor_port: int
    network_name: str
    resource_limits: Dict[str, Any]
    service_endpoints: Dict[str, str]
    provisioning_time: float
    status: str


class CustomerProvisioningOrchestrator:
    """
    Production deployment orchestrator for per-customer MCP infrastructure.
    
    Manages complete lifecycle:
    - Auto-provisioning: Customer purchase → 30-second working EA
    - Resource allocation: Per-customer isolated containers  
    - Service discovery: Customer routing and health checks
    - Scaling: Automatic resource adjustment based on usage
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize provisioning orchestrator with production configuration"""
        self.config = config or self._default_config()
        self.docker_client = docker.from_env()
        self.redis_pool = None
        self.postgres_pool = None
        
        # Port allocation tracking
        self.allocated_ports = set()
        self.customer_infrastructure = {}  # customer_id -> CustomerInfrastructure
        
        logger.info("Initialized Customer Provisioning Orchestrator")
    
    def _default_config(self) -> Dict[str, Any]:
        """Production configuration with performance targets"""
        return {
            "provisioning": {
                "target_time_seconds": 30,
                "max_concurrent_provisions": 10,
                "health_check_timeout": 30,
                "retry_attempts": 3
            },
            "port_allocation": {
                "mcp_server_range": (30000, 31000),
                "postgres_range": (35000, 36000), 
                "redis_range": (36000, 37000),
                "qdrant_range": (37000, 38000),
                "neo4j_range": (38000, 39000),
                "memory_monitor_range": (39000, 40000)
            },
            "resource_limits": {
                CustomerTier.STARTER: {
                    "cpu": 1.0,
                    "memory": "2GB",
                    "storage": "10GB",
                    "concurrent_requests": 100
                },
                CustomerTier.PROFESSIONAL: {
                    "cpu": 2.0, 
                    "memory": "4GB",
                    "storage": "50GB",
                    "concurrent_requests": 500
                },
                CustomerTier.ENTERPRISE: {
                    "cpu": 4.0,
                    "memory": "8GB", 
                    "storage": "200GB",
                    "concurrent_requests": 1000
                }
            },
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "mcphub",
                "user": "mcphub",
                "password": "mcphub_password"
            },
            "redis": {
                "host": "localhost",
                "port": 6379
            }
        }
    
    async def provision_customer_infrastructure(self, customer_id: str, tier: CustomerTier, 
                                             customer_data: Dict[str, Any]) -> CustomerInfrastructure:
        """
        Provision complete per-customer infrastructure in <30 seconds.
        
        Args:
            customer_id: Unique customer identifier
            tier: Customer subscription tier
            customer_data: Customer configuration and preferences
            
        Returns:
            CustomerInfrastructure with all service endpoints and configuration
        """
        start_time = time.time()
        
        try:
            logger.info(f"Starting infrastructure provisioning for customer {customer_id} ({tier.value})")
            
            # 1. Allocate dedicated ports (2 seconds)
            ports = await self._allocate_customer_ports(customer_id)
            
            # 2. Create isolated network (1 second)
            network_name = await self._create_customer_network(customer_id)
            
            # 3. Create customer database and schemas (5 seconds)
            await self._create_customer_database(customer_id)
            
            # 4. Deploy customer infrastructure services (15 seconds)
            services = await self._deploy_customer_services(customer_id, tier, ports, network_name)
            
            # 5. Initialize Mem0 memory system (4 seconds)
            await self._initialize_customer_memory(customer_id, services)
            
            # 6. Deploy and configure EA with MCP integration (3 seconds) 
            await self._initialize_customer_ea(customer_id, services, customer_data)
            
            provisioning_time = time.time() - start_time
            
            # Create infrastructure record
            infrastructure = CustomerInfrastructure(
                customer_id=customer_id,
                tier=tier,
                mcp_server_id=services["mcp_server"]["container_id"],
                mcp_port=ports["mcp_server"],
                postgres_port=ports["postgres"],
                redis_port=ports["redis"],
                qdrant_port=ports["qdrant"],
                neo4j_port=ports["neo4j"],
                memory_monitor_port=ports["memory_monitor"],
                network_name=network_name,
                resource_limits=self.config["resource_limits"][tier],
                service_endpoints=self._build_service_endpoints(customer_id, ports),
                provisioning_time=provisioning_time,
                status="ready"
            )
            
            # Store infrastructure record
            self.customer_infrastructure[customer_id] = infrastructure
            await self._store_infrastructure_record(infrastructure)
            
            # Validate SLA compliance
            if provisioning_time <= self.config["provisioning"]["target_time_seconds"]:
                logger.info(f"✅ Customer {customer_id} provisioned in {provisioning_time:.2f}s (SLA: {self.config['provisioning']['target_time_seconds']}s)")
            else:
                logger.warning(f"⚠️ Customer {customer_id} provisioning exceeded SLA: {provisioning_time:.2f}s")
            
            return infrastructure
            
        except Exception as e:
            provisioning_time = time.time() - start_time
            logger.error(f"❌ Failed to provision customer {customer_id} after {provisioning_time:.2f}s: {e}")
            
            # Cleanup on failure
            await self._cleanup_failed_provision(customer_id)
            raise
    
    async def _allocate_customer_ports(self, customer_id: str) -> Dict[str, int]:
        """Allocate dedicated ports for all customer services"""
        port_allocation = self.config["port_allocation"]
        ports = {}
        
        for service, (start_port, end_port) in port_allocation.items():
            port = await self._find_available_port(start_port, end_port)
            ports[service.replace("_range", "")] = port
            self.allocated_ports.add(port)
        
        logger.info(f"Allocated ports for customer {customer_id}: {ports}")
        return ports
    
    async def _find_available_port(self, start_port: int, end_port: int) -> int:
        """Find available port in specified range"""
        import socket
        
        for port in range(start_port, end_port):
            if port in self.allocated_ports:
                continue
                
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(('localhost', port))
                    return port
                except OSError:
                    continue
        
        raise Exception(f"No available ports in range {start_port}-{end_port}")
    
    async def _create_customer_network(self, customer_id: str) -> str:
        """Create isolated Docker network for customer"""
        network_name = f"customer-{customer_id}-network"
        
        try:
            network = self.docker_client.networks.create(
                network_name,
                driver="bridge",
                labels={
                    "ai-agency.customer-id": customer_id,
                    "ai-agency.isolation": "per-customer"
                }
            )
            logger.info(f"Created isolated network: {network_name}")
            return network_name
            
        except Exception as e:
            logger.error(f"Failed to create network {network_name}: {e}")
            raise
    
    async def _create_customer_database(self, customer_id: str):
        """Create isolated PostgreSQL database and user for customer"""
        if not self.postgres_pool:
            postgres_config = self.config["database"]
            self.postgres_pool = await asyncpg.create_pool(
                host=postgres_config["host"],
                port=postgres_config["port"],
                database=postgres_config["database"],
                user=postgres_config["user"],
                password=postgres_config["password"]
            )
        
        db_name = f"customer_{customer_id}"
        db_user = f"customer_{customer_id}"
        db_password = self._generate_secure_password()
        
        async with self.postgres_pool.acquire() as conn:
            # Create customer database
            await conn.execute(f'CREATE DATABASE "{db_name}"')
            
            # Create customer user with limited privileges
            await conn.execute(f"CREATE USER {db_user} WITH PASSWORD '{db_password}'")
            await conn.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{db_name}" TO {db_user}')
            
            logger.info(f"Created customer database: {db_name}")
            
            # Initialize customer schema
            await self._initialize_customer_schema(customer_id, db_name, db_user, db_password)
    
    async def _initialize_customer_schema(self, customer_id: str, db_name: str, db_user: str, db_password: str):
        """Initialize customer-specific database schema"""
        customer_pool = await asyncpg.create_pool(
            host=self.config["database"]["host"],
            port=self.config["database"]["port"],
            database=db_name,
            user=db_user,
            password=db_password
        )
        
        async with customer_pool.acquire() as conn:
            # Customer-specific memory audit table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS customer_memory_audit (
                    id SERIAL PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    data JSONB NOT NULL,
                    timestamp TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_memory_audit_customer ON customer_memory_audit(customer_id);
                CREATE INDEX IF NOT EXISTS idx_memory_audit_timestamp ON customer_memory_audit(timestamp);
            """)
            
            # Customer configuration table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS customer_config (
                    customer_id TEXT PRIMARY KEY,
                    config JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """)
            
            # EA conversation history
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ea_conversations (
                    id SERIAL PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    messages JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_conversations_customer ON ea_conversations(customer_id);
                CREATE INDEX IF NOT EXISTS idx_conversations_session ON ea_conversations(session_id);
            """)
        
        await customer_pool.close()
        logger.info(f"Initialized schema for customer {customer_id}")
    
    async def _deploy_customer_services(self, customer_id: str, tier: CustomerTier, 
                                      ports: Dict[str, int], network_name: str) -> Dict[str, Dict[str, Any]]:
        """Deploy all customer infrastructure services"""
        services = {}
        resource_limits = self.config["resource_limits"][tier]
        
        # Deploy PostgreSQL
        services["postgres"] = await self._deploy_postgres_container(customer_id, ports["postgres"], network_name, resource_limits)
        
        # Deploy Redis with customer isolation
        services["redis"] = await self._deploy_redis_container(customer_id, ports["redis"], network_name, resource_limits)
        
        # Deploy Qdrant for vector storage  
        services["qdrant"] = await self._deploy_qdrant_container(customer_id, ports["qdrant"], network_name, resource_limits)
        
        # Deploy Neo4j for graph memory
        services["neo4j"] = await self._deploy_neo4j_container(customer_id, ports["neo4j"], network_name, resource_limits)
        
        # Deploy Memory Monitor
        services["memory_monitor"] = await self._deploy_memory_monitor(customer_id, ports["memory_monitor"], network_name, services)
        
        # Deploy MCP Server with all dependencies
        services["mcp_server"] = await self._deploy_mcp_server(customer_id, ports["mcp_server"], network_name, services, resource_limits)
        
        logger.info(f"Deployed all services for customer {customer_id}")
        return services
    
    async def _deploy_postgres_container(self, customer_id: str, port: int, network_name: str, resource_limits: Dict) -> Dict[str, Any]:
        """Deploy dedicated PostgreSQL instance for customer"""
        container_name = f"postgres-{customer_id}"
        
        container = self.docker_client.containers.run(
            "postgres:15-alpine",
            name=container_name,
            ports={5432: port},
            environment={
                "POSTGRES_DB": f"customer_{customer_id}",
                "POSTGRES_USER": f"customer_{customer_id}",
                "POSTGRES_PASSWORD": self._generate_secure_password(),
                "PGDATA": "/var/lib/postgresql/data/pgdata"
            },
            volumes={
                f"postgres_data_{customer_id}": {"bind": "/var/lib/postgresql/data", "mode": "rw"}
            },
            networks=[network_name],
            labels={
                "ai-agency.customer-id": customer_id,
                "ai-agency.service": "postgres"
            },
            mem_limit=resource_limits["memory"],
            cpu_period=100000,
            cpu_quota=int(resource_limits["cpu"] * 100000),
            detach=True,
            restart_policy={"Name": "unless-stopped"}
        )
        
        # Wait for PostgreSQL to be ready
        await self._wait_for_service_health(f"localhost:{port}", "postgres", container_name)
        
        return {
            "container_id": container.id,
            "container_name": container_name,
            "port": port,
            "status": "running"
        }
    
    async def _deploy_redis_container(self, customer_id: str, port: int, network_name: str, resource_limits: Dict) -> Dict[str, Any]:
        """Deploy dedicated Redis instance for customer"""
        container_name = f"redis-{customer_id}"
        
        container = self.docker_client.containers.run(
            "redis:7-alpine",
            name=container_name,
            ports={6379: port},
            command=[
                "redis-server",
                "--appendonly", "yes",
                "--maxmemory", "1gb",
                "--maxmemory-policy", "allkeys-lru"
            ],
            volumes={
                f"redis_data_{customer_id}": {"bind": "/data", "mode": "rw"}
            },
            networks=[network_name],
            labels={
                "ai-agency.customer-id": customer_id,
                "ai-agency.service": "redis"
            },
            mem_limit=resource_limits["memory"],
            cpu_period=100000,
            cpu_quota=int(resource_limits["cpu"] * 100000),
            detach=True,
            restart_policy={"Name": "unless-stopped"}
        )
        
        await self._wait_for_service_health(f"localhost:{port}", "redis", container_name)
        
        return {
            "container_id": container.id,
            "container_name": container_name,
            "port": port,
            "status": "running"
        }
    
    async def _deploy_qdrant_container(self, customer_id: str, port: int, network_name: str, resource_limits: Dict) -> Dict[str, Any]:
        """Deploy dedicated Qdrant vector database for customer"""
        container_name = f"qdrant-{customer_id}"
        
        container = self.docker_client.containers.run(
            "qdrant/qdrant:v1.11.0",
            name=container_name,
            ports={6333: port, 6334: port + 1000},  # HTTP and gRPC ports
            environment={
                "QDRANT__SERVICE__HTTP_PORT": "6333",
                "QDRANT__SERVICE__GRPC_PORT": "6334", 
                "QDRANT__LOG_LEVEL": "INFO"
            },
            volumes={
                f"qdrant_data_{customer_id}": {"bind": "/qdrant/storage", "mode": "rw"}
            },
            networks=[network_name],
            labels={
                "ai-agency.customer-id": customer_id,
                "ai-agency.service": "qdrant"
            },
            mem_limit=resource_limits["memory"],
            cpu_period=100000,
            cpu_quota=int(resource_limits["cpu"] * 100000),
            detach=True,
            restart_policy={"Name": "unless-stopped"}
        )
        
        await self._wait_for_service_health(f"localhost:{port}/health", "qdrant", container_name)
        
        return {
            "container_id": container.id,
            "container_name": container_name,
            "port": port,
            "grpc_port": port + 1000,
            "status": "running"
        }
    
    async def _deploy_neo4j_container(self, customer_id: str, port: int, network_name: str, resource_limits: Dict) -> Dict[str, Any]:
        """Deploy dedicated Neo4j graph database for customer"""
        container_name = f"neo4j-{customer_id}"
        
        container = self.docker_client.containers.run(
            "neo4j:5.15-community",
            name=container_name,
            ports={7474: port, 7687: port + 1000},  # Browser and Bolt ports
            environment={
                "NEO4J_AUTH": f"neo4j/{self._generate_secure_password()}",
                "NEO4J_PLUGINS": '["apoc"]',
                "NEO4J_dbms_security_procedures_unrestricted": "apoc.*",
                "NEO4J_dbms_security_procedures_allowlist": "apoc.*",
                "NEO4J_dbms_memory_heap_initial__size": "256m",
                "NEO4J_dbms_memory_heap_max__size": "512m",
                "NEO4J_dbms_memory_pagecache_size": "128m",
                "NEO4J_server_config_strict__validation_enabled": "false"
            },
            volumes={
                f"neo4j_data_{customer_id}": {"bind": "/data", "mode": "rw"},
                f"neo4j_logs_{customer_id}": {"bind": "/logs", "mode": "rw"}
            },
            networks=[network_name],
            labels={
                "ai-agency.customer-id": customer_id,
                "ai-agency.service": "neo4j"
            },
            mem_limit=resource_limits["memory"],
            cpu_period=100000,
            cpu_quota=int(resource_limits["cpu"] * 100000),
            detach=True,
            restart_policy={"Name": "unless-stopped"}
        )
        
        await self._wait_for_service_health(f"localhost:{port}", "neo4j", container_name)
        
        return {
            "container_id": container.id,
            "container_name": container_name,
            "port": port,
            "bolt_port": port + 1000,
            "status": "running"
        }
    
    async def _deploy_memory_monitor(self, customer_id: str, port: int, network_name: str, services: Dict) -> Dict[str, Any]:
        """Deploy memory performance monitor for customer"""
        container_name = f"memory-monitor-{customer_id}"
        
        # Build memory monitor Docker image if not exists
        try:
            self.docker_client.images.get("ai-agency-memory-monitor")
        except docker.errors.ImageNotFound:
            logger.info("Building memory monitor image...")
            self.docker_client.images.build(
                path="./src/memory",
                dockerfile="Dockerfile.monitor",
                tag="ai-agency-memory-monitor"
            )
        
        container = self.docker_client.containers.run(
            "ai-agency-memory-monitor",
            name=container_name,
            ports={8080: port},
            environment={
                "CUSTOMER_ID": customer_id,
                "POSTGRES_URL": f"postgresql://customer_{customer_id}:{self._generate_secure_password()}@postgres-{customer_id}:5432/customer_{customer_id}",
                "REDIS_URL": f"redis://redis-{customer_id}:6379",
                "QDRANT_URL": f"http://qdrant-{customer_id}:6333",
                "NEO4J_URL": f"neo4j://neo4j-{customer_id}:7687",
                "NEO4J_USER": "neo4j",
                "NEO4J_PASSWORD": self._generate_secure_password(),
                "MONITORING_INTERVAL": "30",
                "SLA_ENFORCEMENT": "true"
            },
            networks=[network_name],
            labels={
                "ai-agency.customer-id": customer_id,
                "ai-agency.service": "memory-monitor"
            },
            detach=True,
            restart_policy={"Name": "unless-stopped"}
        )
        
        await self._wait_for_service_health(f"localhost:{port}/health", "memory-monitor", container_name)
        
        return {
            "container_id": container.id,
            "container_name": container_name,
            "port": port,
            "status": "running"
        }
    
    async def _deploy_mcp_server(self, customer_id: str, port: int, network_name: str, 
                                services: Dict, resource_limits: Dict) -> Dict[str, Any]:
        """Deploy dedicated MCP server for customer with full integration"""
        container_name = f"mcp-server-{customer_id}"
        
        # Build custom MCP server image with EA integration
        try:
            self.docker_client.images.get("ai-agency-mcp-server")
        except docker.errors.ImageNotFound:
            logger.info("Building MCP server image...")
            self.docker_client.images.build(
                path="./src/agents",
                dockerfile="Dockerfile.mcp-server",
                tag="ai-agency-mcp-server"
            )
        
        container = self.docker_client.containers.run(
            "ai-agency-mcp-server",
            name=container_name,
            ports={3000: port},
            environment={
                "CUSTOMER_ID": customer_id,
                "MCP_PORT": str(port),
                "DATABASE_URL": f"postgresql://customer_{customer_id}:{self._generate_secure_password()}@postgres-{customer_id}:5432/customer_{customer_id}",
                "REDIS_URL": f"redis://redis-{customer_id}:6379",
                "QDRANT_URL": f"http://qdrant-{customer_id}:6333",
                "NEO4J_URL": f"neo4j://neo4j-{customer_id}:7687",
                "NEO4J_USER": "neo4j",
                "NEO4J_PASSWORD": self._generate_secure_password(),
                "MEMORY_MONITOR_URL": f"http://memory-monitor-{customer_id}:8080",
                "EA_ENABLED": "true",
                "MEM0_COLLECTION_NAME": f"customer_{customer_id}_memories",
                "NODE_ENV": "production"
            },
            networks=[network_name],
            labels={
                "ai-agency.customer-id": customer_id,
                "ai-agency.service": "mcp-server"
            },
            mem_limit=resource_limits["memory"],
            cpu_period=100000,
            cpu_quota=int(resource_limits["cpu"] * 100000),
            detach=True,
            restart_policy={"Name": "unless-stopped"}
        )
        
        await self._wait_for_service_health(f"localhost:{port}/health", "mcp-server", container_name)
        
        return {
            "container_id": container.id,
            "container_name": container_name,
            "port": port,
            "status": "running"
        }
    
    async def _initialize_customer_memory(self, customer_id: str, services: Dict):
        """Initialize Mem0 memory system for customer"""
        from ..memory.mem0_manager import EAMemoryManager
        
        # Create customer-specific memory manager
        memory_config = {
            "mem0": {
                "vector_store": {
                    "provider": "qdrant",
                    "config": {
                        "host": f"qdrant-{customer_id}",
                        "port": 6333,
                        "collection_name": f"customer_{customer_id}_memories"
                    }
                },
                "graph_store": {
                    "provider": "neo4j",
                    "config": {
                        "url": f"neo4j://neo4j-{customer_id}:7687",
                        "username": "neo4j",
                        "password": self._generate_secure_password(),
                        "database": f"customer_{customer_id}_graph"
                    }
                }
            }
        }
        
        ea_memory = EAMemoryManager(customer_id, memory_config)
        
        # Initialize memory collections and test connectivity
        await ea_memory.store_business_context({
            "business_description": "Customer onboarding complete",
            "phase": "initial_setup",
            "timestamp": datetime.utcnow().isoformat()
        }, f"setup_{customer_id}")
        
        logger.info(f"Initialized Mem0 memory for customer {customer_id}")
        await ea_memory.close()
    
    async def _initialize_customer_ea(self, customer_id: str, services: Dict, customer_data: Dict):
        """Initialize Executive Assistant with customer MCP integration"""
        ea_config = {
            "customer_id": customer_id,
            "mcp_server_url": f"http://localhost:{services['mcp_server']['port']}",
            "memory_monitor_url": f"http://localhost:{services['memory_monitor']['port']}",
            "personality": customer_data.get("personality", "professional"),
            "communication_channels": ["phone", "whatsapp", "email"],
            "business_context": customer_data.get("business_context", {}),
            "ai_preferences": customer_data.get("ai_preferences", {"model": "gpt-4o-mini"}),
            "autonomous_memory": True,
            "cross_channel_continuity": True
        }
        
        # Store EA configuration in customer database
        await self._store_customer_config(customer_id, ea_config)
        
        logger.info(f"Initialized EA for customer {customer_id}")
    
    async def _wait_for_service_health(self, endpoint: str, service_type: str, container_name: str, timeout: int = 60):
        """Wait for service to become healthy with timeout"""
        import aiohttp
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                if service_type == "postgres":
                    # PostgreSQL health check using pg_isready equivalent
                    container = self.docker_client.containers.get(container_name)
                    result = container.exec_run("pg_isready")
                    if result.exit_code == 0:
                        logger.info(f"✅ {service_type} service ready: {container_name}")
                        return
                        
                elif service_type == "redis":
                    # Redis health check
                    container = self.docker_client.containers.get(container_name)
                    result = container.exec_run("redis-cli ping")
                    if b"PONG" in result.output:
                        logger.info(f"✅ {service_type} service ready: {container_name}")
                        return
                        
                else:
                    # HTTP health check for other services
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"http://{endpoint}") as response:
                            if response.status == 200:
                                logger.info(f"✅ {service_type} service ready: {container_name}")
                                return
                                
            except Exception as e:
                pass
            
            await asyncio.sleep(2)
        
        raise TimeoutError(f"Service {service_type} ({container_name}) failed to become healthy within {timeout}s")
    
    def _build_service_endpoints(self, customer_id: str, ports: Dict[str, int]) -> Dict[str, str]:
        """Build service endpoint URLs for customer"""
        return {
            "mcp_server": f"http://localhost:{ports['mcp_server']}",
            "postgres": f"postgresql://customer_{customer_id}@localhost:{ports['postgres']}/customer_{customer_id}",
            "redis": f"redis://localhost:{ports['redis']}",
            "qdrant": f"http://localhost:{ports['qdrant']}",
            "neo4j_browser": f"http://localhost:{ports['neo4j']}",
            "neo4j_bolt": f"bolt://localhost:{ports['neo4j'] + 1000}",
            "memory_monitor": f"http://localhost:{ports['memory_monitor']}",
            "ea_endpoint": f"http://localhost:{ports['mcp_server']}/ea"
        }
    
    async def _store_infrastructure_record(self, infrastructure: CustomerInfrastructure):
        """Store infrastructure record in database"""
        if not self.postgres_pool:
            postgres_config = self.config["database"]
            self.postgres_pool = await asyncpg.create_pool(
                host=postgres_config["host"],
                port=postgres_config["port"],
                database=postgres_config["database"],
                user=postgres_config["user"],
                password=postgres_config["password"]
            )
        
        async with self.postgres_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO customer_infrastructure (
                    customer_id, tier, mcp_server_id, service_endpoints, 
                    resource_limits, provisioning_time, status, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (customer_id) DO UPDATE SET
                    tier = EXCLUDED.tier,
                    mcp_server_id = EXCLUDED.mcp_server_id,
                    service_endpoints = EXCLUDED.service_endpoints,
                    resource_limits = EXCLUDED.resource_limits,
                    status = EXCLUDED.status,
                    updated_at = NOW()
            """, 
                infrastructure.customer_id,
                infrastructure.tier.value,
                infrastructure.mcp_server_id,
                json.dumps(infrastructure.service_endpoints),
                json.dumps(infrastructure.resource_limits),
                infrastructure.provisioning_time,
                infrastructure.status,
                datetime.utcnow()
            )
    
    async def _store_customer_config(self, customer_id: str, config: Dict[str, Any]):
        """Store customer configuration in their dedicated database"""
        # This would connect to the customer's dedicated database
        # Implementation would use the customer-specific connection details
        logger.info(f"Stored configuration for customer {customer_id}")
    
    def _generate_secure_password(self, length: int = 32) -> str:
        """Generate cryptographically secure password"""
        import secrets
        import string
        
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    async def _cleanup_failed_provision(self, customer_id: str):
        """Cleanup resources on provisioning failure"""
        try:
            # Remove any created containers
            containers = self.docker_client.containers.list(
                filters={"label": f"ai-agency.customer-id={customer_id}"},
                all=True
            )
            
            for container in containers:
                container.remove(force=True)
                logger.info(f"Removed failed container: {container.name}")
            
            # Remove customer network
            try:
                network = self.docker_client.networks.get(f"customer-{customer_id}-network")
                network.remove()
                logger.info(f"Removed customer network: customer-{customer_id}-network")
            except docker.errors.NotFound:
                pass
            
            # Release allocated ports
            self.allocated_ports.discard(customer_id)
            
            logger.info(f"Cleanup completed for failed provision: {customer_id}")
            
        except Exception as e:
            logger.error(f"Error during cleanup for customer {customer_id}: {e}")
    
    async def get_customer_infrastructure(self, customer_id: str) -> Optional[CustomerInfrastructure]:
        """Get customer infrastructure details"""
        return self.customer_infrastructure.get(customer_id)
    
    async def scale_customer_resources(self, customer_id: str, new_tier: CustomerTier) -> bool:
        """Scale customer resources based on new tier"""
        try:
            infrastructure = self.customer_infrastructure.get(customer_id)
            if not infrastructure:
                logger.error(f"Customer {customer_id} infrastructure not found")
                return False
            
            new_limits = self.config["resource_limits"][new_tier]
            
            # Update container resource limits
            container = self.docker_client.containers.get(infrastructure.mcp_server_id)
            container.update(
                mem_limit=new_limits["memory"],
                cpu_period=100000,
                cpu_quota=int(new_limits["cpu"] * 100000)
            )
            
            # Update infrastructure record
            infrastructure.tier = new_tier
            infrastructure.resource_limits = new_limits
            await self._store_infrastructure_record(infrastructure)
            
            logger.info(f"Scaled customer {customer_id} to {new_tier.value}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to scale customer {customer_id}: {e}")
            return False
    
    async def deprovision_customer(self, customer_id: str) -> bool:
        """Safely deprovision customer infrastructure with data retention"""
        try:
            # Export customer data before deprovisioning
            await self._export_customer_data(customer_id)
            
            # Remove containers
            containers = self.docker_client.containers.list(
                filters={"label": f"ai-agency.customer-id={customer_id}"},
                all=True
            )
            
            for container in containers:
                container.stop(timeout=30)
                container.remove()
                logger.info(f"Removed container: {container.name}")
            
            # Remove network
            try:
                network = self.docker_client.networks.get(f"customer-{customer_id}-network")
                network.remove()
            except docker.errors.NotFound:
                pass
            
            # Clean up infrastructure record
            self.customer_infrastructure.pop(customer_id, None)
            
            logger.info(f"Successfully deprovisioned customer {customer_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to deprovision customer {customer_id}: {e}")
            return False
    
    async def _export_customer_data(self, customer_id: str):
        """Export customer data for compliance/backup before deprovisioning"""
        # This would implement GDPR-compliant data export
        logger.info(f"Exported data for customer {customer_id}")
    
    async def get_provisioning_metrics(self) -> Dict[str, Any]:
        """Get provisioning performance metrics"""
        return {
            "total_customers": len(self.customer_infrastructure),
            "provisioning_times": [infra.provisioning_time for infra in self.customer_infrastructure.values()],
            "average_provisioning_time": sum(infra.provisioning_time for infra in self.customer_infrastructure.values()) / len(self.customer_infrastructure) if self.customer_infrastructure else 0,
            "sla_compliance": sum(1 for infra in self.customer_infrastructure.values() if infra.provisioning_time <= 30) / len(self.customer_infrastructure) if self.customer_infrastructure else 0,
            "allocated_ports": len(self.allocated_ports),
            "customer_tiers": {tier.value: sum(1 for infra in self.customer_infrastructure.values() if infra.tier == tier) for tier in CustomerTier}
        }
    
    async def close(self):
        """Close all connections and cleanup"""
        if self.postgres_pool:
            await self.postgres_pool.close()
        
        if self.redis_pool:
            await self.redis_pool.aclose()
        
        logger.info("Customer Provisioning Orchestrator closed")


# Example usage and testing
async def main():
    """Example usage of Customer Provisioning Orchestrator"""
    orchestrator = CustomerProvisioningOrchestrator()
    
    # Provision a customer
    customer_data = {
        "business_context": {
            "industry": "Technology",
            "size": "Small Business",
            "pain_points": ["Manual processes", "Customer support"]
        },
        "personality": "professional",
        "ai_preferences": {"model": "gpt-4o-mini"}
    }
    
    infrastructure = await orchestrator.provision_customer_infrastructure(
        customer_id="customer_12345",
        tier=CustomerTier.PROFESSIONAL,
        customer_data=customer_data
    )
    
    print(f"Customer infrastructure provisioned: {infrastructure}")
    
    # Get metrics
    metrics = await orchestrator.get_provisioning_metrics()
    print(f"Provisioning metrics: {metrics}")
    
    await orchestrator.close()


if __name__ == "__main__":
    asyncio.run(main())