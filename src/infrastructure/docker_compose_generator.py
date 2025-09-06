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
            deploy={\n                "resources": {\n                    "limits": {\n                        "memory": tier_config["memory_limit"],\n                        "cpus": tier_config["cpu_limit"]\n                    },\n                    "reservations": {\n                        "memory": "512M",\n                        "cpus": "0.5"\n                    }\n                }\n            },\n            labels={\n                "ai-agency.customer-id": customer_id,\n                "ai-agency.service": "postgres",\n                "ai-agency.tier": tier_config.get("tier", "unknown"),\n                "ai-agency.port": str(port)\n            },\n            networks=[f"customer-{customer_id}-network"]\n        )\n    \n    def _redis_config(self, customer_id: str, port: int, tier_config: Dict[str, Any],\n                     credentials: Dict[str, str], ai_model: str,\n                     custom_config: Optional[Dict[str, Any]]) -> ServiceConfiguration:\n        \"\"\"Generate Redis service configuration\"\"\"\n        return ServiceConfiguration(\n            name=f"redis-{customer_id}",\n            image="redis:7-alpine",\n            ports={"6379": port},\n            environment={},\n            volumes=[\n                f"redis_data_{customer_id}:/data",\n                "./config/redis/redis.conf:/usr/local/etc/redis/redis.conf:ro"\n            ],\n            depends_on=[],\n            command=[\n                "redis-server",\n                "--appendonly", "yes",\n                "--maxmemory", "1gb",\n                "--maxmemory-policy", "allkeys-lru",\n                "--save", "900", "1",\n                "--save", "300", "10",\n                "--save", "60", "10000",\n                "--tcp-keepalive", "300",\n                "--timeout", "300"\n            ],\n            healthcheck={\n                "test": ["CMD", "redis-cli", "ping"],\n                "interval": "10s",\n                "timeout": "3s",\n                "retries": 3,\n                "start_period": "10s"\n            },\n            deploy={\n                "resources": {\n                    "limits": {\n                        "memory": tier_config["memory_limit"],\n                        "cpus": tier_config["cpu_limit"]\n                    },\n                    "reservations": {\n                        "memory": "256M",\n                        "cpus": "0.25"\n                    }\n                }\n            },\n            labels={\n                "ai-agency.customer-id": customer_id,\n                "ai-agency.service": "redis",\n                "ai-agency.tier": tier_config.get("tier", "unknown"),\n                "ai-agency.port": str(port)\n            },\n            networks=[f"customer-{customer_id}-network"]\n        )\n    \n    def _qdrant_config(self, customer_id: str, port: int, tier_config: Dict[str, Any],\n                      credentials: Dict[str, str], ai_model: str,\n                      custom_config: Optional[Dict[str, Any]]) -> ServiceConfiguration:\n        \"\"\"Generate Qdrant service configuration\"\"\"\n        return ServiceConfiguration(\n            name=f"qdrant-{customer_id}",\n            image="qdrant/qdrant:v1.11.0",\n            ports={"6333": port},\n            environment={\n                "QDRANT__SERVICE__HTTP_PORT": "6333",\n                "QDRANT__SERVICE__GRPC_PORT": "6334",\n                "QDRANT__LOG_LEVEL": "INFO",\n                "QDRANT__STORAGE__STORAGE_PATH": "/qdrant/storage",\n                "QDRANT__SERVICE__MAX_REQUEST_SIZE_MB": "32",\n                "QDRANT__CLUSTER__ENABLED": "false",\n                # Production performance tuning\n                "QDRANT__STORAGE__OPTIMIZERS__DEFAULT_SEGMENT_NUMBER": "2",\n                "QDRANT__STORAGE__OPTIMIZERS__MEMMAP_THRESHOLD_KB": "200000",\n                "QDRANT__STORAGE__OPTIMIZERS__INDEXING_THRESHOLD_KB": "20000"\n            },\n            volumes=[\n                f"qdrant_data_{customer_id}:/qdrant/storage",\n                "./config/qdrant/production.yaml:/qdrant/config/production.yaml:ro"\n            ],\n            depends_on=[],\n            healthcheck={\n                "test": ["CMD", "wget", "--no-verbose", "--tries=3", "--spider", "http://localhost:6333/health"],\n                "interval": "30s",\n                "timeout": "10s",\n                "retries": 3,\n                "start_period": "40s"\n            },\n            deploy={\n                "resources": {\n                    "limits": {\n                        "memory": tier_config["memory_limit"],\n                        "cpus": tier_config["cpu_limit"]\n                    },\n                    "reservations": {\n                        "memory": "512M",\n                        "cpus": "0.5"\n                    }\n                }\n            },\n            labels={\n                "ai-agency.customer-id": customer_id,\n                "ai-agency.service": "qdrant",\n                "ai-agency.tier": tier_config.get("tier", "unknown"),\n                "ai-agency.port": str(port)\n            },\n            networks=[f"customer-{customer_id}-network"]\n        )\n    \n    def _mcp_server_config(self, customer_id: str, port: int, tier_config: Dict[str, Any],\n                          credentials: Dict[str, str], ai_model: str,\n                          custom_config: Optional[Dict[str, Any]]) -> ServiceConfiguration:\n        \"\"\"Generate MCP Server service configuration\"\"\"\n        return ServiceConfiguration(\n            name=f"mcp-server-{customer_id}",\n            image="ai-agency/mcp-server:latest",\n            ports={"8080": port},\n            environment={\n                "CUSTOMER_ID": customer_id,\n                "AI_MODEL": ai_model,\n                "POSTGRES_URL": f"postgresql://customer_{customer_id}:{credentials['postgres_password']}@postgres-{customer_id}:5432/customer_{customer_id}",\n                "REDIS_URL": f"redis://redis-{customer_id}:6379",\n                "QDRANT_URL": f"http://qdrant-{customer_id}:6333",\n                "JWT_SECRET": credentials["jwt_secret"],\n                "ENCRYPTION_KEY": credentials["encryption_key"],\n                "LOG_LEVEL": "INFO",\n                "METRICS_ENABLED": "true",\n                "TRACING_ENABLED": "true"\n            },\n            volumes=[\n                f"./logs/mcp-{customer_id}:/app/logs",\n                f"./config/mcp/{customer_id}:/app/config:ro"\n            ],\n            depends_on=[f"postgres-{customer_id}", f"redis-{customer_id}"],\n            healthcheck={\n                "test": ["CMD", "curl", "-f", "http://localhost:8080/health"],\n                "interval": "30s",\n                "timeout": "5s",\n                "retries": 3,\n                "start_period": "60s"\n            },\n            deploy={\n                "resources": {\n                    "limits": {\n                        "memory": tier_config["memory_limit"],\n                        "cpus": tier_config["cpu_limit"]\n                    },\n                    "reservations": {\n                        "memory": "512M",\n                        "cpus": "0.5"\n                    }\n                }\n            },\n            labels={\n                "ai-agency.customer-id": customer_id,\n                "ai-agency.service": "mcp-server",\n                "ai-agency.tier": tier_config.get("tier", "unknown"),\n                "ai-agency.port": str(port)\n            },\n            networks=[f"customer-{customer_id}-network"]\n        )\n    \n    # Additional service configs would go here...\n    def _memory_monitor_config(self, customer_id: str, port: int, tier_config: Dict[str, Any],\n                             credentials: Dict[str, str], ai_model: str,\n                             custom_config: Optional[Dict[str, Any]]) -> ServiceConfiguration:\n        \"\"\"Generate Memory Monitor service configuration\"\"\"\n        return ServiceConfiguration(\n            name=f"memory-monitor-{customer_id}",\n            image=f"ai-agency-memory-monitor:{customer_id}",\n            ports={"8080": port},\n            environment={\n                "CUSTOMER_ID": customer_id,\n                "POSTGRES_URL": f"postgresql://customer_{customer_id}:{credentials['postgres_password']}@postgres-{customer_id}:5432/customer_{customer_id}",\n                "REDIS_URL": f"redis://redis-{customer_id}:6379",\n                "QDRANT_URL": f"http://qdrant-{customer_id}:6333",\n                "MONITORING_INTERVAL": "30",\n                "SLA_ENFORCEMENT": "true",\n                "METRICS_RETENTION_DAYS": "30",\n                "ALERT_THRESHOLD_MEMORY": "0.85",\n                "ALERT_THRESHOLD_CPU": "0.80",\n                "ALERT_THRESHOLD_RESPONSE_TIME_MS": "500"\n            },\n            volumes=[\n                f"./logs/memory-{customer_id}:/app/logs"\n            ],\n            depends_on=[f"postgres-{customer_id}", f"redis-{customer_id}"],\n            healthcheck={\n                "test": ["CMD", "curl", "-f", "http://localhost:8080/health"],\n                "interval": "30s",\n                "timeout": "5s",\n                "retries": 3\n            },\n            deploy={\n                "resources": {\n                    "limits": {\n                        "memory": "1G",\n                        "cpus": "0.5"\n                    },\n                    "reservations": {\n                        "memory": "256M",\n                        "cpus": "0.1"\n                    }\n                }\n            },\n            labels={\n                "ai-agency.customer-id": customer_id,\n                "ai-agency.service": "memory-monitor",\n                "ai-agency.tier": tier_config.get("tier", "unknown"),\n                "ai-agency.port": str(port)\n            },\n            networks=[f"customer-{customer_id}-network"]\n        )\n    \n    # Stub implementations for other services\n    def _qdrant_grpc_config(self, *args, **kwargs) -> ServiceConfiguration:\n        return self._qdrant_config(*args, **kwargs)  # Simplified for now\n    \n    def _neo4j_config(self, *args, **kwargs) -> ServiceConfiguration:\n        # Implementation would go here\n        pass\n    \n    def _neo4j_bolt_config(self, *args, **kwargs) -> ServiceConfiguration:\n        # Implementation would go here  \n        pass\n    \n    def _security_api_config(self, *args, **kwargs) -> ServiceConfiguration:\n        # Implementation would go here\n        pass\n    \n    def _service_to_dict(self, service: ServiceConfiguration) -> Dict[str, Any]:\n        \"\"\"Convert ServiceConfiguration to Docker Compose service dict\"\"\"\n        service_dict = {\n            "image": service.image,\n            "container_name": service.name,\n            "ports": [f"{host_port}:{container_port}" for container_port, host_port in service.ports.items()],\n            "environment": service.environment,\n            "volumes": service.volumes,\n            "healthcheck": service.healthcheck,\n            "deploy": service.deploy,\n            "labels": [f"{k}={v}" for k, v in service.labels.items()],\n            "restart": "unless-stopped",\n            "logging": {\n                "driver": "json-file",\n                "options": {\n                    "max-size": "100m",\n                    "max-file": "3"\n                }\n            }\n        }\n        \n        if service.depends_on:\n            service_dict["depends_on"] = service.depends_on\n        \n        if service.command:\n            service_dict["command"] = service.command\n        \n        if service.networks:\n            service_dict["networks"] = service.networks\n        \n        return service_dict\n    \n    def _generate_env_file(self,\n                          customer_id: str,\n                          tier: str,\n                          credentials: Dict[str, str],\n                          allocated_ports: Dict[ServiceType, int],\n                          ai_model: str,\n                          env_file_path: Path):\n        \"\"\"Generate environment file for customer deployment\"\"\"\n        tier_config = self.tier_configs[tier]\n        \n        env_content = f\"\"\"# AI Agency Platform - Customer Environment Configuration\n# Customer: {customer_id}\n# Tier: {tier}\n# Generated: {os.environ.get('TIMESTAMP', 'auto-generated')}\n\n# Customer Identification\nCUSTOMER_ID={customer_id}\nCUSTOMER_TIER={tier}\n\n# AI Model Configuration\nAI_MODEL={ai_model}\n\n# Allocated Ports\n\"\"\"\n        \n        for service_type, port in allocated_ports.items():\n            port_var_name = f\"{service_type.value.upper().replace('_', '_')}_PORT\"\n            env_content += f\"{port_var_name}={port}\\n\"\n        \n        env_content += f\"\"\"\\n# Resource Limits\nTIER_MEMORY_LIMIT={tier_config['memory_limit']}\nTIER_CPU_LIMIT={tier_config['cpu_limit']}\n\n# Security Credentials\nSECURE_PASSWORD={credentials['postgres_password']}\nJWT_SECRET={credentials['jwt_secret']}\nENCRYPTION_KEY={credentials['encryption_key']}\n\n# Neo4j Credentials (if applicable)\nNEO4J_PASSWORD={credentials.get('neo4j_password', credentials['postgres_password'])}\n\n# Redis Auth (if applicable)\nREDIS_AUTH={credentials.get('redis_auth', '')}\n\n# Service URLs (for internal communication)\nPOSTGRES_URL=postgresql://customer_{customer_id}:{credentials['postgres_password']}@postgres-{customer_id}:5432/customer_{customer_id}\nREDIS_URL=redis://redis-{customer_id}:6379\nQDRANT_URL=http://qdrant-{customer_id}:6333\n\n# Monitoring and Logging\nLOG_LEVEL=INFO\nMETRICS_ENABLED=true\nTRACING_ENABLED=true\n\n# Performance Tuning\nMONITORING_INTERVAL=30\nSLA_ENFORCEMENT=true\nALERT_THRESHOLD_MEMORY=0.85\nALERT_THRESHOLD_CPU=0.80\nALERT_THRESHOLD_RESPONSE_TIME_MS=500\n\"\"\"\n        \n        with open(env_file_path, 'w') as f:\n            f.write(env_content)\n        \n        logger.info(f\"✅ Generated environment file: {env_file_path}\")\n    \n    def generate_deployment_script(self, customer_id: str, compose_file: Path) -> Path:\n        \"\"\"Generate deployment script for customer environment\"\"\"\n        script_path = self.output_dir / f\"deploy-{customer_id}.sh\"\n        \n        script_content = f\"\"\"#!/bin/bash\n# AI Agency Platform - Customer Deployment Script\n# Customer: {customer_id}\n# Generated automatically - do not edit manually\n\nset -e  # Exit on any error\n\nCUSTOMER_ID=\"{customer_id}\"\nCOMPOSE_FILE=\"{compose_file}\"\nENV_FILE=\"{compose_file.parent}/.env.{customer_id}\"\n\necho \"🚀 Deploying environment for customer $CUSTOMER_ID...\"\n\n# Validate files exist\nif [ ! -f \"$COMPOSE_FILE\" ]; then\n    echo \"❌ Compose file not found: $COMPOSE_FILE\"\n    exit 1\nfi\n\nif [ ! -f \"$ENV_FILE\" ]; then\n    echo \"❌ Environment file not found: $ENV_FILE\"\n    exit 1\nfi\n\n# Load environment variables\nsource \"$ENV_FILE\"\n\n# Create necessary directories\nmkdir -p \"./logs/mcp-$CUSTOMER_ID\"\nmkdir -p \"./logs/memory-$CUSTOMER_ID\"\nmkdir -p \"./config/mcp/$CUSTOMER_ID\"\n\n# Deploy using docker-compose\necho \"📦 Starting services...\"\ndocker-compose -f \"$COMPOSE_FILE\" --env-file \"$ENV_FILE\" up -d\n\n# Wait for services to become healthy\necho \"🔍 Waiting for services to become healthy...\"\nsleep 30\n\n# Health check\necho \"❤️ Performing health check...\"\ndocker-compose -f \"$COMPOSE_FILE\" ps\n\n# Verify critical services\nif docker-compose -f \"$COMPOSE_FILE\" ps | grep -q \"Up.*healthy\"; then\n    echo \"✅ Customer environment deployed successfully!\"\nelse\n    echo \"⚠️ Some services may not be fully healthy. Check docker-compose logs for details.\"\nfi\n\necho \"📊 Deployment completed for customer $CUSTOMER_ID\"\necho \"🌐 Services available at allocated ports (check .env file for details)\"\n\"\"\"\n        \n        with open(script_path, 'w') as f:\n            f.write(script_content)\n        \n        # Make script executable\n        script_path.chmod(0o755)\n        \n        logger.info(f\"✅ Generated deployment script: {script_path}\")\n        \n        return script_path


if __name__ == \"__main__\":\n    # Demo functionality\n    async def main():\n        from .port_allocator import create_port_allocator, ServiceType\n        \n        # Create port allocator\n        port_allocator = await create_port_allocator()\n        \n        try:\n            # Create generator\n            generator = DockerComposeGenerator(port_allocator)\n            \n            # Test customer\n            test_customer = \"demo_customer_001\"\n            tier = \"professional\"\n            ai_model = \"claude-3.5-sonnet\"\n            \n            # Allocate ports\n            services = [ServiceType.POSTGRES, ServiceType.REDIS, ServiceType.QDRANT, \n                       ServiceType.MCP_SERVER, ServiceType.MEMORY_MONITOR]\n            allocated_ports = {}\n            \n            for service_type in services:\n                allocation = await port_allocator.allocate_port(test_customer, service_type)\n                allocated_ports[service_type] = allocation.port\n            \n            # Generate credentials\n            credentials = {\n                \"postgres_password\": \"test_postgres_pass_123\",\n                \"jwt_secret\": \"test_jwt_secret_456\",\n                \"encryption_key\": \"test_encryption_key_789\"\n            }\n            \n            # Generate configuration\n            compose_file = await generator.generate_customer_compose(\n                customer_id=test_customer,\n                tier=tier,\n                ai_model=ai_model,\n                credentials=credentials,\n                allocated_ports=allocated_ports\n            )\n            \n            print(f\"✅ Generated configuration: {compose_file}\")\n            \n            # Generate deployment script\n            script_file = generator.generate_deployment_script(test_customer, compose_file)\n            print(f\"✅ Generated deployment script: {script_file}\")\n            \n        finally:\n            await port_allocator.close()\n    \n    import asyncio\n    asyncio.run(main())