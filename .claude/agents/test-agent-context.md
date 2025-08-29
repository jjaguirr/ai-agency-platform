# Agent Context Test

## Purpose
Validate that streamlined agents can properly access project context from PRD files.

## Test Scenarios

### 1. Infrastructure Engineer Test
- Task: "Set up infrastructure for the Executive Assistant"
- Expected: Agent reads Phase-1 PRD and extracts:
  - Per-customer MCP server requirements
  - 30-second provisioning target
  - PostgreSQL, Redis, Qdrant stack

### 2. Security Engineer Test  
- Task: "Validate customer isolation"
- Expected: Agent reads Phase-1 PRD and extracts:
  - 100% data isolation requirement
  - Per-customer MCP servers
  - No shared infrastructure

### 3. AI/ML Engineer Test
- Task: "Design the EA conversation system"
- Expected: Agent reads Phase-1 PRD and extracts:
  - Single Executive Assistant focus
  - Conversational business learning
  - Vendor-agnostic model support

## Success Criteria
✅ Agents reference PRD files for context
✅ No hardcoded project details in agent files
✅ Context extracted matches current phase requirements
✅ Forward compatibility maintained with Phase 2/3