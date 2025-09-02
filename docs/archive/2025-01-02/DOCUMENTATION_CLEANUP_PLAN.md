# Documentation Cleanup & Consolidation Plan
*Updated: 2025-01-02*

## 🗂️ Current Documentation State

### Root Level (Needs Action)
- ❌ `URGENT_PLAN.MD` → Archive (outdated, replaced by PHASE_1_CRITICAL_PATH.md)
- ✅ `PHASE_1_CRITICAL_PATH.md` → Keep (current active plan)
- ❓ `SOPHISTICATED_EA_IMPLEMENTATION_SUMMARY.md` → Review (may be outdated)
- ❓ `TESTING_FRAMEWORK_SUMMARY.md` → Review (partially complete)
- ✅ `CLAUDE.md` → Keep (project instructions)

### .claude/ Directory (Claude Dev specific)
- ❓ `DIRECT_SDK_INTEGRATION_PLAN.md` → Review (check if still relevant)
- ❓ `UNIFIED_TODO_WORKFLOW_TEMPLATES.md` → Review
- ❓ `BEHAVIORAL_ENFORCEMENT_CONFIG.md` → Keep (Claude behavior config)
- ✅ `agents/*.md` → Keep (agent definitions for TDD workflow)

### docs/architecture/ (Major cleanup needed)
- ❌ `mcp-memory-service-integration.md` → Archive (MCPMemoryServiceClient removed)
- ✅ `Mem0-Integration-Plan.md` → Keep (current memory approach)
- ✅ `Phase-1-PRD.md` → Keep (primary requirements doc)
- ❓ `Phase-2-PRD.md` → Keep (future phases)
- ❓ `Phase-3-PRD.md` → Keep (future phases)
- ✅ `Technical Design Document.md` → Keep (core architecture)
- ❓ `META-PRD.md` → Review (may be outdated)
- ❓ `LAUNCH-Bot-Architecture.md` → Review
- ❓ `per-customer-mcp-architecture.md` → Review (check alignment with current)
- ❓ `langfuse-integration-plan.md` → Keep (future integration)

### docs/development/
- ❓ `TDD-Research-Plan.md` → Review

### docs/testing/
- ✅ `TESTING.md` → Update (needs current test status)

### docs/security/
- ✅ `llamaguard-integration-guide.md` → Keep (security implementation)

## 📋 Action Items

### 1. Archive Outdated Documents
```bash
mkdir -p docs/archive/2025-01-02
mv URGENT_PLAN.MD docs/archive/2025-01-02/
mv docs/architecture/mcp-memory-service-integration.md docs/archive/2025-01-02/
```

### 2. Consolidate Duplicate Information
- Merge EA implementation summaries into Technical Design Document
- Consolidate test documentation into single TESTING.md
- Update Phase-1-PRD with actual implementation status

### 3. Create Master Documentation Index
```markdown
# docs/README.md
## Current Project Status
- Active Phase: Phase 1 (Executive Assistant MVP)
- Current Plan: [PHASE_1_CRITICAL_PATH.md](../PHASE_1_CRITICAL_PATH.md)
- Architecture: [Technical Design Document](architecture/Technical-Design-Document.md)

## Documentation Structure
- `/architecture` - System design and PRDs
- `/development` - Development guidelines and TDD approach
- `/testing` - Test strategy and current test status
- `/security` - Security implementations
- `/archive` - Historical documents
```

### 4. Update Key Documents

#### Technical Design Document Updates Needed:
- ✅ Mem0 integration (already correct)
- ❌ Remove references to MCPMemoryServiceClient
- ❌ Update LangGraph implementation details
- ❌ Add communication channel architecture
- ❌ Document actual test infrastructure

#### Phase-1-PRD Updates Needed:
- Mark completed features
- Update timeline with actual progress
- Document deviations from original plan

### 5. Remove/Archive Redundant Files
- Archive any duplicate PRD versions
- Remove mock test implementations
- Clean up temporary planning documents

## 🎯 Final Documentation Structure Goal

```
ai-agency-platform/
├── README.md (project overview)
├── PHASE_1_CRITICAL_PATH.md (current sprint plan)
├── CLAUDE.md (project instructions)
├── docs/
│   ├── README.md (documentation index)
│   ├── architecture/
│   │   ├── Technical-Design-Document.md (master architecture)
│   │   ├── Phase-1-PRD.md (current requirements)
│   │   ├── Phase-2-PRD.md (future)
│   │   └── Phase-3-PRD.md (future)
│   ├── development/
│   │   └── TDD-Guidelines.md
│   ├── testing/
│   │   └── TESTING.md (consolidated test docs)
│   ├── security/
│   │   └── llamaguard-integration-guide.md
│   └── archive/
│       └── 2025-01-02/ (old documents)
└── .claude/
    ├── agents/ (TDD agent definitions)
    └── config/ (Claude behavior configs)
```

## 🔄 Next Steps
1. Execute archive commands
2. Update Technical Design Document
3. Consolidate test documentation
4. Create documentation index
5. Update Phase-1-PRD with current status