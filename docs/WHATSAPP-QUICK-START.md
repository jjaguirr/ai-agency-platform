# WhatsApp Integration Quick Start Guide

## Architecture Overview

The AI Agency Platform uses a **centralized WhatsApp service** that enables multiple client EA deployments to share a single WhatsApp Business API integration.

```
WhatsApp Cloud API ──▶ Webhook Service (DigitalOcean) ──▶ Client EA Deployments
                      (Shared Infrastructure)              (Private Environments)
```

## Quick Setup

### 1. Start Local Development Environment

```bash
# Start the full development stack
./scripts/dev-whatsapp-start.sh

# This starts:
# - WhatsApp Webhook Service (port 8000)
# - EA Client Simulator (port 8001)
# - Core infrastructure (PostgreSQL, Redis, Qdrant)
```

### 2. Test the Integration

```bash
# Run comprehensive tests
python scripts/test-whatsapp-webhook.py

# Test specific components
python scripts/test-whatsapp-webhook.py --test health
python scripts/test-whatsapp-webhook.py --test verify
python scripts/test-whatsapp-webhook.py --test message
```

### 3. Monitor Services

```bash
# Check service status
docker compose ps

# View logs
docker compose logs -f whatsapp-webhook
docker compose logs -f ea-client-simulator

# Health checks
curl http://localhost:8000/health      # Webhook service
curl http://localhost:8001/health      # EA client
curl http://localhost:8000/ea/clients  # List registered clients
```

## Production Deployment

### Centralized Webhook Service (Your Infrastructure)

Deploy to DigitalOcean App Platform:

```yaml
# .do/app.yaml
name: whatsapp-webhook-service
services:
- name: webhook
  source_dir: /
  dockerfile_path: src/webhook/Dockerfile.webhook-service
  instance_count: 2
  instance_size_slug: basic-xxs
  http_port: 8000
  env:
  - key: WHATSAPP_BUSINESS_TOKEN
    value: YOUR_WHATSAPP_TOKEN
  - key: WHATSAPP_BUSINESS_PHONE_ID
    value: YOUR_PHONE_ID
  - key: WHATSAPP_VERIFY_TOKEN
    value: YOUR_VERIFY_TOKEN
  - key: REDIS_URL
    value: redis://your-redis-instance
```

### Client EA Deployments (Client Infrastructure)

Each client deploys their own EA that connects to your webhook service:

```bash
# Create client environment file
cat > .env.client << EOF
CUSTOMER_ID=client-unique-id
WHATSAPP_PHONE_NUMBER=client-phone-number
WHATSAPP_WEBHOOK_SERVICE_URL=https://your-webhook.ondigitalocean.app
EA_AUTH_TOKEN=secure-client-token
OPENAI_API_KEY=client-openai-key
POSTGRES_URL=client-database-url
REDIS_URL=client-redis-url
EOF

# Deploy client EA
./scripts/deploy-client-ea.sh docker .env.client
```

## Business Model Integration

### For Your Business (Platform Provider)
- **Single WhatsApp Account**: One Meta business integration
- **Centralized Service**: Managed webhook infrastructure
- **Multiple Clients**: Route messages to different client EAs
- **Subscription Revenue**: Clients pay for WhatsApp EA services

### For Clients (EA Users)
- **Private Deployment**: EA runs in their environment
- **Data Isolation**: Business data never leaves their infrastructure
- **WhatsApp Access**: Get WhatsApp integration without Meta setup
- **Scalable Solution**: From single server to enterprise Kubernetes

## Development Workflow

### Local Development
```bash
# 1. Start development environment
./scripts/dev-whatsapp-start.sh

# 2. Make code changes to webhook service or EA bridge
# Files auto-reload with volume mounts

# 3. Test changes
python scripts/test-whatsapp-webhook.py

# 4. Stop when done
./scripts/dev-whatsapp-stop.sh
```

### Adding New Features

1. **Webhook Service Changes**:
   - Edit `src/webhook/whatsapp_webhook_service.py`
   - Changes auto-reload in development
   - Test with mock WhatsApp payloads

2. **EA Bridge Changes**:
   - Edit `src/communication/ea_whatsapp_bridge.py`
   - Test client-webhook communication
   - Verify MCP protocol handling

3. **Integration Testing**:
   - Use test scripts to verify end-to-end flow
   - Monitor logs for debugging
   - Test multiple client scenarios

## Key Files

### Core Implementation
- `src/webhook/whatsapp_webhook_service.py` - Centralized webhook service
- `src/communication/ea_whatsapp_bridge.py` - Client EA bridge
- `docker-compose.yml` - Development environment

### Deployment
- `src/webhook/Dockerfile.webhook-service` - Webhook service container
- `src/communication/Dockerfile.ea-bridge` - EA bridge container
- `scripts/deploy-client-ea.sh` - Client deployment script

### Development Tools
- `scripts/dev-whatsapp-start.sh` - Start development environment
- `scripts/test-whatsapp-webhook.py` - Testing framework
- `docs/deployment/WhatsApp-Service-Architecture.md` - Architecture guide

## Message Flow

1. **WhatsApp ▶ Webhook Service**:
   ```
   Meta servers ──POST──▶ /webhook/whatsapp
   ```

2. **Webhook Service ▶ Client EA**:
   ```
   Webhook Service ──MCP──▶ Client EA Bridge ──▶ Local EA
   ```

3. **Response Flow**:
   ```
   Local EA ──▶ EA Bridge ──MCP──▶ Webhook Service ──API──▶ WhatsApp
   ```

## Security Features

- **IP Allowlisting**: WhatsApp server IPs only
- **Webhook Signatures**: Validate message authenticity
- **Client Authentication**: Secure token-based auth
- **Data Isolation**: Client data stays in private environments
- **Encrypted Communication**: TLS for all service communication

## Monitoring & Debugging

### Health Checks
```bash
curl http://localhost:8000/health      # Overall webhook service health
curl http://localhost:8001/health      # EA bridge health
curl http://localhost:8000/ea/clients  # Active client registrations
```

### Common Issues

**EA Bridge Won't Register**:
```bash
# Check webhook service accessibility
curl https://your-webhook-service.app/health

# Verify client configuration
cat .env.client

# Check EA bridge logs
docker logs ea-bridge-customer-id
```

**Messages Not Routing**:
```bash
# Test webhook endpoint
python scripts/test-whatsapp-webhook.py --test message

# Check client registration
curl http://localhost:8000/ea/clients

# Verify MCP connectivity
curl http://localhost:8001/health
```

## Next Steps

1. **Production Setup**: Deploy webhook service to DigitalOcean
2. **Client Onboarding**: Use deployment scripts for new clients
3. **Monitoring**: Set up logging and alerting
4. **Scaling**: Add load balancing and redundancy
5. **Features**: Enhance with media processing and advanced routing

---

**Questions?** Check the [Architecture Guide](deployment/WhatsApp-Service-Architecture.md) or [GitHub Issues](https://github.com/your-org/ai-agency-platform/issues).