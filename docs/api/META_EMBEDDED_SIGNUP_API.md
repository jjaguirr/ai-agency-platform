# Meta Embedded Signup API Documentation

## Overview

The Meta Embedded Signup API enables seamless integration of WhatsApp Business Accounts with the AI Agency Platform's centralized webhook service. This allows clients to "acquire EA WhatsApp Services" by connecting their WhatsApp Business accounts to our shared infrastructure.

## Architecture

- **Centralized Webhook Service**: All WhatsApp messages route through a single webhook endpoint
- **Client Registry**: Redis-based storage for EA client mappings with MCP communication
- **Business Model**: Multiple clients connect their WABA to our shared webhook infrastructure
- **Security**: Encrypted business token storage and Meta-compliant webhook verification

## Authentication

All API endpoints require appropriate authentication:
- **Client Authentication**: Standard EA client auth tokens
- **Meta Webhooks**: Meta signature verification using app secret
- **Business Tokens**: Encrypted storage with AES-256

## Environment Variables

```bash
# Meta App Configuration
META_APP_ID=your-meta-app-id
META_APP_SECRET=your-meta-app-secret
META_API_VERSION=v20.0
META_WEBHOOK_VERIFY_TOKEN=your-verify-token
META_BUSINESS_TOKEN_TTL=5184000  # 60 days
META_TOKEN_ENCRYPTION_KEY=your-32-char-encryption-key

# WhatsApp Business API
WHATSAPP_BUSINESS_TOKEN=your-fallback-token
WHATSAPP_BUSINESS_PHONE_ID=your-phone-number-id
WHATSAPP_WEBHOOK_SECRET=your-webhook-secret
```

## API Endpoints

### 1. Token Exchange

Exchange Meta's 30-second authorization code for a permanent business token.

```http
POST /embedded-signup/token-exchange
Content-Type: application/json
```

**Request Body:**
```json
{
  "authorization_code": "string (required) - Meta authorization code",
  "client_id": "string (required) - EA client identifier",
  "customer_id": "string (required) - Customer identifier",
  "mcp_endpoint": "string (required) - MCP endpoint URL",
  "auth_token": "string (required) - EA authentication token"
}
```

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Authorization code exchanged successfully",
  "integration_data": {
    "waba_id": "string - WhatsApp Business Account ID",
    "business_phone_number_id": "string - Business phone number ID",
    "display_phone_number": "string - Display phone number",
    "waba_name": "string - WABA name",
    "business_name": "string - Business name",
    "token_expires": "string - ISO timestamp"
  }
}
```

**Error Responses:**
```json
// 400 Bad Request
{
  "error": "Token exchange failed",
  "message": "Invalid authorization code"
}

// 400 Bad Request - Missing fields
{
  "error": "Missing required field: authorization_code"
}

// 400 Bad Request - No business accounts
{
  "error": "No business accounts found",
  "message": "The connected account has no accessible business accounts"
}
```

### 2. Complete Client Registration

Complete the Meta Embedded Signup process by registering the client.

```http
POST /embedded-signup/register-client
Content-Type: application/json
```

**Request Body:**
```json
{
  "client_id": "string (required) - EA client identifier",
  "phone_number": "string (required) - Client phone number with country code"
}
```

**Response (201 Created):**
```json
{
  "status": "success",
  "message": "Meta WhatsApp integration completed successfully",
  "client_id": "string",
  "integration_details": {
    "waba_id": "string",
    "business_phone_number_id": "string",
    "display_phone_number": "string",
    "webhook_subscribed": true,
    "registration_completed": true
  }
}
```

**Error Responses:**
```json
// 404 Not Found
{
  "error": "Integration data not found",
  "message": "Token exchange must be completed first, or session has expired"
}

// 500 Internal Server Error
{
  "error": "Failed to register EA client"
}
```

### 3. Client Status

Get Meta integration status for a client.

```http
GET /embedded-signup/client-status/{client_id}
```

**Response (200 OK):**
```json
{
  "status": "success",
  "meta_integration_status": {
    "client_id": "string",
    "embedded_signup_completed": true,
    "has_meta_integration": true,
    "waba_id": "string",
    "business_phone_number_id": "string",
    "business_id": "string",
    "meta_token_expires": "string - ISO timestamp",
    "token_valid": true,
    "active": true,
    "last_seen": "string - ISO timestamp"
  },
  "pending_integration": null
}
```

**With Pending Integration:**
```json
{
  "status": "success",
  "meta_integration_status": {
    "embedded_signup_completed": false,
    // ... other fields
  },
  "pending_integration": {
    "token_exchange_completed": true,
    "awaiting_registration": true,
    "waba_id": "string",
    "display_phone_number": "string",
    "expires_at": "string - ISO timestamp"
  }
}
```

### 4. Revoke Integration

Revoke Meta WhatsApp integration for a client.

```http
DELETE /embedded-signup/revoke-client/{client_id}
```

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Meta WhatsApp integration revoked successfully",
  "client_id": "string"
}
```

**Error Responses:**
```json
// 404 Not Found
{
  "error": "Client not found"
}

// 400 Bad Request
{
  "error": "No Meta integration to revoke"
}
```

### 5. Embedded Signup UI

Serve the Meta Embedded Signup user interface.

```http
GET /embedded-signup/
GET /embedded-signup/{path}
```

Returns HTML interface for completing the Meta Embedded Signup flow.

### 6. WhatsApp Webhook (Enhanced)

Enhanced webhook endpoint supporting both Meta and legacy integrations.

```http
POST /webhook/whatsapp
Content-Type: application/json
X-Hub-Signature-256: sha256={signature}
```

**Enhanced Message Routing:**
1. **Business Phone Number ID Lookup** (Meta integration)
2. **Traditional Phone Number Lookup** (Legacy fallback)
3. **Meta API Message Sending** (for integrated clients)
4. **Legacy API Fallback** (for non-integrated clients)

### 7. Meta Deauthorization Webhook

Handle Meta app deauthorization events.

```http
POST /webhook/meta-deauth
Content-Type: application/json
X-Hub-Signature-256: sha256={signature}
```

## Integration Flow

### Complete Integration Process

1. **Frontend Initiation**
   ```javascript
   // Redirect to Meta Embedded Signup
   const signupUrl = `https://www.facebook.com/dialog/oauth?client_id=${META_APP_ID}&redirect_uri=${encodeURIComponent(redirectUri)}&config_id=${configId}&response_type=code`;
   window.location.href = signupUrl;
   ```

2. **Authorization Code Exchange**
   ```bash
   curl -X POST https://your-webhook-service.com/embedded-signup/token-exchange \
     -H "Content-Type: application/json" \
     -d '{
       "authorization_code": "received_from_meta",
       "client_id": "your_client_id",
       "customer_id": "your_customer_id",
       "mcp_endpoint": "https://your-ea.com/mcp",
       "auth_token": "your_auth_token"
     }'
   ```

3. **Client Registration**
   ```bash
   curl -X POST https://your-webhook-service.com/embedded-signup/register-client \
     -H "Content-Type: application/json" \
     -d '{
       "client_id": "your_client_id",
       "phone_number": "+1234567890"
     }'
   ```

4. **Status Verification**
   ```bash
   curl -X GET https://your-webhook-service.com/embedded-signup/client-status/your_client_id
   ```

## Enhanced Client Data Structure

```python
@dataclass
class EAClient:
    # Original fields
    client_id: str
    customer_id: str
    phone_number: str
    mcp_endpoint: str
    auth_token: str
    active: bool = True
    last_seen: Optional[datetime] = None

    # Meta Embedded Signup fields
    waba_id: Optional[str] = None
    business_phone_number_id: Optional[str] = None
    business_id: Optional[str] = None
    meta_business_token: Optional[str] = None  # Encrypted
    meta_token_expires: Optional[datetime] = None
    embedded_signup_completed: bool = False
    meta_app_id: Optional[str] = None
    meta_webhook_token: Optional[str] = None
```

## Message Routing Logic

```python
async def handle_incoming_message(message, value):
    # 1. Extract Meta webhook metadata
    business_phone_number_id = value.get('metadata', {}).get('phone_number_id')

    # 2. Try Meta integration lookup first
    if business_phone_number_id:
        client = await ea_registry.get_client_by_business_phone_id(business_phone_number_id)

    # 3. Fallback to traditional lookup
    if not client:
        client = await ea_registry.get_client_by_phone(from_number)

    # 4. Route message with Meta context
    if client:
        response = await route_to_ea_client(client, content, message_id, message_type)

        # 5. Send via appropriate API
        if client.embedded_signup_completed and client.meta_business_token:
            await send_via_meta_api(client, from_number, response)
        else:
            await send_whatsapp_response(from_number, response)
```

## Security Implementation

### Token Encryption
```python
def _encrypt_token(self, token: str) -> str:
    """AES-256 encryption for Meta business tokens"""
    key = os.getenv('META_TOKEN_ENCRYPTION_KEY')[:32]
    cipher = AES.new(key, AES.MODE_CBC)
    encrypted = cipher.encrypt(pad(token.encode(), AES.block_size))
    return base64.b64encode(cipher.iv + encrypted).decode()
```

### Webhook Signature Validation
```python
def validate_webhook_signature(self, payload: bytes, signature: str) -> bool:
    """Meta webhook signature validation"""
    expected_signature = hmac.new(
        self.app_secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature.replace('sha256=', ''))
```

## Rate Limiting

- **Token Exchange**: 10 requests/minute per IP
- **Client Registration**: 5 requests/minute per IP
- **Status Checks**: 10 requests/minute per IP
- **Revocation**: 5 requests/minute per IP

## Error Handling

### Meta API Errors
- **Invalid Authorization Code**: 30-second TTL exceeded
- **Insufficient Permissions**: Missing required scopes
- **Business Account Issues**: No accessible WABA or phone numbers
- **Token Expiry**: Refresh required after 60 days

### System Errors
- **Redis Connection**: Graceful degradation to local cache
- **MCP Communication**: Timeout handling and retries
- **Webhook Failures**: Comprehensive logging and monitoring

## Monitoring & Health Checks

Enhanced health check endpoint includes Meta integration status:

```http
GET /health
```

```json
{
  "status": "healthy",
  "checks": {
    "meta_integration_enabled": true,
    "meta_clients": 15,
    "legacy_clients": 5,
    "registered_clients": 20,
    // ... other health checks
  }
}
```

## Testing

Run the comprehensive test suite:

```bash
# Run all Meta integration tests
pytest tests/test_meta_embedded_signup.py -v

# Run specific test categories
pytest tests/test_meta_embedded_signup.py::TestMetaTokenExchange -v
pytest tests/test_meta_embedded_signup.py::TestMetaClientRegistration -v
pytest tests/test_meta_embedded_signup.py::TestMetaMessageRouting -v
```

## Deployment Considerations

### Production Requirements
1. **HTTPS**: Required for Meta webhook callbacks
2. **Domain Verification**: Meta app domain validation
3. **Rate Limiting**: Production-grade Redis for rate limiting
4. **Monitoring**: Comprehensive logging and alerting
5. **Backup**: Regular backup of client registry data

### Scaling
- **Horizontal Scaling**: Stateless design supports load balancing
- **Redis Clustering**: For high-availability client registry
- **Message Queuing**: For high-volume message processing
- **CDN Integration**: For Embedded Signup UI assets

## Troubleshooting

### Common Issues

1. **Authorization Code Expired**
   - Ensure token exchange completes within 30 seconds
   - Check network latency and processing time

2. **No Business Accounts Found**
   - Verify user has admin access to Facebook Business Manager
   - Check WhatsApp Business Account setup

3. **Webhook Subscription Failed**
   - Verify webhook URL is accessible and returns 200
   - Check Meta app webhook configuration

4. **Token Decryption Failed**
   - Verify META_TOKEN_ENCRYPTION_KEY consistency
   - Check token storage integrity

### Debug Mode

Enable debug logging:
```bash
export LOG_LEVEL=debug
export FLASK_DEBUG=true
```

### Meta Graph API Explorer

Use Meta's Graph API Explorer for testing:
- Test token permissions and scopes
- Verify business account access
- Debug webhook subscription issues

## Support

For integration support:
- Check Meta Business API documentation
- Review webhook service logs
- Use Meta Graph API Explorer for debugging
- Contact support with client_id and error details