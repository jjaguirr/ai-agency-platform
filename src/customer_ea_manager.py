#!/usr/bin/env python3
"""
AI Agency Platform - Customer Executive Assistant Manager
Multi-tenant EA provisioning and management system for WhatsApp integration
"""

import asyncio
import json
import logging
import os
import uuid
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import redis
import psycopg2
from psycopg2.extras import RealDictCursor

from agents.executive_assistant import ExecutiveAssistant, ConversationChannel, BusinessContext

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CustomerTier(Enum):
    """Customer subscription tiers"""
    TRIAL = "trial"
    PREMIUM_CASUAL = "premium_casual"
    BUSINESS_PRO = "business_pro"
    ENTERPRISE = "enterprise"

class EAStatus(Enum):
    """EA Instance Status"""
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"

@dataclass
class CustomerEAInstance:
    """Customer EA Instance Configuration"""
    customer_id: str
    whatsapp_number: str
    phone_number: str = ""
    email: str = ""
    business_name: str = ""
    tier: CustomerTier = CustomerTier.TRIAL
    status: EAStatus = EAStatus.PROVISIONING
    ea_name: str = "Sarah"
    personality: str = "professional"
    
    # Resource limits based on tier
    monthly_message_limit: int = 1000
    workflow_limit: int = 5
    memory_retention_days: int = 30
    
    # Infrastructure config
    redis_db: int = 0
    qdrant_collection: str = ""
    postgres_schema: str = ""
    
    # Timestamps
    created_at: datetime = None
    activated_at: datetime = None
    last_interaction: datetime = None
    trial_expires_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.trial_expires_at is None and self.tier == CustomerTier.TRIAL:
            self.trial_expires_at = datetime.now() + timedelta(days=14)  # 14-day trial
        if not self.qdrant_collection:
            self.qdrant_collection = f"customer_{self.customer_id}_memory"
        if not self.postgres_schema:
            # Use cryptographic hash for secure, consistent customer isolation
            customer_hash = hashlib.sha256(self.customer_id.encode()).hexdigest()
            self.postgres_schema = f"customer_{customer_hash[:16]}"

class CustomerEAManager:
    """
    Multi-tenant Customer Executive Assistant Management System
    
    Features:
    - Automatic customer provisioning from WhatsApp interactions
    - Tier-based resource allocation and limits
    - Infrastructure isolation (Redis DB, Qdrant collections, PostgreSQL schemas)
    - Customer lifecycle management
    - Usage tracking and billing integration
    """
    
    def __init__(self):
        # Master customer registry (Redis)
        self.registry = redis.Redis(
            host='localhost', 
            port=6379, 
            db=15,  # Dedicated DB for customer registry
            decode_responses=True
        )
        
        # Master database connection
        try:
            self.db_connection = psycopg2.connect(
                host="localhost",
                database="mcphub",
                user="mcphub", 
                password="mcphub_password"
            )
            self._initialize_customer_tables()
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            self.db_connection = None
        
        # Active EA instances cache
        self.ea_instances: Dict[str, ExecutiveAssistant] = {}
        
        # Tier configurations
        self.tier_configs = {
            CustomerTier.TRIAL: {
                "monthly_message_limit": 500,
                "workflow_limit": 2,
                "memory_retention_days": 7,
                "features": ["basic_conversation", "simple_workflows"]
            },
            CustomerTier.PREMIUM_CASUAL: {
                "monthly_message_limit": 2000,
                "workflow_limit": 10,
                "memory_retention_days": 90,
                "features": ["advanced_conversation", "workflow_templates", "business_learning"]
            },
            CustomerTier.BUSINESS_PRO: {
                "monthly_message_limit": 10000,
                "workflow_limit": 50,
                "memory_retention_days": 365,
                "features": ["all_features", "priority_support", "custom_integrations"]
            },
            CustomerTier.ENTERPRISE: {
                "monthly_message_limit": 50000,
                "workflow_limit": 200,
                "memory_retention_days": -1,  # Unlimited
                "features": ["all_features", "dedicated_support", "custom_development"]
            }
        }
        
        logger.info("Customer EA Manager initialized")
    
    def _initialize_customer_tables(self):
        """Initialize customer management tables"""
        try:
            with self.db_connection.cursor() as cursor:
                # Customer EA instances table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS customer_ea_instances (
                        customer_id VARCHAR(255) PRIMARY KEY,
                        whatsapp_number VARCHAR(50) NOT NULL,
                        phone_number VARCHAR(50),
                        email VARCHAR(255),
                        business_name VARCHAR(255),
                        tier VARCHAR(50) DEFAULT 'trial',
                        status VARCHAR(50) DEFAULT 'provisioning',
                        ea_name VARCHAR(100) DEFAULT 'Sarah',
                        personality VARCHAR(50) DEFAULT 'professional',
                        monthly_message_limit INTEGER DEFAULT 1000,
                        workflow_limit INTEGER DEFAULT 5,
                        memory_retention_days INTEGER DEFAULT 30,
                        redis_db INTEGER,
                        qdrant_collection VARCHAR(255),
                        postgres_schema VARCHAR(255),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        activated_at TIMESTAMP,
                        last_interaction TIMESTAMP,
                        trial_expires_at TIMESTAMP,
                        metadata JSONB DEFAULT '{}'
                    )
                """)
                
                # Customer usage tracking
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS customer_usage_tracking (
                        id SERIAL PRIMARY KEY,
                        customer_id VARCHAR(255) REFERENCES customer_ea_instances(customer_id),
                        month_year VARCHAR(7), -- YYYY-MM format
                        messages_sent INTEGER DEFAULT 0,
                        workflows_created INTEGER DEFAULT 0,
                        ai_interactions INTEGER DEFAULT 0,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(customer_id, month_year)
                    )
                """)
                
                # Customer interaction log
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS customer_interaction_log (
                        id SERIAL PRIMARY KEY,
                        customer_id VARCHAR(255) REFERENCES customer_ea_instances(customer_id),
                        channel VARCHAR(50),
                        message_type VARCHAR(50),
                        conversation_id VARCHAR(255),
                        intent_classified VARCHAR(100),
                        confidence_score FLOAT,
                        workflow_created BOOLEAN DEFAULT FALSE,
                        response_time_ms INTEGER,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        metadata JSONB DEFAULT '{}'
                    )
                """)
                
                self.db_connection.commit()
                logger.info("Customer management tables initialized")
                
        except Exception as e:
            logger.error(f"Error initializing customer tables: {e}")
    
    async def provision_customer_from_whatsapp(self, whatsapp_number: str, tier: CustomerTier = CustomerTier.TRIAL) -> CustomerEAInstance:
        """
        Automatically provision a new customer EA from WhatsApp interaction
        """
        try:
            # Generate customer ID from WhatsApp number
            customer_id = f"whatsapp_{whatsapp_number.replace('+', '').replace(' ', '')}"
            
            # Check if customer already exists
            existing_instance = await self.get_customer_instance(customer_id)
            if existing_instance:
                logger.info(f"Customer {customer_id} already exists, returning existing instance")
                return existing_instance
            
            # Allocate infrastructure resources  
            redis_db = await self._allocate_redis_db()
            # Use cryptographic hash for secure, consistent customer isolation
            customer_hash = hashlib.sha256(customer_id.encode()).hexdigest()
            postgres_schema = f"customer_{customer_hash[:16]}"
            
            # Get tier configuration
            tier_config = self.tier_configs[tier]
            
            # Create customer instance
            instance = CustomerEAInstance(
                customer_id=customer_id,
                whatsapp_number=whatsapp_number,
                tier=tier,
                monthly_message_limit=tier_config["monthly_message_limit"],
                workflow_limit=tier_config["workflow_limit"],
                memory_retention_days=tier_config["memory_retention_days"],
                redis_db=redis_db,
                postgres_schema=postgres_schema
            )
            
            # Store in database
            await self._store_customer_instance(instance)
            
            # Store in Redis registry for fast lookup
            self.registry.setex(
                f"customer:{customer_id}",
                86400,  # 24 hour cache
                json.dumps(asdict(instance), default=str)
            )
            
            # Initialize EA instance
            ea_instance = await self._initialize_ea_instance(instance)
            self.ea_instances[customer_id] = ea_instance
            
            # Mark as active
            instance.status = EAStatus.ACTIVE
            instance.activated_at = datetime.now()
            await self._update_customer_instance(instance)
            
            logger.info(f"✅ Successfully provisioned customer EA for {whatsapp_number} -> {customer_id}")
            
            return instance
            
        except Exception as e:
            logger.error(f"Error provisioning customer from WhatsApp {whatsapp_number}: {e}")
            raise
    
    async def get_customer_instance(self, customer_id: str) -> Optional[CustomerEAInstance]:
        """Get customer EA instance"""
        try:
            # Try Redis cache first
            cached = self.registry.get(f"customer:{customer_id}")
            if cached:
                data = json.loads(cached)
                # Convert string timestamps back to datetime
                for field in ['created_at', 'activated_at', 'last_interaction', 'trial_expires_at']:
                    if data.get(field):
                        data[field] = datetime.fromisoformat(data[field])
                return CustomerEAInstance(**data)
            
            # Fallback to database
            if self.db_connection:
                with self.db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        "SELECT * FROM customer_ea_instances WHERE customer_id = %s",
                        (customer_id,)
                    )
                    result = cursor.fetchone()
                    
                    if result:
                        return CustomerEAInstance(
                            customer_id=result['customer_id'],
                            whatsapp_number=result['whatsapp_number'],
                            phone_number=result['phone_number'] or "",
                            email=result['email'] or "",
                            business_name=result['business_name'] or "",
                            tier=CustomerTier(result['tier']),
                            status=EAStatus(result['status']),
                            ea_name=result['ea_name'],
                            personality=result['personality'],
                            monthly_message_limit=result['monthly_message_limit'],
                            workflow_limit=result['workflow_limit'],
                            memory_retention_days=result['memory_retention_days'],
                            redis_db=result['redis_db'],
                            qdrant_collection=result['qdrant_collection'],
                            postgres_schema=result['postgres_schema'],
                            created_at=result['created_at'],
                            activated_at=result['activated_at'],
                            last_interaction=result['last_interaction'],
                            trial_expires_at=result['trial_expires_at']
                        )
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting customer instance {customer_id}: {e}")
            return None
    
    async def get_ea_instance(self, customer_id: str) -> Optional[ExecutiveAssistant]:
        """Get or create EA instance for customer"""
        try:
            # Return cached instance if available
            if customer_id in self.ea_instances:
                return self.ea_instances[customer_id]
            
            # Get customer configuration
            customer_instance = await self.get_customer_instance(customer_id)
            if not customer_instance:
                logger.error(f"Customer instance not found: {customer_id}")
                return None
            
            # Create new EA instance
            ea_instance = await self._initialize_ea_instance(customer_instance)
            self.ea_instances[customer_id] = ea_instance
            
            return ea_instance
            
        except Exception as e:
            logger.error(f"Error getting EA instance for {customer_id}: {e}")
            return None
    
    async def handle_whatsapp_message(self, whatsapp_number: str, message: str, conversation_id: str = None) -> str:
        """
        Handle WhatsApp message with automatic customer provisioning and EA routing
        """
        try:
            customer_id = f"whatsapp_{whatsapp_number.replace('+', '').replace(' ', '')}"
            
            # Auto-provision customer if needed
            customer_instance = await self.get_customer_instance(customer_id)
            if not customer_instance:
                customer_instance = await self.provision_customer_from_whatsapp(whatsapp_number)
            
            # Check if customer is active and within limits
            if customer_instance.status != EAStatus.ACTIVE:
                return "Your Executive Assistant service is currently inactive. Please contact support for assistance."
            
            # Check trial expiration
            if (customer_instance.tier == CustomerTier.TRIAL and 
                customer_instance.trial_expires_at and 
                datetime.now() > customer_instance.trial_expires_at):
                return "Your trial period has expired. Please upgrade to continue using your Executive Assistant. Visit our website to upgrade your plan."
            
            # Check monthly message limits
            if not await self._check_usage_limits(customer_id):
                return "You've reached your monthly message limit. Please upgrade your plan for unlimited conversations with your Executive Assistant."
            
            # Get EA instance
            ea_instance = await self.get_ea_instance(customer_id)
            if not ea_instance:
                return "I'm experiencing technical difficulties. Please try again in a few moments."
            
            # Track interaction
            start_time = datetime.now()
            
            # Process message through EA
            response = await ea_instance.handle_customer_interaction(
                message=message,
                channel=ConversationChannel.WHATSAPP,
                conversation_id=conversation_id or f"wa_{whatsapp_number}_{uuid.uuid4().hex[:8]}"
            )
            
            end_time = datetime.now()
            response_time_ms = int((end_time - start_time).total_seconds() * 1000)
            
            # Update usage tracking
            await self._track_usage(customer_id, "message", response_time_ms)
            
            # Update last interaction
            customer_instance.last_interaction = datetime.now()
            await self._update_customer_instance(customer_instance)
            
            return response
            
        except Exception as e:
            logger.error(f"Error handling WhatsApp message from {whatsapp_number}: {e}")
            return "I apologize, but I'm experiencing technical difficulties. Please try again in a few moments."
    
    async def _allocate_redis_db(self) -> int:
        """Allocate available Redis database number for new customer"""
        for db_num in range(0, 15):  # Redis DBs 0-14 (15 reserved for registry)
            try:
                test_client = redis.Redis(host='localhost', port=6379, db=db_num, decode_responses=True)
                # Check if this DB is already allocated
                allocated = self.registry.get(f"redis_db:{db_num}")
                if not allocated:
                    # Reserve this DB
                    self.registry.set(f"redis_db:{db_num}", "allocated")
                    return db_num
            except:
                continue
        
        # If no DB available, use secure hash-based allocation
        fallback_hash = hashlib.sha256(datetime.now().isoformat().encode()).hexdigest()
        return (int(fallback_hash[:8], 16) % 14) + 1  # Use DBs 1-14, avoid DB 0
    
    async def _initialize_ea_instance(self, customer_instance: CustomerEAInstance) -> ExecutiveAssistant:
        """Initialize EA instance with customer-specific configuration"""
        try:
            # Create EA with customer isolation
            ea = ExecutiveAssistant(customer_instance.customer_id)
            
            # Configure EA personality and settings
            ea.name = customer_instance.ea_name
            ea.personality = customer_instance.personality
            
            logger.info(f"EA instance initialized for customer {customer_instance.customer_id}")
            return ea
            
        except Exception as e:
            logger.error(f"Error initializing EA instance: {e}")
            raise
    
    async def _store_customer_instance(self, instance: CustomerEAInstance):
        """Store customer instance in database"""
        try:
            if self.db_connection:
                with self.db_connection.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO customer_ea_instances 
                        (customer_id, whatsapp_number, phone_number, email, business_name, 
                         tier, status, ea_name, personality, monthly_message_limit, 
                         workflow_limit, memory_retention_days, redis_db, qdrant_collection, 
                         postgres_schema, created_at, trial_expires_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        instance.customer_id, instance.whatsapp_number, instance.phone_number,
                        instance.email, instance.business_name, instance.tier.value,
                        instance.status.value, instance.ea_name, instance.personality,
                        instance.monthly_message_limit, instance.workflow_limit,
                        instance.memory_retention_days, instance.redis_db,
                        instance.qdrant_collection, instance.postgres_schema,
                        instance.created_at, instance.trial_expires_at
                    ))
                    self.db_connection.commit()
                    
        except Exception as e:
            logger.error(f"Error storing customer instance: {e}")
            raise
    
    async def _update_customer_instance(self, instance: CustomerEAInstance):
        """Update customer instance in database and cache"""
        try:
            if self.db_connection:
                with self.db_connection.cursor() as cursor:
                    cursor.execute("""
                        UPDATE customer_ea_instances SET
                            status = %s, activated_at = %s, last_interaction = %s
                        WHERE customer_id = %s
                    """, (
                        instance.status.value, instance.activated_at, 
                        instance.last_interaction, instance.customer_id
                    ))
                    self.db_connection.commit()
            
            # Update cache
            self.registry.setex(
                f"customer:{instance.customer_id}",
                86400,
                json.dumps(asdict(instance), default=str)
            )
            
        except Exception as e:
            logger.error(f"Error updating customer instance: {e}")
    
    async def _check_usage_limits(self, customer_id: str) -> bool:
        """Check if customer is within usage limits"""
        try:
            customer_instance = await self.get_customer_instance(customer_id)
            if not customer_instance:
                return False
            
            # Get current month usage
            current_month = datetime.now().strftime("%Y-%m")
            
            if self.db_connection:
                with self.db_connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT messages_sent FROM customer_usage_tracking 
                        WHERE customer_id = %s AND month_year = %s
                    """, (customer_id, current_month))
                    
                    result = cursor.fetchone()
                    current_usage = result[0] if result else 0
                    
                    return current_usage < customer_instance.monthly_message_limit
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking usage limits: {e}")
            return True  # Allow by default on error
    
    async def _track_usage(self, customer_id: str, usage_type: str, response_time_ms: int = 0):
        """Track customer usage for billing and limits"""
        try:
            current_month = datetime.now().strftime("%Y-%m")
            
            if self.db_connection:
                with self.db_connection.cursor() as cursor:
                    # Update usage counters
                    if usage_type == "message":
                        cursor.execute("""
                            INSERT INTO customer_usage_tracking (customer_id, month_year, messages_sent)
                            VALUES (%s, %s, 1)
                            ON CONFLICT (customer_id, month_year)
                            DO UPDATE SET 
                                messages_sent = customer_usage_tracking.messages_sent + 1,
                                last_updated = CURRENT_TIMESTAMP
                        """, (customer_id, current_month))
                    
                    # Log interaction
                    cursor.execute("""
                        INSERT INTO customer_interaction_log 
                        (customer_id, channel, message_type, response_time_ms)
                        VALUES (%s, %s, %s, %s)
                    """, (customer_id, "whatsapp", usage_type, response_time_ms))
                    
                    self.db_connection.commit()
                    
        except Exception as e:
            logger.error(f"Error tracking usage: {e}")

# Global customer manager instance
customer_manager = CustomerEAManager()

# Convenience function for webhook integration
async def handle_whatsapp_customer_message(whatsapp_number: str, message: str, conversation_id: str = None) -> str:
    """
    Convenience function for webhook integration
    Handles complete customer provisioning and message routing
    """
    return await customer_manager.handle_whatsapp_message(whatsapp_number, message, conversation_id)

# Testing function
async def test_customer_provisioning():
    """Test customer provisioning system"""
    print("🚀 === Testing Customer EA Manager ===")
    
    test_number = "+19496212077"
    test_messages = [
        "Hi! I just got your service and I'm excited to try it out.",
        "I run a marketing agency and I need help with automation.",
        "Can you create a workflow for my social media posting?",
        "What can you help me with day-to-day?",
        "How do I upgrade my plan?"
    ]
    
    for i, message in enumerate(test_messages, 1):
        print(f"\n📱 Test Message {i}: {message}")
        response = await handle_whatsapp_customer_message(test_number, message)
        print(f"🤖 EA Response: {response[:200]}...")
        
        # Simulate conversation delay
        await asyncio.sleep(1)
    
    print("\n✅ Customer provisioning test completed!")

if __name__ == "__main__":
    asyncio.run(test_customer_provisioning())