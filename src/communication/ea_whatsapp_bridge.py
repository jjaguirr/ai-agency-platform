#!/usr/bin/env python3
"""
EA WhatsApp Bridge - MCP Client for EA Deployments
Connects client EA agents to centralized WhatsApp webhook service
"""

import asyncio
import aiohttp
import json
import logging
import os
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
import uuid
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

@dataclass
class WhatsAppBridgeConfig:
    """Configuration for WhatsApp bridge"""
    webhook_service_url: str
    client_id: str
    customer_id: str
    phone_number: str
    auth_token: str
    mcp_port: int = 8001
    heartbeat_interval: int = 300  # 5 minutes
    retry_attempts: int = 3
    retry_delay: int = 5

class EAWhatsAppBridge:
    """Bridge between EA agent and centralized WhatsApp service"""

    def __init__(self, config: WhatsAppBridgeConfig, ea_handler: Callable):
        self.config = config
        self.ea_handler = ea_handler  # Function to handle messages with EA
        self.is_registered = False
        self.last_heartbeat = None
        self.session = None

    async def start(self):
        """Start the WhatsApp bridge"""
        try:
            logger.info(f"🌉 Starting WhatsApp bridge for {self.config.customer_id}")

            # Initialize HTTP session
            self.session = aiohttp.ClientSession()

            # Register with webhook service
            if await self.register_with_webhook_service():
                logger.info("✅ Successfully registered with webhook service")

                # Start MCP server for webhook service to communicate with us
                await asyncio.gather(
                    self.run_mcp_server(),
                    self.heartbeat_loop(),
                    return_exceptions=True
                )
            else:
                logger.error("❌ Failed to register with webhook service")

        except Exception as e:
            logger.error(f"Error starting WhatsApp bridge: {e}")
        finally:
            if self.session:
                await self.session.close()

    async def register_with_webhook_service(self) -> bool:
        """Register this EA client with the webhook service"""
        try:
            registration_data = {
                "client_id": self.config.client_id,
                "customer_id": self.config.customer_id,
                "phone_number": self.config.phone_number,
                "mcp_endpoint": f"http://localhost:{self.config.mcp_port}/mcp",
                "auth_token": self.config.auth_token
            }

            url = f"{self.config.webhook_service_url}/ea/register"

            for attempt in range(self.config.retry_attempts):
                try:
                    async with self.session.post(
                        url,
                        json=registration_data,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:

                        if response.status == 201:
                            result = await response.json()
                            logger.info(f"✅ Registration successful: {result}")
                            self.is_registered = True
                            return True
                        else:
                            error_text = await response.text()
                            logger.error(f"Registration failed: {response.status} - {error_text}")

                except asyncio.TimeoutError:
                    logger.warning(f"Registration timeout (attempt {attempt + 1})")
                except Exception as e:
                    logger.error(f"Registration error (attempt {attempt + 1}): {e}")

                if attempt < self.config.retry_attempts - 1:
                    await asyncio.sleep(self.config.retry_delay)

            return False

        except Exception as e:
            logger.error(f"Error registering with webhook service: {e}")
            return False

    async def run_mcp_server(self):
        """Run MCP server to handle webhook service requests"""
        from aiohttp import web

        app = web.Application()
        app.router.add_post('/mcp', self.handle_mcp_request)
        app.router.add_get('/health', self.handle_health_check)

        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(runner, 'localhost', self.config.mcp_port)
        await site.start()

        logger.info(f"🔗 MCP server running on port {self.config.mcp_port}")

        # Keep server running
        try:
            await asyncio.Event().wait()  # Wait indefinitely
        except asyncio.CancelledError:
            logger.info("MCP server shutting down")
        finally:
            await runner.cleanup()

    async def handle_mcp_request(self, request: web.Request) -> web.Response:
        """Handle incoming MCP requests from webhook service"""
        try:
            # Verify authorization
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                return web.Response(status=401, text="Unauthorized")

            token = auth_header.split(' ', 1)[1]
            if token != self.config.auth_token:
                return web.Response(status=401, text="Invalid token")

            # Parse MCP request
            data = await request.json()
            method = data.get('method')
            params = data.get('params', {})

            logger.info(f"🔗 MCP request: {method}")

            if method == 'handle_whatsapp_message':
                result = await self.handle_whatsapp_message(params)
                response_data = {"result": result}
            elif method == 'ping':
                response_data = {"result": "pong"}
            else:
                response_data = {"error": f"Unknown method: {method}"}

            return web.Response(
                text=json.dumps(response_data),
                content_type='application/json'
            )

        except Exception as e:
            logger.error(f"Error handling MCP request: {e}")
            return web.Response(
                status=500,
                text=json.dumps({"error": str(e)}),
                content_type='application/json'
            )

    async def handle_health_check(self, request: web.Request) -> web.Response:
        """Handle health check requests"""
        health_data = {
            "status": "healthy",
            "client_id": self.config.client_id,
            "customer_id": self.config.customer_id,
            "registered": self.is_registered,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "timestamp": datetime.now().isoformat()
        }

        return web.Response(
            text=json.dumps(health_data),
            content_type='application/json'
        )

    async def handle_whatsapp_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle WhatsApp message from webhook service"""
        try:
            message = params.get('message', '')
            message_id = params.get('message_id', '')
            message_type = params.get('message_type', 'text')
            from_number = params.get('from_number', '')
            customer_id = params.get('customer_id', '')
            timestamp = params.get('timestamp', '')

            logger.info(f"📱 Processing WhatsApp message: {message[:100]}...")

            # Call EA handler function
            try:
                ea_response = await self.ea_handler(
                    message=message,
                    message_id=message_id,
                    message_type=message_type,
                    from_number=from_number,
                    customer_id=customer_id
                )

                return {
                    "success": True,
                    "response": ea_response,
                    "processed_at": datetime.now().isoformat()
                }

            except Exception as e:
                logger.error(f"EA handler error: {e}")
                return {
                    "success": False,
                    "response": "I'm experiencing technical difficulties. Please try again.",
                    "error": str(e)
                }

        except Exception as e:
            logger.error(f"Error handling WhatsApp message: {e}")
            return {
                "success": False,
                "response": "Sorry, I couldn't process your message right now.",
                "error": str(e)
            }

    async def heartbeat_loop(self):
        """Send periodic heartbeats to webhook service"""
        while True:
            try:
                await asyncio.sleep(self.config.heartbeat_interval)

                if self.is_registered:
                    # Send heartbeat ping
                    url = f"{self.config.webhook_service_url}/ea/clients"

                    try:
                        async with self.session.get(
                            url,
                            timeout=aiohttp.ClientTimeout(total=5)
                        ) as response:
                            if response.status == 200:
                                self.last_heartbeat = datetime.now()
                                logger.debug("💓 Heartbeat successful")
                            else:
                                logger.warning(f"Heartbeat failed: {response.status}")
                    except Exception as e:
                        logger.warning(f"Heartbeat error: {e}")

                else:
                    # Try to re-register
                    logger.info("🔄 Attempting to re-register with webhook service")
                    await self.register_with_webhook_service()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")

    async def stop(self):
        """Stop the WhatsApp bridge"""
        try:
            if self.is_registered:
                # Unregister from webhook service
                url = f"{self.config.webhook_service_url}/ea/unregister/{self.config.client_id}"

                if self.session:
                    try:
                        async with self.session.delete(url) as response:
                            if response.status == 200:
                                logger.info("✅ Successfully unregistered from webhook service")
                            else:
                                logger.warning(f"Unregister failed: {response.status}")
                    except Exception as e:
                        logger.warning(f"Unregister error: {e}")

            if self.session:
                await self.session.close()

            logger.info("🔌 WhatsApp bridge stopped")

        except Exception as e:
            logger.error(f"Error stopping WhatsApp bridge: {e}")

# Helper function for EA integration
async def create_ea_whatsapp_handler(customer_id: str):
    """Create WhatsApp message handler that integrates with EA"""

    async def handle_message(message: str, message_id: str, message_type: str,
                           from_number: str, customer_id: str) -> str:
        """Handle WhatsApp message with EA integration"""
        try:
            # Import EA here to avoid circular dependencies
            from agents.executive_assistant import ExecutiveAssistant, ConversationChannel

            logger.info(f"🤖 Processing with EA: customer={customer_id}")

            # Initialize EA for customer
            ea = ExecutiveAssistant(customer_id=customer_id)

            # Process message
            response = await ea.handle_customer_interaction(
                message,
                ConversationChannel.WHATSAPP
            )

            logger.info(f"✅ EA response generated: {len(response)} characters")
            return response

        except Exception as e:
            logger.error(f"❌ EA processing error: {e}")
            return "I'm having trouble processing your message right now. Let me get back to you in a moment."

    return handle_message

# Example usage and configuration
def create_bridge_config() -> WhatsAppBridgeConfig:
    """Create bridge configuration from environment"""

    return WhatsAppBridgeConfig(
        webhook_service_url=os.getenv('WHATSAPP_WEBHOOK_SERVICE_URL', 'https://your-webhook-service.ondigitalocean.app'),
        client_id=str(uuid.uuid4()),
        customer_id=os.getenv('CUSTOMER_ID', 'default-customer'),
        phone_number=os.getenv('WHATSAPP_PHONE_NUMBER', ''),
        auth_token=os.getenv('EA_AUTH_TOKEN', str(uuid.uuid4())),
        mcp_port=int(os.getenv('MCP_PORT', '8001')),
        heartbeat_interval=int(os.getenv('HEARTBEAT_INTERVAL', '300')),
        retry_attempts=int(os.getenv('RETRY_ATTEMPTS', '3')),
        retry_delay=int(os.getenv('RETRY_DELAY', '5'))
    )

async def main():
    """Main function for running EA WhatsApp bridge"""
    try:
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # Create configuration
        config = create_bridge_config()

        # Create EA handler
        ea_handler = await create_ea_whatsapp_handler(config.customer_id)

        # Create and start bridge
        bridge = EAWhatsAppBridge(config, ea_handler)

        logger.info(f"🚀 Starting EA WhatsApp Bridge for {config.customer_id}")

        try:
            await bridge.start()
        except KeyboardInterrupt:
            logger.info("👋 Shutting down EA WhatsApp Bridge")
        finally:
            await bridge.stop()

    except Exception as e:
        logger.error(f"Failed to start EA WhatsApp Bridge: {e}")

if __name__ == "__main__":
    asyncio.run(main())