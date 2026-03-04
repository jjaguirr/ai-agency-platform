"""Unit tests for platform configuration."""
import os
import pytest
from src.utils.config import DatabaseConfig, RedisConfig, PlatformConfig


class TestDatabaseConfig:
    def test_default_values(self):
        config = DatabaseConfig()
        assert config.host == "localhost"
        assert config.port == 5432

    def test_url_property(self):
        config = DatabaseConfig()
        assert "postgresql://" in config.url

    def test_from_env(self):
        os.environ["POSTGRES_HOST"] = "testhost"
        config = DatabaseConfig.from_env()
        assert config.host == "testhost"
        del os.environ["POSTGRES_HOST"]


class TestRedisConfig:
    def test_default_values(self):
        config = RedisConfig()
        assert config.host == "localhost"
        assert config.port == 6379

    def test_url_property(self):
        config = RedisConfig()
        assert config.url == "redis://localhost:6379/0"


class TestPlatformConfig:
    def test_from_env(self):
        config = PlatformConfig.from_env()
        assert config.database is not None
        assert config.redis is not None
