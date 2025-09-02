# Test Organization

## Directory Structure

### `/unit/` - Unit Tests
- `test_ea_core_modern.py` - Core EA functionality tests
- Tests isolated components with minimal dependencies

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