#!/usr/bin/env python3
"""
Simple EA Basic Test for CI
Tests that Executive Assistant core conversation flow works
"""

import asyncio
import sys
import os
from unittest.mock import Mock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from src.agents.executive_assistant import ExecutiveAssistant, ConversationChannel
except ImportError as e:
    print(f"❌ Failed to import EA: {e}")
    sys.exit(1)

async def test_ea_basic_conversation():
    """Ultra-simple test: EA can handle basic conversation"""
    print("🤖 Testing EA basic conversation...")
    
    try:
        # Mock external dependencies to avoid real connections
        with patch('src.agents.executive_assistant.redis.Redis'), \
             patch('src.agents.executive_assistant.QdrantClient'), \
             patch('src.agents.executive_assistant.psycopg2.connect'):
            
            # Initialize EA
            ea = ExecutiveAssistant("test-customer-ci", "mock-mcp-url")
            
            # Test basic conversation
            response = await ea.handle_customer_interaction(
                "Hi, I run a small bakery called Sweet Dreams",
                ConversationChannel.CHAT
            )
            
            # Validate response
            assert response is not None, "EA returned None"
            assert isinstance(response, str), "EA response is not string"
            assert len(response) > 0, "EA returned empty response"
            assert "error" not in response.lower(), "EA returned error"
            
            print(f"✅ EA responded: {response[:100]}...")
            return True
            
    except Exception as e:
        print(f"❌ EA test failed: {e}")
        return False

async def main():
    """Run simple EA test"""
    print("=== EA Basic Test ===")
    
    success = await test_ea_basic_conversation()
    
    if success:
        print("✅ EA basic test PASSED")
        sys.exit(0)
    else:
        print("❌ EA basic test FAILED")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())