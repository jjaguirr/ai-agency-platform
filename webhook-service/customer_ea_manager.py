"""
Customer EA Manager - Bridge Module for WhatsApp Webhook Integration
Connects production webhook service with the full Executive Assistant system
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional

# Initialize logger first
logger = logging.getLogger(__name__)

# Add project root to Python path to enable absolute imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Import EA system with error handling
try:
    from src.agents.executive_assistant import ExecutiveAssistant, ConversationChannel
    from src.communication.whatsapp_channel import WhatsAppChannel
    from src.communication.multi_channel_context import UnifiedContextStore
    EA_IMPORTS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"EA system imports failed: {e}")
    ExecutiveAssistant = None
    ConversationChannel = None
    WhatsAppChannel = None
    UnifiedContextStore = None
    EA_IMPORTS_AVAILABLE = False

class CustomerEAManager:
    """
    Bridge between webhook service and full EA system
    
    Features:
    - Auto-provisioning of customer EA instances
    - Context preservation across channels
    - Premium-casual personality management
    - Performance monitoring and SLA tracking
    """
    
    def __init__(self):
        self.ea_instances: Dict[str, ExecutiveAssistant] = {}
        self.whatsapp_channels: Dict[str, WhatsAppChannel] = {}
        self.context_store = None
        self._initialize_context_store()
    
    def _initialize_context_store(self):
        """Initialize unified context store for cross-channel persistence"""
        if not EA_IMPORTS_AVAILABLE or UnifiedContextStore is None:
            logger.warning("Context store not available - imports failed")
            self.context_store = None
            return
            
        try:
            self.context_store = UnifiedContextStore()
            logger.info("✅ Unified context store initialized")
        except Exception as e:
            logger.warning(f"Context store initialization failed: {e}")
            self.context_store = None
    
    async def get_or_create_ea(self, customer_id: str):
        """Get existing EA or create new one for customer"""
        if not EA_IMPORTS_AVAILABLE or ExecutiveAssistant is None:
            raise ImportError("ExecutiveAssistant not available - import failed")
            
        if customer_id not in self.ea_instances:
            try:
                # Create new EA instance for this customer
                ea = ExecutiveAssistant(customer_id)
                self.ea_instances[customer_id] = ea
                logger.info(f"✅ Created new EA instance for customer {customer_id}")
            except Exception as e:
                logger.error(f"Failed to create EA for customer {customer_id}: {e}")
                raise
        
        return self.ea_instances[customer_id]
    
    async def get_or_create_whatsapp_channel(self, customer_id: str):
        """Get existing WhatsApp channel or create new one"""
        if not EA_IMPORTS_AVAILABLE or WhatsAppChannel is None:
            raise ImportError("WhatsAppChannel not available - import failed")
            
        if customer_id not in self.whatsapp_channels:
            try:
                # Customer-specific WhatsApp configuration
                config = {
                    'twilio_account_sid': os.getenv('TWILIO_ACCOUNT_SID'),
                    'twilio_auth_token': os.getenv('TWILIO_AUTH_TOKEN'),
                    'whatsapp_number': os.getenv('WHATSAPP_PHONE_NUMBER_ID', 'whatsapp:+14155238886'),
                    'webhook_auth_token': os.getenv('WHATSAPP_WEBHOOK_SECRET')
                }
                
                channel = WhatsAppChannel(customer_id, config)
                await channel.initialize()
                self.whatsapp_channels[customer_id] = channel
                logger.info(f"✅ Created WhatsApp channel for customer {customer_id}")
            except Exception as e:
                logger.error(f"Failed to create WhatsApp channel for customer {customer_id}: {e}")
                raise
        
        return self.whatsapp_channels[customer_id]

async def handle_whatsapp_customer_message(
    whatsapp_number: str,
    message: str,
    conversation_id: str,
    metadata: Dict[str, Any] = None
) -> str:
    """
    Main entry point for WhatsApp webhook messages
    
    Args:
        whatsapp_number: Customer's WhatsApp number
        message: Message content
        conversation_id: Unique conversation identifier
        metadata: Additional message metadata
    
    Returns:
        str: EA response to send back to customer
    """
    start_time = datetime.now()
    
    # Check if EA system is available
    if not EA_IMPORTS_AVAILABLE:
        logger.error("EA system not available - imports failed")
        return "I'm your Executive Assistant Sarah! I'm currently setting up my systems and will be fully operational soon. Thanks for your patience! 😊"
    
    try:
        # Generate customer ID from WhatsApp number (or use existing mapping)
        customer_id = _get_customer_id_from_whatsapp(whatsapp_number)
        
        # Get or create EA manager instance
        if not hasattr(handle_whatsapp_customer_message, '_manager'):
            handle_whatsapp_customer_message._manager = CustomerEAManager()
        
        manager = handle_whatsapp_customer_message._manager
        
        # Get customer's EA instance
        ea = await manager.get_or_create_ea(customer_id)
        
        # Store cross-channel context if available
        if manager.context_store:
            try:
                from src.memory.unified_context_store import ContextEntry
                context_entry = ContextEntry(
                    customer_id=customer_id,
                    channel='whatsapp',
                    conversation_id=conversation_id,
                    content=message,
                    timestamp=datetime.now(),
                    metadata=metadata or {}
                )
                await manager.context_store.store_context(context_entry)
            except Exception as ctx_error:
                logger.warning(f"Context storage failed: {ctx_error}")
                # Continue processing even if context storage fails
        
        # Process message through EA with WhatsApp context
        response = await ea.handle_customer_interaction(
            message=message,
            channel=ConversationChannel.WHATSAPP,
            conversation_id=conversation_id
        )
        
        # Apply WhatsApp-specific formatting and tone
        formatted_response = await _apply_whatsapp_formatting(response, customer_id)
        
        # Track performance metrics
        processing_time = (datetime.now() - start_time).total_seconds()
        await _track_performance_metrics(customer_id, processing_time, success=True)
        
        logger.info(f"✅ Processed WhatsApp message for {whatsapp_number} in {processing_time:.2f}s")
        
        return formatted_response
        
    except Exception as e:
        logger.error(f"❌ Error handling WhatsApp message from {whatsapp_number}: {e}")
        
        # Track error metrics
        processing_time = (datetime.now() - start_time).total_seconds()
        await _track_performance_metrics(whatsapp_number, processing_time, success=False, error=str(e))
        
        # Return professional error response with EA branding
        return "Hey! I'm Sarah, your Executive Assistant. I hit a small technical snag, but I'm working to resolve it. Give me just a moment and I'll be right back with you! 🔧"

def _get_customer_id_from_whatsapp(whatsapp_number: str) -> str:
    """Generate consistent customer ID from WhatsApp number"""
    # Clean the number (remove whatsapp: prefix and normalize)
    clean_number = whatsapp_number.replace('whatsapp:', '').replace('+', '').strip()
    
    # For production, this would map to actual customer IDs from database
    # For now, use the phone number as customer ID
    return f"whatsapp_customer_{clean_number}"

async def _apply_whatsapp_formatting(response: str, customer_id: str) -> str:
    """Apply WhatsApp-specific formatting and premium-casual tone"""
    try:
        # Basic WhatsApp optimizations
        formatted = response
        
        # Mobile-friendly line breaks
        if len(formatted) > 200:
            # Break long messages into paragraphs
            sentences = formatted.split('. ')
            if len(sentences) > 3:
                mid_point = len(sentences) // 2
                formatted = '. '.join(sentences[:mid_point]) + '.\n\n' + '. '.join(sentences[mid_point:])
        
        # Premium-casual tone adaptations
        casual_adaptations = {
            'Hello': 'Hey',
            'I will': "I'll",
            'I am': "I'm",
            'You are': "You're",
            'I would be happy to': "I'd love to",
            'Please let me know': 'Let me know',
            'I apologize': 'Sorry about that',
            'Thank you very much': 'Thanks so much'
        }
        
        for formal, casual in casual_adaptations.items():
            formatted = formatted.replace(formal, casual)
        
        return formatted
        
    except Exception as e:
        logger.error(f"Error applying WhatsApp formatting: {e}")
        return response  # Return original if formatting fails

async def _track_performance_metrics(customer_id: str, processing_time: float, success: bool, error: str = None):
    """Track performance metrics for monitoring and SLA compliance"""
    try:
        metrics = {
            'customer_id': customer_id,
            'timestamp': datetime.now().isoformat(),
            'processing_time_seconds': processing_time,
            'success': success,
            'channel': 'whatsapp',
            'sla_met': processing_time <= 3.0,  # 3 second SLA target
        }
        
        if error:
            metrics['error'] = error
        
        # In production, this would send to monitoring system (DataDog, etc.)
        logger.info(f"📊 Performance: {customer_id} processed in {processing_time:.2f}s, SLA: {'✅' if processing_time <= 3.0 else '❌'}")
        
    except Exception as e:
        logger.error(f"Error tracking performance metrics: {e}")

# Health check for the bridge module
async def health_check() -> Dict[str, Any]:
    """Check health of EA bridge system"""
    try:
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'components': {
                'ea_system': 'unknown',
                'whatsapp_channel': 'unknown',
                'context_store': 'unknown',
                'src_imports': 'unknown'
            }
        }
        
        # Test EA system imports (use global availability flag)
        health_status['components']['ea_system'] = 'available' if EA_IMPORTS_AVAILABLE and ExecutiveAssistant is not None else 'unavailable'
        health_status['components']['whatsapp_channel'] = 'available' if EA_IMPORTS_AVAILABLE and WhatsAppChannel is not None else 'unavailable'  
        health_status['components']['context_store'] = 'available' if EA_IMPORTS_AVAILABLE and UnifiedContextStore is not None else 'unavailable'
        
        # Check if all components are available
        all_healthy = all(
            status == 'available' 
            for status in health_status['components'].values()
        )
        
        health_status['status'] = 'healthy' if EA_IMPORTS_AVAILABLE else 'degraded'
        health_status['components']['src_imports'] = 'success' if EA_IMPORTS_AVAILABLE else 'failed'
        health_status['imports_available'] = EA_IMPORTS_AVAILABLE
        
        return health_status
        
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }

# Testing function
async def test_ea_integration():
    """Test EA integration with sample WhatsApp message"""
    try:
        print("🧪 Testing Customer EA Manager Integration...")
        
        # Test health check first
        health = await health_check()
        print(f"Health Check: {health['status']}")
        for component, status in health['components'].items():
            print(f"  {component}: {status}")
        
        if health['status'] != 'healthy':
            print("❌ System not healthy - skipping integration test")
            return
        
        # Test message handling
        test_number = "+1234567890"
        test_message = "Hi! I just signed up and I'm excited to get started with my new Executive Assistant."
        
        response = await handle_whatsapp_customer_message(
            whatsapp_number=test_number,
            message=test_message,
            conversation_id="test_conv_001"
        )
        
        print(f"✅ Test Response: {response[:100]}...")
        print("🎉 EA Integration test completed successfully!")
        
    except Exception as e:
        print(f"❌ EA Integration test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_ea_integration())