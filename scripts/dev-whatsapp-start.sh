#!/bin/bash
# Start local WhatsApp development environment
# This starts the webhook service and EA client simulator

set -e

echo "🚀 Starting WhatsApp Development Environment"
echo "============================================"

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

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    log_error "Docker is not running. Please start Docker and try again."
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    log_error ".env file not found. Please create it from .env.example"
    exit 1
fi

# Create logs directories
log_info "Creating log directories..."
mkdir -p logs/webhook
mkdir -p logs/ea-client

# Stop any existing containers
log_info "Stopping existing WhatsApp containers..."
docker compose stop whatsapp-webhook ea-client-simulator 2>/dev/null || true
docker compose rm -f whatsapp-webhook ea-client-simulator 2>/dev/null || true

# Start core infrastructure if not running
log_info "Starting core infrastructure..."
docker compose up -d postgres redis qdrant

# Wait for core services
log_info "Waiting for core services to be ready..."
sleep 10

# Build and start WhatsApp services
log_info "Building WhatsApp services..."
docker compose build whatsapp-webhook ea-client-simulator

log_info "Starting WhatsApp Webhook Service..."
docker compose up -d whatsapp-webhook

# Wait for webhook service
log_info "Waiting for webhook service to be ready..."
sleep 5

# Check webhook service health
if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    log_success "Webhook service is healthy"
else
    log_warning "Webhook service may not be ready yet"
fi

log_info "Starting EA Client Simulator..."
docker compose up -d ea-client-simulator

# Wait for EA client
log_info "Waiting for EA client simulator to be ready..."
sleep 5

# Check EA client health
if curl -f http://localhost:8001/health > /dev/null 2>&1; then
    log_success "EA client simulator is healthy"
else
    log_warning "EA client simulator may not be ready yet"
fi

echo ""
log_success "🎉 WhatsApp Development Environment Started!"
echo ""
echo "📋 Service URLs:"
echo "  🔗 Webhook Service: http://localhost:8000"
echo "  🤖 EA Client Simulator: http://localhost:8001"
echo "  📊 Health Checks: http://localhost:8000/health"
echo "  📱 WhatsApp Webhook: http://localhost:8000/webhook/whatsapp"
echo ""
echo "🧪 Testing:"
echo "  📝 Test webhook: curl http://localhost:8000/test"
echo "  🔍 List EA clients: curl http://localhost:8000/ea/clients"
echo "  💓 EA health: curl http://localhost:8001/health"
echo ""
echo "📊 Monitoring:"
echo "  📈 View logs: docker compose logs -f whatsapp-webhook ea-client-simulator"
echo "  🔍 Webhook logs: docker compose logs -f whatsapp-webhook"
echo "  🤖 EA logs: docker compose logs -f ea-client-simulator"
echo ""
echo "🛑 To stop: ./scripts/dev-whatsapp-stop.sh"
echo ""

# Show running containers
log_info "Running containers:"
docker compose ps whatsapp-webhook ea-client-simulator

echo ""
log_info "🔧 Development setup complete!"
log_info "🚀 Ready for WhatsApp webhook testing and EA integration development"