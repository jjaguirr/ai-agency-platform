#!/usr/bin/env bash
# Tear down local development environment
set -euo pipefail

echo "Tearing down AI Agency Platform development environment..."

docker compose down -v

echo "All services stopped and volumes removed."
