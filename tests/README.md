# Test Organization

## Directory Structure

### `/unit/` - Unit Tests
- `test_ea_core_modern.py` - Core EA functionality tests
- Tests isolated components with minimal dependencies

#### `/unit/proactive/` - Proactive Intelligence

All tests use `fakeredis.aioredis` for Redis and `pytest-asyncio` for async.

| File | What it covers |
|---|---|
| `test_heartbeat.py` | Daemon lifecycle (start/stop), tick iteration, concurrency timeouts, settings cache wiring with clock injection |
| `test_behaviors.py` | Morning briefing (timezone, dedup, personalization by tone), follow-up tracker (deadline proximity, overdue), idle nudge (idle period, cooldown) |
| `test_gate.py` | Noise gate filter chain: cooldown, priority threshold, quiet hours (midnight wrap), daily cap, URGENT bypass |
| `test_state.py` | Redis state store: cooldowns, briefing time, follow-ups, daily count, pending notifications, notification lifecycle (add/read/snooze/dismiss/TTL/isolation) |
| `test_settings_cache.py` | Per-customer config from Redis: defaults, quiet hours derived from inverted working hours, TTL caching, personality passthrough |
| `test_outbound.py` | DefaultOutboundDispatcher: WhatsApp delivery with argument verification, persistent notification storage, failure resilience |
| `test_finance_proactive.py` | Transaction tracking (stats, latest), anomaly detection (threshold, configurable multiplier, boundary at exactly 2.0x), payload content |
| `test_scheduling_proactive.py` | Calendar conflict detection: overlap in 24h window, payload with event details, no-calendar graceful degradation |
| `test_workflow_health.py` | n8n execution failure detection: error/crashed statuses, multiple workflows, cooldown keys, client error resilience |
| `test_customer_aware_heartbeat.py` | Integration: priority threshold routing, quiet hours from working hours (boundary at exact start/end), daily cap, briefing config passthrough, defaults fallback |

#### `/unit/api/` - API Endpoint Tests

| File | What it covers |
|---|---|
| `test_notifications.py` | GET listing (persistent + legacy, priority ordering, tenant isolation), POST read/snooze/dismiss lifecycle, snooze-reappear after expiry, 404 on nonexistent, auth required |
| `test_settings.py` | PUT/GET roundtrip for all dashboard settings including proactive thresholds and personality |

### `/integration/` - Integration Tests  
- `test_real_executive_assistant.py` - Full EA integration with real services
- `test_integration_docker.py` - Docker service integration tests
- Tests components working together with real dependencies

### `/acceptance/` - User Acceptance Tests
- `test_customer_scenarios.py` - End-to-end customer scenarios
- Tests complete user journeys and business requirements

### `/demos/` - Demonstration Scripts
- `demo_enhanced_ea.py` - Shows sophisticated LangGraph conversation management
- Executable examples for understanding system capabilities

### `/legacy/` - Historical Test Files
- `test_enhanced_ea.py` - Previous test iterations
- `test_enhanced_ea_fixed.py` - Fixed version with LangGraph testing patterns
- `test_ea_basic.py` - Simple CI test with mocks
- `test_mcp_memory_integration.py` - Old MCP memory tests (now using Mem0)
- **Note**: These may contain useful test patterns for reference

## Running Tests

### Quick Test (Current working tests)
```bash
./scripts/quick_test.sh
```

### Full Test Suite
```bash
# Unit tests (fast)
pytest tests/unit/ -v

# Integration tests (requires services)
docker-compose up redis postgres
pytest tests/integration/ -v

# All tests
pytest tests/ -v --ignore=tests/legacy --ignore=tests/demos
```

### Demo Scripts
```bash
# Show EA capabilities
python tests/demos/demo_enhanced_ea.py
```

## Test Configuration
- `conftest.py` - Shared fixtures and configuration
- `pytest.ini` - Pytest settings

## Current Status
- ✅ Unit tests: Basic structure in place
- 🔧 Integration tests: Need async fixture fixes  
- 📝 Acceptance tests: Framework ready
- ✅ Demos: Working examples available
- 📚 Legacy: Historical implementations preserved