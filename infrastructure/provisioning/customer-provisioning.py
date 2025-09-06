#!/usr/bin/env python3
"""
Customer Provisioning Service
Automated per-customer MCP server deployment pipeline for 30-second EA availability

Handles:
- Customer purchase webhook processing
- Pre-warmed resource pool management
- Per-customer MCP server instantiation
- Database schema initialization
- Monitoring setup and health validation
- EA assignment and welcome call scheduling
"""

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

import aiohttp
import asyncpg
import redis.asyncio as redis
from kubernetes_asyncio import client, config
from kubernetes_asyncio.client.rest import ApiException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class CustomerProvisioningRequest:
    """Customer provisioning request data"""
    customer_id: str
    email: str
    phone: str
    plan_type: str
    payment_id: str
    requested_region: str = "us-east-1"
    ea_preference: str = "voice_priority"  # voice_priority, text_only, hybrid
    ai_model: str = "gpt-4o"  # gpt-4o, claude-3.5-sonnet, local
    
@dataclass
class ProvisioningResult:
    """Result of customer provisioning operation"""
    customer_id: str
    mcp_server_url: str
    ea_phone_number: str
    database_url: str
    redis_namespace: str
    qdrant_collection: str
    status: str
    provisioning_time: float
    welcome_call_scheduled: bool
    infrastructure_ready: bool


class CustomerProvisioningService:
    """
    Handles automated customer provisioning with 30-second SLA
    
    Architecture:
    - Pre-warmed resource pools for instant allocation
    - Kubernetes-based per-customer MCP deployment
    - Background infrastructure completion during welcome call
    - Progressive capability unlock as infrastructure comes online
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.redis_pool = None
        self.postgres_pool = None
        self.k8s_client = None
        self.pre_warmed_pools = {
            "mcp_containers": [],
            "phone_numbers": [],
            "ea_instances": [],
            "database_schemas": []
        }
        
    async def initialize(self):
        """Initialize provisioning service connections and pools"""
        try:
            # Initialize Redis connection pool
            self.redis_pool = redis.Redis(
                host=self.config["redis"]["host"],
                port=self.config["redis"]["port"],
                decode_responses=True
            )
            
            # Initialize PostgreSQL connection pool
            self.postgres_pool = await asyncpg.create_pool(
                host=self.config["postgres"]["host"],
                port=self.config["postgres"]["port"],
                database=self.config["postgres"]["database"],
                user=self.config["postgres"]["user"],
                password=self.config["postgres"]["password"],
                min_size=5, max_size=20
            )
            
            # Initialize Kubernetes client
            await config.load_incluster_config()  # For in-cluster deployment
            self.k8s_client = client.ApiClient()
            
            # Initialize pre-warmed resource pools
            await self._initialize_pre_warmed_pools()
            
            logger.info("Customer provisioning service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize provisioning service: {e}")
            raise
    
    async def _initialize_pre_warmed_pools(self):
        """Initialize and maintain pre-warmed resource pools"""
        try:
            # Pre-warm MCP container pool (5-10 ready containers)
            await self._maintain_mcp_container_pool()
            
            # Pre-allocate Twilio phone numbers
            await self._maintain_phone_number_pool()
            
            # Pre-warm EA instances
            await self._maintain_ea_instance_pool()
            
            # Pre-create database schemas
            await self._maintain_database_schema_pool()
            
            logger.info("Pre-warmed resource pools initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize pre-warmed pools: {e}")
            raise
    
    async def provision_customer(self, request: CustomerProvisioningRequest) -> ProvisioningResult:
        """
        Provision complete customer infrastructure with 30-second SLA
        
        Strategy:
        1. Immediate EA assignment from pre-warmed pool (5-10 seconds)
        2. Schedule welcome call while provisioning infrastructure
        3. Complete infrastructure setup during call (background)
        4. Progressive capability unlock as services come online
        """
        start_time = time.time()
        
        try:
            logger.info(f"Starting provisioning for customer {request.customer_id}")
            
            # Phase 1: Immediate EA Assignment (Target: 5-10 seconds)
            ea_assignment = await self._assign_pre_warmed_ea(request)
            
            # Phase 2: Schedule Welcome Call (Target: 30-60 seconds total)
            welcome_call_task = asyncio.create_task(
                self._schedule_welcome_call(request, ea_assignment)
            )
            
            # Phase 3: Background Infrastructure Provisioning (During call)
            infrastructure_task = asyncio.create_task(
                self._provision_complete_infrastructure(request, ea_assignment)
            )
            
            # Wait for EA assignment and welcome call scheduling
            await welcome_call_task
            
            # Create initial result with EA available immediately  
            provisioning_time = time.time() - start_time
            initial_result = ProvisioningResult(
                customer_id=request.customer_id,
                mcp_server_url=ea_assignment["mcp_server_url"],
                ea_phone_number=ea_assignment["phone_number"],
                database_url=ea_assignment["database_url"], 
                redis_namespace=ea_assignment["redis_namespace"],
                qdrant_collection=ea_assignment["qdrant_collection"],
                status="ea_assigned_welcome_scheduled",
                provisioning_time=provisioning_time,
                welcome_call_scheduled=True,
                infrastructure_ready=False  # Will be updated when complete
            )
            
            # Continue infrastructure provisioning in background
            asyncio.create_task(
                self._complete_infrastructure_and_update_status(
                    request, infrastructure_task, initial_result
                )
            )
            
            logger.info(
                f"Customer {request.customer_id} EA assigned in {provisioning_time:.2f}s, "
                f"infrastructure provisioning in progress"
            )
            
            return initial_result
            
        except Exception as e:
            logger.error(f"Failed to provision customer {request.customer_id}: {e}")
            raise
    
    async def _assign_pre_warmed_ea(self, request: CustomerProvisioningRequest) -> Dict[str, Any]:
        """Assign pre-warmed EA and resources from pools"""
        try:
            # Get pre-warmed MCP container
            mcp_container = await self._allocate_mcp_container(request.customer_id)
            
            # Get pre-allocated phone number
            phone_number = await self._allocate_phone_number(request.customer_id)
            
            # Get pre-warmed EA instance
            ea_instance = await self._allocate_ea_instance(request.customer_id)
            
            # Assign Redis namespace and Qdrant collection
            redis_namespace = f"customer_{request.customer_id}"
            qdrant_collection = f"customer_{request.customer_id}_memories"
            
            # Quick database schema assignment
            database_url = await self._allocate_database_schema(request.customer_id)
            
            return {
                "mcp_server_url": mcp_container["url"],
                "mcp_container_id": mcp_container["id"],
                "phone_number": phone_number,
                "ea_instance_id": ea_instance["id"],
                "database_url": database_url,
                "redis_namespace": redis_namespace,
                "qdrant_collection": qdrant_collection,
                "assigned_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to assign pre-warmed EA for {request.customer_id}: {e}")
            raise
    
    async def _schedule_welcome_call(self, request: CustomerProvisioningRequest, ea_assignment: Dict[str, Any]):
        """Schedule EA welcome call within 60 seconds of purchase"""
        try:
            # Configure EA with customer-specific context
            ea_config = {
                "customer_id": request.customer_id,
                "customer_phone": request.phone,
                "customer_email": request.email,
                "plan_type": request.plan_type,
                "ea_preference": request.ea_preference,
                "welcome_script": "business_discovery_call",
                "call_objective": "learn_business_create_first_automation"
            }
            
            # Update EA instance with customer configuration
            await self._configure_ea_instance(
                ea_assignment["ea_instance_id"], 
                ea_config
            )
            
            # Schedule immediate welcome call
            call_request = {
                "customer_id": request.customer_id,
                "customer_phone": request.phone,
                "ea_phone_number": ea_assignment["phone_number"],
                "call_type": "welcome_business_discovery",
                "schedule_time": "immediate",  # Call within 60 seconds
                "expected_duration": 300,  # 5 minutes for business learning
                "objectives": [
                    "introduce_ea_capabilities",
                    "learn_business_context", 
                    "create_first_automation",
                    "schedule_follow_up"
                ]
            }
            
            await self._trigger_welcome_call(call_request)
            
            logger.info(f"Welcome call scheduled for customer {request.customer_id}")
            
        except Exception as e:
            logger.error(f"Failed to schedule welcome call for {request.customer_id}: {e}")
            raise
    
    async def _provision_complete_infrastructure(self, request: CustomerProvisioningRequest, ea_assignment: Dict[str, Any]):
        """Provision complete per-customer infrastructure during welcome call"""
        try:
            # Deploy complete per-customer MCP server stack
            deployment_config = await self._generate_customer_deployment_config(request, ea_assignment)
            
            # Deploy to Kubernetes
            await self._deploy_customer_infrastructure(request.customer_id, deployment_config)
            
            # Initialize customer-specific databases and collections
            await self._initialize_customer_data_stores(request, ea_assignment)
            
            # Setup customer-specific monitoring and alerting
            await self._setup_customer_monitoring(request.customer_id)
            
            # Configure backup and disaster recovery
            await self._configure_customer_backup(request.customer_id)
            
            # Validate infrastructure health
            health_check = await self._validate_customer_infrastructure(request.customer_id)
            
            if health_check["status"] == "healthy":
                logger.info(f"Complete infrastructure provisioned for customer {request.customer_id}")
            else:
                logger.error(f"Infrastructure health check failed for customer {request.customer_id}: {health_check}")
                
        except Exception as e:
            logger.error(f"Failed to provision complete infrastructure for {request.customer_id}: {e}")
            raise
    
    async def _maintain_mcp_container_pool(self):
        """Maintain pool of 5-10 ready MCP containers"""
        try:
            current_pool_size = len(self.pre_warmed_pools["mcp_containers"])
            target_pool_size = self.config["provisioning"]["mcp_pool_size"]
            
            if current_pool_size < target_pool_size:
                containers_to_create = target_pool_size - current_pool_size
                
                for _ in range(containers_to_create):
                    container_id = f"mcp-pool-{uuid.uuid4().hex[:8]}"
                    
                    # Deploy pre-warmed MCP container
                    container_config = {
                        "name": container_id,
                        "image": "ai-agency-platform/mcp-server:latest",
                        "resources": {
                            "requests": {"cpu": "100m", "memory": "256Mi"},
                            "limits": {"cpu": "500m", "memory": "512Mi"}
                        },
                        "env": {
                            "POOL_CONTAINER": "true",
                            "WARM_STATE": "ready_for_assignment"
                        }
                    }
                    
                    deployment_result = await self._deploy_k8s_container(container_config)
                    
                    self.pre_warmed_pools["mcp_containers"].append({
                        "id": container_id,
                        "url": f"http://{container_id}.default.svc.cluster.local:8000",
                        "status": "available",
                        "created_at": datetime.utcnow().isoformat()
                    })
                    
                logger.info(f"MCP container pool maintained: {len(self.pre_warmed_pools['mcp_containers'])} containers")
                
        except Exception as e:
            logger.error(f"Failed to maintain MCP container pool: {e}")
    
    async def _allocate_mcp_container(self, customer_id: str) -> Dict[str, Any]:
        """Allocate MCP container from pre-warmed pool"""
        try:
            available_containers = [
                c for c in self.pre_warmed_pools["mcp_containers"] 
                if c["status"] == "available"
            ]
            
            if not available_containers:
                # Emergency: Create container on demand
                logger.warning(f"No pre-warmed MCP containers available, creating on-demand for {customer_id}")
                return await self._create_mcp_container_on_demand(customer_id)
            
            # Allocate first available container
            allocated_container = available_containers[0]
            allocated_container["status"] = "allocated"
            allocated_container["customer_id"] = customer_id
            allocated_container["allocated_at"] = datetime.utcnow().isoformat()
            
            # Customize container for customer
            await self._customize_mcp_container(allocated_container, customer_id)
            
            # Schedule pool replenishment
            asyncio.create_task(self._maintain_mcp_container_pool())
            
            return allocated_container
            
        except Exception as e:
            logger.error(f"Failed to allocate MCP container for {customer_id}: {e}")
            raise
    
    async def get_customer_status(self, customer_id: str) -> Dict[str, Any]:
        """Get current provisioning status for customer"""
        try:
            async with self.postgres_pool.acquire() as conn:
                result = await conn.fetchrow("""
                    SELECT * FROM customer_provisioning_status 
                    WHERE customer_id = $1
                """, customer_id)
                
                if result:
                    return dict(result)
                else:
                    return {"status": "not_found", "customer_id": customer_id}
                    
        except Exception as e:
            logger.error(f"Failed to get customer status for {customer_id}: {e}")
            return {"status": "error", "error": str(e)}
    
    async def cleanup_customer_infrastructure(self, customer_id: str) -> bool:
        """Clean up customer infrastructure (for cancellations/testing)"""
        try:
            # Remove Kubernetes deployments
            await self._cleanup_k8s_resources(customer_id)
            
            # Clear customer databases
            await self._cleanup_customer_databases(customer_id)
            
            # Release phone number back to pool
            await self._release_phone_number(customer_id)
            
            # Clean up monitoring
            await self._cleanup_customer_monitoring(customer_id)
            
            logger.info(f"Customer infrastructure cleaned up for {customer_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cleanup customer infrastructure for {customer_id}: {e}")
            return False
    
    async def close(self):
        """Close all connections"""
        try:
            if self.redis_pool:
                await self.redis_pool.aclose()
            if self.postgres_pool:
                await self.postgres_pool.close()
            if self.k8s_client:
                await self.k8s_client.close()
                
            logger.info("Customer provisioning service connections closed")
            
        except Exception as e:
            logger.error(f"Error closing provisioning service connections: {e}")


# Configuration management
def load_provisioning_config() -> Dict[str, Any]:
    """Load provisioning service configuration"""
    return {
        "redis": {
            "host": os.getenv("REDIS_HOST", "localhost"),
            "port": int(os.getenv("REDIS_PORT", "6379"))
        },
        "postgres": {
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "database": os.getenv("POSTGRES_DB", "mcphub"),
            "user": os.getenv("POSTGRES_USER", "mcphub"),
            "password": os.getenv("POSTGRES_PASSWORD", "mcphub_password")
        },
        "provisioning": {
            "mcp_pool_size": int(os.getenv("MCP_POOL_SIZE", "8")),
            "phone_pool_size": int(os.getenv("PHONE_POOL_SIZE", "20")),
            "ea_pool_size": int(os.getenv("EA_POOL_SIZE", "10")),
            "provisioning_timeout": int(os.getenv("PROVISIONING_TIMEOUT", "300")),
            "welcome_call_delay": int(os.getenv("WELCOME_CALL_DELAY", "60"))
        },
        "twilio": {
            "account_sid": os.getenv("TWILIO_ACCOUNT_SID"),
            "auth_token": os.getenv("TWILIO_AUTH_TOKEN"),
            "phone_number_pool": os.getenv("TWILIO_PHONE_POOL", "").split(",")
        },
        "kubernetes": {
            "namespace": os.getenv("K8S_NAMESPACE", "ai-agency-customers"),
            "registry": os.getenv("DOCKER_REGISTRY", "ai-agency-platform")
        }
    }


# FastAPI webhook endpoint for purchase processing
async def process_customer_purchase_webhook(request_data: Dict[str, Any]) -> ProvisioningResult:
    """Process customer purchase webhook and trigger provisioning"""
    provisioning_request = CustomerProvisioningRequest(
        customer_id=request_data["customer_id"],
        email=request_data["customer_email"],
        phone=request_data["customer_phone"],
        plan_type=request_data["plan_type"],
        payment_id=request_data["payment_id"],
        requested_region=request_data.get("region", "us-east-1"),
        ea_preference=request_data.get("ea_preference", "voice_priority"),
        ai_model=request_data.get("ai_model", "gpt-4o")
    )
    
    config = load_provisioning_config()
    provisioning_service = CustomerProvisioningService(config)
    
    try:
        await provisioning_service.initialize()
        result = await provisioning_service.provision_customer(provisioning_request)
        return result
    finally:
        await provisioning_service.close()


if __name__ == "__main__":
    # Test provisioning service
    async def test_provisioning():
        config = load_provisioning_config()
        service = CustomerProvisioningService(config)
        
        try:
            await service.initialize()
            
            test_request = CustomerProvisioningRequest(
                customer_id="test_customer_001",
                email="test@example.com",
                phone="+15551234567",
                plan_type="professional",
                payment_id="test_payment_001"
            )
            
            result = await service.provision_customer(test_request)
            print(f"Provisioning result: {asdict(result)}")
            
        finally:
            await service.close()
    
    asyncio.run(test_provisioning())