"""Tests for ConversationRepository intelligence extensions.

These test the new query methods added for summarization, quality signals,
and tag-filtered listing. Pool is mocked — real Postgres coverage is in
integration tests.
"""
import json
from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.database.conversation_repository import ConversationRepository


def _ts(iso: str = "2026-03-21T09:00:00+00:00") -> datetime:
    return datetime.fromisoformat(iso)


@pytest.fixture
def mock_repo():
    pool = MagicMock()
    conn = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire.return_value = ctx
    return ConversationRepository(pool), conn


class TestGetConversationsNeedingSummary:
    async def test_returns_conversations_without_summary(self, mock_repo):
        repo, conn = mock_repo
        conn.fetch = AsyncMock(return_value=[
            {
                "id": "conv_1",
                "customer_id": "cust_a",
                "updated_at": _ts(),
            },
        ])

        result = await repo.get_conversations_needing_summary(
            idle_threshold_minutes=30, limit=10,
        )

        assert len(result) == 1
        assert result[0]["id"] == "conv_1"
        sql = conn.fetch.await_args[0][0]
        assert "summary IS NULL" in sql
        assert "updated_at" in sql

    async def test_respects_limit(self, mock_repo):
        repo, conn = mock_repo
        conn.fetch = AsyncMock(return_value=[])

        await repo.get_conversations_needing_summary(
            idle_threshold_minutes=30, limit=5,
        )

        args = conn.fetch.await_args[0]
        assert 5 in args  # limit parameter

    async def test_empty_result(self, mock_repo):
        repo, conn = mock_repo
        conn.fetch = AsyncMock(return_value=[])

        result = await repo.get_conversations_needing_summary(
            idle_threshold_minutes=30, limit=10,
        )

        assert result == []


class TestSetSummary:
    async def test_updates_summary_column(self, mock_repo):
        repo, conn = mock_repo
        conn.execute = AsyncMock()

        await repo.set_summary(
            conversation_id="conv_1",
            summary="Customer asked about invoices.",
        )

        conn.execute.assert_awaited_once()
        sql = conn.execute.await_args[0][0]
        assert "UPDATE conversations" in sql
        assert "summary" in sql
        args = conn.execute.await_args[0]
        assert "conv_1" in args
        assert "Customer asked about invoices." in args


class TestSetQualitySignals:
    async def test_updates_quality_signals_column(self, mock_repo):
        repo, conn = mock_repo
        conn.execute = AsyncMock()

        signals = {"escalation": True, "unresolved": False, "long": False}
        await repo.set_quality_signals(
            conversation_id="conv_1",
            signals=signals,
        )

        conn.execute.assert_awaited_once()
        sql = conn.execute.await_args[0][0]
        assert "UPDATE conversations" in sql
        assert "quality_signals" in sql


class TestListConversationsWithIntelligence:
    async def test_select_includes_new_fields(self, mock_repo):
        repo, conn = mock_repo
        conn.fetch = AsyncMock(return_value=[
            {
                "id": "conv_1",
                "channel": "chat",
                "created_at": _ts(),
                "updated_at": _ts("2026-03-21T10:00:00+00:00"),
                "summary": "Discussed invoices.",
                "tags": ["finance"],
                "quality_signals": {"escalation": False},
            },
        ])

        result = await repo.list_conversations(customer_id="cust_a")

        assert result[0]["summary"] == "Discussed invoices."
        assert result[0]["tags"] == ["finance"]
        assert result[0]["quality_signals"] == {"escalation": False}

    async def test_null_summary_becomes_none(self, mock_repo):
        repo, conn = mock_repo
        conn.fetch = AsyncMock(return_value=[
            {
                "id": "conv_1",
                "channel": "chat",
                "created_at": _ts(),
                "updated_at": _ts("2026-03-21T10:00:00+00:00"),
                "summary": None,
                "tags": [],
                "quality_signals": {},
            },
        ])

        result = await repo.list_conversations(customer_id="cust_a")

        assert result[0]["summary"] is None

    async def test_tag_filter_adds_where_clause(self, mock_repo):
        repo, conn = mock_repo
        conn.fetch = AsyncMock(return_value=[])

        await repo.list_conversations(
            customer_id="cust_a", tags=["finance"],
        )

        sql = conn.fetch.await_args[0][0]
        assert "tags" in sql
        assert "@>" in sql

    async def test_no_tag_filter_omits_clause(self, mock_repo):
        repo, conn = mock_repo
        conn.fetch = AsyncMock(return_value=[])

        await repo.list_conversations(customer_id="cust_a")

        sql = conn.fetch.await_args[0][0]
        assert "@>" not in sql
