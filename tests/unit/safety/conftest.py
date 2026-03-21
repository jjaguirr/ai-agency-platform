"""Shared fixtures for safety layer tests."""
import os
import pytest

os.environ.setdefault(
    "JWT_SECRET", "test-secret-do-not-use-in-prod-32-chars-min-xxxxxxxx"
)


@pytest.fixture
def safety_config():
    from src.safety.config import SafetyConfig
    return SafetyConfig()


@pytest.fixture
def prompt_guard():
    from src.safety.prompt_guard import PromptGuard
    return PromptGuard()


@pytest.fixture
def input_pipeline(safety_config, prompt_guard):
    from src.safety.input_pipeline import InputPipeline
    return InputPipeline(config=safety_config, prompt_guard=prompt_guard)
