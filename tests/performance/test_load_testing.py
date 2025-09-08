#!/usr/bin/env python3
"""
Load Testing Framework - Enterprise Scale Validation

Advanced load testing capabilities to validate EA system performance
at enterprise scale with realistic business scenarios.

Test Scenarios:
1. 1000+ concurrent customers simulation
2. Peak business hours traffic patterns  
3. Mixed workload scenarios
4. Failover and recovery testing
5. Performance degradation monitoring
6. Resource exhaustion testing

Author: AI Agency Platform - Performance Engineering
Version: 1.0.0
"""

import asyncio
import time
import random
import statistics
from typing import List, Dict, Any, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
import pytest
import psutil
import json

from src.agents.executive_assistant import ExecutiveAssistant, ConversationChannel

@dataclass
class LoadTestConfig:
    """Load test configuration parameters"""
    concurrent_users: int = 100
    test_duration_seconds: int = 300  # 5 minutes
    ramp_up_seconds: int = 60  # 1 minute ramp-up
    target_rps: float = 10.0  # requests per second
    failure_threshold: float = 0.05  # 5% failure rate threshold

@dataclass 
class LoadTestResult:
    """Load test execution results"""
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_response_time: float
    p95_response_time: float  
    p99_response_time: float
    max_response_time: float
    min_response_time: float
    throughput_rps: float
    error_rate: float
    test_duration: float
    peak_cpu_usage: float
    peak_memory_usage: float

class EnterpriseLoadTester:
    """Enterprise-grade load testing framework"""
    
    def __init__(self, config: LoadTestConfig):
        self.config = config
        self.results: List[Dict[str, Any]] = []
        self.system_metrics: List[Dict[str, Any]] = []
        self.active_customers: Dict[str, ExecutiveAssistant] = {}
        
    async def generate_realistic_customer_interaction(self, customer_id: str, scenario: str) -> Dict[str, Any]:
        """Generate realistic customer interactions based on business scenarios"""
        
        scenarios = {
            "business_discovery": [
                "I need help understanding what automation could benefit my business",
                "Can you analyze my current business processes for inefficiencies?",
                "What automation tools would work best for a {business_type} business?",
                "Help me identify the biggest time wasters in my daily operations"
            ],
            "automation_creation": [
                "Create a WhatsApp automation for customer inquiries",
                "Set up an Instagram automation for lead generation", 
                "Build a customer onboarding workflow for my business",
                "Create social media posting automation for my brand"
            ],
            "technical_support": [
                "My WhatsApp automation isn't working properly",
                "How do I modify my existing customer onboarding workflow?",
                "I need help troubleshooting my Instagram automation",
                "Can you help me understand my automation performance metrics?"
            ],
            "advanced_consultation": [
                "I need a comprehensive business automation strategy",
                "Help me design an omnichannel customer experience",
                "Create a complete sales funnel with automation touchpoints",
                "Design a business intelligence dashboard for my operations"
            ]
        }
        
        business_types = ["consulting", "ecommerce", "restaurant", "real_estate", "healthcare", "fitness", "marketing"]
        channels = [ConversationChannel.PHONE, ConversationChannel.WHATSAPP, ConversationChannel.EMAIL, ConversationChannel.CHAT]
        
        # Select random interaction parameters
        selected_scenario = scenarios.get(scenario, scenarios["business_discovery"])
        message_template = random.choice(selected_scenario)
        business_type = random.choice(business_types)
        channel = random.choice(channels)
        
        # Format message with business type if template includes it
        message = message_template.format(business_type=business_type) if "{business_type}" in message_template else message_template
        
        return {
            "customer_id": customer_id,
            "message": message,
            "channel": channel,
            "business_type": business_type,
            "scenario": scenario
        }
    
    async def execute_customer_interaction(self, interaction_params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single customer interaction with performance tracking"""
        customer_id = interaction_params["customer_id"]
        message = interaction_params["message"] 
        channel = interaction_params["channel"]
        
        start_time = time.time()
        success = True
        error_message = None
        response_length = 0
        
        try:
            # Get or create EA instance for customer
            if customer_id not in self.active_customers:
                self.active_customers[customer_id] = ExecutiveAssistant(customer_id=customer_id)
            
            ea = self.active_customers[customer_id]
            
            # Execute interaction
            response = await ea.handle_customer_interaction(message, channel)
            response_length = len(response) if response else 0
            
        except Exception as e:
            success = False
            error_message = str(e)
            
        response_time = time.time() - start_time
        
        return {
            "customer_id": customer_id,
            "success": success,
            "response_time": response_time,
            "response_length": response_length,
            "error_message": error_message,
            "timestamp": datetime.now().isoformat(),
            **interaction_params
        }
    
    async def monitor_system_resources(self, duration_seconds: int):
        """Monitor system resources during load test"""
        monitoring_interval = 1.0  # 1 second intervals
        end_time = time.time() + duration_seconds
        
        while time.time() < end_time:
            metrics = {
                "timestamp": datetime.now().isoformat(),
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory_percent": psutil.virtual_memory().percent,
                "memory_used_gb": psutil.virtual_memory().used / (1024**3),
                "disk_io_read_mb": psutil.disk_io_counters().read_bytes / (1024**2) if psutil.disk_io_counters() else 0,
                "disk_io_write_mb": psutil.disk_io_counters().write_bytes / (1024**2) if psutil.disk_io_counters() else 0,
                "network_sent_mb": psutil.net_io_counters().bytes_sent / (1024**2) if psutil.net_io_counters() else 0,
                "network_recv_mb": psutil.net_io_counters().bytes_recv / (1024**2) if psutil.net_io_counters() else 0,
                "active_connections": len(psutil.net_connections()),
                "active_processes": len(psutil.pids())
            }
            
            self.system_metrics.append(metrics)
            await asyncio.sleep(monitoring_interval)
    
    async def execute_load_test(self, scenario_distribution: Dict[str, float] = None) -> LoadTestResult:
        """Execute comprehensive load test with realistic traffic patterns"""
        
        if scenario_distribution is None:
            scenario_distribution = {
                "business_discovery": 0.4,  # 40% discovery conversations
                "automation_creation": 0.3,  # 30% automation requests
                "technical_support": 0.2,    # 20% support interactions  
                "advanced_consultation": 0.1  # 10% advanced consultations
            }
        
        print(f"🚀 Starting enterprise load test:")
        print(f"   • Concurrent users: {self.config.concurrent_users}")
        print(f"   • Test duration: {self.config.test_duration_seconds}s")
        print(f"   • Target RPS: {self.config.target_rps}")
        print(f"   • Ramp-up time: {self.config.ramp_up_seconds}s")
        
        # Start system monitoring
        monitoring_task = asyncio.create_task(
            self.monitor_system_resources(self.config.test_duration_seconds + 30)
        )
        
        # Calculate request scheduling
        total_requests = int(self.config.target_rps * self.config.test_duration_seconds)
        request_interval = 1.0 / self.config.target_rps
        
        # Generate interaction parameters
        interactions = []
        for i in range(total_requests):
            # Select scenario based on distribution
            scenario = random.choices(
                list(scenario_distribution.keys()),
                weights=list(scenario_distribution.values())
            )[0]
            
            customer_id = f"load_test_customer_{i % self.config.concurrent_users:04d}"
            interaction = await self.generate_realistic_customer_interaction(customer_id, scenario)
            interactions.append(interaction)
        
        # Execute load test with controlled rate
        start_time = time.time()
        tasks = []
        
        for i, interaction in enumerate(interactions):
            # Calculate when this request should be sent
            scheduled_time = start_time + (i * request_interval)
            
            # Wait until scheduled time
            current_time = time.time()
            if scheduled_time > current_time:
                await asyncio.sleep(scheduled_time - current_time)
            
            # Create task for this interaction
            task = asyncio.create_task(self.execute_customer_interaction(interaction))
            tasks.append(task)
            
            # Implement gradual ramp-up
            if i < (self.config.target_rps * self.config.ramp_up_seconds):
                ramp_factor = i / (self.config.target_rps * self.config.ramp_up_seconds)
                await asyncio.sleep(request_interval * (2 - ramp_factor))  # Gradual speed up
        
        print(f"   • All requests scheduled. Waiting for completion...")
        
        # Wait for all interactions to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        test_end_time = time.time()
        
        # Stop monitoring
        monitoring_task.cancel()
        try:
            await monitoring_task
        except asyncio.CancelledError:
            pass
        
        # Process results
        successful_results = [r for r in results if isinstance(r, dict) and r.get('success', False)]
        failed_results = [r for r in results if isinstance(r, dict) and not r.get('success', True)] + [r for r in results if not isinstance(r, dict)]
        
        # Calculate performance metrics
        response_times = [r['response_time'] for r in successful_results]
        
        if response_times:
            avg_response_time = statistics.mean(response_times)
            p95_response_time = statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 20 else max(response_times)
            p99_response_time = statistics.quantiles(response_times, n=100)[98] if len(response_times) >= 100 else max(response_times) 
            max_response_time = max(response_times)
            min_response_time = min(response_times)
        else:
            avg_response_time = p95_response_time = p99_response_time = max_response_time = min_response_time = 0
        
        # Calculate system resource peaks
        peak_cpu = max([m['cpu_percent'] for m in self.system_metrics]) if self.system_metrics else 0
        peak_memory = max([m['memory_percent'] for m in self.system_metrics]) if self.system_metrics else 0
        
        # Calculate throughput
        actual_duration = test_end_time - start_time
        actual_throughput = len(successful_results) / actual_duration if actual_duration > 0 else 0
        
        load_test_result = LoadTestResult(
            total_requests=len(results),
            successful_requests=len(successful_results),
            failed_requests=len(failed_results),
            avg_response_time=avg_response_time,
            p95_response_time=p95_response_time,
            p99_response_time=p99_response_time,
            max_response_time=max_response_time,
            min_response_time=min_response_time,
            throughput_rps=actual_throughput,
            error_rate=len(failed_results) / len(results) if results else 0,
            test_duration=actual_duration,
            peak_cpu_usage=peak_cpu,
            peak_memory_usage=peak_memory
        )
        
        self.results = results  # Store for detailed analysis
        return load_test_result

class TestEnterpriseLoadTesting:
    """Enterprise load testing test suite"""
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_moderate_concurrent_load(self):
        """
        Test: Moderate concurrent load handling
        Target: 100 concurrent users with <200ms P95 response time
        Business Impact: Peak business hours performance
        """
        config = LoadTestConfig(
            concurrent_users=100,
            test_duration_seconds=120,  # 2 minutes
            target_rps=8.0,
            ramp_up_seconds=30
        )
        
        load_tester = EnterpriseLoadTester(config)
        result = await load_tester.execute_load_test()
        
        # Performance assertions
        assert result.error_rate <= 0.05, f"Error rate {result.error_rate*100:.2f}% exceeds 5% threshold"
        assert result.p95_response_time <= 0.2, f"P95 response time {result.p95_response_time:.3f}s exceeds 200ms SLA"
        assert result.throughput_rps >= 6.0, f"Throughput {result.throughput_rps:.2f} RPS below minimum of 6.0"
        
        # Resource utilization assertions
        assert result.peak_cpu_usage <= 80, f"Peak CPU usage {result.peak_cpu_usage:.1f}% exceeds 80% limit"
        assert result.peak_memory_usage <= 85, f"Peak memory usage {result.peak_memory_usage:.1f}% exceeds 85% limit"
        
        print(f"✅ Moderate Load Test Results:")
        print(f"   • Total requests: {result.total_requests}")
        print(f"   • Success rate: {(1-result.error_rate)*100:.2f}%")
        print(f"   • Avg response: {result.avg_response_time*1000:.1f}ms")
        print(f"   • P95 response: {result.p95_response_time*1000:.1f}ms") 
        print(f"   • Throughput: {result.throughput_rps:.2f} RPS")
        print(f"   • Peak CPU: {result.peak_cpu_usage:.1f}%")
        print(f"   • Peak Memory: {result.peak_memory_usage:.1f}%")
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.stress
    async def test_high_concurrent_load(self):
        """
        Test: High concurrent load stress test
        Target: 500 concurrent users with acceptable degradation
        Business Impact: Black Friday / high traffic event handling
        """
        config = LoadTestConfig(
            concurrent_users=500,
            test_duration_seconds=180,  # 3 minutes
            target_rps=15.0,
            ramp_up_seconds=60
        )
        
        load_tester = EnterpriseLoadTester(config)
        result = await load_tester.execute_load_test()
        
        # Relaxed performance assertions for high load
        assert result.error_rate <= 0.10, f"Error rate {result.error_rate*100:.2f}% exceeds 10% threshold under high load"
        assert result.p95_response_time <= 0.5, f"P95 response time {result.p95_response_time:.3f}s exceeds 500ms under high load"
        assert result.throughput_rps >= 10.0, f"Throughput {result.throughput_rps:.2f} RPS below minimum of 10.0 under high load"
        
        # System should remain stable even under stress
        assert result.peak_cpu_usage <= 95, f"Peak CPU usage {result.peak_cpu_usage:.1f}% indicates system instability"
        assert result.peak_memory_usage <= 95, f"Peak memory usage {result.peak_memory_usage:.1f}% indicates memory exhaustion risk"
        
        print(f"✅ High Load Stress Test Results:")
        print(f"   • Total requests: {result.total_requests}")
        print(f"   • Success rate: {(1-result.error_rate)*100:.2f}%")
        print(f"   • Avg response: {result.avg_response_time*1000:.1f}ms")
        print(f"   • P95 response: {result.p95_response_time*1000:.1f}ms")
        print(f"   • P99 response: {result.p99_response_time*1000:.1f}ms") 
        print(f"   • Throughput: {result.throughput_rps:.2f} RPS")
        print(f"   • Peak CPU: {result.peak_cpu_usage:.1f}%")
        print(f"   • Peak Memory: {result.peak_memory_usage:.1f}%")
    
    @pytest.mark.asyncio
    async def test_mixed_workload_scenarios(self):
        """
        Test: Mixed business scenario workload
        Target: Realistic business traffic patterns performance
        Business Impact: Real-world usage validation
        """
        # Define realistic scenario distribution
        scenario_distribution = {
            "business_discovery": 0.5,     # 50% - New customer exploration
            "automation_creation": 0.25,   # 25% - Active implementation
            "technical_support": 0.15,     # 15% - Support requests
            "advanced_consultation": 0.10  # 10% - Complex consultations  
        }
        
        config = LoadTestConfig(
            concurrent_users=150,
            test_duration_seconds=240,  # 4 minutes
            target_rps=12.0,
            ramp_up_seconds=45
        )
        
        load_tester = EnterpriseLoadTester(config)
        result = await load_tester.execute_load_test(scenario_distribution)
        
        # Business-focused assertions
        assert result.error_rate <= 0.03, f"Error rate {result.error_rate*100:.2f}% exceeds 3% business quality threshold"
        assert result.p95_response_time <= 0.3, f"P95 response time {result.p95_response_time:.3f}s exceeds 300ms business expectation"
        assert result.avg_response_time <= 0.15, f"Average response time {result.avg_response_time:.3f}s exceeds 150ms user expectation"
        
        # Analyze scenario-specific performance
        scenario_results = {}
        for interaction_result in load_tester.results:
            if isinstance(interaction_result, dict) and 'scenario' in interaction_result:
                scenario = interaction_result['scenario']
                if scenario not in scenario_results:
                    scenario_results[scenario] = []
                scenario_results[scenario].append(interaction_result)
        
        print(f"✅ Mixed Workload Test Results:")
        print(f"   • Overall success rate: {(1-result.error_rate)*100:.2f}%")
        print(f"   • Overall P95 response: {result.p95_response_time*1000:.1f}ms")
        print(f"   • Throughput: {result.throughput_rps:.2f} RPS")
        
        # Per-scenario analysis
        for scenario, results in scenario_results.items():
            successful = [r for r in results if r.get('success', False)]
            if successful:
                scenario_avg = statistics.mean([r['response_time'] for r in successful])
                success_rate = len(successful) / len(results)
                print(f"   • {scenario}: {success_rate*100:.1f}% success, {scenario_avg*1000:.1f}ms avg")
    
    @pytest.mark.asyncio
    async def test_performance_degradation_monitoring(self):
        """
        Test: Performance degradation detection under increasing load
        Target: Identify performance cliff points
        Business Impact: Capacity planning and scaling decisions
        """
        load_levels = [50, 100, 200, 300]  # Progressive load increase
        degradation_results = []
        
        for concurrent_users in load_levels:
            print(f"🔍 Testing with {concurrent_users} concurrent users...")
            
            config = LoadTestConfig(
                concurrent_users=concurrent_users,
                test_duration_seconds=90,  # Shorter tests for comparison
                target_rps=concurrent_users * 0.1,  # Scale RPS with users
                ramp_up_seconds=20
            )
            
            load_tester = EnterpriseLoadTester(config)
            result = await load_tester.execute_load_test()
            
            degradation_results.append({
                'concurrent_users': concurrent_users,
                'p95_response_time': result.p95_response_time,
                'error_rate': result.error_rate,
                'throughput_rps': result.throughput_rps,
                'peak_cpu': result.peak_cpu_usage,
                'peak_memory': result.peak_memory_usage
            })
        
        # Analyze performance degradation
        print(f"\n📈 Performance Degradation Analysis:")
        print("-" * 60)
        print(f"{'Users':<8} {'P95 (ms)':<10} {'Error %':<8} {'RPS':<8} {'CPU %':<8} {'Mem %':<8}")
        print("-" * 60)
        
        for result in degradation_results:
            print(f"{result['concurrent_users']:<8} "
                  f"{result['p95_response_time']*1000:<10.1f} "
                  f"{result['error_rate']*100:<8.2f} "
                  f"{result['throughput_rps']:<8.1f} "
                  f"{result['peak_cpu']:<8.1f} "
                  f"{result['peak_memory']:<8.1f}")
        
        # Detect performance cliffs
        for i in range(1, len(degradation_results)):
            current = degradation_results[i]
            previous = degradation_results[i-1]
            
            # Check for significant performance degradation
            response_degradation = (current['p95_response_time'] - previous['p95_response_time']) / previous['p95_response_time']
            error_increase = current['error_rate'] - previous['error_rate']
            
            if response_degradation > 0.5:  # 50% response time increase
                print(f"⚠️  Performance cliff detected at {current['concurrent_users']} users: {response_degradation*100:.1f}% response time increase")
            
            if error_increase > 0.02:  # 2% error rate increase
                print(f"⚠️  Error rate cliff detected at {current['concurrent_users']} users: {error_increase*100:.1f}% error rate increase")
        
        # Recommend optimal capacity
        stable_results = [r for r in degradation_results if r['error_rate'] <= 0.05 and r['p95_response_time'] <= 0.2]
        if stable_results:
            max_stable_users = max([r['concurrent_users'] for r in stable_results])
            print(f"\n✅ Recommended maximum concurrent users: {max_stable_users}")
        else:
            print(f"\n❌ No configuration met SLA targets - system requires optimization")
        
        # Assert that we can handle at least 100 concurrent users
        users_100_result = next((r for r in degradation_results if r['concurrent_users'] == 100), None)
        if users_100_result:
            assert users_100_result['error_rate'] <= 0.05, f"Error rate {users_100_result['error_rate']*100:.2f}% at 100 users exceeds 5%"
            assert users_100_result['p95_response_time'] <= 0.2, f"P95 response time {users_100_result['p95_response_time']:.3f}s at 100 users exceeds 200ms"

@pytest.mark.asyncio  
async def test_enterprise_scale_validation():
    """
    Ultimate enterprise scale validation test
    Target: 1000+ concurrent customers with acceptable performance
    Business Impact: Enterprise customer scalability validation
    """
    print("🏢 ENTERPRISE SCALE VALIDATION TEST")
    print("=" * 50)
    
    config = LoadTestConfig(
        concurrent_users=1000,
        test_duration_seconds=300,  # 5 minutes
        target_rps=25.0,
        ramp_up_seconds=120  # 2-minute ramp-up for enterprise scale
    )
    
    load_tester = EnterpriseLoadTester(config)
    
    print("⚠️  This test requires significant system resources")
    print("   Running enterprise scale simulation...")
    
    result = await load_tester.execute_load_test()
    
    # Enterprise-grade performance validation
    enterprise_sla_met = (
        result.error_rate <= 0.10 and           # 10% error tolerance for extreme load
        result.p95_response_time <= 1.0 and     # 1 second P95 under extreme load  
        result.throughput_rps >= 15.0            # Minimum 15 RPS throughput
    )
    
    print(f"\n🏢 ENTERPRISE SCALE TEST RESULTS:")
    print("=" * 50)
    print(f"Scale: {result.total_requests:,} total requests")
    print(f"Success Rate: {(1-result.error_rate)*100:.2f}%")
    print(f"Average Response: {result.avg_response_time*1000:.1f}ms")
    print(f"P95 Response: {result.p95_response_time*1000:.1f}ms")
    print(f"P99 Response: {result.p99_response_time*1000:.1f}ms")
    print(f"Max Response: {result.max_response_time*1000:.1f}ms")
    print(f"Throughput: {result.throughput_rps:.2f} RPS")
    print(f"Peak CPU: {result.peak_cpu_usage:.1f}%")
    print(f"Peak Memory: {result.peak_memory_usage:.1f}%")
    print(f"Test Duration: {result.test_duration:.1f} seconds")
    
    enterprise_readiness = "✅ ENTERPRISE READY" if enterprise_sla_met else "⚠️  REQUIRES OPTIMIZATION"
    print(f"\nEnterprise Readiness: {enterprise_readiness}")
    
    if enterprise_sla_met:
        print("\n🎉 System validated for enterprise scale deployment!")
        print("   • Capable of handling 1000+ concurrent customers")
        print("   • Maintains acceptable performance under extreme load")
        print("   • Ready for production enterprise customers")
    else:
        print("\n🔧 System requires optimization for enterprise scale:")
        if result.error_rate > 0.10:
            print(f"   • Reduce error rate from {result.error_rate*100:.2f}% to <10%")
        if result.p95_response_time > 1.0:
            print(f"   • Improve P95 response time from {result.p95_response_time*1000:.1f}ms to <1000ms")
        if result.throughput_rps < 15.0:
            print(f"   • Increase throughput from {result.throughput_rps:.2f} to >15 RPS")
    
    # Store enterprise test results for analysis
    with open(f"enterprise_load_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", "w") as f:
        json.dump({
            "test_config": {
                "concurrent_users": config.concurrent_users,
                "test_duration_seconds": config.test_duration_seconds, 
                "target_rps": config.target_rps
            },
            "results": {
                "total_requests": result.total_requests,
                "successful_requests": result.successful_requests,
                "failed_requests": result.failed_requests,
                "avg_response_time": result.avg_response_time,
                "p95_response_time": result.p95_response_time,
                "p99_response_time": result.p99_response_time,
                "max_response_time": result.max_response_time,
                "throughput_rps": result.throughput_rps,
                "error_rate": result.error_rate,
                "peak_cpu_usage": result.peak_cpu_usage,
                "peak_memory_usage": result.peak_memory_usage
            },
            "enterprise_sla_met": enterprise_sla_met,
            "timestamp": datetime.now().isoformat()
        }, f, indent=2)
    
    return enterprise_sla_met, result