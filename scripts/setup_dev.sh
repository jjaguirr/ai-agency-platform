#!/usr/bin/env bash
# Set up local development environment
set -euo pipefail

echo "Setting up AI Agency Platform development environment..."

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed"
    exit 1
fi

# Start services
echo "Starting Docker services..."
docker compose up -d

# Wait for healthy
echo "Waiting for services to be healthy..."
for service in postgres redis qdrant neo4j; do
    echo -n "  $service: "
    for i in $(seq 1 30); do
        if docker compose ps "$service" | grep -q healthy; then
            echo "ready"
            break
        fi
        sleep 2
    done
done

# Install Python deps
if [ -f pyproject.toml ]; then
    echo "Installing Python dependencies..."
    pip install -e ".[dev]" --quiet
fi

echo "Development environment ready."
