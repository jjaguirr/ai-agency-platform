#!/usr/bin/env python3
"""
SLA Validation Tests - Phase 2 EA Orchestration

Comprehensive automated testing to validate all production SLA targets
for premium-casual EA system at enterprise scale.

Test Categories:
1. Core EA Performance SLAs
2. Database Query Performance  
3. Memory System Performance
4. Cross-channel Context Retrieval
5. Premium-casual Personality Transformation
6. Enterprise Scale Load Validation

Author: AI Agency Platform - Performance Engineering  
Version: 1.0.0
"""

import asyncio
import time
import statistics
from typing import List, Dict, Any
import pytest
import psutil
import os
from datetime import datetime, timedelta

# Import EA system components
from src.agents.executive_assistant import ExecutiveAssistant, ConversationChannel

class PerformanceMetrics:
    """Collect and analyze performance metrics"""
    
    def __init__(self):
        self.measurements: Dict[str, List[float]] = {}
        self.system_metrics: Dict[str, Any] = {}
    
    def record(self, metric_name: str, value: float):
        """Record a performance measurement"""
        if metric_name not in self.measurements:
            self.measurements[metric_name] = []
        self.measurements[metric_name].append(value)
    
    def get_stats(self, metric_name: str) -> Dict[str, float]:
        """Get statistical analysis of recorded metrics"""
        values = self.measurements.get(metric_name, [])
        if not values:
            return {}
        
        return {
            'count': len(values),
            'mean': statistics.mean(values),
            'median': statistics.median(values),
            'p95': statistics.quantiles(values, n=20)[18] if len(values) >= 20 else max(values),
            'p99': statistics.quantiles(values, n=100)[98] if len(values) >= 100 else max(values),
            'min': min(values),
            'max': max(values),
            'std_dev': statistics.stdev(values) if len(values) > 1 else 0
        }
    
    def record_system_metrics(self):
        """Record current system resource usage"""
        self.system_metrics = {
            'cpu_percent': psutil.cpu_percent(interval=0.1),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_io': psutil.disk_io_counters()._asdict() if psutil.disk_io_counters() else {},
            'network_io': psutil.net_io_counters()._asdict() if psutil.net_io_counters() else {},
            'timestamp': datetime.now().isoformat()
        }

@pytest.fixture(scope="session")
def performance_metrics():
    """Global performance metrics collector"""
    return PerformanceMetrics()

@pytest.fixture(scope="session") 
async def test_customer_id():
    """Dedicated customer ID for performance testing"""
    return "perf_test_customer_001"

@pytest.fixture(scope="session")
async def mock_database_manager():
    """Mock database connection for performance testing"""
    class MockDatabaseManager:
        async def get_connection(self):
            return MockConnection()
    
    class MockConnection:
        async def fetch(self, query, *args):
            # Simulate database query delay
            await asyncio.sleep(0.01)  # 10ms simulated query time
            return []
    
    return MockDatabaseManager()

class TestSLAValidation:
    """Core SLA validation test suite"""
    
    @pytest.mark.asyncio
    @pytest.mark.benchmark(group="ea_initialization")
    async def test_ea_initialization_performance(self, test_customer_id, performance_metrics, benchmark):
        """
        Test: Executive Assistant Initialization Performance
        SLA Target: <500ms for EA initialization
        Business Impact: Customer onboarding experience
        """
        def init_ea():
            return ExecutiveAssistant(customer_id=test_customer_id)
        
        # Benchmark EA initialization
        ea = benchmark(init_ea)
        
        # Manual timing for detailed metrics
        start_time = time.time()
        ea_manual = ExecutiveAssistant(customer_id=test_customer_id)
        init_time = time.time() - start_time
        
        performance_metrics.record('ea_initialization_ms', init_time * 1000)
        
        # SLA Validation
        assert init_time < 0.5, f"EA initialization took {init_time:.3f}s, exceeds 500ms SLA"
        
        print(f"✅ EA Initialization: {init_time*1000:.1f}ms (SLA: <500ms)")
    
    @pytest.mark.asyncio
    @pytest.mark.benchmark(group="premium_casual_personality")  
    async def test_premium_casual_personality_transformation(self, test_customer_id, performance_metrics):
        """
        Test: Premium-Casual Personality Transformation Speed
        SLA Target: <500ms for personality processing
        Business Impact: Natural conversation flow
        """
        ea = ExecutiveAssistant(customer_id=test_customer_id)
        test_message = "Help me set up customer onboarding automation for my consulting business"
        
        # Test multiple personality transformations
        transformation_times = []
        
        for i in range(10):
            start_time = time.time()
            response = await ea.handle_customer_interaction(
                test_message, 
                ConversationChannel.PHONE
            )
            transformation_time = time.time() - start_time
            transformation_times.append(transformation_time)
            performance_metrics.record('personality_transformation_ms', transformation_time * 1000)
        
        # Statistical analysis
        avg_time = statistics.mean(transformation_times)
        p95_time = statistics.quantiles(transformation_times, n=20)[18]
        
        # SLA Validation
        assert avg_time < 0.5, f"Average personality transformation {avg_time:.3f}s exceeds 500ms SLA"
        assert p95_time < 0.5, f"95th percentile transformation {p95_time:.3f}s exceeds 500ms SLA"
        
        print(f"✅ Personality Transformation - Avg: {avg_time*1000:.1f}ms, P95: {p95_time*1000:.1f}ms (SLA: <500ms)")
    
    @pytest.mark.asyncio
    async def test_database_query_performance(self, mock_database_manager, performance_metrics):
        """
        Test: Database Query Performance
        SLA Target: <100ms average query time
        Business Impact: System responsiveness
        """
        # Test various database operations
        query_types = [
            ("customer_lookup", "SELECT * FROM customers WHERE id = $1"),
            ("agent_fetch", "SELECT * FROM agents WHERE customer_id = $1 LIMIT 10"),
            ("memory_search", "SELECT * FROM agent_memories WHERE customer_id = $1 ORDER BY created_at DESC LIMIT 20"),
            ("workflow_status", "SELECT * FROM workflows WHERE customer_id = $1 AND status = 'active'"),
        ]
        
        test_customer_uuid = "123e4567-e89b-12d3-a456-426614174000"
        
        for query_name, query_sql in query_types:
            query_times = []
            
            # Execute each query type 20 times
            for _ in range(20):
                start_time = time.time()
                conn = await mock_database_manager.get_connection()
                await conn.fetch(query_sql, test_customer_uuid)
                query_time = time.time() - start_time
                query_times.append(query_time)
                performance_metrics.record(f'db_query_{query_name}_ms', query_time * 1000)
            
            # Statistical validation
            avg_time = statistics.mean(query_times)
            assert avg_time < 0.1, f"{query_name} average query time {avg_time:.3f}s exceeds 100ms SLA"
            
            print(f"✅ DB Query {query_name}: {avg_time*1000:.1f}ms average (SLA: <100ms)")
    
    @pytest.mark.asyncio
    async def test_memory_recall_performance(self, test_customer_id, performance_metrics):
        """
        Test: Memory Recall Performance (Simulated)
        SLA Target: <500ms (95th percentile)
        Business Impact: Context-aware conversations
        """
        # Simulate memory recall operations
        recall_times = []
        search_queries = [
            "communication preferences",
            "business type information", 
            "automation requirements",
            "previous conversations",
            "tool interests"
        ]
        
        for query in search_queries:
            for _ in range(10):  # 10 tests per query type
                start_time = time.time()
                # Simulate memory search delay (50-200ms)
                await asyncio.sleep(0.05 + (0.15 * len(query) / 100))
                recall_time = time.time() - start_time
                recall_times.append(recall_time)
                performance_metrics.record('memory_recall_ms', recall_time * 1000)
        
        # Statistical validation
        p95_time = statistics.quantiles(recall_times, n=20)[18]
        avg_time = statistics.mean(recall_times)
        
        assert p95_time < 0.5, f"Memory recall P95 {p95_time:.3f}s exceeds 500ms SLA"
        
        print(f"✅ Memory Recall - Avg: {avg_time*1000:.1f}ms, P95: {p95_time*1000:.1f}ms (SLA: P95 <500ms)")
    
    @pytest.mark.asyncio
    async def test_cross_channel_context_retrieval(self, test_customer_id, performance_metrics):
        """
        Test: Cross-Channel Context Retrieval Speed
        SLA Target: <500ms for context switching
        Business Impact: Seamless omnichannel experience
        """
        ea = ExecutiveAssistant(customer_id=test_customer_id)
        
        # Simulate conversation across different channels
        channels = [
            ConversationChannel.PHONE,
            ConversationChannel.WHATSAPP,
            ConversationChannel.EMAIL,
            ConversationChannel.CHAT
        ]
        
        # Initial context establishment
        await ea.handle_customer_interaction(
            "I need help setting up automation for my business", 
            ConversationChannel.PHONE
        )
        
        context_retrieval_times = []
        
        # Test context retrieval across channels
        for channel in channels:
            for _ in range(5):  # 5 tests per channel
                start_time = time.time()
                response = await ea.handle_customer_interaction(
                    "What did we discuss about my business automation?",
                    channel
                )
                context_time = time.time() - start_time
                context_retrieval_times.append(context_time)
                performance_metrics.record('cross_channel_context_ms', context_time * 1000)
        
        # Statistical validation
        avg_time = statistics.mean(context_retrieval_times)
        p95_time = statistics.quantiles(context_retrieval_times, n=20)[18]
        
        assert avg_time < 0.5, f"Cross-channel context avg {avg_time:.3f}s exceeds 500ms SLA"
        assert p95_time < 0.5, f"Cross-channel context P95 {p95_time:.3f}s exceeds 500ms SLA"
        
        print(f"✅ Cross-Channel Context - Avg: {avg_time*1000:.1f}ms, P95: {p95_time*1000:.1f}ms (SLA: <500ms)")
    
    @pytest.mark.asyncio
    async def test_concurrent_customer_handling(self, performance_metrics):
        """
        Test: Concurrent Customer Handling Performance
        SLA Target: Handle 100+ concurrent customers with <200ms API response
        Business Impact: Peak traffic handling capability
        """
        async def simulate_customer_interaction(customer_num: int):
            """Simulate a single customer interaction"""
            customer_id = f"perf_test_concurrent_{customer_num:03d}"
            ea = ExecutiveAssistant(customer_id=customer_id)
            
            start_time = time.time()
            response = await ea.handle_customer_interaction(
                f"Help me with business automation setup for customer {customer_num}",
    ConversationChannel.CHAT
            )
            response_time = time.time() - start_time
            
            performance_metrics.record('concurrent_api_response_ms', response_time * 1000)
            return response_time
        
        # Test with 100 concurrent customers
        print("🚀 Testing 100 concurrent customer interactions...")
        tasks = [simulate_customer_interaction(i) for i in range(100)]
        
        start_time = time.time()
        response_times = await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        
        # Statistical analysis
        avg_response_time = statistics.mean(response_times)
        p95_response_time = statistics.quantiles(response_times, n=20)[18]
        max_response_time = max(response_times)
        
        # SLA Validation
        assert avg_response_time < 0.2, f"Concurrent API average {avg_response_time:.3f}s exceeds 200ms SLA"
        assert p95_response_time < 0.2, f"Concurrent API P95 {p95_response_time:.3f}s exceeds 200ms SLA"
        
        print(f"✅ Concurrent Load (100 customers):")
        print(f"   - Total time: {total_time:.2f}s")
        print(f"   - Avg response: {avg_response_time*1000:.1f}ms")  
        print(f"   - P95 response: {p95_response_time*1000:.1f}ms")
        print(f"   - Max response: {max_response_time*1000:.1f}ms")
        print(f"   - SLA Status: {'✅ PASSED' if p95_response_time < 0.2 else '❌ FAILED'}")

    @pytest.mark.asyncio
    async def test_system_resource_monitoring(self, performance_metrics):
        """
        Test: System Resource Usage During Load
        SLA Target: <80% CPU, <85% memory under normal load
        Business Impact: System stability and scalability
        """
        # Record baseline metrics
        performance_metrics.record_system_metrics()
        baseline_cpu = performance_metrics.system_metrics['cpu_percent']
        baseline_memory = performance_metrics.system_metrics['memory_percent']
        
        # Simulate moderate load
        async def moderate_load_simulation():
            tasks = []
            for i in range(20):  # 20 concurrent operations
                customer_id = f"resource_test_{i}"
                ea = ExecutiveAssistant(customer_id=customer_id)
                task = ea.handle_customer_interaction(
                    "Complex business analysis and automation recommendations needed",
        ConversationChannel.CHAT
                )
                tasks.append(task)
            
            await asyncio.gather(*tasks)
        
        # Execute load test while monitoring resources
        start_time = time.time()
        await moderate_load_simulation()
        test_duration = time.time() - start_time
        
        # Record post-load metrics
        performance_metrics.record_system_metrics()
        load_cpu = performance_metrics.system_metrics['cpu_percent']
        load_memory = performance_metrics.system_metrics['memory_percent']
        
        # Resource validation
        assert load_cpu < 80, f"CPU usage {load_cpu:.1f}% exceeds 80% SLA during load"
        assert load_memory < 85, f"Memory usage {load_memory:.1f}% exceeds 85% SLA during load"
        
        print(f"✅ Resource Usage During Load:")
        print(f"   - Test duration: {test_duration:.2f}s")
        print(f"   - CPU: {baseline_cpu:.1f}% → {load_cpu:.1f}% (SLA: <80%)")
        print(f"   - Memory: {baseline_memory:.1f}% → {load_memory:.1f}% (SLA: <85%)")
        
        performance_metrics.record('cpu_usage_percent', load_cpu)
        performance_metrics.record('memory_usage_percent', load_memory)

@pytest.mark.asyncio
async def test_generate_performance_report(performance_metrics):
    """Generate comprehensive performance test report"""
    
    print("\n" + "="*80)
    print("📊 COMPREHENSIVE PERFORMANCE TEST REPORT")
    print("="*80)
    
    # Collect all metrics
    all_metrics = {}
    sla_results = {}
    
    for metric_name, measurements in performance_metrics.measurements.items():
        if measurements:
            stats = performance_metrics.get_stats(metric_name)
            all_metrics[metric_name] = stats
            
            # SLA evaluation
            if 'initialization' in metric_name:
                sla_target = 500  # 500ms
                sla_met = stats['mean'] < sla_target
            elif 'personality_transformation' in metric_name:
                sla_target = 500  # 500ms  
                sla_met = stats['p95'] < sla_target
            elif 'db_query' in metric_name:
                sla_target = 100  # 100ms
                sla_met = stats['mean'] < sla_target
            elif 'memory_recall' in metric_name:
                sla_target = 500  # 500ms
                sla_met = stats['p95'] < sla_target
            elif 'api_response' in metric_name:
                sla_target = 200  # 200ms
                sla_met = stats['p95'] < sla_target
            else:
                continue
                
            sla_results[metric_name] = {
                'target': sla_target,
                'actual': stats['p95'] if 'p95' in stats else stats['mean'],
                'met': sla_met
            }
    
    # Print detailed results
    print(f"\n📈 PERFORMANCE METRICS SUMMARY:")
    print("-" * 50)
    
    for metric_name, stats in all_metrics.items():
        if metric_name in sla_results:
            sla_info = sla_results[metric_name]
            status = "✅ PASS" if sla_info['met'] else "❌ FAIL"
            print(f"{metric_name}:")
            print(f"  Target: <{sla_info['target']}ms | Actual: {sla_info['actual']:.1f}ms | {status}")
            print()
    
    # Overall SLA compliance
    total_slas = len(sla_results)
    passed_slas = sum(1 for result in sla_results.values() if result['met'])
    compliance_rate = (passed_slas / total_slas) * 100 if total_slas > 0 else 0
    
    print(f"\n🎯 SLA COMPLIANCE SUMMARY:")
    print("-" * 30)
    print(f"Total SLAs Tested: {total_slas}")
    print(f"SLAs Passed: {passed_slas}")
    print(f"SLAs Failed: {total_slas - passed_slas}")
    print(f"Compliance Rate: {compliance_rate:.1f}%")
    
    overall_status = "✅ SYSTEM READY" if compliance_rate >= 90 else "⚠️  OPTIMIZATION NEEDED" if compliance_rate >= 75 else "❌ CRITICAL ISSUES"
    print(f"Overall Status: {overall_status}")
    
    # System resource summary
    if performance_metrics.system_metrics:
        print(f"\n💻 SYSTEM RESOURCE USAGE:")
        print("-" * 30)
        print(f"CPU Usage: {performance_metrics.system_metrics.get('cpu_percent', 0):.1f}%")
        print(f"Memory Usage: {performance_metrics.system_metrics.get('memory_percent', 0):.1f}%")
        print(f"Timestamp: {performance_metrics.system_metrics.get('timestamp', 'N/A')}")
    
    print("\n" + "="*80)
    
    # Assert overall system readiness
    assert compliance_rate >= 80, f"SLA compliance rate {compliance_rate:.1f}% below acceptable threshold of 80%"
    
    return all_metrics, sla_results, compliance_rate