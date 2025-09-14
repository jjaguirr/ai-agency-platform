#!/bin/bash
# Stop WhatsApp development environment

set -e

echo "🛑 Stopping WhatsApp Development Environment"
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

# Stop WhatsApp services
log_info "Stopping WhatsApp services..."
docker compose stop whatsapp-webhook ea-client-simulator

# Remove containers
log_info "Removing WhatsApp containers..."
docker compose rm -f whatsapp-webhook ea-client-simulator

# Optionally stop all services
if [ "$1" = "all" ]; then
    log_info "Stopping all services..."
    docker compose down
fi

log_success "✅ WhatsApp development environment stopped"

if [ "$1" = "all" ]; then
    echo ""
    echo "🔧 All services stopped. To restart:"
    echo "  🚀 Full stack: docker compose up -d"
    echo "  📱 WhatsApp only: ./scripts/dev-whatsapp-start.sh"
else
    echo ""
    echo "🔧 WhatsApp services stopped. Core infrastructure still running."
    echo "  🚀 Restart: ./scripts/dev-whatsapp-start.sh"
    echo "  🛑 Stop all: ./scripts/dev-whatsapp-stop.sh all"
fi