"""Tests for SafetyConfig."""
import os
import pytest


class TestSafetyConfigDefaults:
    def test_default_max_input_length(self, safety_config):
        assert safety_config.max_input_length == 4000

    def test_default_injection_high_threshold(self, safety_config):
        assert safety_config.injection_high_threshold == 0.7

    def test_default_injection_medium_threshold(self, safety_config):
        assert safety_config.injection_medium_threshold == 0.3

    def test_default_per_customer_per_minute(self, safety_config):
        assert safety_config.per_customer_per_minute == 30

    def test_default_per_customer_per_day(self, safety_config):
        assert safety_config.per_customer_per_day == 500

    def test_default_global_rps(self, safety_config):
        assert safety_config.global_rps == 200

    def test_default_whatsapp_max_length(self, safety_config):
        assert safety_config.whatsapp_max_length == 1600

    def test_default_audit_ttl(self, safety_config):
        assert safety_config.audit_ttl_seconds == 2_592_000

    def test_default_audit_page_size(self, safety_config):
        assert safety_config.audit_page_size == 50


class TestSafetyConfigFromEnv:
    def test_reads_env_overrides(self, monkeypatch):
        monkeypatch.setenv("SAFETY_MAX_INPUT_LENGTH", "8000")
        monkeypatch.setenv("SAFETY_RATE_PER_MINUTE", "60")
        monkeypatch.setenv("SAFETY_RATE_PER_DAY", "1000")
        monkeypatch.setenv("SAFETY_RATE_GLOBAL_RPS", "400")

        from src.safety.config import SafetyConfig
        cfg = SafetyConfig.from_env()
        assert cfg.max_input_length == 8000
        assert cfg.per_customer_per_minute == 60
        assert cfg.per_customer_per_day == 1000
        assert cfg.global_rps == 400

    def test_falls_back_to_defaults(self):
        from src.safety.config import SafetyConfig
        cfg = SafetyConfig.from_env()
        # Defaults should hold when env vars are absent
        assert cfg.max_input_length == 4000
        assert cfg.whatsapp_max_length == 1600
