"""
WhatsApp Webhook Server
FastAPI server to handle Twilio WhatsApp Business webhooks
"""

import asyncio
import json
import logging
import os
from typing import Dict, Any, Optional
from urllib.parse import parse_qs

import uvicorn
from fastapi import FastAPI, Request, HTTPException, Depends, BackgroundTasks
from fastapi.security import HTTPBearer
from fastapi.responses import PlainTextResponse

from .whatsapp_channel import WhatsAppChannel
from ..agents.executive_assistant import ExecutiveAssistant

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="WhatsApp Business Webhook Server",
    description="Handles Twilio WhatsApp Business API webhooks for AI Agency Platform",
    version="1.0.0"
)

# Security
security = HTTPBearer()

# Customer routing - maps phone numbers to customer IDs
CUSTOMER_ROUTING: Dict[str, str] = {}

# WhatsApp channels cache
whatsapp_channels: Dict[str, WhatsAppChannel] = {}

class WhatsAppWebhookServer:
    """WhatsApp webhook server for handling Twilio webhooks"""
    
    def __init__(self):
        self.active_channels: Dict[str, WhatsAppChannel] = {}
        self.default_config = {
            'twilio_account_sid': os.getenv('TWILIO_ACCOUNT_SID'),
            'twilio_auth_token': os.getenv('TWILIO_AUTH_TOKEN'),
            'whatsapp_number': os.getenv('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886'),
            'webhook_auth_token': os.getenv('TWILIO_WEBHOOK_AUTH_TOKEN')
        }
    
    async def get_or_create_channel(self, customer_id: str) -> WhatsAppChannel:
        """Get existing channel or create new one for customer"""
        if customer_id not in self.active_channels:
            channel = WhatsAppChannel(customer_id, self.default_config)
            await channel.initialize()
            self.active_channels[customer_id] = channel
        
        return self.active_channels[customer_id]
    
    def route_phone_to_customer(self, phone_number: str) -> str:
        """Route phone number to customer ID"""
        # Remove whatsapp: prefix and clean phone number
        clean_number = phone_number.replace('whatsapp:', '').replace('+', '').replace(' ', '')
        
        # Check customer routing table
        if clean_number in CUSTOMER_ROUTING:
            return CUSTOMER_ROUTING[clean_number]
        
        # For demo purposes, create customer ID from phone number
        # In production, this would lookup in customer database
        customer_id = f"customer-{clean_number[-4:]}"
        CUSTOMER_ROUTING[clean_number] = customer_id
        
        logger.info(f"Routed phone {phone_number} to customer {customer_id}")
        return customer_id
    
    async def process_webhook_async(self, webhook_data: Dict[str, Any]):
        """Process webhook in background"""
        try:
            from_number = webhook_data.get('From', '')
            customer_id = self.route_phone_to_customer(from_number)
            
            # Get or create WhatsApp channel for this customer
            channel = await self.get_or_create_channel(customer_id)
            
            # Process the webhook
            response = await channel.handle_webhook(webhook_data)
            
            logger.info(f"Processed webhook for customer {customer_id}: {response[:100]}...")
            
        except Exception as e:
            logger.error(f"Error processing webhook asynchronously: {e}")

# Initialize server
webhook_server = WhatsAppWebhookServer()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "whatsapp-webhook-server",
        "active_channels": len(webhook_server.active_channels),
        "environment": os.getenv("ENVIRONMENT", "development")
    }

@app.post("/webhook/whatsapp")
async def handle_whatsapp_webhook(
    request: Request, 
    background_tasks: BackgroundTasks
):
    """
    Handle incoming WhatsApp webhooks from Twilio
    
    This endpoint receives webhooks from Twilio WhatsApp Business API
    and routes them to the appropriate customer's Executive Assistant
    """
    try:
        # Get request body
        body = await request.body()
        
        # Parse form data (Twilio sends form-encoded data)
        content_type = request.headers.get('content-type', '')
        if 'application/x-www-form-urlencoded' in content_type:
            # Parse form data
            form_data = parse_qs(body.decode('utf-8'))
            webhook_data = {k: v[0] if v else '' for k, v in form_data.items()}
        else:
            # Try to parse as JSON
            try:
                webhook_data = json.loads(body.decode('utf-8'))
            except:
                webhook_data = {}
        
        # Validate webhook signature (optional but recommended)
        signature = request.headers.get('x-twilio-signature', '')
        if signature:
            # For production, validate signature
            # webhook_server.validate_signature(body.decode('utf-8'), signature)
            pass
        
        # Log incoming webhook for debugging
        logger.info(f"Received WhatsApp webhook: {webhook_data.get('From', 'unknown')} -> {webhook_data.get('Body', 'no body')[:100]}")
        
        # Route to customer based on phone number
        from_number = webhook_data.get('From', '')
        if not from_number:
            raise HTTPException(status_code=400, detail="Missing 'From' field in webhook")
        
        customer_id = webhook_server.route_phone_to_customer(from_number)
        
        # Get or create WhatsApp channel for this customer
        channel = await webhook_server.get_or_create_channel(customer_id)
        
        # Process webhook synchronously for immediate response
        try:
            response = await channel.handle_webhook(webhook_data)
            
            # Also process asynchronously for any additional background work
            background_tasks.add_task(webhook_server.process_webhook_async, webhook_data)
            
            logger.info(f"WhatsApp webhook processed for customer {customer_id}")
            
            return PlainTextResponse(
                content="Webhook processed successfully",
                status_code=200
            )
            
        except Exception as e:
            logger.error(f"Error processing webhook for customer {customer_id}: {e}")
            
            # Send error response to user
            try:
                await channel.send_message(
                    from_number.replace('whatsapp:', ''),
                    "I apologize, but I encountered an issue processing your message. Let me get back to you in just a moment."
                )
            except:
                pass  # Fail silently
            
            return PlainTextResponse(
                content="Webhook processed with errors",
                status_code=200  # Still return 200 to Twilio
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in webhook handler: {e}")
        return PlainTextResponse(
            content="Internal server error",
            status_code=500
        )

@app.post("/webhook/whatsapp/status")
async def handle_message_status(request: Request):
    """Handle message status updates from Twilio"""
    try:
        body = await request.body()
        
        # Parse form data
        content_type = request.headers.get('content-type', '')
        if 'application/x-www-form-urlencoded' in content_type:
            form_data = parse_qs(body.decode('utf-8'))
            status_data = {k: v[0] if v else '' for k, v in form_data.items()}
        else:
            status_data = json.loads(body.decode('utf-8'))
        
        # Log status update
        message_sid = status_data.get('MessageSid', 'unknown')
        message_status = status_data.get('MessageStatus', 'unknown')
        to_number = status_data.get('To', '')
        
        logger.info(f"Message status update: {message_sid} -> {message_status} for {to_number}")
        
        # Update message status in database if needed
        # This could be implemented to track delivery status
        
        return PlainTextResponse("Status updated", status_code=200)
        
    except Exception as e:
        logger.error(f"Error handling status update: {e}")
        return PlainTextResponse("Error processing status", status_code=200)

@app.get("/customers/{customer_id}/whatsapp/health")
async def customer_whatsapp_health(customer_id: str):
    """Get WhatsApp channel health for specific customer"""
    try:
        if customer_id in webhook_server.active_channels:
            channel = webhook_server.active_channels[customer_id]
            health = await channel.health_check()
            return health
        else:
            return {
                "customer_id": customer_id,
                "status": "not_initialized",
                "message": "WhatsApp channel not active for this customer"
            }
    except Exception as e:
        logger.error(f"Error getting customer WhatsApp health: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/customers/{customer_id}/whatsapp/conversations")
async def get_customer_conversations(
    customer_id: str, 
    phone_number: str = None,
    limit: int = 50
):
    """Get conversation history for customer"""
    try:
        if customer_id not in webhook_server.active_channels:
            channel = await webhook_server.get_or_create_channel(customer_id)
        else:
            channel = webhook_server.active_channels[customer_id]
        
        if phone_number:
            history = await channel.get_conversation_history(phone_number, limit)
            return {"conversations": history}
        else:
            return {"message": "phone_number parameter required"}
    
    except Exception as e:
        logger.error(f"Error getting conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/customers/{customer_id}/whatsapp/send")
async def send_whatsapp_message(
    customer_id: str,
    request: Request
):
    """Send WhatsApp message via API"""
    try:
        data = await request.json()
        to_number = data.get('to')
        content = data.get('message')
        
        if not to_number or not content:
            raise HTTPException(status_code=400, detail="Both 'to' and 'message' are required")
        
        # Get or create channel
        channel = await webhook_server.get_or_create_channel(customer_id)
        
        # Send message
        message_id = await channel.send_message(to_number, content, **data)
        
        return {
            "message_id": message_id,
            "status": "sent",
            "to": to_number,
            "customer_id": customer_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/customer-routing")
async def update_customer_routing(request: Request):
    """Update customer routing table"""
    try:
        data = await request.json()
        phone_number = data.get('phone_number', '').replace('whatsapp:', '').replace('+', '')
        customer_id = data.get('customer_id')
        
        if not phone_number or not customer_id:
            raise HTTPException(status_code=400, detail="phone_number and customer_id required")
        
        CUSTOMER_ROUTING[phone_number] = customer_id
        
        return {
            "message": "Customer routing updated",
            "phone_number": phone_number,
            "customer_id": customer_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating customer routing: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/customer-routing")
async def get_customer_routing():
    """Get current customer routing table"""
    return {"routing": CUSTOMER_ROUTING}

# Development server configuration
if __name__ == "__main__":
    port = int(os.getenv("WEBHOOK_PORT", 8000))
    host = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    
    logger.info(f"Starting WhatsApp webhook server on {host}:{port}")
    logger.info("Configured for Twilio WhatsApp Business API")
    logger.info(f"Twilio Account SID: {webhook_server.default_config.get('twilio_account_sid', 'Not configured')[:10]}...")
    
    uvicorn.run(
        "webhook_server:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )