# Meta Developer Console Setup Guide
## WhatsApp Business Platform Integration for Tech Providers

This guide provides step-by-step instructions for configuring your Meta Developer Console and WhatsApp Business Platform for production deployment with Embedded Signup capabilities.

## Prerequisites

- [ ] Meta Business Account with Admin privileges
- [ ] WhatsApp Business Account (verified)
- [ ] DigitalOcean App Platform deployment (webhook service)
- [ ] Domain with SSL certificate (webhook.aiagency.platform)
- [ ] Tech Provider approval status (recommended)

## Phase 1: Meta App Configuration

### 1.1 Create Meta App for Business

1. **Access Meta for Developers**
   - Visit: https://developers.facebook.com/
   - Log in with your Meta Business Account
   - Click "Create App"

2. **Select App Type**
   - Choose: **"Business"**
   - App Name: `AI Agency Platform WhatsApp Integration`
   - App Contact Email: `support@aiagency.platform`
   - Business Account: Select your verified business account

3. **Add WhatsApp Product**
   - In App Dashboard, click "Add Product"
   - Select **"WhatsApp Business Platform"**
   - Click "Set up" to configure

### 1.2 Configure App Basic Settings

1. **App Domains** (Critical for Embedded Signup)
   ```
   Production Domain: webhook.aiagency.platform
   Staging Domain: staging-webhook.aiagency.platform
   Development: localhost (for testing)
   ```

2. **App URLs**
   ```
   Privacy Policy URL: https://aiagency.platform/privacy
   Terms of Service URL: https://aiagency.platform/terms
   User Data Deletion URL: https://webhook.aiagency.platform/data-deletion
   ```

3. **App Review Information**
   ```
   Category: Business and Productivity
   Subcategory: Customer Service
   Description: Enterprise AI assistant platform providing WhatsApp Business integration
   ```

## Phase 2: WhatsApp Business Platform Setup

### 2.1 Configure WhatsApp Business API

1. **Access WhatsApp Configuration**
   - In App Dashboard → WhatsApp → Configuration
   - Note your **App ID** and **App Secret** (store securely)

2. **Add Phone Numbers**
   ```
   Business Phone Number: +1-XXX-XXX-XXXX (your verified number)
   Display Name: "AI Agency Platform"
   Category: "Business Services"
   ```

3. **Generate Access Token**
   - Go to WhatsApp → API Setup
   - Create System User with **admin** privileges
   - Generate permanent access token with these permissions:
     ```
     whatsapp_business_messaging
     whatsapp_business_management
     business_management
     ```

### 2.2 Configure Webhook Endpoints

1. **Webhook Configuration**
   ```
   Webhook URL: https://webhook.aiagency.platform/webhook/whatsapp
   Verify Token: [Use value from WHATSAPP_VERIFY_TOKEN env var]
   ```

2. **Subscribe to Webhook Events**
   - ✅ `messages` - Incoming messages from customers
   - ✅ `message_deliveries` - Message delivery receipts
   - ✅ `message_reads` - Message read receipts
   - ✅ `messaging_postbacks` - Interactive message responses

3. **Test Webhook Connection**
   ```bash
   # Meta will send verification request:
   GET https://webhook.aiagency.platform/webhook/whatsapp?hub.mode=subscribe&hub.challenge=RANDOM_STRING&hub.verify_token=YOUR_VERIFY_TOKEN

   # Your service should respond with the challenge value
   ```

## Phase 3: Embedded Signup Configuration

### 3.1 Configure Embedded Signup

1. **Access Configuration**
   - WhatsApp → Configuration → Embedded signup

2. **Create Configuration**
   ```
   Configuration Name: "AI Agency Platform Client Onboarding"
   Callback URL: https://webhook.aiagency.platform/embedded-signup/callback
   Verify Token: [Use META_WEBHOOK_VERIFY_TOKEN value]
   ```

3. **Set Permissions**
   ```
   Required Permissions:
   - whatsapp_business_messaging (Send/receive messages)
   - whatsapp_business_management (Manage phone numbers)
   - business_management (Access business information)
   ```

4. **Configure Client Experience**
   ```
   Pre-filled Business Info: Enabled
   Skip Business Verification: Disabled (for production)
   Enable Phone Number Selection: Enabled
   Default Country Code: +1 (or your market)
   ```

### 3.2 Note Configuration ID

- **Important**: Save the Configuration ID from the embedded signup setup
- This goes in your `EMBEDDED_SIGNUP_CONFIG_ID` environment variable

## Phase 4: Production Environment Variables

### 4.1 Required Meta Configuration

Add these to your DigitalOcean App Platform secrets:

```bash
# Meta App Configuration
META_APP_ID=1234567890123456
META_APP_SECRET=abcdef1234567890abcdef1234567890

# WhatsApp Business API
WHATSAPP_BUSINESS_TOKEN=EAAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
WHATSAPP_BUSINESS_PHONE_ID=1234567890123456
WHATSAPP_VERIFY_TOKEN=ai-agency-platform-verify-token-secure-12345

# Embedded Signup
EMBEDDED_SIGNUP_CONFIG_ID=9876543210987654
META_WEBHOOK_VERIFY_TOKEN=meta-embedded-signup-verify-secure-67890

# Security
WHATSAPP_WEBHOOK_SECRET=your-webhook-signature-secret-32-chars
ENCRYPTION_KEY=your-32-character-encryption-key!!
```

### 4.2 Validate Configuration

Test your configuration with these endpoints:

```bash
# 1. Health Check
curl https://webhook.aiagency.platform/health

# 2. Webhook Verification
curl "https://webhook.aiagency.platform/webhook/whatsapp?hub.mode=subscribe&hub.challenge=test123&hub.verify_token=YOUR_VERIFY_TOKEN"

# 3. Embedded Signup Page
curl https://webhook.aiagency.platform/embedded-signup
```

## Phase 5: Testing and Validation

### 5.1 Test Message Flow

1. **Send Test Message**
   ```bash
   curl -X POST \
     https://graph.facebook.com/v20.0/YOUR_PHONE_ID/messages \
     -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "messaging_product": "whatsapp",
       "to": "YOUR_TEST_NUMBER",
       "type": "text",
       "text": {"body": "Hello from AI Agency Platform!"}
     }'
   ```

2. **Verify Webhook Reception**
   - Check your application logs for incoming webhook
   - Verify message routing to appropriate EA instance

### 5.2 Test Embedded Signup

1. **Access Signup Page**
   - Visit: `https://webhook.aiagency.platform/embedded-signup`
   - Verify Facebook SDK loads properly

2. **Complete Signup Flow**
   - Test with a real business account
   - Verify token exchange completes within 30 seconds
   - Confirm client registration in your system

## Phase 6: Production Launch Preparation

### 6.1 Security Checklist

- [ ] All webhook signatures validated
- [ ] IP allowlisting configured for Meta servers
- [ ] SSL certificate valid and HTTPS enforced
- [ ] Rate limiting configured appropriately
- [ ] Error handling covers all Meta API error codes

### 6.2 Monitoring Setup

- [ ] Health checks monitoring webhook endpoints
- [ ] Performance metrics for <2s response times
- [ ] Business metrics for signup conversions
- [ ] Error tracking for failed API calls
- [ ] Uptime monitoring for 99.9% SLA

### 6.3 Business Model Validation

- [ ] Client onboarding flow tested end-to-end
- [ ] EA provisioning triggers after successful signup
- [ ] Customer isolation verified
- [ ] Billing integration functional

## Phase 7: Go Live Process

### 7.1 Pre-Launch Validation

1. **Load Testing**
   ```bash
   # Test webhook endpoint under load
   ab -n 1000 -c 10 https://webhook.aiagency.platform/health

   # Test embedded signup page performance
   ab -n 500 -c 5 https://webhook.aiagency.platform/embedded-signup
   ```

2. **Integration Testing**
   - Complete signup flow with test business account
   - Send/receive messages through full pipeline
   - Verify EA conversation handling

### 7.2 Launch Sequence

1. **Deploy to Production**
   ```bash
   cd ai-agency-platform
   ./scripts/deploy_production_webhook.sh
   ```

2. **Update DNS Records** (if using custom domain)
   ```
   webhook.aiagency.platform → DigitalOcean App Platform
   whatsapp.aiagency.platform → DigitalOcean App Platform (alias)
   ```

3. **Final Meta Configuration**
   - Update webhook URLs in Meta Developer Console
   - Submit for App Review (if required)
   - Enable production mode

### 7.3 Post-Launch Monitoring

- **First 24 hours**: Monitor continuously
- **Performance SLAs**: <2s response time, >99.9% uptime
- **Business metrics**: Track signup conversion rates
- **Customer support**: Monitor for onboarding issues

## Troubleshooting Common Issues

### Issue 1: Webhook Verification Failed
```
Solution:
1. Check WHATSAPP_VERIFY_TOKEN matches Meta console
2. Verify HTTPS is working properly
3. Check webhook endpoint responds to GET requests
4. Validate URL encoding in Meta console
```

### Issue 2: Embedded Signup Token Exchange Timeout
```
Solution:
1. Ensure token exchange completes within 30 seconds
2. Check Meta API rate limits not exceeded
3. Verify app secret configuration
4. Test with Meta's Graph API Explorer
```

### Issue 3: Message Delivery Failed
```
Solution:
1. Verify phone number is registered and verified
2. Check business account has messaging permissions
3. Validate message format against WhatsApp requirements
4. Monitor rate limiting and quota usage
```

### Issue 4: Customer Isolation Problems
```
Solution:
1. Check Redis client registry is working
2. Verify customer ID extraction from messages
3. Test EA routing logic with multiple customers
4. Validate token encryption/decryption
```

## Support and Resources

- **Meta for Developers**: https://developers.facebook.com/docs/whatsapp
- **WhatsApp Business Platform**: https://business.whatsapp.com/
- **DigitalOcean Support**: https://www.digitalocean.com/support/
- **Project Documentation**: `/docs/architecture/`

## Compliance Notes

### Tech Provider Requirements
- Handle customer data according to Meta's data policy
- Implement proper business verification flows
- Maintain 99.9% uptime for business customers
- Provide customer support during business hours
- Follow Meta's brand guidelines for WhatsApp integration

### Data Privacy
- All customer business tokens encrypted at rest
- Message content not stored permanently
- Customer isolation verified and audited
- GDPR/CCPA compliance for data handling
- Regular security audits and penetration testing

---

**Ready for Production?** ✅
Once you've completed all phases and validations, your Meta-compliant WhatsApp webhook service will be ready to support the business model where clients "acquire EA WhatsApp Services" through your centralized infrastructure.