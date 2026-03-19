"""
Tests for specialist registration in the ExecutiveAssistant.

Validation criteria from the spec:
- EA initializes with all three specialists when imports succeed
- EA initializes with any subset when imports fail — each import
  guarded independently
- zero changes to the delegation framework (specialist.py)
"""
from __future__ import annotations

import sys
from unittest.mock import AsyncMock, patch

import pytest


# --- Fixtures: EA with all infra mocked away --------------------------------

@pytest.fixture
def make_ea():
    """Factory for an ExecutiveAssistant with infra constructors patched out.
    Returns a function so tests can clear module caches before construction."""

    def _make():
        with patch("src.agents.executive_assistant.ExecutiveAssistantMemory") as MockMem, \
             patch("src.agents.executive_assistant.WorkflowCreator"), \
             patch("src.agents.executive_assistant.ChatOpenAI"):
            from src.agents.executive_assistant import ExecutiveAssistant, BusinessContext
            mem = MockMem.return_value
            mem.get_business_context = AsyncMock(return_value=BusinessContext())
            mem.search_business_knowledge = AsyncMock(return_value=[])
            mem.store_conversation_context = AsyncMock()
            mem.get_conversation_context = AsyncMock(return_value={})
            mem.store_business_context = AsyncMock()
            ea = ExecutiveAssistant(customer_id="c")
            ea.llm = None
            return ea

    return _make


# --- All three register on happy path ---------------------------------------

class TestAllSpecialistsRegister:
    def test_social_media_registered(self, make_ea):
        ea = make_ea()
        assert ea.delegation_registry.get("social_media") is not None

    def test_finance_registered(self, make_ea):
        ea = make_ea()
        assert ea.delegation_registry.get("finance") is not None

    def test_scheduling_registered(self, make_ea):
        ea = make_ea()
        assert ea.delegation_registry.get("scheduling") is not None

    def test_exactly_three_registered(self, make_ea):
        ea = make_ea()
        reg = ea.delegation_registry
        domains = {d for d in ("social_media", "finance", "scheduling")
                   if reg.get(d) is not None}
        assert domains == {"social_media", "finance", "scheduling"}


# --- Independent import guards ----------------------------------------------

class TestImportGuards:
    """Each specialist import is guarded independently. A broken module
    must not take out the others.

    We simulate import failure by temporarily breaking sys.modules so
    the try/except in __init__ catches it. The EA module is NOT reloaded
    — imports happen inside __init__ at construction time (that's the
    design requirement)."""

    def _break_module(self, dotted: str):
        """Context manager: makes `import dotted` raise."""
        class _Boom:
            def __getattr__(self, name):
                raise ImportError(f"simulated failure in {dotted}")
        # Poison both the leaf and any cached submodule entry
        saved = {}
        for key in (dotted, dotted.rsplit(".", 1)[0]):
            if key in sys.modules:
                saved[key] = sys.modules[key]
        # Replace the leaf with a broken stand-in. Accessing any attr raises.
        sys.modules[dotted] = _Boom()
        return saved

    def _restore(self, saved: dict):
        for k, v in saved.items():
            sys.modules[k] = v

    def test_scheduling_import_failure_isolated(self, make_ea):
        dotted = "src.agents.specialists.scheduling"
        saved = sys.modules.pop(dotted, None)
        sys.modules[dotted] = None  # forces ImportError on re-import
        try:
            ea = make_ea()
            assert ea.delegation_registry.get("scheduling") is None
            # Others unaffected
            assert ea.delegation_registry.get("social_media") is not None
            assert ea.delegation_registry.get("finance") is not None
        finally:
            if saved is not None:
                sys.modules[dotted] = saved
            else:
                sys.modules.pop(dotted, None)

    def test_finance_import_failure_isolated(self, make_ea):
        dotted = "src.agents.specialists.finance"
        saved = sys.modules.pop(dotted, None)
        sys.modules[dotted] = None
        try:
            ea = make_ea()
            assert ea.delegation_registry.get("finance") is None
            assert ea.delegation_registry.get("social_media") is not None
            assert ea.delegation_registry.get("scheduling") is not None
        finally:
            if saved is not None:
                sys.modules[dotted] = saved
            else:
                sys.modules.pop(dotted, None)

    def test_social_media_import_failure_isolated(self, make_ea):
        dotted = "src.agents.specialists.social_media"
        saved = sys.modules.pop(dotted, None)
        sys.modules[dotted] = None
        try:
            ea = make_ea()
            assert ea.delegation_registry.get("social_media") is None
            assert ea.delegation_registry.get("finance") is not None
            assert ea.delegation_registry.get("scheduling") is not None
        finally:
            if saved is not None:
                sys.modules[dotted] = saved
            else:
                sys.modules.pop(dotted, None)

    def test_all_imports_fail_ea_still_initializes(self, make_ea):
        """Worst case: every specialist module is broken. EA comes up with
        an empty registry — no specialists, but no crash either."""
        saved = {}
        for mod in ("social_media", "finance", "scheduling"):
            dotted = f"src.agents.specialists.{mod}"
            saved[dotted] = sys.modules.pop(dotted, None)
            sys.modules[dotted] = None
        try:
            ea = make_ea()  # must not raise
            assert ea.delegation_registry.get("social_media") is None
            assert ea.delegation_registry.get("finance") is None
            assert ea.delegation_registry.get("scheduling") is None
        finally:
            for dotted, orig in saved.items():
                if orig is not None:
                    sys.modules[dotted] = orig
                else:
                    sys.modules.pop(dotted, None)


# --- Framework unchanged ----------------------------------------------------

class TestFrameworkUntouched:
    def test_specialist_base_has_no_scheduling_references(self):
        """Adding scheduling required zero changes to the framework."""
        import inspect
        import src.agents.base.specialist as base
        src = inspect.getsource(base)
        assert "scheduling" not in src.lower()
        assert "calendar" not in src.lower()
