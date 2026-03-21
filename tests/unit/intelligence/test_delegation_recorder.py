"""Tests for DelegationRecorder — writes delegation lifecycle to Postgres."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from src.intelligence.delegation_recorder import DelegationRecorder


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = ctx
    return pool, conn


class TestRecordStart:
    async def test_inserts_row_and_returns_id(self, mock_pool):
        pool, conn = mock_pool
        expected_id = str(uuid.uuid4())
        conn.fetchval = AsyncMock(return_value=expected_id)

        recorder = DelegationRecorder(pool)
        record_id = await recorder.record_start(
            conversation_id="conv_1",
            customer_id="cust_a",
            specialist_domain="finance",
        )

        assert record_id == expected_id
        conn.fetchval.assert_awaited_once()
        sql = conn.fetchval.await_args[0][0]
        assert "INSERT INTO delegation_records" in sql
        assert "status" in sql

    async def test_passes_correct_parameters(self, mock_pool):
        pool, conn = mock_pool
        conn.fetchval = AsyncMock(return_value="some-id")

        recorder = DelegationRecorder(pool)
        await recorder.record_start(
            conversation_id="conv_99",
            customer_id="cust_b",
            specialist_domain="scheduling",
        )

        args = conn.fetchval.await_args[0]
        assert "conv_99" in args
        assert "cust_b" in args
        assert "scheduling" in args


class TestRecordEnd:
    async def test_updates_status_and_completed_at(self, mock_pool):
        pool, conn = mock_pool
        conn.execute = AsyncMock()

        recorder = DelegationRecorder(pool)
        await recorder.record_end(
            record_id="rec_1",
            status="completed",
            turns=3,
            confirmation_requested=False,
            confirmation_outcome=None,
        )

        conn.execute.assert_awaited_once()
        sql = conn.execute.await_args[0][0]
        assert "UPDATE delegation_records" in sql
        assert "completed_at" in sql
        assert "status" in sql

    async def test_passes_confirmation_fields(self, mock_pool):
        pool, conn = mock_pool
        conn.execute = AsyncMock()

        recorder = DelegationRecorder(pool)
        await recorder.record_end(
            record_id="rec_2",
            status="cancelled",
            turns=2,
            confirmation_requested=True,
            confirmation_outcome="declined",
        )

        args = conn.execute.await_args[0]
        assert "cancelled" in args
        assert "declined" in args

    async def test_passes_error_message_for_failed(self, mock_pool):
        pool, conn = mock_pool
        conn.execute = AsyncMock()

        recorder = DelegationRecorder(pool)
        await recorder.record_end(
            record_id="rec_3",
            status="failed",
            turns=1,
            confirmation_requested=False,
            confirmation_outcome=None,
            error_message="timeout after 30s",
        )

        args = conn.execute.await_args[0]
        assert "timeout after 30s" in args


class TestUpdateTagsFromDelegations:
    async def test_sets_tags_from_delegation_domains(self, mock_pool):
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[
            {"specialist_domain": "finance"},
            {"specialist_domain": "scheduling"},
        ])
        conn.execute = AsyncMock()

        recorder = DelegationRecorder(pool)
        await recorder.update_tags_from_delegations(
            customer_id="cust_a",
            conversation_id="conv_1",
        )

        # Should fetch distinct domains then update tags
        assert conn.fetch.await_count == 1
        assert conn.execute.await_count == 1
        update_args = conn.execute.await_args[0]
        assert "UPDATE conversations" in update_args[0]
        assert "tags" in update_args[0]

    async def test_sets_general_tag_when_no_delegations(self, mock_pool):
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])
        conn.execute = AsyncMock()

        recorder = DelegationRecorder(pool)
        await recorder.update_tags_from_delegations(
            customer_id="cust_a",
            conversation_id="conv_1",
        )

        update_args = conn.execute.await_args[0]
        # The tags array should contain "general"
        assert ["general"] in update_args or "general" in str(update_args)


class TestDeleteCustomerData:
    async def test_deletes_records_for_customer(self, mock_pool):
        pool, conn = mock_pool
        conn.execute = AsyncMock(return_value="DELETE 5")

        recorder = DelegationRecorder(pool)
        count = await recorder.delete_customer_data(customer_id="cust_a")

        assert count == 5
        sql = conn.execute.await_args[0][0]
        assert "DELETE FROM delegation_records" in sql
        assert "customer_id" in sql

    async def test_returns_zero_when_nothing_to_delete(self, mock_pool):
        pool, conn = mock_pool
        conn.execute = AsyncMock(return_value="DELETE 0")

        recorder = DelegationRecorder(pool)
        count = await recorder.delete_customer_data(customer_id="cust_nobody")

        assert count == 0
