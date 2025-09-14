# WhatsApp Business Integration - Technical Implementation Specifications

## Executive Summary

This document provides comprehensive technical specifications for implementing Meta Embedded Signup integration with our centralized WhatsApp webhook service. The implementation enables EA clients to seamlessly connect their WhatsApp Business accounts while maintaining complete business isolation through per-customer MCP servers.

## Architecture Overview

### System Components

```mermaid
graph TB
    subgraph "Client Environment"
        UI[WhatsApp Onboarding UI]
        EA[Executive Assistant]
        MCP[Per-Customer MCP Server]
        DB[(Client Database)]
    end

    subgraph "Meta Integration"
        FB[Facebook JavaScript SDK]
        GRAPH[Graph API]
        SIGNUP[Embedded Signup Flow]
    end

    subgraph "Centralized Webhook Service"
        WH[Webhook Handler]
        ROUTE[Message Router]
        REG[Client Registry]
        REDIS[(Redis Cache)]
    end

    UI --> FB
    FB --> SIGNUP
    SIGNUP --> GRAPH
    GRAPH --> WH
    WH --> ROUTE
    ROUTE --> REG
    REG --> REDIS
    ROUTE --> MCP
    MCP --> EA
    EA --> DB
```

### Integration Flow Sequence

```mermaid
sequenceDiagram
    participant C as Client Browser
    participant FB as Facebook SDK
    participant META as Meta Graph API
    participant BE as Backend API
    participant WS as Webhook Service
    participant EA as Client EA

    C->>FB: Initialize Embedded Signup
    FB->>META: Launch Business Login
    META->>C: Display Account Selection
    C->>META: Grant Permissions
    META->>FB: Return Authorization Code (30s TTL)
    FB->>C: Code Received
    C->>BE: Exchange Code for Tokens
    BE->>META: Token Exchange Request
    META->>BE: Business Access Tokens
    BE->>WS: Register EA with Webhook Service
    WS->>WS: Store Client Registry
    WS->>BE: Registration Success
    BE->>C: Connection Complete
    Note over WS,EA: Message routing active
```

## Meta Embedded Signup Implementation

### Facebook JavaScript SDK Configuration

```javascript
// SDK Initialization
window.fbAsyncInit = function() {
    FB.init({
        appId: process.env.FACEBOOK_APP_ID,
        autoLogAppEvents: true,
        xfbml: true,
        version: 'v18.0'
    });

    // Configure WhatsApp Business Login
    FB.login(function(response) {
        if (response.authResponse) {
            handleSignupSuccess(response);
        } else {
            handleSignupError(response.error);
        }
    }, {
        config_id: process.env.WHATSAPP_CONFIG_ID,
        response_type: 'code',
        override_default_response_type: true,
        extras: {
            setup: {
                'messenger_welcome_flow': 'enabled',
                'customer_chat_display_style': 'card'
            }
        }
    });
};

// Load SDK asynchronously
(function(d, s, id) {
    var js, fjs = d.getElementsByTagName(s)[0];
    if (d.getElementById(id)) return;
    js = d.createElement(s); js.id = id;
    js.src = "https://connect.facebook.net/en_US/sdk.js";
    fjs.parentNode.insertBefore(js, fjs);
}(document, 'script', 'facebook-jssdk'));
```

### Critical Data Capture

The Meta Embedded Signup flow captures essential business data:

```typescript
interface WhatsAppBusinessData {
    phone_number_id: string;    // Business phone number ID for API calls
    waba_id: string;           // WhatsApp Business Account ID
    business_id: string;       // Business Manager portfolio ID
    code: string;              // 30-second TTL authorization code
    access_token?: string;     // Short-lived user access token
}

interface ExchangeTokenRequest {
    code: string;              // Authorization code from signup flow
    redirect_uri: string;      // Must match registered redirect URI
    client_id: string;         // Facebook App ID
    client_secret: string;     // Facebook App Secret
}

interface BusinessTokenResponse {
    access_token: string;      // Long-term business access token
    token_type: 'bearer';
    expires_in?: number;       // Token expiration (if applicable)
    phone_number_id: string;   // Associated phone number ID
    waba_id: string;          // Associated WABA ID
    business_id: string;       // Associated business ID
}
```

## Backend API Implementation

### Token Exchange Endpoint

```python
from flask import Flask, request, jsonify
import requests
import os
from datetime import datetime, timedelta

@app.route('/api/whatsapp/exchange-token', methods=['POST'])
def exchange_whatsapp_token():
    """Exchange Meta authorization code for business access tokens"""

    data = request.get_json()
    required_fields = ['code', 'customer_id', 'redirect_uri']

    # Validate request
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    # Exchange code for access token (30-second window)
    try:
        token_response = requests.post(
            'https://graph.facebook.com/v18.0/oauth/access_token',
            data={
                'client_id': os.environ['FACEBOOK_APP_ID'],
                'client_secret': os.environ['FACEBOOK_APP_SECRET'],
                'code': data['code'],
                'redirect_uri': data['redirect_uri']
            },
            timeout=10
        )

        if not token_response.ok:
            return jsonify({
                'error': 'Token exchange failed',
                'details': token_response.json()
            }), 400

        tokens = token_response.json()

        # Get WhatsApp Business Account details
        waba_response = requests.get(
            f"https://graph.facebook.com/v18.0/me/businesses",
            headers={'Authorization': f"Bearer {tokens['access_token']}"},
            timeout=10
        )

        if not waba_response.ok:
            return jsonify({
                'error': 'Failed to fetch business details',
                'details': waba_response.json()
            }), 400

        businesses = waba_response.json()['data']

        # Find WhatsApp Business Account
        waba_data = None
        for business in businesses:
            # Query for WhatsApp Business Accounts
            waba_check = requests.get(
                f"https://graph.facebook.com/v18.0/{business['id']}/owned_whatsapp_business_accounts",
                headers={'Authorization': f"Bearer {tokens['access_token']}"},
                timeout=10
            )

            if waba_check.ok:
                wabas = waba_check.json().get('data', [])
                if wabas:
                    waba_data = {
                        'business_id': business['id'],
                        'waba_id': wabas[0]['id'],
                        'access_token': tokens['access_token']
                    }

                    # Get phone number ID
                    phone_response = requests.get(
                        f"https://graph.facebook.com/v18.0/{waba_data['waba_id']}/phone_numbers",
                        headers={'Authorization': f"Bearer {tokens['access_token']}"},
                        timeout=10
                    )

                    if phone_response.ok:
                        phones = phone_response.json().get('data', [])
                        if phones:
                            waba_data['phone_number_id'] = phones[0]['id']
                            waba_data['phone_number'] = phones[0]['display_phone_number']
                    break

        if not waba_data:
            return jsonify({'error': 'No WhatsApp Business Account found'}), 400

        # Store connection data securely
        connection_data = {
            'customer_id': data['customer_id'],
            'phone_number_id': waba_data['phone_number_id'],
            'waba_id': waba_data['waba_id'],
            'business_id': waba_data['business_id'],
            'phone_number': waba_data['phone_number'],
            'access_token': encrypt_token(waba_data['access_token']),
            'connected_at': datetime.utcnow().isoformat(),
            'status': 'active'
        }

        # Save to database
        save_whatsapp_connection(connection_data)

        return jsonify({
            'success': True,
            'phone_number_id': waba_data['phone_number_id'],
            'waba_id': waba_data['waba_id'],
            'business_id': waba_data['business_id'],
            'phone_number': waba_data['phone_number']
        })

    except requests.Timeout:
        return jsonify({'error': 'Request timeout during token exchange'}), 504
    except requests.RequestException as e:
        return jsonify({'error': f'Network error: {str(e)}'}), 502
    except Exception as e:
        logger.error(f"Token exchange error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

def encrypt_token(token):
    """Encrypt access token for secure storage"""
    from cryptography.fernet import Fernet
    key = os.environ['ENCRYPTION_KEY'].encode()
    cipher = Fernet(key)
    return cipher.encrypt(token.encode()).decode()

def save_whatsapp_connection(data):
    """Save WhatsApp connection to database with proper isolation"""
    # Implementation depends on your database architecture
    # Should ensure per-customer data isolation
    pass
```

### Webhook Service Registration

```python
@app.route('/api/whatsapp/register-webhook', methods=['POST'])
def register_webhook_service():
    """Register client EA with centralized webhook service"""

    data = request.get_json()
    required_fields = ['customer_id', 'phone_number_id', 'waba_id', 'business_id']

    # Validate request
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    webhook_service_url = os.environ['WEBHOOK_SERVICE_URL']

    try:
        # Register with centralized webhook service
        registration_response = requests.post(
            f"{webhook_service_url}/api/ea/register",
            json={
                'customer_id': data['customer_id'],
                'phone_number_id': data['phone_number_id'],
                'waba_id': data['waba_id'],
                'business_id': data['business_id'],
                'ea_endpoint': f"https://{request.host}/api/ea/webhook",
                'auth_token': generate_ea_auth_token(data['customer_id']),
                'client_info': {
                    'name': get_customer_name(data['customer_id']),
                    'tier': get_customer_tier(data['customer_id']),
                    'mcp_server_id': get_mcp_server_id(data['customer_id'])
                }
            },
            headers={
                'Authorization': f"Bearer {os.environ['WEBHOOK_SERVICE_AUTH_TOKEN']}",
                'Content-Type': 'application/json'
            },
            timeout=30
        )

        if not registration_response.ok:
            return jsonify({
                'error': 'Webhook service registration failed',
                'details': registration_response.json()
            }), 400

        registration_data = registration_response.json()

        # Update local connection record
        update_connection_status(
            data['customer_id'],
            'webhook_registered',
            registration_data.get('webhook_id')
        )

        return jsonify({
            'success': True,
            'webhook_id': registration_data['webhook_id'],
            'webhook_url': registration_data['webhook_url'],
            'status': 'active',
            'message': 'EA successfully registered with WhatsApp webhook service'
        })

    except Exception as e:
        logger.error(f"Webhook registration error: {str(e)}")
        return jsonify({'error': 'Registration failed'}), 500

def generate_ea_auth_token(customer_id):
    """Generate secure auth token for EA communication"""
    import secrets
    import hashlib

    # Generate unique token for customer
    token_data = f"{customer_id}:{secrets.token_urlsafe(32)}:{datetime.utcnow().isoformat()}"
    token = hashlib.sha256(token_data.encode()).hexdigest()

    # Store token securely for later validation
    store_ea_auth_token(customer_id, token)

    return token
```

## Centralized Webhook Service Architecture

### Message Routing Implementation

```python
from flask import Flask, request, jsonify
import redis
import requests
import hmac
import hashlib
import json
from datetime import datetime

app = Flask(__name__)
redis_client = redis.Redis(
    host=os.environ['REDIS_HOST'],
    port=int(os.environ['REDIS_PORT']),
    password=os.environ['REDIS_PASSWORD'],
    decode_responses=True
)

@app.route('/webhook', methods=['GET', 'POST'])
def whatsapp_webhook():
    """Handle WhatsApp webhook events and route to appropriate EA"""

    if request.method == 'GET':
        # Webhook verification
        return verify_webhook()

    # POST - Handle incoming messages
    return handle_incoming_message()

def verify_webhook():
    """Verify webhook with Meta's challenge"""
    verify_token = os.environ['WHATSAPP_VERIFY_TOKEN']

    if request.args.get('hub.verify_token') == verify_token:
        return request.args.get('hub.challenge')
    else:
        return 'Verification failed', 403

def handle_incoming_message():
    """Route incoming WhatsApp messages to appropriate client EA"""

    # Verify webhook signature
    if not verify_signature(request.data, request.headers.get('X-Hub-Signature-256', '')):
        return 'Invalid signature', 403

    data = request.get_json()

    # Extract message information
    try:
        entry = data['entry'][0]
        changes = entry['changes'][0]
        value = changes['value']

        # Handle different webhook event types
        if 'messages' in value:
            return route_message(value)
        elif 'statuses' in value:
            return route_status_update(value)
        else:
            return jsonify({'status': 'ignored'}), 200

    except (KeyError, IndexError) as e:
        logger.error(f"Invalid webhook payload: {str(e)}")
        return jsonify({'error': 'Invalid payload'}), 400

def route_message(webhook_data):
    """Route message to appropriate client EA"""

    try:
        # Extract routing information
        phone_number_id = webhook_data['metadata']['phone_number_id']
        messages = webhook_data['messages']

        # Find client EA for this phone number
        client_info = get_client_by_phone_number_id(phone_number_id)

        if not client_info:
            logger.warning(f"No client found for phone_number_id: {phone_number_id}")
            return jsonify({'error': 'No client registered'}), 404

        # Route message to client EA
        for message in messages:
            success = forward_to_client_ea(client_info, message, webhook_data['metadata'])

            if not success:
                logger.error(f"Failed to forward message to client: {client_info['customer_id']}")
                # Implement fallback mechanism
                send_fallback_response(phone_number_id, message['from'])

        return jsonify({'status': 'routed'}), 200

    except Exception as e:
        logger.error(f"Message routing error: {str(e)}")
        return jsonify({'error': 'Routing failed'}), 500

def get_client_by_phone_number_id(phone_number_id):
    """Retrieve client information from registry"""

    # Check Redis cache first
    cache_key = f"phone_mapping:{phone_number_id}"
    cached_client = redis_client.get(cache_key)

    if cached_client:
        return json.loads(cached_client)

    # Fallback to database lookup
    client_info = db_get_client_by_phone_number_id(phone_number_id)

    if client_info:
        # Cache for future lookups
        redis_client.setex(
            cache_key,
            3600,  # 1 hour cache
            json.dumps(client_info)
        )

    return client_info

def forward_to_client_ea(client_info, message, metadata):
    """Forward message to client's EA via MCP server"""

    try:
        ea_payload = {
            'event_type': 'whatsapp_message',
            'message': message,
            'metadata': metadata,
            'customer_id': client_info['customer_id'],
            'timestamp': datetime.utcnow().isoformat()
        }

        response = requests.post(
            client_info['ea_endpoint'],
            json=ea_payload,
            headers={
                'Authorization': f"Bearer {client_info['auth_token']}",
                'Content-Type': 'application/json',
                'X-Webhook-Source': 'whatsapp-central-service'
            },
            timeout=30
        )

        if response.ok:
            # Log successful delivery
            log_message_delivery(client_info['customer_id'], message['id'], 'delivered')
            return True
        else:
            # Log delivery failure
            log_message_delivery(client_info['customer_id'], message['id'], 'failed')
            logger.error(f"EA endpoint error: {response.status_code} - {response.text}")
            return False

    except requests.Timeout:
        log_message_delivery(client_info['customer_id'], message['id'], 'timeout')
        logger.error(f"Timeout forwarding to EA: {client_info['customer_id']}")
        return False
    except Exception as e:
        log_message_delivery(client_info['customer_id'], message['id'], 'error')
        logger.error(f"Error forwarding to EA: {str(e)}")
        return False

def verify_signature(payload, signature):
    """Verify webhook signature from Meta"""

    app_secret = os.environ['WHATSAPP_APP_SECRET']
    expected_signature = hmac.new(
        app_secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(f"sha256={expected_signature}", signature)
```

### Client Registry Management

```python
class ClientRegistry:
    """Manage client EA registrations and routing information"""

    def __init__(self, redis_client, db_connection):
        self.redis = redis_client
        self.db = db_connection

    def register_client(self, registration_data):
        """Register new client EA with webhook service"""

        required_fields = [
            'customer_id', 'phone_number_id', 'waba_id',
            'business_id', 'ea_endpoint', 'auth_token'
        ]

        # Validate registration data
        for field in required_fields:
            if field not in registration_data:
                raise ValueError(f"Missing required field: {field}")

        # Generate unique webhook ID
        webhook_id = self.generate_webhook_id(registration_data['customer_id'])

        # Store in database with full isolation
        client_record = {
            'webhook_id': webhook_id,
            'customer_id': registration_data['customer_id'],
            'phone_number_id': registration_data['phone_number_id'],
            'waba_id': registration_data['waba_id'],
            'business_id': registration_data['business_id'],
            'ea_endpoint': registration_data['ea_endpoint'],
            'auth_token': self.encrypt_auth_token(registration_data['auth_token']),
            'client_info': registration_data.get('client_info', {}),
            'registered_at': datetime.utcnow().isoformat(),
            'status': 'active',
            'last_heartbeat': datetime.utcnow().isoformat()
        }

        # Save to database
        self.db.clients.insert_one(client_record)

        # Cache routing information in Redis
        routing_cache = {
            'customer_id': registration_data['customer_id'],
            'ea_endpoint': registration_data['ea_endpoint'],
            'auth_token': registration_data['auth_token'],
            'client_info': registration_data.get('client_info', {})
        }

        self.redis.setex(
            f"phone_mapping:{registration_data['phone_number_id']}",
            86400,  # 24 hour cache
            json.dumps(routing_cache)
        )

        return {
            'webhook_id': webhook_id,
            'webhook_url': f"{os.environ['WEBHOOK_SERVICE_URL']}/webhook",
            'status': 'registered',
            'routing_active': True
        }

    def update_client_heartbeat(self, customer_id):
        """Update client heartbeat for health monitoring"""

        # Update database
        self.db.clients.update_one(
            {'customer_id': customer_id},
            {
                '$set': {
                    'last_heartbeat': datetime.utcnow().isoformat(),
                    'status': 'active'
                }
            }
        )

        # Update cache
        phone_number_id = self.get_phone_number_id(customer_id)
        if phone_number_id:
            cache_key = f"phone_mapping:{phone_number_id}"
            cached_data = self.redis.get(cache_key)
            if cached_data:
                client_data = json.loads(cached_data)
                client_data['last_heartbeat'] = datetime.utcnow().isoformat()
                self.redis.setex(cache_key, 86400, json.dumps(client_data))

    def get_client_status(self, customer_id):
        """Get comprehensive client status information"""

        client = self.db.clients.find_one({'customer_id': customer_id})

        if not client:
            return None

        # Calculate health metrics
        last_heartbeat = datetime.fromisoformat(client['last_heartbeat'])
        time_since_heartbeat = datetime.utcnow() - last_heartbeat

        # Determine status
        if time_since_heartbeat.total_seconds() > 300:  # 5 minutes
            status = 'disconnected'
        elif time_since_heartbeat.total_seconds() > 120:  # 2 minutes
            status = 'warning'
        else:
            status = 'connected'

        return {
            'customer_id': customer_id,
            'phone_number_id': client['phone_number_id'],
            'waba_id': client['waba_id'],
            'business_id': client['business_id'],
            'status': status,
            'last_heartbeat': client['last_heartbeat'],
            'registered_at': client['registered_at'],
            'client_info': client.get('client_info', {}),
            'routing_active': status in ['connected', 'warning']
        }
```

## Client-Side EA Integration

### MCP Server WhatsApp Handler

```python
from mcp.server.models import Notification
from mcp.server import Server
import asyncio
import json
from datetime import datetime

class EAWhatsAppHandler:
    """Handle WhatsApp messages within client's MCP server environment"""

    def __init__(self, mcp_server: Server, ea_instance, customer_id):
        self.mcp_server = mcp_server
        self.ea = ea_instance
        self.customer_id = customer_id
        self.webhook_service_url = os.environ['WEBHOOK_SERVICE_URL']

    async def handle_incoming_message(self, webhook_payload):
        """Process incoming WhatsApp message with EA"""

        try:
            message = webhook_payload['message']
            metadata = webhook_payload['metadata']

            # Extract message content
            message_text = self.extract_message_text(message)
            sender_phone = message['from']
            message_id = message['id']

            if not message_text:
                logger.warning(f"No text content in message {message_id}")
                return

            # Process with EA
            ea_context = {
                'channel': 'whatsapp',
                'sender': sender_phone,
                'message_id': message_id,
                'customer_id': self.customer_id,
                'timestamp': datetime.utcnow().isoformat()
            }

            # Generate EA response with business context
            ea_response = await self.ea.process_message(
                message_text,
                context=ea_context
            )

            # Send response via centralized service
            success = await self.send_whatsapp_response(
                sender_phone,
                ea_response,
                metadata['phone_number_id']
            )

            if success:
                # Log successful interaction for business learning
                await self.ea.log_successful_interaction(
                    message_text,
                    ea_response,
                    ea_context
                )
            else:
                logger.error(f"Failed to send WhatsApp response for message {message_id}")

        except Exception as e:
            logger.error(f"Error processing WhatsApp message: {str(e)}")
            # Send generic error response
            await self.send_error_response(webhook_payload)

    def extract_message_text(self, message):
        """Extract text content from WhatsApp message"""

        if message['type'] == 'text':
            return message['text']['body']
        elif message['type'] == 'button':
            return message['button']['text']
        elif message['type'] == 'interactive':
            if 'button_reply' in message['interactive']:
                return message['interactive']['button_reply']['title']
            elif 'list_reply' in message['interactive']:
                return message['interactive']['list_reply']['title']

        # Handle other message types (image, document, voice, etc.)
        # For non-text messages, could extract captions or return type info
        return f"[{message['type']} message]"

    async def send_whatsapp_response(self, to_phone, ea_response, phone_number_id):
        """Send EA response via webhook service"""

        try:
            # Format response for WhatsApp
            whatsapp_message = self.format_ea_response_for_whatsapp(ea_response)

            # Send via centralized webhook service
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: requests.post(
                    f"{self.webhook_service_url}/api/send-message",
                    json={
                        'phone_number_id': phone_number_id,
                        'to': to_phone,
                        'message': whatsapp_message,
                        'customer_id': self.customer_id
                    },
                    headers={
                        'Authorization': f"Bearer {self.get_auth_token()}",
                        'Content-Type': 'application/json'
                    },
                    timeout=30
                )
            )

            return response.ok

        except Exception as e:
            logger.error(f"Error sending WhatsApp response: {str(e)}")
            return False

    def format_ea_response_for_whatsapp(self, ea_response):
        """Format EA response for WhatsApp delivery with premium-casual tone"""

        # Apply premium-casual personality transformation
        casual_response = self.apply_premium_casual_tone(ea_response['text'])

        message = {
            'messaging_product': 'whatsapp',
            'type': 'text',
            'text': {
                'body': casual_response
            }
        }

        # Add interactive elements if EA suggests actions
        if ea_response.get('suggested_actions'):
            message['type'] = 'interactive'
            message['interactive'] = {
                'type': 'button',
                'body': {'text': casual_response},
                'action': {
                    'buttons': [
                        {
                            'type': 'reply',
                            'reply': {
                                'id': f"action_{i}",
                                'title': action['title'][:20]  # WhatsApp limit
                            }
                        }
                        for i, action in enumerate(ea_response['suggested_actions'][:3])
                    ]
                }
            }

        return message

    def apply_premium_casual_tone(self, text):
        """Apply premium-casual personality to EA responses"""

        # Transform formal language to approachable while maintaining sophistication
        casual_text = text

        # Common transformations for premium-casual tone
        transformations = [
            ("I have identified", "I noticed"),
            ("I recommend that you", "You might want to"),
            ("Please find attached", "Here's what I've got for you"),
            ("I would suggest", "How about we"),
            ("At your earliest convenience", "when you get a chance"),
            ("I have completed", "Done!"),
            ("Please be advised", "Just so you know"),
            ("I am pleased to inform", "Great news!")
        ]

        for formal, casual in transformations:
            casual_text = casual_text.replace(formal, casual)

        # Add motivational elements for ambitious professionals
        if any(keyword in text.lower() for keyword in ['growth', 'opportunity', 'business', 'success']):
            motivational_endings = [
                "This is going to be great for your growth! 🚀",
                "You're building something awesome here! ✨",
                "Let's get you ahead of the competition! 💪",
                "This will definitely boost your profile! 📈"
            ]

            import random
            casual_text += f" {random.choice(motivational_endings)}"

        return casual_text
```

## Security Implementation

### Token Management

```python
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

class SecureTokenManager:
    """Secure management of WhatsApp Business tokens"""

    def __init__(self):
        self.master_key = os.environ['MASTER_ENCRYPTION_KEY'].encode()
        self.salt = os.environ['ENCRYPTION_SALT'].encode()
        self.cipher = self._generate_cipher()

    def _generate_cipher(self):
        """Generate encryption cipher from master key"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.master_key))
        return Fernet(key)

    def encrypt_business_token(self, token, customer_id):
        """Encrypt WhatsApp Business access token"""

        # Add customer context for additional security
        token_data = f"{customer_id}:{token}:{datetime.utcnow().isoformat()}"
        encrypted_token = self.cipher.encrypt(token_data.encode())

        return base64.urlsafe_b64encode(encrypted_token).decode()

    def decrypt_business_token(self, encrypted_token, customer_id):
        """Decrypt WhatsApp Business access token"""

        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_token.encode())
            decrypted_data = self.cipher.decrypt(encrypted_bytes).decode()

            # Validate customer context
            parts = decrypted_data.split(':', 2)
            if len(parts) != 3 or parts[0] != customer_id:
                raise ValueError("Invalid token context")

            return parts[1]  # Return actual token

        except Exception as e:
            logger.error(f"Token decryption failed: {str(e)}")
            raise ValueError("Token decryption failed")
```

### Webhook Signature Verification

```python
import hmac
import hashlib

def verify_whatsapp_signature(payload, signature, app_secret):
    """Verify Meta webhook signature for security"""

    # Generate expected signature
    expected_signature = hmac.new(
        app_secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()

    # Compare signatures securely
    expected_sig_header = f"sha256={expected_signature}"

    return hmac.compare_digest(expected_sig_header, signature)

@app.before_request
def verify_webhook_security():
    """Middleware to verify all webhook requests"""

    # Skip verification for non-webhook endpoints
    if not request.endpoint or 'webhook' not in request.endpoint:
        return

    # Get signature from headers
    signature = request.headers.get('X-Hub-Signature-256')
    if not signature:
        return jsonify({'error': 'Missing signature'}), 403

    # Verify signature
    app_secret = os.environ['WHATSAPP_APP_SECRET']
    if not verify_whatsapp_signature(request.data, signature, app_secret):
        logger.warning(f"Invalid webhook signature from {request.remote_addr}")
        return jsonify({'error': 'Invalid signature'}), 403
```

## Performance Optimization

### Message Routing Optimization

```python
class HighPerformanceRouter:
    """Optimized message routing for high-volume environments"""

    def __init__(self):
        self.connection_pool = redis.ConnectionPool(
            host=os.environ['REDIS_HOST'],
            port=int(os.environ['REDIS_PORT']),
            password=os.environ['REDIS_PASSWORD'],
            max_connections=20,
            decode_responses=True
        )
        self.redis_client = redis.Redis(connection_pool=self.connection_pool)

        # Pre-compile routing cache for faster lookups
        self.routing_cache = {}
        self.cache_refresh_interval = 300  # 5 minutes
        self.last_cache_refresh = 0

    async def route_message_optimized(self, phone_number_id, message_data):
        """Optimized message routing with caching and connection pooling"""

        # Check if cache needs refresh
        current_time = time.time()
        if current_time - self.last_cache_refresh > self.cache_refresh_interval:
            await self.refresh_routing_cache()
            self.last_cache_refresh = current_time

        # Fast cache lookup
        client_info = self.routing_cache.get(phone_number_id)

        if not client_info:
            # Fallback to Redis lookup
            client_info = await self.redis_lookup(phone_number_id)
            if client_info:
                self.routing_cache[phone_number_id] = client_info

        if client_info:
            # Use async HTTP client for better performance
            return await self.send_async_request(client_info, message_data)

        return False

    async def refresh_routing_cache(self):
        """Periodically refresh routing cache from Redis"""

        try:
            # Get all phone number mappings
            keys = self.redis_client.keys("phone_mapping:*")

            new_cache = {}
            for key in keys:
                phone_number_id = key.split(':', 1)[1]
                client_data = self.redis_client.get(key)

                if client_data:
                    new_cache[phone_number_id] = json.loads(client_data)

            self.routing_cache = new_cache
            logger.info(f"Refreshed routing cache with {len(new_cache)} entries")

        except Exception as e:
            logger.error(f"Cache refresh failed: {str(e)}")

    async def send_async_request(self, client_info, message_data):
        """Send async HTTP request to client EA"""

        import aiohttp

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    client_info['ea_endpoint'],
                    json=message_data,
                    headers={
                        'Authorization': f"Bearer {client_info['auth_token']}",
                        'Content-Type': 'application/json'
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:

                    return response.status == 200

            except asyncio.TimeoutError:
                logger.error(f"Timeout sending to EA: {client_info['customer_id']}")
                return False
            except Exception as e:
                logger.error(f"Error sending to EA: {str(e)}")
                return False
```

## Monitoring & Analytics

### Performance Metrics Collection

```python
class WhatsAppMetricsCollector:
    """Collect and analyze WhatsApp integration performance metrics"""

    def __init__(self):
        self.metrics_db = self.get_metrics_database()
        self.redis_client = redis.Redis(
            host=os.environ['REDIS_HOST'],
            port=int(os.environ['REDIS_PORT']),
            decode_responses=True
        )

    def track_message_processing(self, customer_id, message_id, processing_time, success):
        """Track message processing performance"""

        metric = {
            'customer_id': customer_id,
            'message_id': message_id,
            'processing_time': processing_time,
            'success': success,
            'timestamp': datetime.utcnow().isoformat(),
            'date': datetime.utcnow().date().isoformat()
        }

        # Store in time-series database
        self.metrics_db.message_processing.insert_one(metric)

        # Update real-time counters in Redis
        date_key = f"metrics:{customer_id}:{datetime.utcnow().date()}"
        self.redis_client.hincrby(date_key, 'total_messages', 1)

        if success:
            self.redis_client.hincrby(date_key, 'successful_messages', 1)

        # Track response time moving average
        self.update_response_time_average(customer_id, processing_time)

    def track_ea_workflow_creation(self, customer_id, workflow_type, creation_time):
        """Track EA workflow creation metrics"""

        metric = {
            'customer_id': customer_id,
            'workflow_type': workflow_type,
            'creation_time': creation_time,
            'timestamp': datetime.utcnow().isoformat(),
            'date': datetime.utcnow().date().isoformat()
        }

        self.metrics_db.workflow_creation.insert_one(metric)

        # Update daily workflow counter
        date_key = f"metrics:{customer_id}:{datetime.utcnow().date()}"
        self.redis_client.hincrby(date_key, 'workflows_created', 1)

    def get_customer_metrics(self, customer_id, period='7d'):
        """Get comprehensive metrics for customer dashboard"""

        end_date = datetime.utcnow().date()

        if period == '7d':
            start_date = end_date - timedelta(days=7)
        elif period == '30d':
            start_date = end_date - timedelta(days=30)
        elif period == '90d':
            start_date = end_date - timedelta(days=90)
        else:
            start_date = end_date - timedelta(days=7)

        # Aggregate metrics from database
        metrics = {
            'total_messages': 0,
            'successful_messages': 0,
            'avg_response_time': 0.0,
            'workflows_created': 0,
            'satisfaction_score': 4.8,  # Would be calculated from feedback
            'daily_breakdown': []
        }

        # Get daily metrics
        current_date = start_date
        while current_date <= end_date:
            daily_key = f"metrics:{customer_id}:{current_date}"
            daily_data = self.redis_client.hgetall(daily_key)

            daily_metrics = {
                'date': current_date.isoformat(),
                'messages': int(daily_data.get('total_messages', 0)),
                'successful': int(daily_data.get('successful_messages', 0)),
                'workflows': int(daily_data.get('workflows_created', 0))
            }

            metrics['daily_breakdown'].append(daily_metrics)
            metrics['total_messages'] += daily_metrics['messages']
            metrics['successful_messages'] += daily_metrics['successful']
            metrics['workflows_created'] += daily_metrics['workflows']

            current_date += timedelta(days=1)

        # Calculate average response time
        response_times = self.get_response_times(customer_id, start_date, end_date)
        if response_times:
            metrics['avg_response_time'] = sum(response_times) / len(response_times)

        return metrics
```

## Testing Strategy

### Integration Test Suite

```python
import unittest
import asyncio
import json
from unittest.mock import Mock, patch, MagicMock

class WhatsAppIntegrationTestSuite(unittest.TestCase):
    """Comprehensive test suite for WhatsApp Business integration"""

    def setUp(self):
        """Set up test environment"""
        self.test_customer_id = 'test-customer-123'
        self.test_phone_number_id = 'test-phone-123'
        self.test_waba_id = 'test-waba-123'
        self.test_access_token = 'test-access-token'

        # Mock external services
        self.mock_meta_api = Mock()
        self.mock_webhook_service = Mock()
        self.mock_ea_instance = Mock()

    def test_meta_token_exchange(self):
        """Test Meta authorization code exchange"""

        # Mock Meta Graph API response
        self.mock_meta_api.post.return_value.ok = True
        self.mock_meta_api.post.return_value.json.return_value = {
            'access_token': self.test_access_token,
            'token_type': 'bearer'
        }

        with patch('requests.post', self.mock_meta_api.post):
            result = exchange_whatsapp_token({
                'code': 'test-auth-code',
                'customer_id': self.test_customer_id,
                'redirect_uri': 'https://test.example.com/callback'
            })

        self.assertTrue(result['success'])
        self.assertEqual(result['phone_number_id'], self.test_phone_number_id)

    def test_webhook_registration(self):
        """Test webhook service registration"""

        self.mock_webhook_service.post.return_value.ok = True
        self.mock_webhook_service.post.return_value.json.return_value = {
            'webhook_id': 'test-webhook-123',
            'status': 'registered'
        }

        with patch('requests.post', self.mock_webhook_service.post):
            result = register_webhook_service({
                'customer_id': self.test_customer_id,
                'phone_number_id': self.test_phone_number_id,
                'waba_id': self.test_waba_id,
                'business_id': 'test-business-123'
            })

        self.assertTrue(result['success'])
        self.assertEqual(result['status'], 'active')

    def test_message_routing(self):
        """Test message routing to client EA"""

        # Mock incoming webhook payload
        webhook_payload = {
            'entry': [{
                'changes': [{
                    'value': {
                        'metadata': {
                            'phone_number_id': self.test_phone_number_id
                        },
                        'messages': [{
                            'id': 'test-message-123',
                            'from': '+1234567890',
                            'type': 'text',
                            'text': {'body': 'Hello EA, how is my business doing?'},
                            'timestamp': '1234567890'
                        }]
                    }
                }]
            }]
        }

        # Mock client lookup
        with patch('get_client_by_phone_number_id') as mock_lookup:
            mock_lookup.return_value = {
                'customer_id': self.test_customer_id,
                'ea_endpoint': 'https://test-ea.example.com/webhook',
                'auth_token': 'test-ea-token'
            }

            # Mock EA endpoint response
            with patch('requests.post') as mock_post:
                mock_post.return_value.ok = True

                result = route_message(webhook_payload['entry'][0]['changes'][0]['value'])

        self.assertEqual(result[1], 200)  # HTTP 200 status

    def test_ea_response_processing(self):
        """Test EA response processing and WhatsApp formatting"""

        # Mock EA response
        ea_response = {
            'text': 'I have identified several opportunities for growth in your business this week.',
            'suggested_actions': [
                {'title': 'View Growth Report', 'action': 'view_report'},
                {'title': 'Schedule Review', 'action': 'schedule_meeting'}
            ]
        }

        handler = EAWhatsAppHandler(None, self.mock_ea_instance, self.test_customer_id)

        # Test premium-casual tone application
        casual_response = handler.apply_premium_casual_tone(ea_response['text'])

        self.assertIn('I noticed', casual_response)
        self.assertNotIn('I have identified', casual_response)

        # Test WhatsApp message formatting
        whatsapp_message = handler.format_ea_response_for_whatsapp(ea_response)

        self.assertEqual(whatsapp_message['type'], 'interactive')
        self.assertEqual(len(whatsapp_message['interactive']['action']['buttons']), 2)

    def test_security_signature_verification(self):
        """Test webhook signature verification"""

        app_secret = 'test-app-secret'
        payload = b'{"test": "payload"}'

        # Generate valid signature
        import hmac
        import hashlib

        expected_signature = hmac.new(
            app_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        signature_header = f"sha256={expected_signature}"

        # Test verification
        result = verify_whatsapp_signature(payload, signature_header, app_secret)
        self.assertTrue(result)

        # Test invalid signature
        invalid_signature = "sha256=invalid_signature"
        result = verify_whatsapp_signature(payload, invalid_signature, app_secret)
        self.assertFalse(result)

    def test_performance_metrics_collection(self):
        """Test metrics collection and aggregation"""

        metrics_collector = WhatsAppMetricsCollector()

        # Mock database and Redis
        with patch.object(metrics_collector, 'metrics_db') as mock_db:
            with patch.object(metrics_collector, 'redis_client') as mock_redis:

                # Track message processing
                metrics_collector.track_message_processing(
                    self.test_customer_id,
                    'test-message-123',
                    1.5,  # processing time in seconds
                    True   # success
                )

                # Verify database insert was called
                mock_db.message_processing.insert_one.assert_called_once()

                # Verify Redis counters were updated
                mock_redis.hincrby.assert_called()

    async def test_async_message_handling(self):
        """Test asynchronous message handling performance"""

        handler = EAWhatsAppHandler(None, self.mock_ea_instance, self.test_customer_id)

        # Mock EA processing
        self.mock_ea_instance.process_message = AsyncMock(return_value={
            'text': 'Your business metrics look great this week!',
            'processing_time': 0.8
        })

        # Mock WhatsApp response sending
        with patch.object(handler, 'send_whatsapp_response', return_value=True):

            webhook_payload = {
                'message': {
                    'id': 'test-message-123',
                    'from': '+1234567890',
                    'type': 'text',
                    'text': {'body': 'How is my business performing?'}
                },
                'metadata': {
                    'phone_number_id': self.test_phone_number_id
                }
            }

            # Process message
            await handler.handle_incoming_message(webhook_payload)

            # Verify EA was called
            self.mock_ea_instance.process_message.assert_called_once()

if __name__ == '__main__':
    unittest.main()
```

## Deployment Configuration

### Environment Variables

```bash
# Meta/Facebook Configuration
FACEBOOK_APP_ID=your_facebook_app_id
FACEBOOK_APP_SECRET=your_facebook_app_secret
WHATSAPP_CONFIG_ID=your_whatsapp_configuration_id
WHATSAPP_VERIFY_TOKEN=your_webhook_verify_token
WHATSAPP_APP_SECRET=your_whatsapp_app_secret

# Webhook Service Configuration
WEBHOOK_SERVICE_URL=https://your-webhook-service.ondigitalocean.app
WEBHOOK_SERVICE_AUTH_TOKEN=your_webhook_service_auth_token

# Database Configuration
DATABASE_URL=postgresql://user:password@host:port/database
REDIS_HOST=your-redis-host
REDIS_PORT=6379
REDIS_PASSWORD=your-redis-password

# Security Configuration
MASTER_ENCRYPTION_KEY=your_master_encryption_key
ENCRYPTION_SALT=your_encryption_salt

# MCP Server Configuration
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=8001

# Monitoring Configuration
LOG_LEVEL=INFO
METRICS_COLLECTION_ENABLED=true
```

### Docker Deployment

```dockerfile
# WhatsApp Integration Service
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 whatsapp && chown -R whatsapp:whatsapp /app
USER whatsapp

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start application
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--worker-class", "aiohttp.GunicornWebWorker", "app:create_app()"]
```

### Kubernetes Configuration

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: whatsapp-integration-service
  labels:
    app: whatsapp-integration
spec:
  replicas: 3
  selector:
    matchLabels:
      app: whatsapp-integration
  template:
    metadata:
      labels:
        app: whatsapp-integration
    spec:
      containers:
      - name: whatsapp-service
        image: ai-agency/whatsapp-integration:latest
        ports:
        - containerPort: 8000
        env:
        - name: FACEBOOK_APP_ID
          valueFrom:
            secretKeyRef:
              name: whatsapp-secrets
              key: facebook-app-id
        - name: FACEBOOK_APP_SECRET
          valueFrom:
            secretKeyRef:
              name: whatsapp-secrets
              key: facebook-app-secret
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: database-secrets
              key: connection-string
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: whatsapp-integration-service
spec:
  selector:
    app: whatsapp-integration
  ports:
    - protocol: TCP
      port: 80
      targetPort: 8000
  type: LoadBalancer
```

## Success Metrics & KPIs

### Technical Performance Metrics

- **Connection Success Rate**: >98% successful Meta Embedded Signup completions
- **Token Exchange Speed**: <5 seconds for authorization code to business token exchange
- **Message Routing Latency**: <100ms average for webhook-to-EA message routing
- **EA Response Time**: <2 seconds average for premium-casual responses
- **System Uptime**: 99.9% availability for centralized webhook service

### Business Impact Metrics

- **Onboarding Completion Rate**: >80% of started flows result in active connections
- **Customer Satisfaction**: >4.5/5.0 rating for WhatsApp integration experience
- **EA Interaction Volume**: >50% increase in EA usage post-WhatsApp connection
- **Workflow Creation Rate**: >15 automated workflows created per customer per month
- **Support Ticket Reduction**: >60% decrease in WhatsApp-related support requests

### Security & Compliance Metrics

- **Data Isolation Validation**: 100% customer data separation through per-MCP architecture
- **Token Security**: Zero unauthorized access incidents to encrypted business tokens
- **Webhook Security**: 100% signature verification for all Meta webhook payloads
- **GDPR Compliance**: Full data processing within customer boundary controls
- **Audit Trail Completeness**: 100% logging coverage for all message routing and processing

This comprehensive technical specification provides the development team with all necessary implementation details for seamlessly integrating Meta Embedded Signup with our centralized WhatsApp webhook service while maintaining the premium-casual EA experience and complete business isolation that defines our platform.