# Removed code archive

Files moved here were not reachable from `src/api/app.py` (the production
entrypoint) or any non-stub test. They are preserved for reference; git
history at the parent of the removal commit has the original locations.

## Mem0 / Qdrant / Neo4j layer

The semantic-memory layer was specced early but never wired into the live
system. The EA fell through to `memory_client = None` on every boot.

| Path | Why removed |
|---|---|
| `src/memory/` | Mem0+Qdrant+Neo4j manager, isolation validator, perf monitor — never used by the app |
| `src/agents/memory/` | EA↔Mem0 bridge; only reached via a try/except that always failed |
| `src/agents/ai_ml/business_learning_engine.py` | spaCy/sentence-transformers NLP over Mem0 results; only reached via the same try/except |
| `src/agents/ai_ml/workflow_template_matcher.py` | numpy similarity over Mem0 results; same try/except |
| `config/qdrant/`, `config/neo4j/` | Service config for stores no longer deployed |

## Security validators built on the Mem0 layer

| Path | Why removed |
|---|---|
| `src/security/advanced_isolation_tester.py` | Instantiates `EAMemoryManager` to probe Qdrant/Neo4j isolation |
| `src/security/gdpr_compliance_manager.py` | Hard-imports `mem0`; superseded by `customer_deletion_pipeline` for the deletion path |
| `src/security/security_monitor.py` | Imports `EAMemoryManager`; no live caller |
| `src/security/run_security_validation.py` | CLI runner for the three above |
| `src/security/llamaguard-api.py` | Standalone Flask shim; dash in filename made it unimportable anyway — superseded by `src/safety/` |

## Speculative modules

| Path | Why removed |
|---|---|
| `src/evaluation/` | LLM-judge / ROI evaluators; no caller, only stub tests |
| `src/infrastructure/cli.py` | Click CLI for the orchestrator; app uses the orchestrator directly |

## Tests

| Path | Why removed |
|---|---|
| `tests/memory/` | Exercised `src/memory/` directly |
| `tests/integration/test_ea_mem0_integration.py` | Live Mem0 integration test |
| `tests/integration/test_ai_ml_integration.py` | Live business-learning-engine test |
| `tests/integration/test_qdrant_vectors.py` | Stub (all skipped) for removed store |
| `tests/integration/test_neo4j_graph.py` | Stub (all skipped) for removed store |
| `tests/legacy/test_mcp_memory_integration.py` | Pre-Mem0 ChromaDB experiment |
| `tests/unit/test_mem0_manager.py` | Stub for `src/memory/mem0_manager.py` |
| `tests/unit/test_isolation_validator.py` | Stub for `src/memory/isolation_validator.py` |
| `tests/unit/test_performance_monitor.py` | Stub for `src/memory/performance_monitor.py` |
| `tests/unit/test_gdpr_compliance.py` | Stub for removed `gdpr_compliance_manager` |
| `tests/unit/test_security_monitor.py` | Stub for removed `security_monitor` |
| `tests/unit/test_llamaguard.py` | Stub for removed `llamaguard-api` |
| `tests/unit/test_conversation_quality.py` | Stub for removed `src/evaluation/` |
| `tests/unit/test_evaluation_schemas.py` | Stub for removed `src/evaluation/` |
| `tests/unit/test_roi_validation.py` | Stub for removed `src/evaluation/` |

## What stayed

`src/security/customer_deletion_pipeline.py` was kept (it has a real 900-line
test suite and the Redis/Postgres stages are still needed for GDPR Article 17),
but its Qdrant and Neo4j stages were stripped since those stores are no longer
deployed. The two audit tables it writes to (`gdpr_compliance_audit`,
`customer_deletion_operations`) were lifted out of `src/memory/schema.sql`
into `src/database/migrations/003_gdpr_deletion.sql`.

`src/infrastructure/{port_allocator,infrastructure_orchestrator,docker_compose_generator}.py`
were kept — `create_default_app()` imports the first two, and the third has a
unit-test placeholder plus an integration test. They still carry
`ServiceType.QDRANT`/`NEO4J` enum values; those are inert config and can be
pruned in a follow-up if the per-customer provisioning path is dropped.

## Follow-up: ops scripts not scrubbed

Several standalone ops scripts under `scripts/` still reference the removed
services (`production_deployment_orchestrator.py`, `infrastructure-health-monitor.sh`,
`infrastructure-integration-report.sh`, `scale_performance_validator.py`,
`validate_phase3_implementation.py`, `validate_production_deployment.py`).
They are not part of the `src/` import graph, docker-compose, or CI, so they
were left as-is for this pass. They will fail or report missing services if
run; clean them up alongside the `ServiceType` enum prune.
