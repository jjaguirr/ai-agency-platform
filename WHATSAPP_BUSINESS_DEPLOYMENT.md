# WhatsApp Business API Deployment Guide

**Status**: ✅ PRODUCTION READY  
**Version**: 1.0  
**Date**: 2025-01-09  
**Issue**: #51 - Production Deployment Documentation  

---

## Executive Summary

This comprehensive deployment guide provides step-by-step procedures for deploying the WhatsApp Business API integration as part of the AI Agency Platform Phase 2. The integration delivers premium-casual communication channels with enterprise-grade operational excellence, supporting 500+ concurrent users with <3 second response time SLA.

## Prerequisites & Setup

### System Requirements

```yaml
Hardware Minimums:
  CPU: 4 cores (8 cores recommended for production)
  Memory: 8GB RAM (16GB recommended)
  Storage: 100GB SSD (NVMe preferred)
  Network: Stable internet with low latency to Twilio endpoints

Software Requirements:
  Operating System: Ubuntu 20.04 LTS or RHEL 8+
  Docker: 24.0+ with Compose Plugin
  Python: 3.9+
  Node.js: 18.x LTS
  PostgreSQL: 13+
  Redis: 6.2+
  
Network Requirements:
  Inbound: HTTPS (443), HTTP (80) for webhooks
  Outbound: HTTPS to Twilio API endpoints
  Internal: Docker network communication (configurable ports)
```

### Business API Prerequisites

#### Twilio WhatsApp Business API Setup

1. **Create Twilio Account**
   ```bash
   # Visit https://www.twilio.com/console
   # Enable WhatsApp Business API in your console
   # Complete business verification process (required for production)
   ```

2. **WhatsApp Business Profile Setup**
   ```bash
   # Required information:
   BUSINESS_NAME="Your Business Name"
   BUSINESS_CATEGORY="Technology" # or appropriate category
   BUSINESS_WEBSITE="https://yourbusiness.com"
   BUSINESS_DESCRIPTION="Brief description of your business"
   ```

3. **Obtain API Credentials**
   ```bash
   # From Twilio Console, collect:
   TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_PHONE_NUMBER_ID=+14155238886  # Your WhatsApp number
   TWILIO_WEBHOOK_VERIFY_TOKEN=your_secure_webhook_token
   ```

#### SSL Certificate Requirements

```yaml
SSL Configuration:
  Certificate Type: TLS 1.2+ (TLS 1.3 recommended)
  Certificate Authority: Trusted CA (Let's Encrypt, DigiCert, etc.)
  Domain Validation: Required for webhook endpoints
  Certificate Renewal: Automated renewal recommended
  
Webhook Endpoints:
  Primary: https://yourdomain.com/webhook/whatsapp
  Health Check: https://yourdomain.com/health
  Status: https://yourdomain.com/status
```

## Step-by-Step Deployment

### Phase 1: Environment Preparation (30 minutes)

#### 1.1 System Setup

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y curl wget git software-properties-common \
  apt-transport-https ca-certificates gnupg lsb-release

# Install Docker
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Verify Docker installation
docker --version
docker compose --version
```

#### 1.2 Clone Repository and Navigate

```bash
# Clone the WhatsApp integration stream
cd /opt
sudo git clone https://github.com/jjaguirr/ai-agency-platform.git whatsapp-integration
cd whatsapp-integration

# Switch to WhatsApp integration stream
git fetch --all
git checkout whatsapp-integration-stream

# Verify you're in the correct stream
pwd
# Should show: /opt/whatsapp-integration
```

#### 1.3 Create Directory Structure

```bash
# Create required directories with proper permissions
sudo mkdir -p /opt/whatsapp-integration/{logs,data,backups,ssl,media-storage}
sudo mkdir -p /var/log/whatsapp
sudo mkdir -p /etc/whatsapp

# Set ownership and permissions
sudo chown -R $USER:$USER /opt/whatsapp-integration
sudo chown -R $USER:$USER /var/log/whatsapp
sudo chmod -R 755 /opt/whatsapp-integration
sudo chmod -R 755 /var/log/whatsapp
```

### Phase 2: Configuration Management (45 minutes)

#### 2.1 Environment Variables Configuration

```bash
# Copy environment template
cp .env.production.template .env.production

# Edit production environment variables
nano .env.production
```

**Complete Environment Configuration:**

```bash
# ========================================
# WhatsApp Business API Configuration
# ========================================

# Twilio WhatsApp Business API
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_PHONE_NUMBER_ID=+14155238886
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
TWILIO_WEBHOOK_VERIFY_TOKEN=your_secure_webhook_verification_token

# WhatsApp Business Configuration
WHATSAPP_BUSINESS_ACCOUNT_ID=your_business_account_id
WHATSAPP_BUSINESS_NAME="Your Business Name"
WHATSAPP_BUSINESS_CATEGORY="Technology"
WHATSAPP_BUSINESS_WEBSITE="https://yourbusiness.com"
WHATSAPP_BUSINESS_DESCRIPTION="Professional AI assistant services"

# ========================================
# Phase 2 Premium-Casual Features
# ========================================

# Communication Style Configuration
WHATSAPP_PERSONALITY_TONE=premium-casual
WHATSAPP_ENABLE_EMOJIS=true
WHATSAPP_MOBILE_OPTIMIZED=true
WHATSAPP_CASUAL_GREETINGS=true

# Media Processing Configuration
WHATSAPP_MEDIA_STORAGE_PATH=/opt/whatsapp-integration/media-storage
WHATSAPP_MAX_FILE_SIZE_MB=16
WHATSAPP_SUPPORTED_IMAGE_TYPES=jpg,jpeg,png,gif,webp
WHATSAPP_SUPPORTED_AUDIO_TYPES=ogg,mp3,wav,aac,m4a
WHATSAPP_SUPPORTED_VIDEO_TYPES=mp4,3gp,mov
WHATSAPP_SUPPORTED_DOCUMENT_TYPES=pdf,doc,docx,xls,xlsx,ppt,pptx,txt

# ========================================
# Performance & Scalability Configuration
# ========================================

# Performance Targets (Phase 2 SLA)
WHATSAPP_MAX_CONCURRENT_USERS=500
WHATSAPP_RESPONSE_TIME_TARGET=3.0
WHATSAPP_MESSAGE_PROCESSING_TIMEOUT=30.0
WHATSAPP_MEDIA_PROCESSING_TIMEOUT=60.0

# Connection Pool Configuration
WHATSAPP_REDIS_POOL_SIZE=20
WHATSAPP_DB_POOL_SIZE=25
WHATSAPP_HTTP_POOL_SIZE=50

# Rate Limiting
WHATSAPP_RATE_LIMIT_MESSAGES_PER_MINUTE=100
WHATSAPP_RATE_LIMIT_MEDIA_PER_MINUTE=20
WHATSAPP_RATE_LIMIT_PER_CUSTOMER=50

# ========================================
# Database Configuration
# ========================================

# PostgreSQL Database
DATABASE_URL=postgresql://whatsapp_user:secure_password@localhost:5432/whatsapp_production
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=30
DATABASE_POOL_TIMEOUT=30
DATABASE_POOL_RECYCLE=3600

# Redis Configuration
REDIS_URL=redis://localhost:6379/1
REDIS_CACHE_TTL=3600
REDIS_SESSION_TTL=86400
REDIS_MEDIA_CACHE_TTL=7200

# ========================================
# Webhook Security Configuration
# ========================================

# Webhook Configuration
WEBHOOK_BASE_URL=https://yourdomain.com
WEBHOOK_SECRET=your_32_character_webhook_secret_key
WEBHOOK_TIMEOUT=30
ENABLE_WEBHOOK_SIGNATURE_VALIDATION=true

# Security Configuration
JWT_SECRET_KEY=your_256_bit_jwt_secret_key
CUSTOMER_ENCRYPTION_KEY=your_32_character_customer_encryption_key
SESSION_SECRET_KEY=your_secure_session_secret_key

# CORS Configuration
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
CORS_METHODS=GET,POST,PUT,DELETE,OPTIONS
CORS_HEADERS=Content-Type,Authorization,X-Requested-With

# ========================================
# Monitoring & Logging Configuration
# ========================================

# Prometheus Metrics
ENABLE_METRICS=true
METRICS_PORT=9090
METRICS_PATH=/metrics
PROMETHEUS_NAMESPACE=whatsapp_business

# Application Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_FILE_PATH=/var/log/whatsapp/application.log
LOG_MAX_SIZE_MB=100
LOG_BACKUP_COUNT=10

# Performance Monitoring
ENABLE_PERFORMANCE_MONITORING=true
PERFORMANCE_METRICS_INTERVAL=60
SLA_MONITORING_ENABLED=true
ALERT_ON_SLA_VIOLATION=true

# Health Check Configuration
HEALTH_CHECK_INTERVAL=30
HEALTH_CHECK_TIMEOUT=10
HEALTH_CHECK_RETRIES=3

# ========================================
# Cross-Channel Integration Configuration
# ========================================

# Channel Handoff Configuration
ENABLE_CROSS_CHANNEL_HANDOFF=true
HANDOFF_TIMEOUT=300
HANDOFF_CONTEXT_RETENTION=86400

# Integration Endpoints
VOICE_INTEGRATION_URL=http://voice-service:8080
EMAIL_INTEGRATION_URL=http://email-service:8080
UNIFIED_MEMORY_URL=http://memory-service:8080

# Customer Context Sharing
ENABLE_CONTEXT_SHARING=true
CONTEXT_SHARING_ENCRYPTION=true
CONTEXT_RETENTION_DAYS=30

# ========================================
# Production Environment Settings
# ========================================

# Environment Configuration
NODE_ENV=production
FLASK_ENV=production
DEBUG=false
TESTING=false

# Service Configuration
SERVICE_NAME=whatsapp-business-api
SERVICE_VERSION=2.0.0
SERVICE_PORT=8000
SERVICE_HOST=0.0.0.0

# Container Configuration
CONTAINER_TIMEZONE=UTC
CONTAINER_USER=whatsapp
CONTAINER_GROUP=whatsapp

# SSL/TLS Configuration
SSL_CERT_PATH=/opt/whatsapp-integration/ssl/cert.pem
SSL_KEY_PATH=/opt/whatsapp-integration/ssl/key.pem
SSL_CA_PATH=/opt/whatsapp-integration/ssl/ca.pem
ENABLE_SSL=true
SSL_VERIFY=true

# ========================================
# Business Verification Configuration
# ========================================

# Business Verification
ENABLE_BUSINESS_VERIFICATION=true
BUSINESS_VERIFICATION_TOKEN=your_business_verification_token
BUSINESS_PROFILE_DESCRIPTION="Professional AI assistant for business automation"
BUSINESS_CATEGORY_ID=business_technology
BUSINESS_TIMEZONE=America/New_York

# Customer Onboarding
ENABLE_AUTO_CUSTOMER_SETUP=true
CUSTOMER_SETUP_TIMEOUT=30
DEFAULT_CUSTOMER_TIER=professional
```

#### 2.2 SSL Certificate Configuration

```bash
# Option 1: Let's Encrypt (Recommended for production)
sudo apt install -y certbot
sudo certbot certonly --standalone -d yourdomain.com -d api.yourdomain.com

# Copy certificates to application directory
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem /opt/whatsapp-integration/ssl/cert.pem
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem /opt/whatsapp-integration/ssl/key.pem
sudo chown $USER:$USER /opt/whatsapp-integration/ssl/*.pem

# Option 2: Self-signed certificates (Development/Testing only)
# openssl req -x509 -newkey rsa:4096 -keyout /opt/whatsapp-integration/ssl/key.pem -out /opt/whatsapp-integration/ssl/cert.pem -days 365 -nodes
```

#### 2.3 Webhook Security Setup

```bash
# Generate secure tokens
python3 -c "
import secrets
import string

def generate_token(length=32):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for i in range(length))

def generate_jwt_secret():
    return secrets.token_urlsafe(32)

print('WEBHOOK_SECRET=' + generate_token(32))
print('JWT_SECRET_KEY=' + generate_jwt_secret())
print('CUSTOMER_ENCRYPTION_KEY=' + generate_token(32))
print('SESSION_SECRET_KEY=' + generate_token(32))
"

# Add generated tokens to .env.production file
```

### Phase 3: Database Setup and Migrations (20 minutes)

#### 3.1 PostgreSQL Database Setup

```bash
# Install PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# Start and enable PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Create database and user
sudo -u postgres psql << EOF
CREATE DATABASE whatsapp_production;
CREATE USER whatsapp_user WITH ENCRYPTED PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE whatsapp_production TO whatsapp_user;
ALTER USER whatsapp_user CREATEDB;
\q
EOF

# Verify database connection
PGPASSWORD=secure_password psql -h localhost -U whatsapp_user -d whatsapp_production -c "SELECT version();"
```

#### 3.2 Database Schema Initialization

```bash
# Run database migrations
cd /opt/whatsapp-integration
python3 -c "
import asyncio
from src.communication.whatsapp_manager import whatsapp_manager

async def init_db():
    print('Initializing WhatsApp database schema...')
    await whatsapp_manager.create_database_tables()
    print('Database initialization complete.')

asyncio.run(init_db())
"

# Verify tables were created
PGPASSWORD=secure_password psql -h localhost -U whatsapp_user -d whatsapp_production -c "\dt"
```

#### 3.3 Redis Configuration

```bash
# Install Redis
sudo apt install -y redis-server

# Configure Redis for production
sudo nano /etc/redis/redis.conf

# Key configurations to update:
# maxmemory 2gb
# maxmemory-policy allkeys-lru
# save 900 1
# save 300 10
# save 60 10000

# Start and enable Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Test Redis connection
redis-cli ping
```

### Phase 4: Service Deployment Procedures (60 minutes)

#### 4.1 Docker Container Build

```bash
# Build production Docker images
cd /opt/whatsapp-integration

# Build WhatsApp webhook server
docker build -t whatsapp-webhook-server:latest -f docker/Dockerfile.webhook .

# Build WhatsApp MCP server
docker build -t whatsapp-mcp-server:latest -f docker/Dockerfile.mcp .

# Build performance monitor
docker build -t whatsapp-performance-monitor:latest -f docker/Dockerfile.monitoring .

# Verify images were built
docker images | grep whatsapp
```

#### 4.2 Production Docker Compose Deployment

```bash
# Copy production Docker Compose configuration
cp docker-compose.production.yml docker-compose.yml

# Review and customize configuration
nano docker-compose.yml
```

**Production Docker Compose Configuration:**

```yaml
version: '3.8'

services:
  whatsapp-webhook-server:
    image: whatsapp-webhook-server:latest
    container_name: whatsapp-webhook-server
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - NODE_ENV=production
    env_file:
      - .env.production
    volumes:
      - ./logs:/app/logs
      - ./media-storage:/app/media-storage
      - ./ssl:/app/ssl
    depends_on:
      - postgres
      - redis
    networks:
      - whatsapp-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  whatsapp-mcp-server:
    image: whatsapp-mcp-server:latest
    container_name: whatsapp-mcp-server
    restart: unless-stopped
    ports:
      - "3001:3001"
    environment:
      - NODE_ENV=production
    env_file:
      - .env.production
    volumes:
      - ./logs:/app/logs
      - ./media-storage:/app/media-storage
    depends_on:
      - postgres
      - redis
    networks:
      - whatsapp-network
    healthcheck:
      test: ["CMD", "node", "health-check.js"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  whatsapp-performance-monitor:
    image: whatsapp-performance-monitor:latest
    container_name: whatsapp-performance-monitor
    restart: unless-stopped
    ports:
      - "9090:9090"
    environment:
      - NODE_ENV=production
    env_file:
      - .env.production
    volumes:
      - ./logs:/app/logs
    depends_on:
      - postgres
      - redis
    networks:
      - whatsapp-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9090/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  postgres:
    image: postgres:13
    container_name: whatsapp-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: whatsapp_production
      POSTGRES_USER: whatsapp_user
      POSTGRES_PASSWORD: secure_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
    networks:
      - whatsapp-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U whatsapp_user -d whatsapp_production"]
      interval: 30s
      timeout: 10s
      retries: 3

  redis:
    image: redis:6.2-alpine
    container_name: whatsapp-redis
    restart: unless-stopped
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    networks:
      - whatsapp-network
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3

  nginx:
    image: nginx:alpine
    container_name: whatsapp-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
      - ./logs/nginx:/var/log/nginx
    depends_on:
      - whatsapp-webhook-server
    networks:
      - whatsapp-network
    healthcheck:
      test: ["CMD", "nginx", "-t"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  postgres_data:
  redis_data:

networks:
  whatsapp-network:
    driver: bridge
```

#### 4.3 NGINX Reverse Proxy Configuration

```bash
# Create NGINX configuration
cat > nginx.conf << EOF
events {
    worker_connections 1024;
}

http {
    upstream whatsapp_webhook {
        server whatsapp-webhook-server:8000;
    }

    upstream whatsapp_mcp {
        server whatsapp-mcp-server:3001;
    }

    upstream whatsapp_monitoring {
        server whatsapp-performance-monitor:9090;
    }

    # Rate limiting
    limit_req_zone \$binary_remote_addr zone=webhook:10m rate=10r/s;
    limit_req_zone \$binary_remote_addr zone=api:10m rate=60r/m;

    # SSL Configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers off;

    # Main WhatsApp webhook endpoint
    server {
        listen 80;
        server_name yourdomain.com;
        return 301 https://\$server_name\$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name yourdomain.com;

        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;

        # Webhook endpoint with rate limiting
        location /webhook/whatsapp {
            limit_req zone=webhook burst=20 nodelay;
            proxy_pass http://whatsapp_webhook;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
            proxy_connect_timeout 30s;
            proxy_send_timeout 30s;
            proxy_read_timeout 30s;
        }

        # Health check endpoint
        location /health {
            proxy_pass http://whatsapp_webhook;
            proxy_set_header Host \$host;
            access_log off;
        }

        # Status and metrics endpoints
        location /status {
            limit_req zone=api burst=10 nodelay;
            proxy_pass http://whatsapp_webhook;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
        }

        # MCP endpoint
        location /mcp/ {
            limit_req zone=api burst=30 nodelay;
            proxy_pass http://whatsapp_mcp/;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
            proxy_http_version 1.1;
            proxy_set_header Upgrade \$http_upgrade;
            proxy_set_header Connection "upgrade";
        }

        # Monitoring endpoint (internal only)
        location /metrics {
            allow 127.0.0.1;
            allow 10.0.0.0/8;
            allow 172.16.0.0/12;
            allow 192.168.0.0/16;
            deny all;
            proxy_pass http://whatsapp_monitoring;
            proxy_set_header Host \$host;
        }

        # Security headers
        add_header X-Content-Type-Options nosniff;
        add_header X-Frame-Options DENY;
        add_header X-XSS-Protection "1; mode=block";
        add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload";
        add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';";
    }
}
EOF
```

#### 4.4 Start Services

```bash
# Start all services
docker compose up -d

# Verify services are running
docker compose ps

# Check service logs
docker compose logs -f whatsapp-webhook-server

# Wait for services to fully start (about 2-3 minutes)
sleep 180
```

### Phase 5: Webhook Endpoint Configuration (30 minutes)

#### 5.1 Configure Twilio Webhooks

```bash
# Configure webhook URLs in Twilio Console
# 1. Log into https://console.twilio.com/
# 2. Navigate to Messaging > Settings > WhatsApp sandbox settings
# 3. Set webhook URL to: https://yourdomain.com/webhook/whatsapp
# 4. Set HTTP method to: POST
# 5. Set webhook events to: 
#    - Messages (incoming, delivery status)
#    - Media (incoming media messages)
#    - Status (message status updates)

# Test webhook endpoint
curl -X POST https://yourdomain.com/webhook/whatsapp \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "MessageSid=TEST123&From=whatsapp:+1234567890&Body=test message"
```

#### 5.2 Webhook Security Validation

```bash
# Test webhook signature validation
python3 -c "
import hashlib
import hmac
import base64
from urllib.parse import urlencode

# Test webhook security
webhook_secret = 'your_32_character_webhook_secret_key'
payload = 'MessageSid=TEST123&From=whatsapp:+1234567890&Body=test message'
url = 'https://yourdomain.com/webhook/whatsapp'

# Generate signature
signature = base64.b64encode(
    hmac.new(
        webhook_secret.encode('utf-8'),
        (url + payload).encode('utf-8'),
        hashlib.sha1
    ).digest()
).decode('ascii')

print('X-Twilio-Signature: ' + signature)
"

# Test with proper signature
curl -X POST https://yourdomain.com/webhook/whatsapp \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "X-Twilio-Signature: [signature-from-above]" \
  -d "MessageSid=TEST123&From=whatsapp:+1234567890&Body=test message"
```

### Phase 6: Testing and Validation (45 minutes)

#### 6.1 Deployment Verification Procedures

```bash
# Run comprehensive deployment validation
cd /opt/whatsapp-integration
python3 scripts/validate-whatsapp-deployment.py

# Expected output:
# ✅ WhatsApp webhook server health check passed
# ✅ MCP server health check passed  
# ✅ Database connectivity verified
# ✅ Redis connectivity verified
# ✅ Webhook endpoint accessible
# ✅ SSL certificate valid
# ✅ Performance metrics collection working
# ✅ All services running and healthy
```

#### 6.2 WhatsApp Business API Connectivity Testing

```bash
# Test outbound WhatsApp message
python3 -c "
import asyncio
from src.communication.whatsapp_manager import whatsapp_manager

async def test_whatsapp():
    # Setup test customer
    result = await whatsapp_manager.setup_customer_whatsapp(
        customer_id='test-deployment-001',
        config={
            'business_name': 'Test Business',
            'is_verified': True
        }
    )
    print(f'Customer setup: {result}')
    
    # Test premium-casual message
    channel = await whatsapp_manager.get_customer_whatsapp_channel('test-deployment-001')
    message_result = await channel.send_message(
        '+1234567890',  # Replace with test number
        'Hey! Your WhatsApp Business API deployment is working perfectly! 🎉'
    )
    print(f'Message sent: {message_result}')

asyncio.run(test_whatsapp())
"
```

#### 6.3 Premium-Casual Tone Validation

```bash
# Test tone adaptation system
python3 -c "
import asyncio
from src.communication.whatsapp_channel import WhatsAppChannel

async def test_tone_adaptation():
    channel = WhatsAppChannel('test-customer')
    
    # Test formal to casual conversion
    formal_message = 'I will assist you with your business requirements. Thank you for your patience.'
    casual_message = await channel.adapt_tone_to_premium_casual(formal_message)
    print(f'Original: {formal_message}')
    print(f'Adapted: {casual_message}')
    
    # Expected: 'I'll help you with your business needs. Thanks for your patience! 😊'

asyncio.run(test_tone_adaptation())
"
```

#### 6.4 Media Processing Testing

```bash
# Test media message processing
python3 -c "
import asyncio
from src.communication.whatsapp_manager import whatsapp_manager

async def test_media_processing():
    # Test image processing
    image_result = await whatsapp_manager.process_media_message(
        'https://example.com/test-image.jpg',
        'image/jpeg',
        'test-deployment-001'
    )
    print(f'Image processing result: {image_result.success}')
    
    # Test voice message processing (if available)
    # voice_result = await whatsapp_manager.process_media_message(
    #     'https://example.com/test-voice.ogg',
    #     'audio/ogg',
    #     'test-deployment-001'
    # )
    # print(f'Voice processing result: {voice_result.success}')

asyncio.run(test_media_processing())
"
```

#### 6.5 Performance Validation

```bash
# Test concurrent user support
python3 -c "
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor

async def test_concurrent_performance():
    async def send_test_message():
        async with aiohttp.ClientSession() as session:
            async with session.post(
                'https://yourdomain.com/webhook/whatsapp',
                data={
                    'MessageSid': f'TEST{hash(asyncio.current_task())}',
                    'From': 'whatsapp:+1234567890',
                    'Body': 'Performance test message'
                }
            ) as response:
                return response.status
    
    # Test 100 concurrent requests
    tasks = [send_test_message() for _ in range(100)]
    results = await asyncio.gather(*tasks)
    
    success_rate = sum(1 for status in results if status == 200) / len(results)
    print(f'Concurrent request success rate: {success_rate:.1%}')
    # Target: >95% success rate

asyncio.run(test_concurrent_performance())
"
```

### Phase 7: Monitoring and Health Checks Setup (30 minutes)

#### 7.1 Health Check Configuration

```bash
# Configure automated health checks
cat > /etc/systemd/system/whatsapp-health-monitor.service << EOF
[Unit]
Description=WhatsApp Business API Health Monitor
After=docker.service
Requires=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/whatsapp-integration
ExecStart=/usr/bin/python3 scripts/health-monitor.py
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
EOF

# Enable and start health monitor
sudo systemctl daemon-reload
sudo systemctl enable whatsapp-health-monitor
sudo systemctl start whatsapp-health-monitor
```

#### 7.2 Prometheus Metrics Configuration

```bash
# Verify metrics endpoint is accessible
curl http://localhost:9090/metrics | grep whatsapp

# Expected metrics:
# whatsapp_messages_total
# whatsapp_response_time_seconds
# whatsapp_concurrent_users
# whatsapp_sla_compliance_percentage
# whatsapp_media_messages_total
```

#### 7.3 Log Monitoring Setup

```bash
# Configure log rotation
sudo cat > /etc/logrotate.d/whatsapp << EOF
/var/log/whatsapp/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0644 whatsapp whatsapp
    postrotate
        docker compose restart whatsapp-webhook-server
    endscript
}
EOF

# Test log rotation configuration
sudo logrotate -d /etc/logrotate.d/whatsapp
```

## Configuration Management

### Environment-Specific Configurations

#### Development Environment

```bash
# Development environment variables (.env.development)
NODE_ENV=development
DEBUG=true
LOG_LEVEL=DEBUG
WHATSAPP_RESPONSE_TIME_TARGET=10.0
ENABLE_WEBHOOK_SIGNATURE_VALIDATION=false
```

#### Staging Environment

```bash
# Staging environment variables (.env.staging)
NODE_ENV=staging
DEBUG=false
LOG_LEVEL=INFO
WHATSAPP_RESPONSE_TIME_TARGET=5.0
ENABLE_WEBHOOK_SIGNATURE_VALIDATION=true
```

#### Production Environment

```bash
# Production environment variables (.env.production)
NODE_ENV=production
DEBUG=false
LOG_LEVEL=WARN
WHATSAPP_RESPONSE_TIME_TARGET=3.0
ENABLE_WEBHOOK_SIGNATURE_VALIDATION=true
```

### Security Configuration

#### Rate Limiting Configuration

```yaml
Rate Limiting Rules:
  Messages per minute: 100 (per customer)
  Media messages per minute: 20 (per customer)
  Webhook calls per second: 10 (per IP)
  API calls per minute: 60 (per IP)
  
Security Headers:
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  X-XSS-Protection: "1; mode=block"
  Strict-Transport-Security: "max-age=63072000; includeSubDomains"
  Content-Security-Policy: "default-src 'self'"
```

#### Data Encryption Configuration

```yaml
Encryption Standards:
  Customer Data: AES-256-GCM
  Database Connections: TLS 1.2+
  API Communications: HTTPS only
  Media Files: Encrypted at rest
  
Key Management:
  Customer Encryption Keys: Rotated every 90 days
  JWT Tokens: HS256 algorithm
  Session Keys: Secure random generation
  Webhook Secrets: 256-bit entropy
```

### Cross-Channel Integration Setup

#### Integration Configuration

```bash
# Cross-channel integration environment variables
ENABLE_CROSS_CHANNEL_HANDOFF=true
VOICE_INTEGRATION_URL=http://voice-service:8080
EMAIL_INTEGRATION_URL=http://email-service:8080
UNIFIED_MEMORY_URL=http://memory-service:8080

HANDOFF_TIMEOUT=300
CONTEXT_SHARING_ENCRYPTION=true
CONTEXT_RETENTION_DAYS=30
```

## Testing and Validation

### Automated Testing Suite

#### Unit Tests

```bash
# Run WhatsApp-specific unit tests
cd /opt/whatsapp-integration/tests
python -m pytest whatsapp/unit/ -v

# Expected test coverage:
# ✅ WhatsApp channel initialization
# ✅ Message sending and receiving
# ✅ Premium-casual tone adaptation
# ✅ Media message processing
# ✅ Error handling and recovery
# ✅ Rate limiting enforcement
# ✅ Security validation
```

#### Integration Tests

```bash
# Run integration tests
python -m pytest whatsapp/integration/ -v

# Expected test results:
# ✅ Twilio API integration
# ✅ Database operations
# ✅ Redis cache operations
# ✅ Cross-channel handoff
# ✅ Performance monitoring
# ✅ Webhook processing
# ✅ Business verification
```

#### Performance Tests

```bash
# Run performance validation tests
python -m pytest whatsapp/performance/ -v

# Performance benchmarks:
# ✅ <3 second response time (SLA)
# ✅ 500+ concurrent user support
# ✅ Media processing <60 seconds
# ✅ Memory usage optimization
# ✅ CPU utilization monitoring
```

### Manual Testing Procedures

#### End-to-End Customer Journey

```bash
# Test complete customer onboarding flow
python3 scripts/test-customer-journey.py --customer-id test-e2e-001

# Expected flow:
# 1. Customer setup (WhatsApp number registration)
# 2. Business verification
# 3. First message exchange
# 4. Premium-casual tone validation
# 5. Media message testing
# 6. Cross-channel handoff testing
# 7. Performance metrics validation
```

### Validation Checklists

#### Pre-Deployment Checklist

```yaml
Infrastructure Validation:
  ✅ All environment variables configured
  ✅ SSL certificates installed and valid
  ✅ Database migrations completed successfully
  ✅ Redis server operational
  ✅ Docker services built and ready
  ✅ NGINX configuration validated
  ✅ Webhook endpoints accessible
  ✅ Security configurations applied

Business API Validation:
  ✅ Twilio WhatsApp Business API credentials configured
  ✅ Business profile setup completed
  ✅ Phone number verification completed
  ✅ Webhook URL configured in Twilio Console
  ✅ Webhook signature validation working
  ✅ Rate limiting configured properly
```

#### Post-Deployment Validation

```yaml
Functional Validation:
  ✅ Health check endpoints responding
  ✅ WhatsApp messages sending successfully
  ✅ Premium-casual tone adaptation working
  ✅ Media message processing functional
  ✅ Business verification system operational
  ✅ Cross-channel handoff functioning
  ✅ Performance metrics collecting
  ✅ SLA monitoring active

Security Validation:
  ✅ Webhook signature validation enforced
  ✅ Rate limiting protecting endpoints
  ✅ SSL/TLS configuration secure
  ✅ Customer data encryption active
  ✅ Access controls functioning
  ✅ Audit logging operational

Performance Validation:
  ✅ Response times <3 seconds (SLA)
  ✅ Concurrent user support >500 users
  ✅ Memory usage within acceptable limits
  ✅ CPU utilization optimized
  ✅ Database performance optimal
  ✅ Media processing <60 seconds
```

## Monitoring and Maintenance

### Health Check Procedures

#### Automated Health Monitoring

```bash
# Primary health check endpoint
curl -f https://yourdomain.com/health

# Expected response:
{
  "status": "healthy",
  "timestamp": "2025-01-09T12:00:00Z",
  "services": {
    "webhook_server": "healthy",
    "mcp_server": "healthy",
    "database": "healthy",
    "redis": "healthy",
    "twilio_api": "healthy"
  },
  "metrics": {
    "response_time_avg": 1.2,
    "concurrent_users": 45,
    "sla_compliance": 98.7
  }
}
```

#### Service-Specific Health Checks

```bash
# WhatsApp MCP Server health
curl http://localhost:3001/health

# Performance monitoring health
curl http://localhost:9090/health

# Database connectivity test
PGPASSWORD=secure_password psql -h localhost -U whatsapp_user -d whatsapp_production -c "SELECT 1;"

# Redis connectivity test
redis-cli ping
```

### Performance Monitoring Setup

#### Key Performance Indicators (KPIs)

```yaml
Primary SLA Metrics:
  Response Time: <3 seconds (95th percentile)
  Concurrent Users: 500+ supported
  Uptime: >99.9% availability
  Message Delivery Success: >99% rate
  
Operational Metrics:
  CPU Utilization: <70% average
  Memory Usage: <80% of allocated
  Database Query Time: <100ms average
  Redis Operation Time: <10ms average
  
Business Metrics:
  Customer Satisfaction: >90%
  Premium-Casual Tone Success: >85%
  Cross-Channel Handoff Success: >95%
  Media Processing Success: >90%
```

#### Alerting Configuration

```bash
# Configure monitoring alerts
cat > /opt/whatsapp-integration/config/alerts.yml << EOF
alerts:
  critical:
    - metric: response_time_p95
      threshold: 5.0
      duration: 2m
      action: page_on_call_team
      
    - metric: uptime_percentage
      threshold: 99.0
      duration: 5m
      action: page_on_call_team
      
    - metric: error_rate
      threshold: 5.0
      duration: 1m
      action: page_on_call_team
      
  warning:
    - metric: concurrent_users
      threshold: 450
      duration: 5m
      action: notify_team
      
    - metric: cpu_utilization
      threshold: 80.0
      duration: 10m
      action: notify_team
      
    - metric: memory_utilization
      threshold: 85.0
      duration: 10m
      action: notify_team
EOF
```

### Error Handling and Troubleshooting

#### Common Issues and Solutions

**Issue 1: Webhook Not Receiving Messages**

```bash
# Diagnosis
curl -v https://yourdomain.com/webhook/whatsapp
docker compose logs whatsapp-webhook-server
sudo netstat -tlpn | grep :443

# Common causes:
# - SSL certificate issues
# - Firewall blocking traffic
# - Twilio webhook URL misconfiguration
# - Service not running

# Solution:
sudo systemctl restart nginx
docker compose restart whatsapp-webhook-server
# Verify Twilio webhook URL configuration
```

**Issue 2: Performance Degradation**

```bash
# Diagnosis
curl http://localhost:9090/metrics | grep response_time
docker stats --no-stream
top -p $(pgrep -f whatsapp)

# Common causes:
# - High concurrent load
# - Database connection issues
# - Memory leaks
# - Network latency

# Solution:
docker compose scale whatsapp-webhook-server=3
# Check database connection pool
# Monitor memory usage
# Optimize Redis configuration
```

**Issue 3: Media Processing Failures**

```bash
# Diagnosis
ls -la /opt/whatsapp-integration/media-storage/
docker compose logs whatsapp-webhook-server | grep media
df -h /opt/whatsapp-integration/

# Common causes:
# - Insufficient disk space
# - File permission issues
# - Media processing timeout
# - Unsupported media format

# Solution:
sudo chown -R whatsapp:whatsapp /opt/whatsapp-integration/media-storage/
# Clean up old media files
# Increase processing timeout
# Verify supported media formats
```

### Customer Impact Assessment During Issues

#### Impact Classification

```yaml
Severity Levels:
  P0 - Critical (Complete service outage):
    - WhatsApp webhook server down
    - Database connectivity lost
    - All customers affected
    - Response time: <15 minutes
    
  P1 - High (Significant degradation):
    - Response time >10 seconds
    - Media processing failures
    - >50% of customers affected
    - Response time: <1 hour
    
  P2 - Medium (Partial degradation):
    - Response time 3-10 seconds
    - Some features unavailable
    - <50% of customers affected
    - Response time: <4 hours
    
  P3 - Low (Minor issues):
    - Response time slightly elevated
    - Non-critical features affected
    - <10% of customers affected
    - Response time: <24 hours
```

#### Customer Communication

```bash
# Automated customer notification system
python3 -c "
from src.notifications.customer_alerts import CustomerAlerts

# P0/P1 incidents - immediate notification
alerts = CustomerAlerts()
await alerts.send_service_alert(
    severity='P1',
    message='We are experiencing elevated response times on WhatsApp. Our team is actively working on a resolution.',
    estimated_resolution='30 minutes',
    updates_every='15 minutes'
)
"
```

## Production Operations Runbook

### Daily Operations

#### Morning Health Check (15 minutes)

```bash
#!/bin/bash
# Daily morning health check script

echo "WhatsApp Business API - Daily Health Check"
echo "Date: $(date)"
echo "========================================"

# Check service status
echo "1. Service Status:"
docker compose ps

# Check health endpoints
echo "2. Health Endpoints:"
curl -s https://yourdomain.com/health | jq .

# Check performance metrics
echo "3. Performance Metrics:"
curl -s http://localhost:9090/metrics | grep -E "(response_time|concurrent_users|sla_compliance)"

# Check error logs
echo "4. Recent Errors:"
tail -50 /var/log/whatsapp/application.log | grep ERROR

# Check disk usage
echo "5. Disk Usage:"
df -h /opt/whatsapp-integration/

# Check memory usage
echo "6. Memory Usage:"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"

echo "========================================"
echo "Daily health check completed."
```

#### Customer Onboarding Monitoring

```bash
# Monitor customer onboarding success
python3 -c "
import asyncio
from src.monitoring.customer_onboarding_monitor import OnboardingMonitor

async def daily_onboarding_report():
    monitor = OnboardingMonitor()
    report = await monitor.get_daily_onboarding_report()
    
    print('Customer Onboarding Report - Last 24 hours')
    print(f'New customers: {report.new_customers}')
    print(f'Successful setups: {report.successful_setups}')
    print(f'Setup success rate: {report.success_rate:.1%}')
    print(f'Average setup time: {report.avg_setup_time:.1f} seconds')
    print(f'Issues requiring attention: {len(report.issues)}')

asyncio.run(daily_onboarding_report())
"
```

### Weekly Maintenance Tasks

#### Performance Optimization (30 minutes)

```bash
#!/bin/bash
# Weekly performance optimization script

echo "WhatsApp Business API - Weekly Maintenance"
echo "Date: $(date)"
echo "========================================"

# Database maintenance
echo "1. Database Optimization:"
PGPASSWORD=secure_password psql -h localhost -U whatsapp_user -d whatsapp_production << EOF
VACUUM ANALYZE;
REINDEX DATABASE whatsapp_production;
\q
EOF

# Redis optimization
echo "2. Redis Optimization:"
redis-cli FLUSHDB 2
redis-cli BGREWRITEAOF

# Log rotation and cleanup
echo "3. Log Cleanup:"
find /var/log/whatsapp/ -name "*.log" -type f -mtime +30 -delete
find /opt/whatsapp-integration/media-storage/ -name "*" -type f -mtime +7 -delete

# Docker cleanup
echo "4. Docker Cleanup:"
docker system prune -f
docker image prune -f

# SSL certificate check
echo "5. SSL Certificate Validation:"
openssl x509 -in /opt/whatsapp-integration/ssl/cert.pem -text -noout | grep "Not After"

# Performance metrics analysis
echo "6. Performance Metrics Analysis:"
python3 scripts/weekly-performance-analysis.py

echo "========================================"
echo "Weekly maintenance completed."
```

#### Security Audit (45 minutes)

```bash
#!/bin/bash
# Weekly security audit script

echo "WhatsApp Business API - Security Audit"
echo "Date: $(date)"
echo "========================================"

# Check for security updates
echo "1. Security Updates:"
apt list --upgradable | grep -i security

# SSL/TLS configuration test
echo "2. SSL/TLS Security Test:"
nmap --script ssl-enum-ciphers -p 443 yourdomain.com

# Container security scan
echo "3. Container Security Scan:"
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  clair/clair:latest clairctl analyze whatsapp-webhook-server:latest

# Access log analysis
echo "4. Access Log Analysis:"
grep -E "4[0-9]{2}|5[0-9]{2}" /var/log/nginx/access.log | tail -20

# Rate limiting effectiveness
echo "5. Rate Limiting Analysis:"
grep "rate limit" /var/log/nginx/error.log | tail -10

# Webhook security validation
echo "6. Webhook Security Test:"
python3 scripts/test-webhook-security.py

echo "========================================"
echo "Security audit completed."
```

### Emergency Response Procedures

#### Incident Response Team Contacts

```yaml
On-Call Rotation:
  Primary: DevOps Engineer (24/7)
  Secondary: Infrastructure Team Lead
  Escalation: CTO/Technical Director
  
Contact Methods:
  PagerDuty: Production incidents (P0/P1)
  Slack: #incidents channel (all severity levels)
  Email: ops-team@company.com (non-urgent)
  Phone: +1-555-EMERGENCY (P0 only)
```

#### Emergency Escalation Procedures

**P0 - Complete Service Outage**

```bash
# Immediate response (0-15 minutes)
1. Acknowledge incident in PagerDuty
2. Post in #incidents Slack channel
3. Begin diagnosis using runbooks
4. Notify Customer Success team
5. Activate status page incident

# Escalation triggers (15 minutes)
- Unable to identify root cause
- Resolution ETA >30 minutes
- Multiple services affected
```

**P1 - Significant Degradation**

```bash
# Response within 1 hour
1. Create incident in tracking system
2. Begin troubleshooting following runbooks
3. Update stakeholders every 30 minutes
4. Consider rollback if recent deployment

# Escalation triggers (1 hour)
- No progress on resolution
- Customer escalations received
- SLA breach imminent
```

### System Scaling Guidelines

#### Horizontal Scaling Triggers

```yaml
Scale Up Triggers:
  - CPU utilization >80% for 5 minutes
  - Response time >5 seconds for 2 minutes
  - Concurrent users approaching 450
  - Error rate >5% for 1 minute
  
Scale Up Actions:
  1. Scale webhook servers: docker compose scale whatsapp-webhook-server=3
  2. Add Redis read replicas
  3. Scale database connections
  4. Update load balancer configuration
```

#### Vertical Scaling Guidelines

```yaml
Resource Upgrade Triggers:
  - Consistent high resource utilization
  - Performance degradation during peak hours
  - Customer growth exceeding capacity
  
Upgrade Process:
  1. Schedule maintenance window
  2. Create infrastructure backups
  3. Update Docker resource limits
  4. Test with staging environment
  5. Deploy during low-traffic period
```

---

## Deployment Validation

### Automated Validation Script

```bash
#!/bin/bash
# WhatsApp Business API Deployment Validation Script

echo "WhatsApp Business API Deployment Validation"
echo "============================================"

VALIDATION_PASSED=true

# Function to check and report
check_status() {
    if [ $1 -eq 0 ]; then
        echo "✅ $2"
    else
        echo "❌ $2"
        VALIDATION_PASSED=false
    fi
}

# 1. Service Health Checks
echo "1. Service Health Validation:"
curl -sf https://yourdomain.com/health > /dev/null
check_status $? "WhatsApp webhook server health check"

curl -sf http://localhost:3001/health > /dev/null  
check_status $? "MCP server health check"

curl -sf http://localhost:9090/health > /dev/null
check_status $? "Performance monitor health check"

# 2. Database Connectivity
echo "2. Database Connectivity:"
PGPASSWORD=secure_password psql -h localhost -U whatsapp_user -d whatsapp_production -c "SELECT 1;" > /dev/null 2>&1
check_status $? "PostgreSQL database connectivity"

redis-cli ping > /dev/null 2>&1
check_status $? "Redis connectivity"

# 3. SSL Certificate Validation
echo "3. SSL Certificate Validation:"
openssl s_client -connect yourdomain.com:443 -servername yourdomain.com < /dev/null 2>/dev/null | openssl x509 -noout -dates
check_status $? "SSL certificate validity"

# 4. Performance Metrics
echo "4. Performance Metrics Validation:"
response_time=$(curl -w "%{time_total}" -s -o /dev/null https://yourdomain.com/health)
if (( $(echo "$response_time < 3.0" | bc -l) )); then
    echo "✅ Response time: ${response_time}s (< 3.0s SLA)"
else
    echo "❌ Response time: ${response_time}s (> 3.0s SLA)"
    VALIDATION_PASSED=false
fi

# 5. Security Validation
echo "5. Security Configuration Validation:"
# Check if webhook signature validation is enabled
if grep -q "ENABLE_WEBHOOK_SIGNATURE_VALIDATION=true" .env.production; then
    echo "✅ Webhook signature validation enabled"
else
    echo "❌ Webhook signature validation not enabled"
    VALIDATION_PASSED=false
fi

# 6. Webhook Endpoint Test
echo "6. Webhook Endpoint Validation:"
webhook_status=$(curl -s -o /dev/null -w "%{http_code}" -X POST https://yourdomain.com/webhook/whatsapp \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "MessageSid=VALIDATION_TEST&From=whatsapp:+1234567890&Body=deployment validation")

if [ "$webhook_status" -eq 200 ]; then
    echo "✅ Webhook endpoint responding correctly"
else
    echo "❌ Webhook endpoint returned status: $webhook_status"
    VALIDATION_PASSED=false
fi

echo "============================================"
if [ "$VALIDATION_PASSED" = true ]; then
    echo "🎉 All validation checks passed! Deployment is ready for production."
    exit 0
else
    echo "⚠️  Some validation checks failed. Please review and resolve issues before proceeding."
    exit 1
fi
```

### Manual Validation Checklist

```yaml
Pre-Deployment Validation:
  Infrastructure Setup:
    ✅ All required services running (Docker containers up)
    ✅ SSL certificates installed and valid (>30 days remaining)
    ✅ Database migrations completed successfully
    ✅ Redis server operational with proper configuration
    ✅ NGINX reverse proxy configured correctly
    ✅ Firewall rules configured for required ports (80, 443)
    ✅ Log directories created with proper permissions
    
  Configuration Validation:
    ✅ All environment variables set in .env.production
    ✅ Twilio API credentials configured and tested
    ✅ Webhook URLs configured in Twilio Console
    ✅ Business profile setup completed
    ✅ Rate limiting configuration active
    ✅ Security headers configured in NGINX
    ✅ CORS settings configured appropriately
    
  Security Validation:
    ✅ Webhook signature validation enabled and tested
    ✅ SSL/TLS configuration uses secure protocols (TLS 1.2+)
    ✅ Strong random secrets generated for all keys
    ✅ Database credentials secured
    ✅ Container security best practices applied
    ✅ Network isolation configured properly
    ✅ Access controls implemented and tested

Post-Deployment Validation:
  Functional Testing:
    ✅ Health check endpoints responding (< 3 second response time)
    ✅ WhatsApp message sending successful
    ✅ WhatsApp message receiving functional
    ✅ Premium-casual tone adaptation working
    ✅ Media message processing operational
    ✅ Business verification system functional
    ✅ Cross-channel handoff working (if applicable)
    ✅ Error handling graceful and informative
    
  Performance Validation:
    ✅ Response time <3 seconds (95th percentile)
    ✅ Concurrent user support >500 users validated
    ✅ Memory usage within acceptable limits (<80%)
    ✅ CPU utilization optimized (<70% average)
    ✅ Database query performance <100ms average
    ✅ Media processing <60 seconds
    ✅ SLA compliance monitoring active and reporting
    
  Monitoring Validation:
    ✅ Prometheus metrics collecting properly
    ✅ Health monitoring service running
    ✅ Log rotation configured and working
    ✅ Alert configuration tested (test alert sent)
    ✅ Dashboard accessible and displaying data
    ✅ Automated backup processes running
    ✅ Incident response procedures documented and tested
```

---

## Summary

This comprehensive WhatsApp Business API deployment guide provides:

✅ **Complete Production Setup**: Step-by-step deployment procedures for enterprise-grade WhatsApp Business API integration  
✅ **Security-First Configuration**: Webhook signature validation, SSL/TLS encryption, and comprehensive security controls  
✅ **Performance Optimization**: Configuration for 500+ concurrent users with <3 second response time SLA  
✅ **Premium-Casual Features**: Tone adaptation system for natural, mobile-optimized communication  
✅ **Monitoring & Operations**: Health checks, performance monitoring, and automated alerting  
✅ **Production Readiness**: Comprehensive validation procedures and operational runbooks

**Status**: ✅ **PRODUCTION READY**  
**Deployment Time**: ~4-5 hours (including validation)  
**SLA Targets**: <3 second response, >99.9% uptime, 500+ concurrent users  

**Next Steps**: Complete cross-system integration documentation and production operations runbook.

---

*Infrastructure-DevOps Agent Implementation*  
*Document Version: 1.0*  
*Last Updated: 2025-01-09*