# Test Organization

## Directory Structure

### `/unit/` — Unit Tests
Isolated component tests, no live services. Organized by module:
- `api/` — FastAPI routes, auth, EA registry, activity counters
- `safety/` — prompt guard, output scanner, rate limiter, audit
- `proactive/` — heartbeat daemon, noise gate, behaviors, triggers
- `intelligence/` — summarizer, quality analyzer, sweep, analytics
- `workflows/` — n8n catalog, client, IR, customizer
- `ai_ml/` — workflow generator, assembler, explainer
- Top-level `test_*.py` — EA core, specialists, channels, config

### `/e2e/` — End-to-End Integration Tests
Full request→response chains through `create_app()` with fakeredis +
in-memory repos. No Docker required.
- `test_customer_onboarding.py` — message pipeline (safety→EA→persist→counter)
- `test_workflow_creation.py` — specialist delegation + action confirmation
- `test_business_discovery.py` — proactive notification lifecycle
- `test_memory_persistence.py` — conversation intelligence sweep
- `test_cross_channel.py` — cross-tenant isolation + dashboard auth

### `/integration/` — Service Integration Tests
Tests against real Postgres/Redis/Qdrant/Neo4j. Skip when services unavailable.

### `/business/`, `/acceptance/` — Scenario Tests
Business-outcome validation with customer personas. Require OpenAI API key.

### `/memory/` — Memory-Layer Tests
Mem0 + conversation continuity integration.

### `/demos/` — Demonstration Scripts
Executable examples, not collected by pytest.

### `/legacy/` — Historical Test Files
Previous iterations kept for reference patterns. Excluded from CI.

### `/utils/` — Test Helpers
`TestDataManager`, `TestResourceManager`, performance utilities.
(Classes prefixed `Test*` for naming convention — they have `__init__`
so pytest correctly skips collecting them.)

## Running Tests

```bash
# Fast dev loop — unit + e2e, no live services
uv run pytest tests/unit/ tests/e2e/ -q

# Single file with failures-first
uv run pytest tests/unit/proactive/ -x

# Integration tests (requires docker compose up postgres redis)
uv run pytest tests/integration/ -v

# Everything except legacy/demos
uv run pytest tests/ --ignore=tests/legacy --ignore=tests/demos
```

## Configuration
- `conftest.py` — shared fixtures (live-service fixtures skip cleanly when unreachable)
- `e2e/conftest.py` — in-memory repos + ScriptedEA for E2E
- `unit/*/conftest.py` — module-specific fixtures
- Pytest settings live in `pyproject.toml` under `[tool.pytest.ini_options]`
  (`asyncio_mode = "auto"`, `--strict-markers`, 30s timeout)
