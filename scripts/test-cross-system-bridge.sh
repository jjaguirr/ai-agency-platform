#!/bin/bash

# AI Agency Platform - Cross-System Message Bridge Test
# Infrastructure Engineer: Validate Redis pub/sub for dual-agent communication

set -e

echo "🌉 Testing Cross-System Message Bridge..."
echo "========================================"

# Test Redis pub/sub communication
echo "Testing Redis pub/sub channels..."

# Create test message
TEST_MESSAGE="Infrastructure-Agent-Bridge-Test-$(date +%s)"

# Start subscriber in background and capture output
redis-cli -p 6379 subscribe "dual-agent-bridge" "claude-code-bridge" "infrastructure-bridge" > /tmp/redis_bridge_test.log 2>&1 &
SUBSCRIBER_PID=$!

echo "Started Redis subscriber (PID: $SUBSCRIBER_PID)"
sleep 2

# Publish test messages to different channels
echo "Publishing test messages..."
redis-cli -p 6379 publish "dual-agent-bridge" "$TEST_MESSAGE" > /dev/null
redis-cli -p 6379 publish "claude-code-bridge" "Claude-Code-Test-$(date +%s)" > /dev/null
redis-cli -p 6379 publish "infrastructure-bridge" "Infrastructure-Test-$(date +%s)" > /dev/null

sleep 3

# Stop subscriber
kill $SUBSCRIBER_PID 2>/dev/null || true

echo ""
echo "Bridge test results:"
echo "==================="

if grep -q "$TEST_MESSAGE" /tmp/redis_bridge_test.log; then
    echo "✅ dual-agent-bridge channel: OPERATIONAL"
else
    echo "❌ dual-agent-bridge channel: FAILED"
fi

if grep -q "Claude-Code-Test" /tmp/redis_bridge_test.log; then
    echo "✅ claude-code-bridge channel: OPERATIONAL"
else
    echo "❌ claude-code-bridge channel: FAILED"
fi

if grep -q "Infrastructure-Test" /tmp/redis_bridge_test.log; then
    echo "✅ infrastructure-bridge channel: OPERATIONAL"
else
    echo "❌ infrastructure-bridge channel: FAILED"
fi

echo ""
echo "Setting up persistent message channels for dual-agent system..."

# Set up Redis configuration for persistent channels
redis-cli -p 6379 CONFIG SET notify-keyspace-events Ex > /dev/null

echo "✅ Redis message bridge configured for dual-agent architecture"
echo ""
echo "Available channels:"
echo "- dual-agent-bridge: Cross-system coordination"
echo "- claude-code-bridge: Claude Code agent updates"
echo "- infrastructure-bridge: Infrastructure agent updates"

# Clean up
rm -f /tmp/redis_bridge_test.log