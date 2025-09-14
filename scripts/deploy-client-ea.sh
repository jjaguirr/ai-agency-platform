#!/bin/bash
# Deploy Client EA with WhatsApp Bridge
# This script sets up a client EA deployment that connects to the centralized WhatsApp webhook service

set -e

echo "🚀 Deploying Client EA with WhatsApp Integration"
echo "================================================"

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

# Configuration
DEPLOYMENT_TYPE=${1:-"docker"}  # docker, kubernetes, docker-compose
CLIENT_ENV_FILE=${2:-".env.client"}

# Validate deployment type
if [[ ! "$DEPLOYMENT_TYPE" =~ ^(docker|kubernetes|docker-compose)$ ]]; then
    log_error "Invalid deployment type. Use: docker, kubernetes, or docker-compose"
    exit 1
fi

# Check if client environment file exists
if [ ! -f "$CLIENT_ENV_FILE" ]; then
    log_error "Client environment file not found: $CLIENT_ENV_FILE"
    log_info "Please create $CLIENT_ENV_FILE with the following variables:"
    cat << 'EOF'
# Client EA WhatsApp Configuration
CUSTOMER_ID=your-unique-client-id
WHATSAPP_PHONE_NUMBER=your-business-phone-number
WHATSAPP_WEBHOOK_SERVICE_URL=https://your-webhook-service.ondigitalocean.app
EA_AUTH_TOKEN=your-secure-authentication-token
MCP_PORT=8001

# EA Dependencies
OPENAI_API_KEY=your-openai-api-key
POSTGRES_URL=postgresql://user:password@localhost:5432/database
REDIS_URL=redis://localhost:6379

# Optional
ELEVENLABS_API_KEY=your-elevenlabs-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key
EOF
    exit 1
fi

# Load client environment
source "$CLIENT_ENV_FILE"

# Validate required environment variables
REQUIRED_VARS=(
    "CUSTOMER_ID"
    "WHATSAPP_PHONE_NUMBER"
    "WHATSAPP_WEBHOOK_SERVICE_URL"
    "EA_AUTH_TOKEN"
    "OPENAI_API_KEY"
    "POSTGRES_URL"
)

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        log_error "Required environment variable not set: $var"
        exit 1
    fi
done

log_info "Client Configuration:"
log_info "  Customer ID: $CUSTOMER_ID"
log_info "  Phone Number: $WHATSAPP_PHONE_NUMBER"
log_info "  Webhook Service: $WHATSAPP_WEBHOOK_SERVICE_URL"
log_info "  MCP Port: ${MCP_PORT:-8001}"
log_info "  Deployment Type: $DEPLOYMENT_TYPE"

# Test webhook service connectivity
log_info "Testing webhook service connectivity..."
if curl -f "$WHATSAPP_WEBHOOK_SERVICE_URL/health" > /dev/null 2>&1; then
    log_success "Webhook service is accessible"
else
    log_error "Cannot reach webhook service at $WHATSAPP_WEBHOOK_SERVICE_URL"
    log_error "Please verify the URL and network connectivity"
    exit 1
fi

# Create deployment directory
DEPLOY_DIR="deployment/$CUSTOMER_ID"
mkdir -p "$DEPLOY_DIR"
log_info "Created deployment directory: $DEPLOY_DIR"

# Copy client environment
cp "$CLIENT_ENV_FILE" "$DEPLOY_DIR/.env"

case "$DEPLOYMENT_TYPE" in
    "docker")
        deploy_docker
        ;;
    "kubernetes")
        deploy_kubernetes
        ;;
    "docker-compose")
        deploy_docker_compose
        ;;
esac

log_success "🎉 Client EA deployment completed!"

# Display connection information
echo ""
echo "📋 Deployment Summary:"
echo "  🏢 Customer: $CUSTOMER_ID"
echo "  📱 Phone: $WHATSAPP_PHONE_NUMBER"
echo "  🔗 EA Bridge: http://localhost:${MCP_PORT:-8001}"
echo "  📊 Health Check: http://localhost:${MCP_PORT:-8001}/health"
echo "  🌐 Webhook Service: $WHATSAPP_WEBHOOK_SERVICE_URL"
echo ""
echo "🔍 Monitoring:"
echo "  📈 Bridge Status: curl http://localhost:${MCP_PORT:-8001}/health"
echo "  📋 Registered Clients: curl $WHATSAPP_WEBHOOK_SERVICE_URL/ea/clients"
echo "  📊 Service Health: curl $WHATSAPP_WEBHOOK_SERVICE_URL/health"
echo ""

deploy_docker() {
    log_info "Deploying with Docker..."

    # Build EA bridge image if needed
    if ! docker image inspect ai-agency/ea-whatsapp-bridge:latest > /dev/null 2>&1; then
        log_info "Building EA WhatsApp Bridge image..."
        docker build -t ai-agency/ea-whatsapp-bridge:latest -f src/communication/Dockerfile.ea-bridge .
    fi

    # Stop existing container
    docker stop "ea-bridge-$CUSTOMER_ID" 2>/dev/null || true
    docker rm "ea-bridge-$CUSTOMER_ID" 2>/dev/null || true

    # Run EA bridge container
    log_info "Starting EA WhatsApp Bridge container..."
    docker run -d \
        --name "ea-bridge-$CUSTOMER_ID" \
        --restart unless-stopped \
        -p "${MCP_PORT:-8001}:8001" \
        --env-file "$DEPLOY_DIR/.env" \
        -v "$PWD/logs:/app/logs" \
        ai-agency/ea-whatsapp-bridge:latest

    # Wait for container to start
    sleep 5

    # Check container health
    if docker ps | grep -q "ea-bridge-$CUSTOMER_ID"; then
        log_success "EA Bridge container is running"

        # Test health endpoint
        if curl -f "http://localhost:${MCP_PORT:-8001}/health" > /dev/null 2>&1; then
            log_success "EA Bridge is healthy and accepting connections"
        else
            log_warning "EA Bridge container is running but health check failed"
        fi
    else
        log_error "EA Bridge container failed to start"
        docker logs "ea-bridge-$CUSTOMER_ID" --tail 20
        exit 1
    fi
}

deploy_kubernetes() {
    log_info "Deploying with Kubernetes..."

    # Create namespace
    kubectl create namespace "ea-$CUSTOMER_ID" --dry-run=client -o yaml | kubectl apply -f -

    # Create secret for environment variables
    kubectl create secret generic "ea-config-$CUSTOMER_ID" \
        --from-env-file="$DEPLOY_DIR/.env" \
        --namespace="ea-$CUSTOMER_ID" \
        --dry-run=client -o yaml | kubectl apply -f -

    # Create Kubernetes deployment manifest
    cat > "$DEPLOY_DIR/kubernetes-deployment.yaml" << EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ea-whatsapp-bridge
  namespace: ea-$CUSTOMER_ID
  labels:
    app: ea-whatsapp-bridge
    customer: $CUSTOMER_ID
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ea-whatsapp-bridge
  template:
    metadata:
      labels:
        app: ea-whatsapp-bridge
        customer: $CUSTOMER_ID
    spec:
      containers:
      - name: ea-bridge
        image: ai-agency/ea-whatsapp-bridge:latest
        ports:
        - containerPort: 8001
          name: mcp-port
        envFrom:
        - secretRef:
            name: ea-config-$CUSTOMER_ID
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
            port: 8001
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8001
          initialDelaySeconds: 5
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: ea-whatsapp-bridge-service
  namespace: ea-$CUSTOMER_ID
spec:
  selector:
    app: ea-whatsapp-bridge
  ports:
  - protocol: TCP
    port: 8001
    targetPort: 8001
  type: ClusterIP
EOF

    # Apply Kubernetes deployment
    kubectl apply -f "$DEPLOY_DIR/kubernetes-deployment.yaml"

    # Wait for deployment
    log_info "Waiting for Kubernetes deployment..."
    kubectl wait --for=condition=available --timeout=300s \
        deployment/ea-whatsapp-bridge -n "ea-$CUSTOMER_ID"

    log_success "Kubernetes deployment completed"

    # Show pod status
    kubectl get pods -n "ea-$CUSTOMER_ID"
}

deploy_docker_compose() {
    log_info "Deploying with Docker Compose..."

    # Create docker-compose file for client
    cat > "$DEPLOY_DIR/docker-compose.client.yml" << EOF
version: '3.8'

services:
  # Client EA with WhatsApp Bridge
  ea-whatsapp-bridge:
    build:
      context: ../../
      dockerfile: src/communication/Dockerfile.ea-bridge
    container_name: ea-bridge-$CUSTOMER_ID
    ports:
      - "${MCP_PORT:-8001}:8001"
    env_file:
      - .env
    volumes:
      - ../../logs:/app/logs
      - ../../src:/app/src:ro
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    networks:
      - ea-network

  # Local PostgreSQL (optional - clients can use their own)
  postgres:
    image: postgres:15-alpine
    container_name: postgres-$CUSTOMER_ID
    environment:
      POSTGRES_DB: ea_client
      POSTGRES_USER: ea_user
      POSTGRES_PASSWORD: ea_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - ea-network

  # Local Redis (optional - clients can use their own)
  redis:
    image: redis:7-alpine
    container_name: redis-$CUSTOMER_ID
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    networks:
      - ea-network

networks:
  ea-network:
    driver: bridge
    name: ea-network-$CUSTOMER_ID

volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local
EOF

    # Start services
    cd "$DEPLOY_DIR"
    docker-compose -f docker-compose.client.yml up -d
    cd - > /dev/null

    # Wait for services
    sleep 10

    # Check service health
    if curl -f "http://localhost:${MCP_PORT:-8001}/health" > /dev/null 2>&1; then
        log_success "Docker Compose deployment successful"
    else
        log_error "Docker Compose deployment failed"
        cd "$DEPLOY_DIR"
        docker-compose -f docker-compose.client.yml logs
        cd - > /dev/null
        exit 1
    fi
}

# Cleanup function
cleanup() {
    log_info "Cleaning up temporary files..."
    # Add any cleanup tasks here
}

# Set trap for cleanup
trap cleanup EXIT

# Test final connectivity
log_info "Testing WhatsApp integration..."
sleep 5

# Check if EA bridge registered successfully
REGISTERED_CLIENTS=$(curl -s "$WHATSAPP_WEBHOOK_SERVICE_URL/ea/clients" | jq -r '.clients[] | select(.customer_id=="'$CUSTOMER_ID'") | .client_id' 2>/dev/null || echo "")

if [ -n "$REGISTERED_CLIENTS" ]; then
    log_success "✅ EA Bridge successfully registered with webhook service"
    log_success "🎯 Client EA is ready to receive WhatsApp messages!"
else
    log_warning "⚠️ EA Bridge may not be registered yet. Check logs:"
    echo "  docker logs ea-bridge-$CUSTOMER_ID"
    echo "  curl http://localhost:${MCP_PORT:-8001}/health"
fi

echo ""
log_info "🚀 Deployment complete! Your EA is now connected to WhatsApp."