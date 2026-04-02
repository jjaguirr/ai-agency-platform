"""Shared fixtures for onboarding unit tests."""
import pytest
import fakeredis.aioredis

from src.onboarding.state import OnboardingStateStore

CID = "cust_onboard_test"
CID_B = "cust_onboard_other"


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def store(fake_redis):
    return OnboardingStateStore(fake_redis)
