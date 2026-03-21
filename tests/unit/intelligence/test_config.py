"""Tests for IntelligenceConfig."""
import os
from unittest.mock import patch

from src.intelligence.config import IntelligenceConfig


class TestIntelligenceConfigDefaults:
    def test_default_idle_threshold(self):
        cfg = IntelligenceConfig()
        assert cfg.summary_idle_threshold_minutes == 30

    def test_default_max_messages(self):
        cfg = IntelligenceConfig()
        assert cfg.summary_max_messages == 50

    def test_default_escalation_phrases(self):
        cfg = IntelligenceConfig()
        assert "talk to a human" in cfg.escalation_phrases
        assert "frustrated" in cfg.escalation_phrases
        assert len(cfg.escalation_phrases) > 0

    def test_default_long_threshold_multiplier(self):
        cfg = IntelligenceConfig()
        assert cfg.long_conversation_threshold_multiplier == 1.5

    def test_default_sweep_batch_size(self):
        cfg = IntelligenceConfig()
        assert cfg.sweep_batch_size == 10


class TestIntelligenceConfigFromEnv:
    def test_reads_idle_threshold_from_env(self):
        with patch.dict(os.environ, {"INTEL_SUMMARY_IDLE_MINUTES": "60"}):
            cfg = IntelligenceConfig.from_env()
            assert cfg.summary_idle_threshold_minutes == 60

    def test_reads_max_messages_from_env(self):
        with patch.dict(os.environ, {"INTEL_SUMMARY_MAX_MESSAGES": "100"}):
            cfg = IntelligenceConfig.from_env()
            assert cfg.summary_max_messages == 100

    def test_reads_batch_size_from_env(self):
        with patch.dict(os.environ, {"INTEL_SWEEP_BATCH_SIZE": "20"}):
            cfg = IntelligenceConfig.from_env()
            assert cfg.sweep_batch_size == 20

    def test_reads_long_multiplier_from_env(self):
        with patch.dict(os.environ, {"INTEL_LONG_THRESHOLD_MULTIPLIER": "2.0"}):
            cfg = IntelligenceConfig.from_env()
            assert cfg.long_conversation_threshold_multiplier == 2.0

    def test_defaults_when_env_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = IntelligenceConfig.from_env()
            assert cfg.summary_idle_threshold_minutes == 30
            assert cfg.summary_max_messages == 50
            assert cfg.sweep_batch_size == 10
