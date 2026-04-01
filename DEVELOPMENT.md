# Development

## Environment

This project uses [uv](https://docs.astral.sh/uv/) for Python and dependency management.

`pyproject.toml` pins `requires-python = ">=3.10,<3.14"`. If your system Python is outside that range (Homebrew ships 3.14 as of 2026), uv handles the interpreter:

```bash
uv python install 3.12
uv sync --extra dev
```

This creates `.venv/` with a compliant interpreter and installs runtime + dev dependencies. The existing `uv.lock` is respected.

## Running tests

Pytest config lives in `pyproject.toml` (`[tool.pytest.ini_options]`):
`asyncio_mode = "auto"`, `--strict-markers`, 30-second per-test timeout.

**Dev loop (fast — unit + e2e, no live services):**
```bash
uv run pytest tests/unit/ tests/e2e/ -q
```

**Single module, fail-fast:**
```bash
uv run pytest tests/unit/proactive/ -x
```

**Coverage for a specific module:**
```bash
uv run pytest --cov=src/agents/ai_ml/workflow_generator --cov-report=term-missing tests/unit/ai_ml/
```

**Full suite (includes integration tests that need live services):**
```bash
uv run pytest
```

## Dashboard

Svelte + Vite in `dashboard/`; FastAPI serves the built assets at `/` with the API at `/v1/`. Requires Node 22+.

**Seed a login (once per customer):**
```bash
uv run scripts/seed_dashboard_auth.py demo_jewelry
# → prints the generated secret; use customer_id + secret at the login form
```

**Full stack (built assets, one process):**
```bash
make serve   # builds dashboard/dist, starts uvicorn on :8000
```

**Dev loop (hot reload, two processes):**
```bash
uv run uvicorn src.api.app:create_default_app --factory --reload   # terminal 1
npm --prefix dashboard run dev                                     # terminal 2 → :5173
```
Vite proxies `/v1/*` to `:8000` so the origin is shared and auth headers flow.

## Version control

Colocated jj + git. Commit with `jj commit -m "..." <paths>` to keep changes scoped — there may be unrelated in-progress work in the working copy.
