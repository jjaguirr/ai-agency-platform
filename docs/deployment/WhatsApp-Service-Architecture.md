# WhatsApp Service Architecture & Deployment Guide

## Overview

The AI Agency Platform WhatsApp service uses a **centralized webhook architecture** that enables multiple client EA deployments to share a single WhatsApp Business API integration.

### Architecture Benefits
- **Scalability**: Single webhook service handles unlimited client EAs
- **Cost Efficiency**: Shared WhatsApp infrastructure reduces per-client costs
- **Security**: Client EAs run in private environments with data isolation
- **Compliance**: Client data stays within their deployment boundaries
- **Management**: Centralized WhatsApp configuration and monitoring

## Architecture Components

```
┌─────────────────────┐    ┌──────────────────────┐    ┌─────────────────────┐
│   WhatsApp Cloud    │───▶│  Webhook Service     │───▶│   Client EA #1      │
│   API (Meta)        │    │  (DigitalOcean)      │    │   (Private Cloud)   │
└─────────────────────┘    │                      │    └─────────────────────┘
                           │  - Message Routing   │
                           │  - Client Registry   │    ┌─────────────────────┐
                           │  - Voice Processing  │───▶│   Client EA #2      │
                           │  - Media Handling    │    │   (On-Premises)     │
                           └──────────────────────┘    └─────────────────────┘
                                     │
                                     ▼                 ┌─────────────────────┐
                           ┌──────────────────────┐───▶│   Client EA #3      │
                           │     Redis Cache      │    │   (Kubernetes)      │
                           │  (Client Registry)   │    └─────────────────────┘
                           └──────────────────────┘
```

## Service Components

### 1. Centralized Webhook Service (DigitalOcean)
**Location**: `https://your-webhook-service.ondigitalocean.app`
**Purpose**: Single endpoint for all WhatsApp Business API webhooks

**Responsibilities**:
- Receive WhatsApp webhooks from Meta's servers
- Authenticate and route messages to correct client EAs
- Handle media downloads and voice processing
- Maintain client EA registry in Redis
- Provide WhatsApp Business API proxy for sending messages

**Key Features**:
- IP allowlisting for WhatsApp servers
- Webhook signature validation
- Rate limiting and security headers
- Health monitoring and logging
- Multi-client message routing

### 2. EA WhatsApp Bridge (Client Side)
**Location**: Client's private infrastructure
**Purpose**: Connect client EAs to centralized webhook service

**Responsibilities**:
- Register with webhook service using client credentials
- Run MCP server to receive messages from webhook service
- Process messages with local EA instance
- Send responses back through webhook service
- Maintain heartbeat connection for health monitoring

**Key Features**:
- Secure MCP communication protocol
- Automatic registration and heartbeat
- Local EA integration
- Error handling and fallback responses
- Health check endpoints

## Deployment Options

### Business Tier - Client Premises
```bash
# Docker deployment on client servers
docker run -d \
  --name ea-whatsapp-bridge \
  -p 8001:8001 \
  -e CUSTOMER_ID="client-business-id" \
  -e WHATSAPP_PHONE_NUMBER="client-phone" \
  -e WHATSAPP_WEBHOOK_SERVICE_URL="https://your-webhook.app" \
  -e EA_AUTH_TOKEN="secure-client-token" \
  ai-agency/ea-whatsapp-bridge:latest
```

### Professional Tier - Private Cloud
```yaml
# Kubernetes deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ea-whatsapp-bridge
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ea-whatsapp-bridge
  template:
    metadata:
      labels:
        app: ea-whatsapp-bridge
    spec:
      containers:
      - name: ea-bridge
        image: ai-agency/ea-whatsapp-bridge:latest
        ports:
        - containerPort: 8001
        env:
        - name: CUSTOMER_ID
          value: "client-professional-id"
        - name: WHATSAPP_WEBHOOK_SERVICE_URL
          value: "https://your-webhook.app"
        - name: EA_AUTH_TOKEN
          valueFrom:
            secretKeyRef:
              name: ea-auth-secret
              key: token
```

### Enterprise Tier - Dedicated Infrastructure
```bash
# High-availability deployment with load balancer
docker-compose -f docker-compose.enterprise.yml up -d
```

## Client Setup Process

### Step 1: Obtain WhatsApp Credentials
Client needs to provide:
- WhatsApp phone number for their business
- Unique customer/client identifier
- Preferred deployment method (premises/cloud/kubernetes)

### Step 2: Generate Client Authentication
```bash
# Generate secure authentication token
CLIENT_TOKEN=$(openssl rand -hex 32)
echo "Client Auth Token: $CLIENT_TOKEN"
```

### Step 3: Configure Environment
Create `.env` file for client EA deployment:
```bash
# Client EA Configuration
CUSTOMER_ID=your-unique-client-id
WHATSAPP_PHONE_NUMBER=your-business-phone
WHATSAPP_WEBHOOK_SERVICE_URL=https://your-webhook-service.ondigitalocean.app
EA_AUTH_TOKEN=your-secure-client-token
MCP_PORT=8001

# EA Dependencies
OPENAI_API_KEY=client-openai-key
POSTGRES_URL=client-database-url
REDIS_URL=client-redis-url
```

### Step 4: Deploy EA Bridge
```bash
# Clone EA bridge code
git clone https://github.com/your-org/ai-agency-platform
cd ai-agency-platform

# Start EA with WhatsApp bridge
./scripts/deploy-client-ea.sh
```

### Step 5: Register with Webhook Service
The EA bridge automatically registers when it starts:
```bash
# Automatic registration on startup
2024-01-15 10:30:00 - INFO - 🌉 Starting WhatsApp bridge for client-id
2024-01-15 10:30:01 - INFO - ✅ Successfully registered with webhook service
2024-01-15 10:30:02 - INFO - 🔗 MCP server running on port 8001
```

## Security & Compliance

### Data Isolation
- **Client Data**: Never leaves client's deployment environment
- **Message Routing**: Only metadata passes through webhook service
- **Authentication**: Each client has unique auth tokens
- **Network**: Private communication channels between services

### Security Features
- **End-to-end encryption** for MCP communication
- **Token-based authentication** for client registration
- **IP allowlisting** for webhook endpoints
- **Rate limiting** and DDoS protection
- **Audit logging** for all message routing

### Compliance Support
- **GDPR**: Data processing within client boundaries
- **HIPAA**: Healthcare clients can deploy on-premises
- **SOC2**: Centralized security monitoring and controls
- **Custom**: Client-specific compliance requirements

## Monitoring & Maintenance

### Health Monitoring
```bash
# Check webhook service health
curl https://your-webhook-service.app/health

# Check client EA bridge health
curl http://localhost:8001/health

# List registered clients
curl https://your-webhook-service.app/ea/clients
```

### Log Monitoring
```bash
# Webhook service logs
docker logs ai-agency-whatsapp-webhook -f

# Client EA bridge logs
docker logs ea-whatsapp-bridge -f

# WhatsApp message routing logs
tail -f logs/webhook/whatsapp-routing.log
```

### Performance Metrics
- **Message throughput**: Messages per second
- **Response latency**: EA processing time
- **Client availability**: Bridge uptime monitoring
- **Error rates**: Failed message delivery tracking

## Troubleshooting

### Common Issues

**1. EA Bridge Registration Failed**
```bash
# Check network connectivity
curl -v https://your-webhook-service.app/health

# Verify authentication token
echo $EA_AUTH_TOKEN

# Check client configuration
cat .env | grep -E "(CUSTOMER_ID|WHATSAPP_PHONE_NUMBER|EA_AUTH_TOKEN)"
```

**2. Messages Not Routing to EA**
```bash
# Check client registration status
curl https://your-webhook-service.app/ea/clients

# Test MCP endpoint accessibility
curl http://localhost:8001/health

# Verify phone number mapping
curl https://your-webhook-service.app/test
```

**3. WhatsApp Webhook Failures**
```bash
# Check webhook service logs
docker logs ai-agency-whatsapp-webhook --tail 100

# Verify WhatsApp credentials
curl -H "Authorization: Bearer $WHATSAPP_TOKEN" \
  https://graph.facebook.com/v18.0/me/phone_numbers

# Test webhook endpoint
python scripts/test-whatsapp-webhook.py --url https://your-webhook-service.app
```

### Support Resources
- **Documentation**: `/docs/deployment/`
- **Sample Configs**: `/examples/client-deployments/`
- **Test Scripts**: `/scripts/test-whatsapp-*`
- **Health Checks**: Built-in endpoints for monitoring
- **Community**: GitHub Issues and Discussions

## Cost Optimization

### Shared Infrastructure Benefits
- **Single WhatsApp Business Account**: All clients share one Meta integration
- **Reduced API Costs**: Bulk pricing and shared rate limits
- **Centralized Management**: Lower operational overhead
- **Economy of Scale**: More clients = lower per-client costs

### Client Tier Pricing
- **Starter**: Shared infrastructure with basic isolation
- **Professional**: Private cloud deployment with dedicated resources
- **Business**: On-premises deployment with full control
- **Enterprise**: Dedicated infrastructure with SLA guarantees

This architecture enables the business model where clients "acquire EA WhatsApp Services" by connecting their private EA deployments to your centralized, managed WhatsApp infrastructure.