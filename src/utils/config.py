"""Configuration management for AI Agency Platform."""
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5432
    database: str = "mcphub"
    user: str = "mcphub"
    password: str = "mcphub_password"

    @property
    def url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        return cls(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "mcphub"),
            user=os.getenv("POSTGRES_USER", "mcphub"),
            password=os.getenv("POSTGRES_PASSWORD", "mcphub_password"),
        )


@dataclass
class RedisConfig:
    host: str = "localhost"
    port: int = 6379
    db: int = 0

    @property
    def url(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.db}"

    @classmethod
    def from_env(cls) -> "RedisConfig":
        return cls(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
        )


@dataclass
class PlatformConfig:
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    openai_api_key: Optional[str] = None
    debug: bool = False

    @classmethod
    def from_env(cls) -> "PlatformConfig":
        return cls(
            database=DatabaseConfig.from_env(),
            redis=RedisConfig.from_env(),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            debug=os.getenv("DEBUG", "false").lower() == "true",
        )
