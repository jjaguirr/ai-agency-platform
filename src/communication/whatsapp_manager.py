"""
WhatsApp Business Integration Manager
Manages WhatsApp Business configurations and customer assignments
"""

import asyncio
import json
import logging
import os
from typing import Dict, Any, Optional, List
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor
import redis

from .whatsapp_channel import WhatsAppChannel

logger = logging.getLogger(__name__)

class WhatsAppBusinessManager:
    """
    Manages WhatsApp Business integration for multiple customers
    
    Features:
    - Customer-specific WhatsApp number assignment
    - Twilio account management
    - Webhook configuration
    - Message routing and analytics
    - Customer onboarding automation
    """
    
    def __init__(self):
        self.db_connection = None
        self.redis_client = None
        self._initialize_connections()
        self.active_channels: Dict[str, WhatsAppChannel] = {}
    
    def _initialize_connections(self):
        """Initialize database and Redis connections"""
        try:
            # Database connection
            self.db_connection = psycopg2.connect(
                host="localhost",
                database="mcphub", 
                user="mcphub",
                password="mcphub_password"
            )
            
            # Redis connection
            self.redis_client = redis.Redis(
                host='localhost',
                port=6379,
                db=0,  # Use DB 0 for manager
                decode_responses=True
            )
            
            logger.info("WhatsApp Business Manager initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize connections: {e}")
    
    async def setup_customer_whatsapp(self, customer_id: str, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Set up WhatsApp Business for a new customer
        
        Args:
            customer_id: Unique customer identifier
            config: Optional WhatsApp configuration override
            
        Returns:
            Setup result with WhatsApp number and configuration
        """
        try:
            # Create customer WhatsApp configuration
            whatsapp_config = {
                'twilio_account_sid': config.get('twilio_account_sid') or os.getenv('TWILIO_ACCOUNT_SID'),
                'twilio_auth_token': config.get('twilio_auth_token') or os.getenv('TWILIO_AUTH_TOKEN'),
                'whatsapp_number': config.get('whatsapp_number') or os.getenv('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886'),
                'webhook_auth_token': config.get('webhook_auth_token') or os.getenv('TWILIO_WEBHOOK_AUTH_TOKEN')
            }
            
            # Create and initialize WhatsApp channel
            channel = WhatsAppChannel(customer_id, whatsapp_config)
            await channel.initialize()
            
            # Store in active channels
            self.active_channels[customer_id] = channel
            
            # Store customer configuration in database
            await self._store_customer_whatsapp_config(customer_id, whatsapp_config)
            
            # Create webhook configuration
            webhook_url = await self._generate_webhook_url(customer_id)
            
            setup_result = {
                "customer_id": customer_id,
                "whatsapp_number": whatsapp_config['whatsapp_number'],
                "webhook_url": webhook_url,
                "status": "configured",
                "created_at": datetime.now().isoformat(),
                "channel_health": await channel.health_check()
            }
            
            logger.info(f"WhatsApp Business configured for customer {customer_id}")
            return setup_result
            
        except Exception as e:
            logger.error(f"Failed to setup WhatsApp for customer {customer_id}: {e}")
            return {
                "customer_id": customer_id,
                "status": "failed",
                "error": str(e)
            }
    
    async def get_customer_whatsapp_channel(self, customer_id: str) -> Optional[WhatsAppChannel]:
        """Get WhatsApp channel for customer"""
        if customer_id in self.active_channels:
            return self.active_channels[customer_id]
        
        # Try to load from database and initialize
        config = await self._load_customer_whatsapp_config(customer_id)
        if config:
            channel = WhatsAppChannel(customer_id, config)
            await channel.initialize()
            self.active_channels[customer_id] = channel
            return channel
        
        return None
    
    async def provision_customer_whatsapp_instantly(self, customer_id: str, phone_number: str) -> Dict[str, Any]:
        """
        Instantly provision WhatsApp for new customer (30-second target)
        
        This method handles the rapid provisioning requirement from the Phase 1 PRD
        """
        start_time = datetime.now()
        
        try:
            # Step 1: Setup WhatsApp channel (5 seconds)
            setup_result = await self.setup_customer_whatsapp(customer_id)
            
            # Step 2: Configure phone number routing (2 seconds)
            await self._configure_phone_routing(customer_id, phone_number)
            
            # Step 3: Initialize Executive Assistant (5 seconds)
            channel = self.active_channels.get(customer_id)
            if channel and channel.ea:
                # Prepare welcome message
                welcome_call = await channel.ea.initialize_welcome_call(phone_number)
            else:
                welcome_call = {"error": "EA not initialized"}
            
            # Step 4: Send initial WhatsApp message (3 seconds)
            if channel:
                welcome_message = """🎉 Welcome to AI Agency Platform!

I'm Sarah, your dedicated Executive Assistant. I'm ready to learn about your business and start automating your daily operations.

You can now:
📱 Message me anytime on WhatsApp
🤖 Tell me about your business processes
⚡ Get instant workflow automations
🧠 I remember everything we discuss

Let's start! Tell me about your business and what you do day-to-day. I'll create your first automation during our conversation."""
                
                try:
                    await channel.send_message(phone_number, welcome_message)
                    sent_welcome = True
                except:
                    sent_welcome = False
            else:
                sent_welcome = False
            
            # Calculate provisioning time
            end_time = datetime.now()
            provisioning_time = (end_time - start_time).total_seconds()
            
            result = {
                "customer_id": customer_id,
                "phone_number": phone_number,
                "whatsapp_number": setup_result.get('whatsapp_number'),
                "webhook_url": setup_result.get('webhook_url'),
                "provisioning_time_seconds": provisioning_time,
                "status": "provisioned" if provisioning_time < 30 else "provisioned_slow",
                "welcome_message_sent": sent_welcome,
                "ea_initialized": welcome_call.get("call_scheduled", False),
                "timestamp": datetime.now().isoformat()
            }
            
            # Log provisioning metrics
            logger.info(f"Customer {customer_id} WhatsApp provisioned in {provisioning_time:.2f}s")
            
            # Store provisioning metrics
            await self._store_provisioning_metrics(customer_id, result)
            
            return result
            
        except Exception as e:
            error_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Failed to provision WhatsApp for {customer_id} in {error_time:.2f}s: {e}")
            
            return {
                "customer_id": customer_id,
                "phone_number": phone_number,
                "status": "failed",
                "error": str(e),
                "provisioning_time_seconds": error_time,
                "timestamp": datetime.now().isoformat()
            }
    
    async def _configure_phone_routing(self, customer_id: str, phone_number: str):
        """Configure phone number routing for customer"""
        try:
            clean_number = phone_number.replace('+', '').replace(' ', '').replace('-', '')
            
            # Store in database
            if self.db_connection:
                with self.db_connection.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO customer_phone_routing 
                        (customer_id, phone_number, created_at)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (phone_number) 
                        DO UPDATE SET customer_id = EXCLUDED.customer_id
                    """, (customer_id, clean_number, datetime.now()))
                    self.db_connection.commit()
            
            # Store in Redis for fast lookup
            if self.redis_client:
                self.redis_client.setex(
                    f"phone_routing:{clean_number}", 
                    86400 * 30,  # 30 days TTL
                    customer_id
                )
            
            logger.info(f"Phone routing configured: {phone_number} -> {customer_id}")
            
        except Exception as e:
            logger.error(f"Failed to configure phone routing: {e}")
    
    async def route_phone_to_customer(self, phone_number: str) -> Optional[str]:
        """Route phone number to customer ID"""
        try:
            clean_number = phone_number.replace('whatsapp:', '').replace('+', '').replace(' ', '').replace('-', '')
            
            # Check Redis first (fast lookup)
            if self.redis_client:
                customer_id = self.redis_client.get(f"phone_routing:{clean_number}")
                if customer_id:
                    return customer_id
            
            # Check database
            if self.db_connection:
                with self.db_connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT customer_id FROM customer_phone_routing WHERE phone_number = %s",
                        (clean_number,)
                    )
                    result = cursor.fetchone()
                    if result:
                        customer_id = result[0]
                        
                        # Cache in Redis
                        if self.redis_client:
                            self.redis_client.setex(
                                f"phone_routing:{clean_number}",
                                86400 * 30,  # 30 days TTL
                                customer_id
                            )
                        
                        return customer_id
            
            # No routing found
            return None
            
        except Exception as e:
            logger.error(f"Error routing phone number: {e}")
            return None
    
    async def _store_customer_whatsapp_config(self, customer_id: str, config: Dict[str, Any]):
        """Store customer WhatsApp configuration"""
        if not self.db_connection:
            return
            
        try:
            with self.db_connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO customer_whatsapp_config 
                    (customer_id, whatsapp_config, created_at, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (customer_id) 
                    DO UPDATE SET 
                        whatsapp_config = EXCLUDED.whatsapp_config,
                        updated_at = EXCLUDED.updated_at
                """, (
                    customer_id,
                    json.dumps(config),
                    datetime.now(),
                    datetime.now()
                ))
                self.db_connection.commit()
                
        except Exception as e:
            logger.error(f"Failed to store WhatsApp config: {e}")
    
    async def _load_customer_whatsapp_config(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """Load customer WhatsApp configuration"""
        if not self.db_connection:
            return None
            
        try:
            with self.db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT whatsapp_config FROM customer_whatsapp_config WHERE customer_id = %s",
                    (customer_id,)
                )
                result = cursor.fetchone()
                
                if result:
                    return json.loads(result['whatsapp_config'])
                    
        except Exception as e:
            logger.error(f"Failed to load WhatsApp config: {e}")
        
        return None
    
    async def _generate_webhook_url(self, customer_id: str) -> str:
        """Generate webhook URL for customer"""
        # In production, this would be the actual webhook endpoint
        base_url = os.getenv('WEBHOOK_BASE_URL', 'https://your-domain.com')
        return f"{base_url}/webhook/whatsapp"
    
    async def _store_provisioning_metrics(self, customer_id: str, metrics: Dict[str, Any]):
        """Store provisioning metrics for analytics"""
        if not self.db_connection:
            return
            
        try:
            with self.db_connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO customer_provisioning_metrics 
                    (customer_id, provisioning_type, metrics, created_at)
                    VALUES (%s, %s, %s, %s)
                """, (
                    customer_id,
                    'whatsapp',
                    json.dumps(metrics),
                    datetime.now()
                ))
                self.db_connection.commit()
                
        except Exception as e:
            logger.error(f"Failed to store provisioning metrics: {e}")
    
    async def get_customer_analytics(self, customer_id: str, days: int = 30) -> Dict[str, Any]:
        """Get WhatsApp analytics for customer"""
        try:
            if not self.db_connection:
                return {"error": "Database not available"}
            
            with self.db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
                # Get message counts
                cursor.execute("""
                    SELECT 
                        direction,
                        COUNT(*) as message_count,
                        DATE(created_at) as date
                    FROM whatsapp_messages 
                    WHERE customer_id = %s 
                    AND created_at >= NOW() - INTERVAL '%s days'
                    GROUP BY direction, DATE(created_at)
                    ORDER BY date DESC
                """, (customer_id, days))
                
                message_stats = cursor.fetchall()
                
                # Get conversation count
                cursor.execute("""
                    SELECT COUNT(DISTINCT conversation_id) as conversation_count
                    FROM whatsapp_messages 
                    WHERE customer_id = %s 
                    AND created_at >= NOW() - INTERVAL '%s days'
                """, (customer_id, days))
                
                conversation_count = cursor.fetchone()['conversation_count']
                
                return {
                    "customer_id": customer_id,
                    "days": days,
                    "total_conversations": conversation_count,
                    "message_stats": [dict(stat) for stat in message_stats],
                    "generated_at": datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error getting analytics: {e}")
            return {"error": str(e)}
    
    async def create_database_tables(self):
        """Create necessary database tables"""
        if not self.db_connection:
            return
            
        try:
            with self.db_connection.cursor() as cursor:
                # Customer WhatsApp configuration table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS customer_whatsapp_config (
                        id SERIAL PRIMARY KEY,
                        customer_id VARCHAR(255) UNIQUE NOT NULL,
                        whatsapp_config JSONB NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Phone number routing table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS customer_phone_routing (
                        id SERIAL PRIMARY KEY,
                        customer_id VARCHAR(255) NOT NULL,
                        phone_number VARCHAR(50) UNIQUE NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Provisioning metrics table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS customer_provisioning_metrics (
                        id SERIAL PRIMARY KEY,
                        customer_id VARCHAR(255) NOT NULL,
                        provisioning_type VARCHAR(50) NOT NULL,
                        metrics JSONB NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                self.db_connection.commit()
                logger.info("Database tables created successfully")
                
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
    
    async def health_check(self) -> Dict[str, Any]:
        """System health check"""
        health = {
            "service": "whatsapp_business_manager",
            "timestamp": datetime.now().isoformat(),
            "active_channels": len(self.active_channels),
            "database_status": "disconnected",
            "redis_status": "disconnected"
        }
        
        # Check database
        if self.db_connection:
            try:
                with self.db_connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    health["database_status"] = "connected"
            except:
                health["database_status"] = "error"
        
        # Check Redis
        if self.redis_client:
            try:
                self.redis_client.ping()
                health["redis_status"] = "connected"
            except:
                health["redis_status"] = "error"
        
        return health

# Global manager instance
whatsapp_manager = WhatsAppBusinessManager()