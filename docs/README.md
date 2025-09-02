# AI Agency Platform Documentation

## 📍 Current Project Status
- **Active Phase**: Phase 1 - Executive Assistant MVP
- **Current Sprint**: [PHASE_1_CRITICAL_PATH.md](../PHASE_1_CRITICAL_PATH.md)
- **Architecture**: [Technical Design Document](architecture/Technical%20Design%20Document.md)
- **Requirements**: [Phase-1-PRD.md](architecture/Phase-1-PRD.md)

## ✅ Completed Features
- Mem0 integration with customer isolation
- Basic LangGraph conversation structure
- Redis for conversation context
- PostgreSQL for persistent storage
- Test infrastructure setup

## 🚧 In Progress
1. **LangGraph Enhancement** - Adding conditional routing and branching
2. **Test Infrastructure** - Fixing async fixtures
3. **Docker Services** - Setting up development environment

## 📚 Documentation Structure

### Core Documents
- [`PHASE_1_CRITICAL_PATH.md`](../PHASE_1_CRITICAL_PATH.md) - Current sprint plan and blockers
- [`CLAUDE.md`](../CLAUDE.md) - Project-specific instructions for Claude

### Architecture (`/architecture`)
- [Technical Design Document](architecture/Technical%20Design%20Document.md) - System architecture and design decisions
- [Phase-1-PRD](architecture/Phase-1-PRD.md) - Executive Assistant MVP requirements
- [Phase-2-PRD](architecture/Phase-2-PRD.md) - Specialist agents and advanced features
- [Phase-3-PRD](architecture/Phase-3-PRD.md) - Enterprise features and scaling
- [Mem0-Integration-Plan](architecture/Mem0-Integration-Plan.md) - Memory system architecture
- [LAUNCH-Bot-Architecture](architecture/LAUNCH-Bot-Architecture.md) - Onboarding system design
- [per-customer-mcp-architecture](architecture/per-customer-mcp-architecture.md) - Customer isolation strategy

### Development (`/development`)
- [TDD-Research-Plan](development/TDD-Research-Plan.md) - Test-driven development approach

### Testing (`/testing`)
- [TESTING.md](testing/TESTING.md) - Test strategy and current status

### Security (`/security`)
- [llamaguard-integration-guide](security/llamaguard-integration-guide.md) - AI safety implementation

### Archive (`/archive`)
Historical documents moved to dated folders when superseded or completed.

## 🎯 Quick Links

### For Development
1. Start here: [PHASE_1_CRITICAL_PATH.md](../PHASE_1_CRITICAL_PATH.md)
2. Understand architecture: [Technical Design Document](architecture/Technical%20Design%20Document.md)
3. Review requirements: [Phase-1-PRD](architecture/Phase-1-PRD.md)

### For Testing
1. Test strategy: [TESTING.md](testing/TESTING.md)
2. Run tests: `./scripts/quick_test.sh`
3. Full suite: `pytest tests/`

### For Deployment
1. Docker setup: `docker-compose up`
2. Environment vars: `.env.example`

## 🔄 Document Status

| Document | Status | Last Updated | Notes |
|----------|--------|--------------|-------|
| PHASE_1_CRITICAL_PATH | Active | 2025-01-02 | Current sprint plan |
| Technical Design Document | Current | 2024-12 | Needs LangGraph updates |
| Phase-1-PRD | Current | 2024-12 | Implementation in progress |
| Mem0-Integration-Plan | Complete | 2024-12 | Successfully implemented |
| TESTING.md | Needs Update | 2024-12 | Update with current test status |

## 📝 Notes
- Documents in `/archive` are historical references
- `.claude/` contains Claude-specific agent definitions and configurations
- All dates in YYYY-MM-DD format