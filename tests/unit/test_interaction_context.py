"""
Unit tests for InteractionContext and ContextBuilder.

The shared context layer gives specialists a read-only, cross-domain
snapshot assembled once per interaction. Key properties under test:

- Frozen / read-only — specialists can't mutate shared state mid-execution
- Lazy assembly — a scheduling delegation doesn't pull finance detail
- Timeout guard — one slow domain source doesn't block the response
- Tenant isolation — all keys are customer-scoped
- Graceful degradation — a failed source yields empty context, not an error
"""
from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.agents.context import (
    InteractionContext,
    ContextBuilder,
    DomainSnapshot,
)


# --- Frozen / read-only -----------------------------------------------------

class TestReadOnly:
    def test_context_is_frozen(self):
        ctx = InteractionContext(
            customer_id="c1",
            recent_turns=(),
            personality={"tone": "professional"},
            domains={},
            delegation_history=(),
        )
        with pytest.raises(FrozenInstanceError):
            ctx.customer_id = "c2"  # type: ignore[misc]

    def test_domain_snapshot_is_frozen(self):
        snap = DomainSnapshot(domain="finance", summary="", data={})
        with pytest.raises(FrozenInstanceError):
            snap.summary = "mutated"  # type: ignore[misc]

    def test_recent_turns_is_tuple_not_list(self):
        """Lists are mutable — caller must not be able to append."""
        ctx = InteractionContext(
            customer_id="c1",
            recent_turns=({"role": "user", "content": "hi"},),
            personality={},
            domains={},
            delegation_history=(),
        )
        assert isinstance(ctx.recent_turns, tuple)


# --- Builder: lazy loading --------------------------------------------------

def _make_sources(**overrides):
    """Domain source doubles. Each is an async callable that returns a
    DomainSnapshot. The builder calls only the ones it's asked to."""
    defaults = {
        "scheduling": AsyncMock(return_value=DomainSnapshot(
            "scheduling", "2 events today", {"count": 2},
        )),
        "finance": AsyncMock(return_value=DomainSnapshot(
            "finance", "net -$400 this month", {"net": -400.0},
        )),
        "workflows": AsyncMock(return_value=DomainSnapshot(
            "workflows", "3 active", {"active": 3},
        )),
        "notifications": AsyncMock(return_value=DomainSnapshot(
            "notifications", "1 pending", {"pending": 1},
        )),
    }
    defaults.update(overrides)
    return defaults


class TestLazyLoading:
    @pytest.mark.asyncio
    async def test_loads_only_primary_domain_by_default(self):
        sources = _make_sources()
        builder = ContextBuilder(sources=sources)

        ctx = await builder.build(
            customer_id="c1",
            primary_domain="scheduling",
            recent_turns=[],
            personality={},
            delegation_history=[],
        )

        sources["scheduling"].assert_awaited_once()
        sources["finance"].assert_not_awaited()
        assert "scheduling" in ctx.domains
        assert "finance" not in ctx.domains

    @pytest.mark.asyncio
    async def test_ambiguous_loads_all_lightweight(self):
        """primary_domain=None means 'ambiguous' — include a light summary
        of every domain rather than skipping or going deep on all of them."""
        sources = _make_sources()
        builder = ContextBuilder(sources=sources)

        ctx = await builder.build(
            customer_id="c1",
            primary_domain=None,
            recent_turns=[],
            personality={},
            delegation_history=[],
        )

        for src in sources.values():
            src.assert_awaited_once()
        assert set(ctx.domains) == set(sources)

    @pytest.mark.asyncio
    async def test_explicit_include_extends_primary(self):
        """Caller can ask for extra domains — e.g. finance specialist
        answering a spend question may want to see upcoming meetings."""
        sources = _make_sources()
        builder = ContextBuilder(sources=sources)

        ctx = await builder.build(
            customer_id="c1",
            primary_domain="finance",
            include=["scheduling"],
            recent_turns=[],
            personality={},
            delegation_history=[],
        )

        assert "finance" in ctx.domains
        assert "scheduling" in ctx.domains
        assert "workflows" not in ctx.domains


# --- Builder: timeout guard -------------------------------------------------

class TestTimeout:
    @pytest.mark.asyncio
    async def test_slow_source_is_skipped(self):
        async def slow_source(customer_id: str) -> DomainSnapshot:
            await asyncio.sleep(5.0)
            return DomainSnapshot("finance", "late", {})

        sources = _make_sources(finance=slow_source)
        builder = ContextBuilder(sources=sources, per_source_timeout=0.05)

        ctx = await builder.build(
            customer_id="c1",
            primary_domain=None,
            recent_turns=[],
            personality={},
            delegation_history=[],
        )

        # Scheduling finished, finance was skipped. The customer still
        # gets a response — just without finance enrichment.
        assert "scheduling" in ctx.domains
        assert "finance" not in ctx.domains

    @pytest.mark.asyncio
    async def test_crashed_source_is_skipped(self):
        async def bad_source(customer_id: str) -> DomainSnapshot:
            raise RuntimeError("redis down")

        sources = _make_sources(workflows=bad_source)
        builder = ContextBuilder(sources=sources)

        ctx = await builder.build(
            customer_id="c1",
            primary_domain=None,
            recent_turns=[],
            personality={},
            delegation_history=[],
        )

        assert "workflows" not in ctx.domains
        assert "scheduling" in ctx.domains

    @pytest.mark.asyncio
    async def test_sources_run_concurrently(self):
        """4 sources × 50ms each should finish in ~50ms if parallel,
        ~200ms if serial. Assert < 150ms to prove concurrency."""
        async def sleepy(customer_id: str) -> DomainSnapshot:
            await asyncio.sleep(0.05)
            return DomainSnapshot("x", "", {})

        sources = {k: sleepy for k in ("a", "b", "c", "d")}
        builder = ContextBuilder(sources=sources, per_source_timeout=1.0)

        start = asyncio.get_event_loop().time()
        await builder.build(
            customer_id="c1", primary_domain=None,
            recent_turns=[], personality={}, delegation_history=[],
        )
        elapsed = asyncio.get_event_loop().time() - start

        assert elapsed < 0.15, f"sources ran serially: {elapsed:.3f}s"


# --- Tenant isolation -------------------------------------------------------

class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_customer_id_passed_to_every_source(self):
        sources = _make_sources()
        builder = ContextBuilder(sources=sources)

        await builder.build(
            customer_id="cust_abc",
            primary_domain=None,
            recent_turns=[],
            personality={},
            delegation_history=[],
        )

        for src in sources.values():
            src.assert_awaited_once_with("cust_abc")

    @pytest.mark.asyncio
    async def test_context_carries_customer_id(self):
        builder = ContextBuilder(sources={})
        ctx = await builder.build(
            customer_id="cust_xyz",
            primary_domain=None,
            recent_turns=[],
            personality={},
            delegation_history=[],
        )
        assert ctx.customer_id == "cust_xyz"


# --- Convenience accessors --------------------------------------------------

class TestAccessors:
    def test_tone_defaults_professional(self):
        ctx = InteractionContext(
            customer_id="c1", recent_turns=(), personality={},
            domains={}, delegation_history=(),
        )
        assert ctx.tone == "professional"

    def test_tone_from_personality(self):
        ctx = InteractionContext(
            customer_id="c1", recent_turns=(),
            personality={"tone": "concise"},
            domains={}, delegation_history=(),
        )
        assert ctx.tone == "concise"

    def test_recent_specialist_domains(self):
        """Delegation history drives 'which specialists fired recently'."""
        ctx = InteractionContext(
            customer_id="c1", recent_turns=(), personality={},
            domains={},
            delegation_history=(
                {"domain": "finance", "status": "completed"},
                {"domain": "scheduling", "status": "completed"},
                {"domain": "finance", "status": "needs_clarification"},
            ),
        )
        assert ctx.recent_domains() == ["finance", "scheduling", "finance"]

    def test_domain_snapshot_accessor(self):
        snap = DomainSnapshot("finance", "summary", {"net": -200})
        ctx = InteractionContext(
            customer_id="c1", recent_turns=(), personality={},
            domains={"finance": snap}, delegation_history=(),
        )
        assert ctx.get_domain("finance") is snap
        assert ctx.get_domain("missing") is None
