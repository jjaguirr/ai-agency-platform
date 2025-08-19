#!/bin/bash
# Test Claude Code <-> Infrastructure agent communication

echo "📡 Testing cross-system communication..."

# Test Redis message bus
echo "Testing Redis connectivity..."
docker exec ai-agency-platform-redis-1 redis-cli ping

# Test message publishing
echo "Testing message publishing..."
docker exec ai-agency-platform-redis-1 redis-cli publish "claude-code:messages" '{"type":"test","message":"Hello from Claude Code","timestamp":"'$(date -Iseconds)'"}'

# Test message subscribing (in background)
echo "Testing message subscription (5 second test)..."
timeout 5s docker exec ai-agency-platform-redis-1 redis-cli subscribe "infrastructure:messages" &

# Test cross-system message storage
echo "Testing cross-system message storage..."
docker exec postgres psql -U postgres -d mcphub -c "
INSERT INTO cross_system_messages (source_system, target_system, message_type, payload) 
VALUES ('claude-code', 'infrastructure', 'status-update', '{\"status\": \"test-complete\", \"agent\": \"technical-lead\"}');"

echo "Retrieving stored messages..."
docker exec postgres psql -U postgres -d mcphub -c "SELECT * FROM cross_system_messages;"

echo "📡 Cross-system communication tests completed"