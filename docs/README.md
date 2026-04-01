# AI Agency Platform Documentation

## Current Project Status
- **Architecture**: [Technical Design Document](architecture/Technical%20Design%20Document.md)
- **Requirements**: [Phase-1-PRD](architecture/Phase-1-PRD.md) · [Phase-2-PRD](architecture/Phase-2-PRD.md) · [Phase-3-PRD](architecture/Phase-3-PRD.md)
- **Development**: [../DEVELOPMENT.md](../DEVELOPMENT.md)

## Shipped
- Mem0 integration with customer isolation
- LangGraph conversation structure with conditional routing
- Redis for conversation context, PostgreSQL for persistent storage
- In-process safety layer — input/output scanning, confirmation gates, rate limiting, audit (#123)
- n8n integration — deploy automations via conversation (#124)
- Conversation intelligence layer — summarization, quality signals, tagging (#127)
- Proactive heartbeat — customer-aware triggers, notification lifecycle (#128)
- Platform wiring + dashboard backend (#130)
- E2E test coverage — 35 integration tests across 7 user flows

## Documentation Structure

### Architecture (`/architecture`)
- [Technical Design Document](architecture/Technical%20Design%20Document.md) — System architecture and design decisions
- [Phase-1-PRD](architecture/Phase-1-PRD.md) — Executive Assistant MVP requirements
- [Phase-2-PRD](architecture/Phase-2-PRD.md) — Specialist agents and advanced features
- [Phase-3-PRD](architecture/Phase-3-PRD.md) — Enterprise features and scaling
- [META-PRD](architecture/META-PRD.md) — Cross-phase product framing
- [Mem0-Integration-Plan](architecture/Mem0-Integration-Plan.md) — Memory system architecture
- [LAUNCH-Bot-Architecture](architecture/LAUNCH-Bot-Architecture.md) — Onboarding system design
- [per-customer-mcp-architecture](architecture/per-customer-mcp-architecture.md) — Customer isolation strategy
- [langfuse-integration-plan](architecture/langfuse-integration-plan.md) — Tracing/observability

### Development (`/development`)
- [TDD-Research-Plan](development/TDD-Research-Plan.md) — Test-driven development approach

### Testing (`/testing`)
- [TESTING.md](testing/TESTING.md) — Test strategy

### Infrastructure (`/infrastructure`)
- [DEPLOYMENT_READINESS.md](infrastructure/DEPLOYMENT_READINESS.md)
- [PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md)

### Security (`/security`)
- [llamaguard-integration-guide](security/llamaguard-integration-guide.md) — AI safety implementation

### Plans & Specs
- [`/plans`](plans/) — Dated implementation plans
- [`/superpowers`](superpowers/) — Feature specs and tightening plans

### Archive (`/archive`)
Historical documents moved to dated folders when superseded or completed.

## Quick Links

### For Development
1. Environment setup: [../DEVELOPMENT.md](../DEVELOPMENT.md)
2. Understand architecture: [Technical Design Document](architecture/Technical%20Design%20Document.md)
3. Review requirements: [Phase-1-PRD](architecture/Phase-1-PRD.md)

### For Testing
1. Test strategy: [TESTING.md](testing/TESTING.md)
2. Quick run: `uv run pytest tests/unit/ tests/e2e/ -q`
3. Full suite: `uv run pytest`

### For Deployment
1. Docker setup: `docker compose up`
2. Production: [PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md)

## Notes
- Documents in `/archive` are historical references
- `.claude/` contains Claude-specific agent definitions and configurations
- All dates in YYYY-MM-DD format
