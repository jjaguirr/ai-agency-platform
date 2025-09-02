#!/bin/bash

# Test script specifically for basic ExecutiveAssistant functionality
# This validates real integration without mocks

set -e

echo "🤖 Testing Basic ExecutiveAssistant (Real Implementation)"
echo "========================================================"

# Activate virtual environment
source venv/bin/activate
export PYTHONPATH=.

# Set Python path
export PYTHONPATH="${PWD}/src:${PYTHONPATH}"

# Test the actual implementation
python3 -c "
import asyncio
import sys
sys.path.append('src')

from src.agents.executive_assistant import ExecutiveAssistant, ConversationChannel

async def test_basic_ea():
    print('🔧 Creating ExecutiveAssistant instance...')
    ea = ExecutiveAssistant(customer_id='test_basic_123')
    print('✅ ExecutiveAssistant created successfully')
    
    print('💬 Testing basic conversation...')
    response = await ea.handle_customer_interaction(
        'Hello, I run a small consulting business and need help with automation',
        ConversationChannel.CHAT
    )
    
    print(f'✅ Got response: {response[:100]}...')
    
    print('💾 Testing memory storage...')
    await ea.memory.store_business_knowledge(
        'Customer runs a consulting business',
        {'category': 'business_info'}
    )
    print('✅ Memory storage successful')
    
    print('🔍 Testing memory search...')
    results = await ea.memory.search_business_knowledge('consulting')
    print(f'✅ Found {len(results)} memory results')
    
    print('🎉 All basic tests passed!')

if __name__ == '__main__':
    asyncio.run(test_basic_ea())
"

echo ""
echo "✅ Basic ExecutiveAssistant test completed successfully!"
echo "🚀 The real implementation is working (no mocks used)"