"""
App factory configuration tests.

These don't exercise routes — they check that create_app() enforces its
configuration invariants at construction time, not at first-request time.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.api.app import create_app
from src.api.dependencies import EAPool


# EAPool() with no factory imports ExecutiveAssistant → langchain cascade.
# Pass a throwaway pool so these tests stay fast.
_DUMMY_POOL = EAPool(ea_factory=lambda cid: MagicMock())


class TestJWTSecretRequired:
    """
    The app signs and verifies tokens with app.state.jwt_secret. A missing
    secret must fail at startup — not silently fall through to a hardcoded
    default that anyone reading the source can use to forge tokens.
    """

    def test_no_kwarg_no_env_var_raises_at_construction(self, monkeypatch):
        monkeypatch.delenv("API_JWT_SECRET", raising=False)

        with pytest.raises(RuntimeError, match="API_JWT_SECRET"):
            create_app(ea_pool=_DUMMY_POOL)

    def test_empty_env_var_raises(self, monkeypatch):
        # `os.environ.get(key, default)` doesn't return default for an empty
        # string — it returns "". Make sure that's also rejected.
        monkeypatch.setenv("API_JWT_SECRET", "")

        with pytest.raises(RuntimeError, match="API_JWT_SECRET"):
            create_app(ea_pool=_DUMMY_POOL)

    def test_env_var_set_is_used_when_kwarg_absent(self, monkeypatch):
        monkeypatch.setenv("API_JWT_SECRET", "secret-from-env")

        app = create_app(ea_pool=_DUMMY_POOL)

        assert app.state.jwt_secret == "secret-from-env"

    def test_explicit_kwarg_wins_over_env_var(self, monkeypatch):
        # Even with env set, an injected secret (tests, alt deployments) takes
        # precedence. The env var is the fallback, not the override.
        monkeypatch.setenv("API_JWT_SECRET", "secret-from-env")

        app = create_app(ea_pool=_DUMMY_POOL, jwt_secret="injected-secret")

        assert app.state.jwt_secret == "injected-secret"

    def test_no_hardcoded_default_exists(self, monkeypatch):
        """
        Regression guard: the old code had `os.environ.get(key, "dev-secret-change-me")`.
        Prove that string is gone — if someone reintroduces a hardcoded
        default, this test breaks before it reaches prod.
        """
        monkeypatch.delenv("API_JWT_SECRET", raising=False)

        # Should raise, not silently return an app with a known secret.
        with pytest.raises(RuntimeError):
            create_app(ea_pool=_DUMMY_POOL)

        # And the old default string should not appear in the module source.
        # Belt-and-suspenders — catches a reintroduction that changes the
        # raise condition but keeps the constant around.
        import src.api.app as app_module
        import inspect
        assert "dev-secret-change-me" not in inspect.getsource(app_module)
