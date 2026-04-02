#!/usr/bin/env python3
"""
Simple EA Basic Test for CI
Tests that Executive Assistant core conversation flow works
"""

import asyncio
import sys

import pytest

from src.agents.executive_assistant import ExecutiveAssistant, ConversationChannel
from tests.conftest import requires_live_services

# This exercises the real EA conversation pipeline (Mem0 embedding model,
# LLM call). Without the live stack it falls through to a slow local-model
# path and the assertions were previously swallowed by a try/except, so it
# never actually validated anything on cold machines. Gate it like the rest
# of tests/legacy/.
pytestmark = [pytest.mark.integration, requires_live_services]


async def test_ea_basic_conversation():
    """EA can handle a basic conversation end-to-end."""
    ea = ExecutiveAssistant("test-customer-ci", "mock-mcp-url")

    response = await ea.handle_customer_interaction(
        "Hi, I run a small bakery called Sweet Dreams",
        ConversationChannel.CHAT,
    )

    assert response is not None, "EA returned None"
    assert isinstance(response, str), "EA response is not string"
    assert len(response) > 0, "EA returned empty response"
    assert "error" not in response.lower(), "EA returned error"


if __name__ == "__main__":
    # Allow running as a standalone smoke script when services are up.
    asyncio.run(test_ea_basic_conversation())
    print("✅ EA basic test PASSED")
    sys.exit(0)
