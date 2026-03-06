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

The pytest config in `pyproject.toml` bakes in `--cov-fail-under=80`, but existing code sits at ~12% coverage. The full suite will always report FAIL on the coverage gate until legacy modules catch up.

**Dev loop (fast, no coverage):**
```bash
uv run pytest --no-cov tests/unit/path/ -x
```

**Coverage for a specific module:**
```bash
uv run pytest --no-cov --cov=src/agents/ai_ml/workflow_generator --cov-report=term-missing tests/unit/ai_ml/
```

**Full suite (CI parity, expect coverage failure on legacy code):**
```bash
uv run pytest
```

## Version control

Colocated jj + git. Commit with `jj commit -m "..." <paths>` to keep changes scoped — there may be unrelated in-progress work in the working copy.
