#!/usr/bin/env bash
# Run test suite with proper markers
set -euo pipefail

MODE="${1:-unit}"

case "$MODE" in
    unit)
        echo "Running unit tests..."
        pytest tests/unit/ -v --tb=short
        ;;
    integration)
        echo "Running integration tests (requires Docker services)..."
        pytest tests/integration/ -v --tb=short -m integration
        ;;
    e2e)
        echo "Running e2e tests (requires full stack)..."
        pytest tests/e2e/ -v --tb=short -m e2e
        ;;
    all)
        echo "Running all tests..."
        pytest tests/ -v --tb=short
        ;;
    *)
        echo "Usage: $0 {unit|integration|e2e|all}"
        exit 1
        ;;
esac
