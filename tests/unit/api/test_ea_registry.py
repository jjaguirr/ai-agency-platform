"""
EA registry: per-customer caching with concurrency safety.

The EA constructor is expensive (mem0 init, Redis connections, LangGraph
compilation) — we must NEVER build two for the same customer, even under
concurrent first-access.
"""
import asyncio

import pytest
from unittest.mock import MagicMock

from src.api.ea_registry import EARegistry


pytestmark = pytest.mark.asyncio


class TestEARegistryCaching:
    async def test_first_get_invokes_factory(self):
        factory = MagicMock(side_effect=lambda cid: MagicMock(customer_id=cid))
        registry = EARegistry(factory=factory)

        ea = await registry.get("cust_a")

        assert ea.customer_id == "cust_a"
        factory.assert_called_once_with("cust_a")

    async def test_second_get_same_customer_hits_cache(self):
        factory = MagicMock(side_effect=lambda cid: MagicMock(customer_id=cid))
        registry = EARegistry(factory=factory)

        ea1 = await registry.get("cust_a")
        ea2 = await registry.get("cust_a")

        assert ea1 is ea2
        assert factory.call_count == 1

    async def test_different_customers_get_distinct_instances(self):
        factory = MagicMock(side_effect=lambda cid: MagicMock(customer_id=cid))
        registry = EARegistry(factory=factory)

        ea_a = await registry.get("cust_a")
        ea_b = await registry.get("cust_b")

        assert ea_a is not ea_b
        assert factory.call_count == 2


class TestEARegistryConcurrency:
    async def test_concurrent_gets_same_customer_create_exactly_one(self):
        # Slow factory so both calls enter the critical section together.
        call_count = 0

        async def slow_factory(cid):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            return MagicMock(customer_id=cid)

        # Registry must support async factories OR sync factories wrapped
        # via run_in_executor / direct call. We test the contract: factory
        # is called once even with N concurrent gets.
        factory_sync = MagicMock(side_effect=lambda cid: MagicMock(customer_id=cid))
        registry = EARegistry(factory=factory_sync)

        # Fire 10 concurrent gets
        results = await asyncio.gather(*(
            registry.get("cust_hot") for _ in range(10)
        ))

        # All ten must be the same instance
        assert all(r is results[0] for r in results)
        assert factory_sync.call_count == 1

    async def test_different_customers_build_in_parallel(self):
        """
        Per-customer locking means cust_b's EA can build while cust_a's
        is still building. If the registry used a global lock, or called
        the factory on the event loop thread, cust_b would serialize
        behind cust_a.

        Signal design: cust_a sets `a_returned` IMMEDIATELY before
        returning; cust_b checks that flag. An Event.wait(timeout) that
        times out doesn't set the event — we can't use that as the
        "a is done" signal or the test becomes tautological.
        """
        import threading

        a_entered = threading.Event()
        a_returned = threading.Event()
        a_may_finish = threading.Event()
        b_ran_while_a_still_inside = threading.Event()

        def factory(cid):
            if cid == "cust_a":
                a_entered.set()
                a_may_finish.wait(timeout=2.0)
                a_returned.set()  # <-- signal we're about to return
            else:  # cust_b
                if a_entered.is_set() and not a_returned.is_set():
                    b_ran_while_a_still_inside.set()
            return MagicMock(customer_id=cid)

        registry = EARegistry(factory=factory)

        async def get_b_after_a_starts():
            while not a_entered.is_set():
                await asyncio.sleep(0.001)
            return await registry.get("cust_b")

        async def release_a_once_b_has_run():
            for _ in range(200):
                if b_ran_while_a_still_inside.is_set():
                    break
                await asyncio.sleep(0.005)
            a_may_finish.set()

        await asyncio.gather(
            registry.get("cust_a"),
            get_b_after_a_starts(),
            release_a_once_b_has_run(),
        )

        assert b_ran_while_a_still_inside.is_set(), (
            "cust_b should have entered its factory while cust_a was still "
            "building — either the lock is global or the factory blocks the loop"
        )

    async def test_factory_exception_does_not_poison_lock(self):
        """
        If the first build attempt raises, a subsequent get() for the
        same customer should retry — not deadlock on a held lock, not
        return a cached exception.
        """
        attempt = {"n": 0}

        def flaky_factory(cid):
            attempt["n"] += 1
            if attempt["n"] == 1:
                raise ConnectionError("mem0 unavailable")
            return MagicMock(customer_id=cid)

        registry = EARegistry(factory=flaky_factory)

        with pytest.raises(Exception):
            await registry.get("cust_retry")

        # Second attempt should succeed — lock released, no poisoned cache
        ea = await registry.get("cust_retry")
        assert ea.customer_id == "cust_retry"
        assert attempt["n"] == 2


class TestEARegistryManagement:
    async def test_clear_evicts_cached_instance(self):
        factory = MagicMock(side_effect=lambda cid: MagicMock(customer_id=cid))
        registry = EARegistry(factory=factory)

        await registry.get("cust_a")
        registry.clear("cust_a")
        await registry.get("cust_a")

        assert factory.call_count == 2

    async def test_clear_unknown_customer_is_noop(self):
        registry = EARegistry(factory=MagicMock())
        registry.clear("nonexistent")  # must not raise
