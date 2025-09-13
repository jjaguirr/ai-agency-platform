# WhatsApp Webhook Credentials Configuration

## 🎯 Overview
This guide explains how to configure WhatsApp Business API credentials for the deployed webhook, with proper separation between personal and commercial use.

## 🚀 Current Deployment Status

**Webhook URL**: `https://ai-agency-platform-webhook-z5olo.ondigitalocean.app`
**App ID**: `be817ff1-9531-4d54-b284-e19ee13de890`
**Status**: ✅ Deployed and Running (Personal Configuration)

## 🔑 Environment Variables Configuration

### Personal Configuration (Current)
```bash
# Personal EA Configuration
CUSTOMER_TYPE=personal
CUSTOMER_ID=jose-personal

# WhatsApp Business API - Personal
WHATSAPP_VERIFY_TOKEN=ai_agency_platform_verify_personal
WHATSAPP_ACCESS_TOKEN=PLACEHOLDER_NEED_REAL_TOKEN
WHATSAPP_PHONE_NUMBER_ID=782822591574136
WHATSAPP_WEBHOOK_SECRET=PLACEHOLDER_NEED_WEBHOOK_SECRET

# Production Settings
ENVIRONMENT=production
FLASK_ENV=production
PORT=8000
```

### Commercial Configuration (Future)
```bash
# Commercial Client Configuration Template
CUSTOMER_TYPE=commercial
CUSTOMER_ID=client_{customer_id}

# WhatsApp Business API - Commercial (Separate tokens per client)
WHATSAPP_VERIFY_TOKEN={customer_specific_verify_token}
WHATSAPP_ACCESS_TOKEN={customer_specific_access_token}
WHATSAPP_PHONE_NUMBER_ID={customer_specific_phone_id}
WHATSAPP_WEBHOOK_SECRET={customer_specific_webhook_secret}
```

## 🔧 Required Actions

### 1. Get WhatsApp Business API Credentials
You need to obtain these from your Meta Business Account:

1. **Access Token** (`WHATSAPP_ACCESS_TOKEN`)
   - Go to Meta Business Manager → WhatsApp → API Setup
   - Generate a permanent access token (not the temporary one)
   - Replace `PLACEHOLDER_NEED_REAL_TOKEN`

2. **Webhook Verification Token** (Already set: `ai_agency_platform_verify_personal`)
   - This is used when setting up the webhook in Meta Business Manager
   - Keep this secure and unique per environment

3. **Webhook Secret** (`WHATSAPP_WEBHOOK_SECRET`)
   - Generate a secure random string (32+ characters)
   - Used for HMAC signature verification
   - Replace `PLACEHOLDER_NEED_WEBHOOK_SECRET`

4. **Phone Number ID** (Already set: `782822591574136`)
   - This is your WhatsApp Business phone number ID
   - Verify this matches your phone number in Meta Business Manager

### 2. Update DigitalOcean Environment Variables

Replace the placeholder values using DigitalOcean CLI or Console:

```bash
# Using DigitalOcean CLI (if you have doctl)
doctl apps update be817ff1-9531-4d54-b284-e19ee13de890 \
  --env "WHATSAPP_ACCESS_TOKEN=your_real_access_token" \
  --env "WHATSAPP_WEBHOOK_SECRET=your_secure_webhook_secret"
```

Or use the DigitalOcean Console:
1. Go to Apps → ai-agency-platform-webhook → Settings → Environment Variables
2. Edit the placeholder values
3. Deploy the updated configuration

### 3. Configure Meta Business API Webhook

In your Meta Business Manager:

1. **Navigate to**: WhatsApp → Configuration → Webhooks
2. **Callback URL**: `https://ai-agency-platform-webhook-z5olo.ondigitalocean.app/webhook/whatsapp`
3. **Verify Token**: `ai_agency_platform_verify_personal`
4. **Subscribe to**: messages, message_deliveries, message_reads, message_reactions

## 🏗️ Architecture: Personal vs Commercial Separation

### Personal EA Webhook (Current)
- **Purpose**: Jose's personal WhatsApp EA interactions
- **Customer ID**: `jose-personal` 
- **Deployment**: Single instance on DigitalOcean
- **Security**: Personal-grade credentials and verification

### Commercial Client Webhooks (Future)
- **Purpose**: Client WhatsApp integrations
- **Customer ID**: `client_{customer_id}` pattern
- **Deployment**: Per-client isolated deployments or multi-tenant routing
- **Security**: Client-specific credentials, enhanced isolation

### Credential Isolation Strategy
```
Personal EA:
├── CUSTOMER_TYPE=personal
├── Single WhatsApp Business Account
├── Direct credential management
└── Simplified verification tokens

Commercial Clients:
├── CUSTOMER_TYPE=commercial  
├── Per-client WhatsApp Business Accounts
├── Customer-specific credential vaults
├── Enhanced security and audit logging
└── Customer-specific verification tokens
```

## 🧪 Testing Instructions

Once credentials are configured:

### 1. Health Check Test
```bash
curl https://ai-agency-platform-webhook-z5olo.ondigitalocean.app/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "whatsapp-webhook-simple",
  "environment": "production",
  "checks": {
    "access_token": true,  // Should be true after credential setup
    "verify_token": true,
    "phone_number_id": true
  }
}
```

### 2. Webhook Verification Test
Meta Business API will test the webhook:
```
GET /webhook/whatsapp?hub.mode=subscribe&hub.challenge=CHALLENGE&hub.verify_token=ai_agency_platform_verify_personal
```

Should return the challenge value if verification succeeds.

### 3. Message Test
Send a test message from WhatsApp to your business number. Check logs:
```bash
# Via DigitalOcean Console → Apps → Runtime Logs
# Should see: "📨 Message from +1234567890: [message content]"
```

## 🔒 Security Best Practices

1. **Never commit credentials** to git repositories
2. **Use unique verify tokens** for each environment/customer  
3. **Rotate access tokens** periodically (Meta Business Manager)
4. **Enable webhook signature validation** in production
5. **Monitor credential usage** via health check endpoints
6. **Separate personal and commercial** credential namespaces

## 📋 Next Steps

1. **Immediate**: Replace placeholder credentials with real values
2. **Short-term**: Test webhook with real WhatsApp messages
3. **Long-term**: Design multi-tenant credential management for commercial clients
4. **Future**: Implement customer-specific credential vaults and rotation

---

**Status**: Webhook infrastructure deployed ✅ | Credentials configuration needed ⏳