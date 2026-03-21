"""Tests for IntelligenceSweep — background batch processor."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.intelligence.config import IntelligenceConfig
from src.intelligence.sweep import IntelligenceSweep


@pytest.fixture
def deps():
    repo = AsyncMock()
    recorder = AsyncMock()
    summarizer = AsyncMock()
    quality = MagicMock()
    config = IntelligenceConfig()
    return repo, recorder, summarizer, quality, config


@pytest.fixture
def sweep(deps):
    repo, recorder, summarizer, quality, config = deps
    return IntelligenceSweep(
        conversation_repo=repo,
        delegation_recorder=recorder,
        summarizer=summarizer,
        quality_analyzer=quality,
        config=config,
    )


class TestSweepRun:
    async def test_processes_idle_conversations(self, deps, sweep):
        repo, recorder, summarizer, quality, _ = deps
        repo.get_conversations_needing_summary = AsyncMock(return_value=[
            {"id": "conv_1", "customer_id": "cust_a"},
        ])
        repo.get_messages = AsyncMock(return_value=[
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ])
        summarizer.summarize = AsyncMock(return_value="Greeting exchange.")
        recorder.get_delegation_statuses = AsyncMock(return_value=[])
        quality.analyze = MagicMock(return_value=MagicMock(to_dict=lambda: {}))
        repo.set_summary = AsyncMock()
        repo.set_quality_signals = AsyncMock()
        recorder.update_tags_from_delegations = AsyncMock()

        count = await sweep.run()

        assert count == 1
        summarizer.summarize.assert_awaited_once()
        repo.set_summary.assert_awaited_once_with(
            conversation_id="conv_1", summary="Greeting exchange.",
        )

    async def test_empty_sweep_is_noop(self, deps, sweep):
        repo, _, summarizer, _, _ = deps
        repo.get_conversations_needing_summary = AsyncMock(return_value=[])

        count = await sweep.run()

        assert count == 0
        summarizer.summarize.assert_not_awaited()

    async def test_individual_failure_does_not_stop_batch(self, deps, sweep):
        repo, recorder, summarizer, quality, _ = deps
        repo.get_conversations_needing_summary = AsyncMock(return_value=[
            {"id": "conv_1", "customer_id": "cust_a"},
            {"id": "conv_2", "customer_id": "cust_b"},
        ])
        # First conversation fails, second succeeds
        call_count = 0

        async def _get_messages(*, customer_id, conversation_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("db error")
            return [{"role": "user", "content": "test"}]

        repo.get_messages = AsyncMock(side_effect=_get_messages)
        summarizer.summarize = AsyncMock(return_value="Summary.")
        recorder.get_delegation_statuses = AsyncMock(return_value=[])
        quality.analyze = MagicMock(return_value=MagicMock(to_dict=lambda: {}))
        repo.set_summary = AsyncMock()
        repo.set_quality_signals = AsyncMock()
        recorder.update_tags_from_delegations = AsyncMock()

        count = await sweep.run()

        assert count == 2  # both attempted
        # Only second should have been summarized
        assert summarizer.summarize.await_count == 1

    async def test_calls_quality_analyzer(self, deps, sweep):
        repo, recorder, summarizer, quality, _ = deps
        repo.get_conversations_needing_summary = AsyncMock(return_value=[
            {"id": "conv_1", "customer_id": "cust_a"},
        ])
        messages = [
            {"role": "user", "content": "I'm frustrated"},
            {"role": "assistant", "content": "Sorry about that"},
        ]
        repo.get_messages = AsyncMock(return_value=messages)
        summarizer.summarize = AsyncMock(return_value="Frustrated customer.")
        recorder.get_delegation_statuses = AsyncMock(return_value=["failed"])
        quality.analyze = MagicMock(return_value=MagicMock(
            to_dict=lambda: {"escalation": True},
        ))
        repo.set_summary = AsyncMock()
        repo.set_quality_signals = AsyncMock()
        recorder.update_tags_from_delegations = AsyncMock()

        await sweep.run()

        quality.analyze.assert_called_once()
        repo.set_quality_signals.assert_awaited_once()

    async def test_updates_tags_from_delegations(self, deps, sweep):
        repo, recorder, summarizer, quality, _ = deps
        repo.get_conversations_needing_summary = AsyncMock(return_value=[
            {"id": "conv_1", "customer_id": "cust_a"},
        ])
        repo.get_messages = AsyncMock(return_value=[
            {"role": "user", "content": "test"},
        ])
        summarizer.summarize = AsyncMock(return_value="Test.")
        recorder.get_delegation_statuses = AsyncMock(return_value=[])
        quality.analyze = MagicMock(return_value=MagicMock(to_dict=lambda: {}))
        repo.set_summary = AsyncMock()
        repo.set_quality_signals = AsyncMock()
        recorder.update_tags_from_delegations = AsyncMock()

        await sweep.run()

        recorder.update_tags_from_delegations.assert_awaited_once_with(
            customer_id="cust_a",
            conversation_id="conv_1",
        )
