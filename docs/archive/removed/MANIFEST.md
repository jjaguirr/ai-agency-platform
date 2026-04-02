# Removed Code Archive — 2026-04-02

Files here were removed from the active tree because nothing in
`src/api/app.py`'s transitive import graph or the test suite reaches them.
Git history is the authoritative record; this directory is a convenience
for anyone wondering "where did X go" without spelunking `git log`.

## src/

| Path | Reason |
|---|---|
| `src/memory/` | Mem0/Qdrant memory manager. Specced early, never wired into the running system. The EA's `from mem0 import Memory` always failed silently in practice; `EAMemoryManager` had no callers outside `src/security/` (also removed). |
| `src/agents-memory/` (was `src/agents/memory/`) | `ea_memory_integration.py` wrapped `EAMemoryManager` and was only reachable via the EA's try/except import block — the import never succeeded because `src/memory/` itself depended on the absent `mem0` package. `mcp_memory_client.py` had zero callers. |
| `src/security/` | `customer_deletion_pipeline.py` orchestrated GDPR deletion across Redis/Qdrant/Neo4j/Postgres — but Qdrant and Neo4j are gone, and the app never invoked the pipeline. Its 935-line test (`test_customer_deletion_pipeline.py`) self-skipped via `importorskip("neo4j")`. The other modules (`gdpr_compliance_manager`, `security_monitor`, `advanced_isolation_tester`, `run_security_validation`) all imported `EAMemoryManager` and were only reachable from each other. `llamaguard-api.py` was a standalone FastAPI service never mounted. |
| `src/evaluation/` | LLM-judge evaluation framework. Imported only by `scripts/run_semantic_evaluation_demo.py` — not by the app, not by tests (the three `tests/unit/test_{conversation_quality,evaluation_schemas,roi_validation}.py` files were `pytest.skip()` stubs). |
| `src/infrastructure-cli.py` (was `src/infrastructure/cli.py`) | Standalone Click CLI for the port allocator. Not imported, not tested, not invoked by any docs. |
| `src/agents-ai_ml/` (was `src/agents/ai_ml/{business_learning_engine,workflow_template_matcher}.py`) | Sole caller was the EA's `if AI_ML_AVAILABLE:` block (removed) and `test_ai_ml_integration.py` (archived above). `business_learning_engine.py` was the last consumer of `sentence-transformers`, `numpy`, `spacy` — those deps fell out with it. The workflow *generator* and n8n catalog stay; they're what `WorkflowSpecialist` actually uses. |

## tests/

| Path | Reason |
|---|---|
| `tests/memory/` | Both files imported from `src.memory.mem0_manager` and `src.agents.memory.ea_memory_integration`. Already gated on `importorskip("mem0")` so they never ran in CI. |
| `tests/test_mem0_manager.py`, `test_isolation_validator.py`, `test_performance_monitor.py` | `pytest.skip()` stubs for `src/memory/`. |
| `tests/test_customer_deletion_pipeline.py` | 935 lines of real test, but pinned against `EAMemoryManager` naming and `importorskip("neo4j")`. Tested deletion from storage backends that no longer exist. |
| `tests/test_security_monitor.py`, `test_gdpr_compliance.py`, `test_llamaguard.py` | `pytest.skip()` stubs for `src/security/`. |
| `tests/test_conversation_quality.py`, `test_evaluation_schemas.py`, `test_roi_validation.py` | `pytest.skip()` stubs for `src/evaluation/`. |
| `tests/test_ea_mem0_integration.py`, `test_ai_ml_integration.py` | Both `importorskip("mem0")` + import `EAMemoryIntegration`. Never ran. |
| `tests/test_qdrant_vectors.py`, `test_neo4j_graph.py` | `pytest.skip()` stubs for services that are gone. |

## config/

| Path | Reason |
|---|---|
| `config/qdrant/` | Qdrant `production.yaml` mounted by the removed docker-compose service. |
| `config/neo4j/` | Neo4j `neo4j.conf` mounted by the removed docker-compose service. |

## Dependencies dropped

`mem0ai`, `neo4j`, `sentence-transformers`, `numpy`, `spacy` from `[project.dependencies]`;
`qdrant-client`, `chromadb` from `[project.optional-dependencies.evaluation]`.

`sentence-transformers` was the long pole — it transitively pulled `torch`,
`transformers`, and `triton`. Resolved lockfile shrank by ~40 packages.
