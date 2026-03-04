#!/usr/bin/env python3
"""
AI Agency Platform - Docker Compose Generator
Phase 3: Intelligent Port Allocation Integration

This module generates dynamic Docker Compose configurations with:
- Intelligent port allocation integration
- Customer-specific environment configurations
- Service tier optimization
- Security and compliance compliance
"""

import os
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import logging

from .port_allocator import ServiceType, PortAllocator

logger = logging.getLogger(__name__)


@dataclass
class ServiceConfiguration:
    """Configuration for a Docker service"""
    name: str
    image: str
    ports: Dict[str, int]  # container_port -> host_port
    environment: Dict[str, str]
    volumes: List[str]
    depends_on: List[str]
    healthcheck: Dict[str, Any]
    deploy: Dict[str, Any]
    labels: Dict[str, str]
    command: Optional[List[str]] = None
    networks: Optional[List[str]] = None


class DockerComposeGenerator:
    """
    Docker Compose Configuration Generator with Port Allocation Integration
    
    Generates customer-specific Docker Compose files with intelligent port
    allocation, service optimization, and compliance requirements.
    """
    
    def __init__(self, 
                 port_allocator: PortAllocator,
                 template_path: str = "./docker-compose.production.yml",
                 output_dir: str = "./deploy/customers"):
        """
        Initialize Docker Compose Generator
        
        Args:
            port_allocator: Port allocation system
            template_path: Path to base template
            output_dir: Directory for generated configurations
        """
        self.port_allocator = port_allocator
        self.template_path = Path(template_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Service tier configurations
        self.TIER_CONFIGS = self.tier_configs = {
            "basic": {
                "memory_limit": "2G",
                "cpu_limit": "1.0",
                "services": [ServiceType.POSTGRES, ServiceType.REDIS, ServiceType.MCP_SERVER],
                "max_replicas": 1
            },
            "professional": {
                "memory_limit": "4G",
                "cpu_limit": "2.0", 
                "services": [ServiceType.POSTGRES, ServiceType.REDIS, ServiceType.QDRANT,
                           ServiceType.MCP_SERVER, ServiceType.MEMORY_MONITOR],
                "max_replicas": 2
            },
            "enterprise": {
                "memory_limit": "8G",
                "cpu_limit": "4.0",
                "services": [ServiceType.POSTGRES, ServiceType.REDIS, ServiceType.QDRANT,
                           ServiceType.QDRANT_GRPC, ServiceType.NEO4J, ServiceType.NEO4J_BOLT,
                           ServiceType.MCP_SERVER, ServiceType.MEMORY_MONITOR, ServiceType.SECURITY_API],
                "max_replicas": 3
            }
        }
    
    async def generate_customer_compose(self,
                                      customer_id: str,
                                      tier: str,
                                      ai_model: str,
                                      credentials: Dict[str, str],
                                      allocated_ports: Dict[ServiceType, int],
                                      custom_config: Optional[Dict[str, Any]] = None) -> Path:
        """
        Generate customer-specific Docker Compose configuration
        
        Args:
            customer_id: Customer identifier
            tier: Service tier (basic, professional, enterprise)
            ai_model: AI model preference
            credentials: Generated secure credentials
            allocated_ports: Port allocations from port allocator
            custom_config: Optional custom configuration
        
        Returns:
            Path to generated Docker Compose file
        """
        if tier not in self.tier_configs:
            raise ValueError(f"Invalid tier: {tier}")
        
        tier_config = self.tier_configs[tier]
        required_services = tier_config["services"]
        
        logger.info(f"Generating Docker Compose for customer {customer_id} (tier: {tier})")
        
        # Build service configurations
        services = {}
        volumes = {}
        networks = {
            f"customer-{customer_id}-network": {
                "driver": "bridge",
                "name": f"customer-{customer_id}-network",
                "labels": {
                    "ai-agency.customer-id": customer_id,
                    "ai-agency.network-type": "customer-isolation"
                }
            }
        }
        
        # Generate each required service
        for service_type in required_services:
            if service_type not in allocated_ports:
                raise ValueError(f"No port allocated for service type: {service_type}")
            
            port = allocated_ports[service_type]
            service_config = self._generate_service_config(
                customer_id=customer_id,
                service_type=service_type,
                port=port,
                tier_config=tier_config,
                credentials=credentials,
                ai_model=ai_model,
                custom_config=custom_config
            )
            
            services[service_config.name] = self._service_to_dict(service_config)
            
            # Add volumes for this service
            for volume in service_config.volumes:
                if ":" in volume:
                    volume_name = volume.split(":")[0]
                    if not volume_name.startswith("./") and not volume_name.startswith("/"):
                        volumes[volume_name] = {"driver": "local"}
        
        # Build complete compose configuration
        compose_config = {
            "version": "3.8",
            "services": services,
            "volumes": volumes,
            "networks": networks
        }
        
        # Write configuration file
        output_file = self.output_dir / f"docker-compose.{customer_id}.yml"
        
        with open(output_file, 'w') as f:
            yaml.dump(compose_config, f, default_flow_style=False, sort_keys=False, indent=2)
        
        # Generate environment file
        env_file = self.output_dir / f".env.{customer_id}"
        self._generate_env_file(customer_id, tier, credentials, allocated_ports, ai_model, env_file)
        
        logger.info(f"✅ Generated Docker Compose configuration: {output_file}")
        
        return output_file
    
    def _generate_service_config(self,
                               customer_id: str,
                               service_type: ServiceType,
                               port: int,
                               tier_config: Dict[str, Any],
                               credentials: Dict[str, str],
                               ai_model: str,
                               custom_config: Optional[Dict[str, Any]]) -> ServiceConfiguration:
        """Generate configuration for a specific service"""
        
        service_configs = {
            ServiceType.POSTGRES: self._postgres_config,
            ServiceType.REDIS: self._redis_config,
            ServiceType.QDRANT: self._qdrant_config,
            ServiceType.QDRANT_GRPC: self._qdrant_grpc_config,
            ServiceType.NEO4J: self._neo4j_config,
            ServiceType.NEO4J_BOLT: self._neo4j_bolt_config,
            ServiceType.MCP_SERVER: self._mcp_server_config,
            ServiceType.MEMORY_MONITOR: self._memory_monitor_config,
            ServiceType.SECURITY_API: self._security_api_config
        }
        
        if service_type not in service_configs:
            raise ValueError(f"Unknown service type: {service_type}")
        
        return service_configs[service_type](
            customer_id, port, tier_config, credentials, ai_model, custom_config
        )
    
    def _postgres_config(self, customer_id: str, port: int, tier_config: Dict[str, Any],
                        credentials: Dict[str, str], ai_model: str, 
                        custom_config: Optional[Dict[str, Any]]) -> ServiceConfiguration:
        """Generate PostgreSQL service configuration"""
        return ServiceConfiguration(
            name=f"postgres-{customer_id}",
            image="postgres:15-alpine",
            ports={"5432": port},
            environment={
                "POSTGRES_DB": f"customer_{customer_id}",
                "POSTGRES_USER": f"customer_{customer_id}",
                "POSTGRES_PASSWORD": credentials["postgres_password"],
                "PGDATA": "/var/lib/postgresql/data/pgdata",
                # Production optimizations
                "POSTGRES_SHARED_BUFFERS": "256MB",
                "POSTGRES_EFFECTIVE_CACHE_SIZE": "1GB",
                "POSTGRES_CHECKPOINT_COMPLETION_TARGET": "0.9",
                "POSTGRES_WAL_BUFFERS": "16MB"
            },
            volumes=[
                f"postgres_data_{customer_id}:/var/lib/postgresql/data",
                "./config/postgres/customer-init.sql:/docker-entrypoint-initdb.d/01-customer-init.sql:ro",
                "./config/postgres/production.conf:/etc/postgresql/postgresql.conf:ro"
            ],
            depends_on=[],
            healthcheck={
                "test": ["CMD-SHELL", f"pg_isready -U customer_{customer_id} -d customer_{customer_id}"],
                "interval": "10s",
                "timeout": "5s",
                "retries": 5,
                "start_period": "30s"
            },
            deploy={
                "resources": {
                    "limits": {
                        "memory": tier_config["memory_limit"],
                        "cpus": tier_config["cpu_limit"]
                    },
                    "reservations": {
                        "memory": "512M",
                        "cpus": "0.5"
                    }
                }
            },
            labels={
                "ai-agency.customer-id": customer_id,
                "ai-agency.service": "postgres",
                "ai-agency.tier": tier_config.get("tier", "unknown"),
                "ai-agency.port": str(port)
            },
            networks=[f"customer-{customer_id}-network"]
        )
    
    def _redis_config(self, customer_id: str, port: int, tier_config: Dict[str, Any],
                     credentials: Dict[str, str], ai_model: str,
                     custom_config: Optional[Dict[str, Any]]) -> ServiceConfiguration:
        """Generate Redis service configuration"""
        return ServiceConfiguration(
            name=f"redis-{customer_id}",
            image="redis:7-alpine",
            ports={"6379": port},
            environment={},
            volumes=[
                f"redis_data_{customer_id}:/data",
                "./config/redis/redis.conf:/usr/local/etc/redis/redis.conf:ro"
            ],
            depends_on=[],
            command=[
                "redis-server",
                "--appendonly", "yes",
                "--maxmemory", "1gb",
                "--maxmemory-policy", "allkeys-lru",
                "--save", "900", "1",
                "--save", "300", "10",
                "--save", "60", "10000",
                "--tcp-keepalive", "300",
                "--timeout", "300"
            ],
            healthcheck={
                "test": ["CMD", "redis-cli", "ping"],
                "interval": "10s",
                "timeout": "3s",
                "retries": 3,
                "start_period": "10s"
            },
            deploy={
                "resources": {
                    "limits": {
                        "memory": tier_config["memory_limit"],
                        "cpus": tier_config["cpu_limit"]
                    },
                    "reservations": {
                        "memory": "256M",
                        "cpus": "0.25"
                    }
                }
            },
            labels={
                "ai-agency.customer-id": customer_id,
                "ai-agency.service": "redis",
                "ai-agency.tier": tier_config.get("tier", "unknown"),
                "ai-agency.port": str(port)
            },
            networks=[f"customer-{customer_id}-network"]
        )
    
    def _qdrant_config(self, customer_id: str, port: int, tier_config: Dict[str, Any],
                      credentials: Dict[str, str], ai_model: str,
                      custom_config: Optional[Dict[str, Any]]) -> ServiceConfiguration:
        """Generate Qdrant service configuration"""
        return ServiceConfiguration(
            name=f"qdrant-{customer_id}",
            image="qdrant/qdrant:v1.11.0",
            ports={"6333": port},
            environment={
                "QDRANT__SERVICE__HTTP_PORT": "6333",
                "QDRANT__SERVICE__GRPC_PORT": "6334",
                "QDRANT__LOG_LEVEL": "INFO",
                "QDRANT__STORAGE__STORAGE_PATH": "/qdrant/storage",
                "QDRANT__SERVICE__MAX_REQUEST_SIZE_MB": "32",
                "QDRANT__CLUSTER__ENABLED": "false",
                # Production performance tuning
                "QDRANT__STORAGE__OPTIMIZERS__DEFAULT_SEGMENT_NUMBER": "2",
                "QDRANT__STORAGE__OPTIMIZERS__MEMMAP_THRESHOLD_KB": "200000",
                "QDRANT__STORAGE__OPTIMIZERS__INDEXING_THRESHOLD_KB": "20000"
            },
            volumes=[
                f"qdrant_data_{customer_id}:/qdrant/storage",
                "./config/qdrant/production.yaml:/qdrant/config/production.yaml:ro"
            ],
            depends_on=[],
            healthcheck={
                "test": ["CMD", "wget", "--no-verbose", "--tries=3", "--spider", "http://localhost:6333/health"],
                "interval": "30s",
                "timeout": "10s",
                "retries": 3,
                "start_period": "40s"
            },
            deploy={
                "resources": {
                    "limits": {
                        "memory": tier_config["memory_limit"],
                        "cpus": tier_config["cpu_limit"]
                    },
                    "reservations": {
                        "memory": "512M",
                        "cpus": "0.5"
                    }
                }
            },
            labels={
                "ai-agency.customer-id": customer_id,
                "ai-agency.service": "qdrant",
                "ai-agency.tier": tier_config.get("tier", "unknown"),
                "ai-agency.port": str(port)
            },
            networks=[f"customer-{customer_id}-network"]
        )
    
    def _mcp_server_config(self, customer_id: str, port: int, tier_config: Dict[str, Any],
                          credentials: Dict[str, str], ai_model: str,
                          custom_config: Optional[Dict[str, Any]]) -> ServiceConfiguration:
        """Generate MCP Server service configuration"""
        return ServiceConfiguration(
            name=f"mcp-server-{customer_id}",
            image="ai-agency/mcp-server:latest",
            ports={"8080": port},
            environment={
                "CUSTOMER_ID": customer_id,
                "AI_MODEL": ai_model,
                "POSTGRES_URL": f"postgresql://customer_{customer_id}:{credentials['postgres_password']}@postgres-{customer_id}:5432/customer_{customer_id}",
                "REDIS_URL": f"redis://redis-{customer_id}:6379",
                "QDRANT_URL": f"http://qdrant-{customer_id}:6333",
                "JWT_SECRET": credentials["jwt_secret"],
                "ENCRYPTION_KEY": credentials["encryption_key"],
                "LOG_LEVEL": "INFO",
                "METRICS_ENABLED": "true",
                "TRACING_ENABLED": "true"
            },
            volumes=[
                f"./logs/mcp-{customer_id}:/app/logs",
                f"./config/mcp/{customer_id}:/app/config:ro"
            ],
            depends_on=[f"postgres-{customer_id}", f"redis-{customer_id}"],
            healthcheck={
                "test": ["CMD", "curl", "-f", "http://localhost:8080/health"],
                "interval": "30s",
                "timeout": "5s",
                "retries": 3,
                "start_period": "60s"
            },
            deploy={
                "resources": {
                    "limits": {
                        "memory": tier_config["memory_limit"],
                        "cpus": tier_config["cpu_limit"]
                    },
                    "reservations": {
                        "memory": "512M",
                        "cpus": "0.5"
                    }
                }
            },
            labels={
                "ai-agency.customer-id": customer_id,
                "ai-agency.service": "mcp-server",
                "ai-agency.tier": tier_config.get("tier", "unknown"),
                "ai-agency.port": str(port)
            },
            networks=[f"customer-{customer_id}-network"]
        )
    
    # Additional service configs would go here...
    def _memory_monitor_config(self, customer_id: str, port: int, tier_config: Dict[str, Any],
                             credentials: Dict[str, str], ai_model: str,
                             custom_config: Optional[Dict[str, Any]]) -> ServiceConfiguration:
        """Generate Memory Monitor service configuration"""
        return ServiceConfiguration(
            name=f"memory-monitor-{customer_id}",
            image=f"ai-agency-memory-monitor:{customer_id}",
            ports={"8080": port},
            environment={
                "CUSTOMER_ID": customer_id,
                "POSTGRES_URL": f"postgresql://customer_{customer_id}:{credentials['postgres_password']}@postgres-{customer_id}:5432/customer_{customer_id}",
                "REDIS_URL": f"redis://redis-{customer_id}:6379",
                "QDRANT_URL": f"http://qdrant-{customer_id}:6333",
                "MONITORING_INTERVAL": "30",
                "SLA_ENFORCEMENT": "true",
                "METRICS_RETENTION_DAYS": "30",
                "ALERT_THRESHOLD_MEMORY": "0.85",
                "ALERT_THRESHOLD_CPU": "0.80",
                "ALERT_THRESHOLD_RESPONSE_TIME_MS": "500"
            },
            volumes=[
                f"./logs/memory-{customer_id}:/app/logs"
            ],
            depends_on=[f"postgres-{customer_id}", f"redis-{customer_id}"],
            healthcheck={
                "test": ["CMD", "curl", "-f", "http://localhost:8080/health"],
                "interval": "30s",
                "timeout": "5s",
                "retries": 3
            },
            deploy={
                "resources": {
                    "limits": {
                        "memory": "1G",
                        "cpus": "0.5"
                    },
                    "reservations": {
                        "memory": "256M",
                        "cpus": "0.1"
                    }
                }
            },
            labels={
                "ai-agency.customer-id": customer_id,
                "ai-agency.service": "memory-monitor",
                "ai-agency.tier": tier_config.get("tier", "unknown"),
                "ai-agency.port": str(port)
            },
            networks=[f"customer-{customer_id}-network"]
        )
    
    # Stub implementations for other services
    def _qdrant_grpc_config(self, *args, **kwargs) -> ServiceConfiguration:
        return self._qdrant_config(*args, **kwargs)  # Simplified for now
    
    def _neo4j_config(self, *args, **kwargs) -> ServiceConfiguration:
        # Implementation would go here
        pass
    
    def _neo4j_bolt_config(self, *args, **kwargs) -> ServiceConfiguration:
        # Implementation would go here  
        pass
    
    def _security_api_config(self, *args, **kwargs) -> ServiceConfiguration:
        # Implementation would go here
        pass
    
    def _service_to_dict(self, service: ServiceConfiguration) -> Dict[str, Any]:
        """Convert ServiceConfiguration to Docker Compose service dict"""
        service_dict = {
            "image": service.image,
            "container_name": service.name,
            "ports": [f"{host_port}:{container_port}" for container_port, host_port in service.ports.items()],
            "environment": service.environment,
            "volumes": service.volumes,
            "healthcheck": service.healthcheck,
            "deploy": service.deploy,
            "labels": [f"{k}={v}" for k, v in service.labels.items()],
            "restart": "unless-stopped",
            "logging": {
                "driver": "json-file",
                "options": {
                    "max-size": "100m",
                    "max-file": "3"
                }
            }
        }
        
        if service.depends_on:
            service_dict["depends_on"] = service.depends_on
        
        if service.command:
            service_dict["command"] = service.command
        
        if service.networks:
            service_dict["networks"] = service.networks
        
        return service_dict
    
    def _generate_env_file(self,
                          customer_id: str,
                          tier: str,
                          credentials: Dict[str, str],
                          allocated_ports: Dict[ServiceType, int],
                          ai_model: str,
                          env_file_path: Path):
        """Generate environment file for customer deployment"""
        tier_config = self.tier_configs[tier]
        
        env_content = f"""# AI Agency Platform - Customer Environment Configuration
# Customer: {customer_id}
# Tier: {tier}
# Generated: {os.environ.get('TIMESTAMP', 'auto-generated')}

# Customer Identification
CUSTOMER_ID={customer_id}
CUSTOMER_TIER={tier}

# AI Model Configuration
AI_MODEL={ai_model}

# Allocated Ports
"""
        
        for service_type, port in allocated_ports.items():
            port_var_name = f"{service_type.value.upper().replace('_', '_')}_PORT"
            env_content += f"{port_var_name}={port}\
"
        
        env_content += f"""\
# Resource Limits
TIER_MEMORY_LIMIT={tier_config['memory_limit']}
TIER_CPU_LIMIT={tier_config['cpu_limit']}

# Security Credentials
SECURE_PASSWORD={credentials['postgres_password']}
JWT_SECRET={credentials['jwt_secret']}
ENCRYPTION_KEY={credentials['encryption_key']}

# Neo4j Credentials (if applicable)
NEO4J_PASSWORD={credentials.get('neo4j_password', credentials['postgres_password'])}

# Redis Auth (if applicable)
REDIS_AUTH={credentials.get('redis_auth', '')}

# Service URLs (for internal communication)
POSTGRES_URL=postgresql://customer_{customer_id}:{credentials['postgres_password']}@postgres-{customer_id}:5432/customer_{customer_id}
REDIS_URL=redis://redis-{customer_id}:6379
QDRANT_URL=http://qdrant-{customer_id}:6333

# Monitoring and Logging
LOG_LEVEL=INFO
METRICS_ENABLED=true
TRACING_ENABLED=true

# Performance Tuning
MONITORING_INTERVAL=30
SLA_ENFORCEMENT=true
ALERT_THRESHOLD_MEMORY=0.85
ALERT_THRESHOLD_CPU=0.80
ALERT_THRESHOLD_RESPONSE_TIME_MS=500
"""
        
        with open(env_file_path, 'w') as f:
            f.write(env_content)
        
        logger.info(f"✅ Generated environment file: {env_file_path}")
    
    def generate_deployment_script(self, customer_id: str, compose_file: Path) -> Path:
        """Generate deployment script for customer environment"""
        script_path = self.output_dir / f"deploy-{customer_id}.sh"
        
        script_content = f"""#!/bin/bash
# AI Agency Platform - Customer Deployment Script
# Customer: {customer_id}
# Generated automatically - do not edit manually

set -e  # Exit on any error

CUSTOMER_ID="{customer_id}"
COMPOSE_FILE="{compose_file}"
ENV_FILE="{compose_file.parent}/.env.{customer_id}"

echo "🚀 Deploying environment for customer $CUSTOMER_ID..."

# Validate files exist
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "❌ Compose file not found: $COMPOSE_FILE"
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Environment file not found: $ENV_FILE"
    exit 1
fi

# Load environment variables
source "$ENV_FILE"

# Create necessary directories
mkdir -p "./logs/mcp-$CUSTOMER_ID"
mkdir -p "./logs/memory-$CUSTOMER_ID"
mkdir -p "./config/mcp/$CUSTOMER_ID"

# Deploy using docker-compose
echo "📦 Starting services..."
docker-compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d

# Wait for services to become healthy
echo "🔍 Waiting for services to become healthy..."
sleep 30

# Health check
echo "❤️ Performing health check..."
docker-compose -f "$COMPOSE_FILE" ps

# Verify critical services
if docker-compose -f "$COMPOSE_FILE" ps | grep -q "Up.*healthy"; then
    echo "✅ Customer environment deployed successfully!"
else
    echo "⚠️ Some services may not be fully healthy. Check docker-compose logs for details."
fi

echo "📊 Deployment completed for customer $CUSTOMER_ID"
echo "🌐 Services available at allocated ports (check .env file for details)"
"""
        
        with open(script_path, 'w') as f:
            f.write(script_content)
        
        # Make script executable
        script_path.chmod(0o755)
        
        logger.info(f"✅ Generated deployment script: {script_path}")
        
        return script_path


if __name__ == "__main__":
    # Demo functionality
    async def main():
        from .port_allocator import create_port_allocator, ServiceType
        
        # Create port allocator
        port_allocator = await create_port_allocator()
        
        try:
            # Create generator
            generator = DockerComposeGenerator(port_allocator)
            
            # Test customer
            test_customer = "demo_customer_001"
            tier = "professional"
            ai_model = "claude-3.5-sonnet"
            
            # Allocate ports
            services = [ServiceType.POSTGRES, ServiceType.REDIS, ServiceType.QDRANT, 
                       ServiceType.MCP_SERVER, ServiceType.MEMORY_MONITOR]
            allocated_ports = {}
            
            for service_type in services:
                allocation = await port_allocator.allocate_port(test_customer, service_type)
                allocated_ports[service_type] = allocation.port
            
            # Generate credentials
            credentials = {
                "postgres_password": "test_postgres_pass_123",
                "jwt_secret": "test_jwt_secret_456",
                "encryption_key": "test_encryption_key_789"
            }
            
            # Generate configuration
            compose_file = await generator.generate_customer_compose(
                customer_id=test_customer,
                tier=tier,
                ai_model=ai_model,
                credentials=credentials,
                allocated_ports=allocated_ports
            )
            
            print(f"✅ Generated configuration: {compose_file}")
            
            # Generate deployment script
            script_file = generator.generate_deployment_script(test_customer, compose_file)
            print(f"✅ Generated deployment script: {script_file}")
            
        finally:
            await port_allocator.close()
    
    import asyncio
    asyncio.run(main())