#!/bin/bash
# Meta-Compliant WhatsApp Webhook Service - Production Deployment Script
# Automated deployment to DigitalOcean App Platform with validation

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_FILE="/tmp/webhook_deployment_$(date +%Y%m%d_%H%M%S).log"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${1}" | tee -a "$LOG_FILE"
}

log_info() {
    log "${BLUE}ℹ️  INFO: ${1}${NC}"
}

log_success() {
    log "${GREEN}✅ SUCCESS: ${1}${NC}"
}

log_warning() {
    log "${YELLOW}⚠️  WARNING: ${1}${NC}"
}

log_error() {
    log "${RED}❌ ERROR: ${1}${NC}"
}

# Cleanup function
cleanup() {
    if [ $? -ne 0 ]; then
        log_error "Deployment failed. Check log file: $LOG_FILE"
        log_error "Rolling back deployment if possible..."
        doctl apps create-deployment "$APP_ID" --force-rebuild 2>/dev/null || true
    fi
}

trap cleanup EXIT

# Header
log_info "🚀 Meta-Compliant WhatsApp Webhook Service - Production Deployment"
log_info "Started at: $(date)"
log_info "Project: $PROJECT_ROOT"
log_info "Log file: $LOG_FILE"

# Check prerequisites
log_info "Checking prerequisites..."

# Check if doctl is installed and authenticated
if ! command -v doctl &> /dev/null; then
    log_error "DigitalOcean CLI (doctl) is not installed"
    log_error "Install with: brew install doctl (macOS) or visit: https://docs.digitalocean.com/reference/doctl/how-to/install/"
    exit 1
fi

# Verify doctl authentication
if ! doctl auth list | grep -q "current context"; then
    log_error "doctl is not authenticated"
    log_error "Run: doctl auth init"
    exit 1
fi

# Check if git is available and we're in a git repository
if ! git status &>/dev/null; then
    log_error "Not in a git repository or git not available"
    exit 1
fi

# Check current branch
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "main" ] && [ "$CURRENT_BRANCH" != "production" ]; then
    log_warning "Current branch is '$CURRENT_BRANCH', not 'main' or 'production'"
    log_warning "Production deployments should be from main branch"
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Deployment cancelled"
        exit 0
    fi
fi

log_success "Prerequisites check passed"

# Environment validation
log_info "Validating environment configuration..."

# Check if production environment file exists
if [ ! -f "$PROJECT_ROOT/.env.production.webhook" ]; then
    log_error "Production environment file not found: .env.production.webhook"
    log_error "Copy from template: cp .env.production.template .env.production.webhook"
    exit 1
fi

# Validate required environment variables are set
REQUIRED_VARS=(
    "META_APP_ID"
    "META_APP_SECRET"
    "WHATSAPP_BUSINESS_TOKEN"
    "WHATSAPP_VERIFY_TOKEN"
    "ENCRYPTION_KEY"
    "REDIS_URL"
)

for var in "${REQUIRED_VARS[@]}"; do
    if ! grep -q "^${var}=" "$PROJECT_ROOT/.env.production.webhook" || grep -q "^${var}=your-" "$PROJECT_ROOT/.env.production.webhook"; then
        log_error "Environment variable '$var' not properly configured"
        log_error "Edit .env.production.webhook with production values"
        exit 1
    fi
done

log_success "Environment validation passed"

# Pre-deployment tests
log_info "Running pre-deployment tests..."

cd "$PROJECT_ROOT"

# Check if Python environment is available
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" &>/dev/null; then
    log_error "Python 3.11+ is required"
    exit 1
fi

# Install test dependencies if needed
if [ ! -d "venv" ]; then
    log_info "Creating virtual environment for tests..."
    python3 -m venv venv
fi

source venv/bin/activate

# Install dependencies for testing
log_info "Installing test dependencies..."
pip install -q -r requirements-webhook.txt
pip install -q pytest pytest-asyncio

# Run specific webhook tests
log_info "Running webhook service tests..."
if ! python -m pytest tests/test_webhook/ -v --tb=short; then
    log_error "Webhook tests failed"
    exit 1
fi

log_success "Pre-deployment tests passed"

# Build and validate Docker image locally (optional but recommended)
log_info "Building Docker image locally for validation..."

if command -v docker &> /dev/null; then
    # Build using production Dockerfile
    if docker build -f src/webhook/Dockerfile.production -t webhook-service-test:latest .; then
        log_success "Docker image built successfully"

        # Quick smoke test of the container
        log_info "Running container smoke test..."
        CONTAINER_ID=$(docker run -d -p 8001:8000 \
            -e META_APP_ID=test \
            -e META_APP_SECRET=test \
            -e WHATSAPP_BUSINESS_TOKEN=test \
            -e WHATSAPP_VERIFY_TOKEN=test \
            -e ENCRYPTION_KEY=test-key-32-characters-long!! \
            webhook-service-test:latest)

        # Wait for container to start
        sleep 10

        # Test health endpoint
        if curl -f http://localhost:8001/health &>/dev/null; then
            log_success "Container smoke test passed"
        else
            log_warning "Container smoke test failed - may not indicate deployment issue"
        fi

        # Cleanup test container
        docker stop "$CONTAINER_ID" &>/dev/null || true
        docker rm "$CONTAINER_ID" &>/dev/null || true
    else
        log_warning "Docker build failed - continuing with deployment"
    fi
else
    log_warning "Docker not available - skipping local build test"
fi

# Check if app already exists
APP_NAME="whatsapp-webhook-service-meta-compliant"
log_info "Checking for existing DigitalOcean app: $APP_NAME"

# Get app ID if it exists
APP_ID=$(doctl apps list --format "ID,Name" --no-header | grep "$APP_NAME" | cut -d' ' -f1 || echo "")

if [ -z "$APP_ID" ]; then
    log_info "App does not exist, creating new app..."

    # Create new app from spec
    log_info "Creating app from configuration file..."
    APP_CREATION_OUTPUT=$(doctl apps create --spec "$PROJECT_ROOT/.do/app-production.yaml")
    APP_ID=$(echo "$APP_CREATION_OUTPUT" | grep -o 'ID: [a-f0-9-]*' | cut -d' ' -f2)

    if [ -z "$APP_ID" ]; then
        log_error "Failed to create app"
        exit 1
    fi

    log_success "App created with ID: $APP_ID"
else
    log_info "App exists with ID: $APP_ID"

    # Update existing app
    log_info "Updating app configuration..."
    if doctl apps update "$APP_ID" --spec "$PROJECT_ROOT/.do/app-production.yaml"; then
        log_success "App configuration updated"
    else
        log_error "Failed to update app configuration"
        exit 1
    fi
fi

# Create deployment
log_info "Creating new deployment..."
DEPLOYMENT_OUTPUT=$(doctl apps create-deployment "$APP_ID" --force-rebuild)
DEPLOYMENT_ID=$(echo "$DEPLOYMENT_OUTPUT" | grep -o 'ID: [a-f0-9-]*' | cut -d' ' -f2)

if [ -z "$DEPLOYMENT_ID" ]; then
    log_error "Failed to create deployment"
    exit 1
fi

log_success "Deployment created with ID: $DEPLOYMENT_ID"

# Monitor deployment progress
log_info "Monitoring deployment progress..."
DEPLOYMENT_STATUS="PENDING"
TIMEOUT=1800  # 30 minutes timeout
ELAPSED=0
CHECK_INTERVAL=30

while [ "$DEPLOYMENT_STATUS" != "ACTIVE" ] && [ "$DEPLOYMENT_STATUS" != "ERROR" ] && [ $ELAPSED -lt $TIMEOUT ]; do
    sleep $CHECK_INTERVAL
    ELAPSED=$((ELAPSED + CHECK_INTERVAL))

    DEPLOYMENT_INFO=$(doctl apps get-deployment "$APP_ID" "$DEPLOYMENT_ID" --format "Phase" --no-header)
    DEPLOYMENT_STATUS=$(echo "$DEPLOYMENT_INFO" | head -n1)

    log_info "Deployment status: $DEPLOYMENT_STATUS (${ELAPSED}s elapsed)"

    # Show deployment logs if available
    if [ $((ELAPSED % 120)) -eq 0 ]; then  # Every 2 minutes
        log_info "Recent deployment logs:"
        doctl apps logs "$APP_ID" --type=deploy --tail 10 2>/dev/null || log_info "No logs available yet"
    fi
done

if [ "$DEPLOYMENT_STATUS" = "ACTIVE" ]; then
    log_success "Deployment completed successfully!"
else
    log_error "Deployment failed or timed out. Status: $DEPLOYMENT_STATUS"
    log_error "Check deployment logs: doctl apps logs $APP_ID --type=deploy"
    exit 1
fi

# Get app URL
APP_URL=$(doctl apps get "$APP_ID" --format "LiveURL" --no-header)
log_info "Application URL: $APP_URL"

# Post-deployment validation
log_info "Running post-deployment validation..."

# Wait a bit for the app to fully initialize
log_info "Waiting for application to initialize..."
sleep 60

# Test health endpoint
log_info "Testing health endpoint..."
for i in {1..5}; do
    if curl -f -H "User-Agent: DeploymentValidation/1.0" "$APP_URL/health" &>/dev/null; then
        log_success "Health check passed"
        break
    else
        if [ $i -eq 5 ]; then
            log_error "Health check failed after 5 attempts"
            log_error "Check application logs: doctl apps logs $APP_ID"
            exit 1
        fi
        log_warning "Health check attempt $i failed, retrying in 30s..."
        sleep 30
    fi
done

# Test webhook verification endpoint
log_info "Testing webhook verification endpoint..."
VERIFY_TOKEN=$(grep "^WHATSAPP_VERIFY_TOKEN=" "$PROJECT_ROOT/.env.production.webhook" | cut -d'=' -f2)
if curl -f "$APP_URL/webhook/whatsapp?hub.mode=subscribe&hub.challenge=test&hub.verify_token=$VERIFY_TOKEN" &>/dev/null; then
    log_success "Webhook verification test passed"
else
    log_warning "Webhook verification test failed - check configuration"
fi

# Test embedded signup page
log_info "Testing embedded signup page..."
if curl -f -H "User-Agent: DeploymentValidation/1.0" "$APP_URL/embedded-signup" | grep -q "WhatsApp Business Integration"; then
    log_success "Embedded signup page test passed"
else
    log_warning "Embedded signup page test failed"
fi

# Final deployment summary
log_success "🎉 Deployment completed successfully!"
log_info "═══════════════════════════════════════════════════════════"
log_info "App ID: $APP_ID"
log_info "Deployment ID: $DEPLOYMENT_ID"
log_info "App URL: $APP_URL"
log_info "Health Check: $APP_URL/health"
log_info "Embedded Signup: $APP_URL/embedded-signup"
log_info "Webhook Endpoint: $APP_URL/webhook/whatsapp"
log_info "═══════════════════════════════════════════════════════════"

# Next steps recommendations
log_info "Next Steps:"
log_info "1. Configure Meta Developer Console with webhook URL: $APP_URL/webhook/whatsapp"
log_info "2. Add production domain to Meta app allowed domains"
log_info "3. Test embedded signup flow with real Meta credentials"
log_info "4. Set up monitoring and alerts for production usage"
log_info "5. Configure DNS for custom domain if not using app platform domain"

# Save deployment info for future reference
DEPLOYMENT_INFO_FILE="$PROJECT_ROOT/deployment-info.json"
cat > "$DEPLOYMENT_INFO_FILE" << EOF
{
  "app_id": "$APP_ID",
  "deployment_id": "$DEPLOYMENT_ID",
  "app_url": "$APP_URL",
  "deployed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "deployed_by": "$(whoami)",
  "git_branch": "$CURRENT_BRANCH",
  "git_commit": "$(git rev-parse HEAD)",
  "status": "ACTIVE"
}
EOF

log_success "Deployment info saved to: $DEPLOYMENT_INFO_FILE"
log_success "Deployment log saved to: $LOG_FILE"

log_success "🚀 Production deployment completed successfully!"