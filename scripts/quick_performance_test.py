#!/usr/bin/env python3
"""
Quick performance test with optimized EA initialization
"""
import asyncio
import time
import os
from src.agents.executive_assistant import ExecutiveAssistant, ConversationChannel

async def test_optimized_performance():
    """Test EA performance with minimal setup"""
    
    # Use simple customer ID to avoid hex conversion issues
    customer_id = "perf_test_456"
    
    print("🚀 Testing optimized EA performance...")
    
    # Test 1: Initialization time
    init_start = time.time()
    ea = ExecutiveAssistant(customer_id=customer_id)
    init_time = time.time() - init_start
    print(f"   ⏱️  Initialization: {init_time:.2f}s")
    
    # Test 2: Simple response 
    message = "Hello, quick test"
    response_start = time.time()
    response = await ea.handle_customer_interaction(message, ConversationChannel.PHONE)
    response_time = time.time() - response_start
    
    print(f"   ⏱️  Response time: {response_time:.2f}s")
    print(f"   📝 Response length: {len(response)} chars")
    
    # Test 3: Second call (should be faster due to initialized memory)
    message2 = "Follow up test"
    response2_start = time.time()
    response2 = await ea.handle_customer_interaction(message2, ConversationChannel.PHONE)
    response2_time = time.time() - response2_start
    
    print(f"   ⏱️  Follow-up response: {response2_time:.2f}s")
    
    total_time = init_time + response_time
    target_met = total_time < 2.0
    
    print(f"\n🎯 PERFORMANCE SUMMARY:")
    print(f"   • Total time (init + first response): {total_time:.2f}s")
    print(f"   • Target <2s: {'✅ MET' if target_met else '❌ FAILED'}")
    print(f"   • Follow-up improvement: {((response_time - response2_time)/response_time*100):.1f}%")
    
    return target_met

if __name__ == "__main__":
    success = asyncio.run(test_optimized_performance())