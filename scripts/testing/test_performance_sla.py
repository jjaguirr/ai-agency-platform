#!/usr/bin/env python3
"""
Real-world performance test for Personality Engine <500ms SLA requirement.
Tests actual API performance with OpenAI rather than mocked responses.
"""

import asyncio
import time
import openai
import os
import sys
from src.agents.personality import PersonalityEngine, CommunicationChannel

async def test_real_performance():
    """Test real API performance against 500ms SLA requirement"""
    print('🔍 Testing real API performance (500ms SLA requirement)...')
    
    # Real OpenAI client
    openai_client = openai.AsyncOpenAI(
        api_key=os.getenv('OPENAI_API_KEY')
    )
    
    # Mock memory client for testing
    class MockMemoryClient:
        async def ensure_collection(self, *args): 
            return True
        async def store_memory(self, *args): 
            return 'test-id'
        async def search_memories(self, *args): 
            return []
    
    engine = PersonalityEngine(
        openai_client=openai_client,
        memory_client=MockMemoryClient(),
        personality_model='gpt-4o-mini'
    )
    
    # Test single transformation
    test_content = 'Please review the quarterly business analysis report and provide strategic recommendations.'
    
    print(f'📝 Original content: "{test_content}"')
    print('⏱️  Starting transformation...')
    
    start_time = time.time()
    result = await engine.transform_message(
        customer_id='perf-test',
        original_content=test_content,
        channel=CommunicationChannel.EMAIL
    )
    end_time = time.time()
    
    actual_time = int((end_time - start_time) * 1000)
    reported_time = result.transformation_time_ms
    sla_compliance = actual_time < 500
    
    print(f'\n✅ Transformation Results:')
    print(f'   Actual time: {actual_time}ms')
    print(f'   Reported time: {reported_time}ms')
    print(f'   SLA compliance: {"✅ PASS" if sla_compliance else "❌ FAIL"} (target: <500ms)')
    print(f'   Content length: {len(result.transformed_content)} chars')
    print(f'   Premium-casual indicators: {len(result.premium_casual_indicators)}')
    print(f'   Consistency score: {result.consistency_score:.2f}')
    
    print(f'\n📜 Transformed content:')
    print(f'   "{result.transformed_content[:200]}..."' if len(result.transformed_content) > 200 else f'   "{result.transformed_content}"')
    
    print(f'\n🏷️  Premium-casual indicators found: {result.premium_casual_indicators}')
    
    return sla_compliance

async def test_multiple_transformations():
    """Test performance consistency across multiple transformations"""
    print('\n🔄 Testing performance consistency (10 transformations)...')
    
    openai_client = openai.AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
    class MockMemoryClient:
        async def ensure_collection(self, *args): return True
        async def store_memory(self, *args): return 'test-id'
        async def search_memories(self, *args): return []
    
    engine = PersonalityEngine(
        openai_client=openai_client,
        memory_client=MockMemoryClient(),
        personality_model='gpt-4o-mini'
    )
    
    test_contents = [
        'Your quarterly financial report shows significant improvement.',
        'Please review the marketing campaign performance data.',
        'Let\'s schedule a meeting to discuss the strategic partnership.',
        'The client feedback indicates high satisfaction with our service.',
        'I need to analyze the competitive landscape for the product launch.',
        'Your LinkedIn engagement metrics show strong performance trends.',
        'We should optimize the customer acquisition strategy.',
        'The business analysis reveals key growth opportunities.',
        'Please prepare the executive summary for the board meeting.',
        'Your team performance metrics exceed expectations this quarter.'
    ]
    
    times = []
    successes = 0
    
    for i, content in enumerate(test_contents):
        print(f'   Transformation {i+1}/10... ', end='', flush=True)
        
        start_time = time.time()
        result = await engine.transform_message(
            customer_id=f'perf-test-{i}',
            original_content=content,
            channel=CommunicationChannel.EMAIL
        )
        end_time = time.time()
        
        actual_time = int((end_time - start_time) * 1000)
        times.append(actual_time)
        
        if actual_time < 500:
            successes += 1
            print(f'✅ {actual_time}ms')
        else:
            print(f'❌ {actual_time}ms (SLA MISS)')
    
    # Calculate statistics
    avg_time = sum(times) / len(times)
    p95_time = sorted(times)[int(0.95 * len(times))]
    compliance_rate = successes / len(times)
    
    print(f'\n📊 Performance Statistics:')
    print(f'   Average time: {avg_time:.1f}ms')
    print(f'   95th percentile: {p95_time}ms')
    print(f'   SLA compliance rate: {compliance_rate*100:.1f}% ({successes}/{len(times)})')
    print(f'   Target compliance: ≥95% under 500ms')
    
    sla_met = compliance_rate >= 0.95
    print(f'   Overall SLA: {"✅ PASSED" if sla_met else "❌ FAILED"}')
    
    return sla_met

async def main():
    """Main performance validation"""
    print('🚀 Personality Engine Performance SLA Validation')
    print('=' * 60)
    
    if not os.getenv('OPENAI_API_KEY'):
        print('❌ OPENAI_API_KEY environment variable required')
        return False
    
    try:
        # Test 1: Single transformation
        single_result = await test_real_performance()
        
        # Test 2: Multiple transformations
        multiple_result = await test_multiple_transformations()
        
        # Final result
        overall_success = single_result and multiple_result
        
        print('\n' + '=' * 60)
        print('🎯 FINAL PERFORMANCE SLA VALIDATION RESULTS:')
        print(f'   Single transformation: {"✅ PASSED" if single_result else "❌ FAILED"}')
        print(f'   Multiple transformations: {"✅ PASSED" if multiple_result else "❌ FAILED"}')
        print(f'   Overall SLA compliance: {"✅ PASSED" if overall_success else "❌ FAILED"}')
        
        if overall_success:
            print('\n🎉 Personality Engine meets <500ms performance requirement!')
        else:
            print('\n⚠️  Performance optimization may be needed.')
        
        return overall_success
        
    except Exception as e:
        print(f'❌ Performance test failed: {e}')
        return False

if __name__ == '__main__':
    success = asyncio.run(main())
    sys.exit(0 if success else 1)