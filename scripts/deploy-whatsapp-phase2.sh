#!/bin/bash

# WhatsApp Business API Phase 2 Deployment Script
# Deploys premium-casual communication features for AI Agency Platform

set -e

echo "🚀 Deploying WhatsApp Business API Phase 2 Integration..."

# Configuration
DEPLOYMENT_ENV=${DEPLOYMENT_ENV:-"production"}
PROJECT_ROOT="/Users/jose/Documents/🚀 Projects/⚡ Active/whatsapp-integration-stream"
VENV_PATH="${PROJECT_ROOT}/venv"
MEDIA_STORAGE_PATH="/opt/whatsapp-media"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Pre-deployment checks
log_info "Running pre-deployment checks..."

# Check Python environment
if [ ! -d "$VENV_PATH" ]; then
    log_info "Creating Python virtual environment..."
    python3 -m venv "$VENV_PATH"
fi

source "$VENV_PATH/bin/activate"

# Check required services
log_info "Checking required services..."

if ! redis-cli ping > /dev/null 2>&1; then
    log_warning "Redis not running. Starting Redis server..."
    redis-server --daemonize yes --port 6379
    sleep 2
fi

if ! psql -h localhost -p 5432 -U mcphub -d mcphub -c "SELECT 1" > /dev/null 2>&1; then
    log_error "PostgreSQL database not accessible. Please ensure database is running."
    exit 1
fi

log_success "All required services are running"

# Install/Update Python dependencies
log_info "Installing Python dependencies for Phase 2..."

cat > "$PROJECT_ROOT/requirements-whatsapp-phase2.txt" << 'EOF'
# Core WhatsApp Business API dependencies
twilio>=8.0.0
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
python-multipart>=0.0.6

# Database and caching
psycopg2-binary>=2.9.0
redis>=5.0.0

# Media processing
Pillow>=10.0.0
aiohttp>=3.9.0
aiofiles>=23.0.0
pydub>=0.25.0
SpeechRecognition>=3.10.0

# Executive Assistant integration
asyncio-mqtt>=0.16.0

# Performance and monitoring
prometheus-client>=0.19.0

# Development and testing
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-mock>=3.12.0
EOF

pip install -r "$PROJECT_ROOT/requirements-whatsapp-phase2.txt"

log_success "Python dependencies installed"

# Create media storage directory
log_info "Setting up media storage..."

sudo mkdir -p "$MEDIA_STORAGE_PATH"
sudo chown -R $(whoami):$(whoami) "$MEDIA_STORAGE_PATH"
chmod 755 "$MEDIA_STORAGE_PATH"

log_success "Media storage directory created at $MEDIA_STORAGE_PATH"

# Install Node.js dependencies for MCP server
log_info "Installing Node.js dependencies for MCP integration..."

cd "$PROJECT_ROOT/src/integrations"

if [ ! -f "package.json" ]; then
    npm init -y
fi

# Update package.json with Phase 2 dependencies
cat > package.json << 'EOF'
{
  "name": "whatsapp-business-mcp-phase2",
  "version": "2.1.0",
  "description": "Premium-casual WhatsApp Business API integration for AI Agency Platform Phase 2",
  "main": "whatsapp-business-mcp.js",
  "type": "module",
  "scripts": {
    "start": "node whatsapp-business-mcp.js",
    "test": "jest",
    "dev": "node --watch whatsapp-business-mcp.js"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.0.0",
    "axios": "^1.6.0",
    "express": "^4.18.0",
    "dotenv": "^16.3.0",
    "multer": "^1.4.5",
    "sharp": "^0.33.0",
    "ffmpeg-static": "^5.2.0"
  },
  "devDependencies": {
    "jest": "^29.7.0",
    "nodemon": "^3.0.0"
  }
}
EOF

npm install

log_success "Node.js dependencies installed"

# Create environment configuration
log_info "Setting up environment configuration..."

if [ ! -f "$PROJECT_ROOT/.env.whatsapp" ]; then
    cat > "$PROJECT_ROOT/.env.whatsapp" << 'EOF'
# WhatsApp Business API Configuration (Phase 2)
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_ACCESS_TOKEN=your_access_token
WHATSAPP_WEBHOOK_VERIFY_TOKEN=your_webhook_verify_token
WHATSAPP_BUSINESS_ACCOUNT_ID=your_business_account_id

# Phase 2 enhancements
WHATSAPP_MEDIA_STORAGE_PATH=/opt/whatsapp-media
WHATSAPP_MAX_CONCURRENT_USERS=500
WHATSAPP_RESPONSE_TIME_TARGET=3.0
WHATSAPP_PERSONALITY_TONE=premium-casual

# Database configuration
DATABASE_URL=postgresql://mcphub:mcphub_password@localhost:5432/mcphub
REDIS_URL=redis://localhost:6379

# Performance monitoring
ENABLE_METRICS=true
METRICS_PORT=9090

# Security
WEBHOOK_SECRET=your_webhook_secret_key
ENABLE_SIGNATURE_VALIDATION=true

# Logging
LOG_LEVEL=info
LOG_FORMAT=json
EOF

    log_warning "Environment file created at $PROJECT_ROOT/.env.whatsapp"
    log_warning "Please update with your actual WhatsApp Business API credentials"
else
    log_info "Environment file already exists"
fi

# Initialize database schema
log_info "Initializing enhanced database schema..."

cd "$PROJECT_ROOT"
source "$VENV_PATH/bin/activate"

python3 << 'EOF'
import asyncio
import sys
sys.path.append('src')
from communication.whatsapp_manager import whatsapp_manager

async def init_db():
    try:
        await whatsapp_manager.create_database_tables()
        print("✅ Database tables created successfully")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        sys.exit(1)

asyncio.run(init_db())
EOF

log_success "Database schema initialized"

# Create systemd service files
log_info "Creating systemd service files..."

sudo tee /etc/systemd/system/whatsapp-webhook-server.service > /dev/null << EOF
[Unit]
Description=WhatsApp Business Webhook Server (Phase 2)
After=network.target postgresql.service redis.service
Wants=postgresql.service redis.service

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$PROJECT_ROOT
Environment=PATH=$VENV_PATH/bin
ExecStart=$VENV_PATH/bin/python src/communication/webhook_server.py
EnvironmentFile=$PROJECT_ROOT/.env.whatsapp
Restart=always
RestartSec=10

# Performance settings for 500+ concurrent users
LimitNOFILE=65536
LimitNPROC=32768

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=whatsapp-webhook

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/whatsapp-mcp-server.service > /dev/null << EOF
[Unit]
Description=WhatsApp Business MCP Server (Phase 2)
After=network.target
Requires=whatsapp-webhook-server.service

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$PROJECT_ROOT/src/integrations
ExecStart=/usr/bin/node whatsapp-business-mcp.js
EnvironmentFile=$PROJECT_ROOT/.env.whatsapp
Restart=always
RestartSec=10

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=whatsapp-mcp

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable services
sudo systemctl daemon-reload
sudo systemctl enable whatsapp-webhook-server.service
sudo systemctl enable whatsapp-mcp-server.service

log_success "Systemd services created and enabled"

# Create deployment validation script
log_info "Creating deployment validation script..."

cat > "$PROJECT_ROOT/scripts/validate-whatsapp-deployment.py" << 'EOF'
#!/usr/bin/env python3
"""
WhatsApp Business API Phase 2 Deployment Validation Script
"""

import asyncio
import json
import sys
import aiohttp
from datetime import datetime

async def validate_deployment():
    """Validate WhatsApp deployment"""
    print("🔍 Validating WhatsApp Business API Phase 2 deployment...")
    
    validation_results = {
        'webhook_server': False,
        'database_connection': False,
        'redis_connection': False,
        'media_storage': False,
        'phase2_features': False
    }
    
    # Test webhook server
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('http://localhost:8000/health') as response:
                if response.status == 200:
                    health_data = await response.json()
                    validation_results['webhook_server'] = True
                    print("✅ Webhook server is running")
                    
                    # Check Phase 2 features
                    if 'phase_2_features' in health_data:
                        validation_results['phase2_features'] = True
                        print("✅ Phase 2 features enabled")
    except Exception as e:
        print(f"❌ Webhook server validation failed: {e}")
    
    # Test database connection
    try:
        import psycopg2
        conn = psycopg2.connect(
            host="localhost",
            database="mcphub",
            user="mcphub",
            password="mcphub_password"
        )
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            validation_results['database_connection'] = True
            print("✅ Database connection successful")
        conn.close()
    except Exception as e:
        print(f"❌ Database validation failed: {e}")
    
    # Test Redis connection
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        validation_results['redis_connection'] = True
        print("✅ Redis connection successful")
    except Exception as e:
        print(f"❌ Redis validation failed: {e}")
    
    # Test media storage
    import os
    media_path = "/opt/whatsapp-media"
    if os.path.exists(media_path) and os.access(media_path, os.W_OK):
        validation_results['media_storage'] = True
        print("✅ Media storage accessible")
    else:
        print(f"❌ Media storage validation failed: {media_path}")
    
    # Summary
    print("\n📊 Validation Summary:")
    total_checks = len(validation_results)
    passed_checks = sum(validation_results.values())
    
    for check, passed in validation_results.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {check.replace('_', ' ').title()}")
    
    print(f"\n🎯 Overall Status: {passed_checks}/{total_checks} checks passed")
    
    if passed_checks == total_checks:
        print("🚀 WhatsApp Business API Phase 2 deployment is ready!")
        return True
    else:
        print("⚠️  Some validation checks failed. Please review and fix issues.")
        return False

if __name__ == "__main__":
    success = asyncio.run(validate_deployment())
    sys.exit(0 if success else 1)
EOF

chmod +x "$PROJECT_ROOT/scripts/validate-whatsapp-deployment.py"

# Start services
log_info "Starting WhatsApp services..."

sudo systemctl start whatsapp-webhook-server.service
sudo systemctl start whatsapp-mcp-server.service

sleep 5

# Validate deployment
log_info "Running deployment validation..."

cd "$PROJECT_ROOT"
source "$VENV_PATH/bin/activate"

if python3 scripts/validate-whatsapp-deployment.py; then
    log_success "🎉 WhatsApp Business API Phase 2 deployment completed successfully!"
    
    echo ""
    echo "📋 Deployment Summary:"
    echo "  🔧 Webhook Server: http://localhost:8000"
    echo "  📱 WhatsApp endpoint: http://localhost:8000/webhook/whatsapp"
    echo "  🗄️  Media Storage: $MEDIA_STORAGE_PATH"
    echo "  📊 Health Check: http://localhost:8000/health"
    echo "  🔍 MCP Server: Running on stdio"
    echo ""
    echo "🎯 Phase 2 Features Enabled:"
    echo "  ✨ Premium-casual personality adaptation"
    echo "  📸 Media processing (images, documents, voice)"
    echo "  🏢 Business verification system"
    echo "  🔄 Cross-channel handoff"
    echo "  ⚡ Performance optimization for 500+ users"
    echo "  💾 Enhanced context preservation"
    echo ""
    echo "📝 Next Steps:"
    echo "  1. Update $PROJECT_ROOT/.env.whatsapp with your WhatsApp Business API credentials"
    echo "  2. Configure webhook URL in Facebook Developer Console"
    echo "  3. Test with: curl http://localhost:8000/health"
    echo "  4. Monitor logs: sudo journalctl -u whatsapp-webhook-server -f"
    echo ""
    
else
    log_error "❌ Deployment validation failed. Please check the logs and fix issues."
    echo ""
    echo "🔍 Troubleshooting:"
    echo "  - Check service status: sudo systemctl status whatsapp-webhook-server"
    echo "  - View logs: sudo journalctl -u whatsapp-webhook-server -n 50"
    echo "  - Test database: psql -h localhost -U mcphub -d mcphub -c 'SELECT 1'"
    echo "  - Test Redis: redis-cli ping"
    exit 1
fi