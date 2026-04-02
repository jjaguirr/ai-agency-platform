"""Unit tests for port allocator."""
import pytest

# port_allocator hard-imports asyncpg and redis at module level.
pytest.importorskip("asyncpg")
pytest.importorskip("redis")

from src.infrastructure.port_allocator import PortAllocator


class TestPortAllocator:
    def test_allocator_initialization(self):
        allocator = PortAllocator()
        assert allocator is not None
