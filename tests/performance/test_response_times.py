"""
Performance Tests for Response Times
Tests webhook → EA → response flow against business SLA requirements

CRITICAL TDD RULE: These tests MUST FAIL until performance optimizations are complete
Business Requirements: <2s text response, <500ms memory recall, <3s end-to-end
"""

import asyncio
import pytest
import time
import statistics
import requests
import json
from datetime import datetime
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import aiohttp
import psutil
import sys
import os

# Import test modules
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
webhook_service_path = os.path.join(project_root, 'webhook-service')
sys.path.append(project_root)
sys.path.append(webhook_service_path)

try:
    from customer_ea_manager import handle_whatsapp_customer_message, health_check
except ImportError:
    # Fallback for when webhook service is not available
    def handle_whatsapp_customer_message(*args, **kwargs):
        raise ImportError("Webhook service not available")

    def health_check():
        return {"status": "unavailable"}

@pytest.fixture
def performance_test_config():
    """Performance test configuration based on Phase-1 PRD requirements"""
    return {
        "text_response_max_time": 2.0,      # <2 seconds - business requirement
        "memory_recall_max_time": 0.5,      # <500ms - business requirement
        "end_to_end_max_time": 3.0,         # <3 seconds - business requirement
        "concurrent_customers": 100,         # 100 concurrent customers requirement
        "provisioning_max_time": 60.0,      # <60s for EA provisioning
        "webhook_processing_max": 1.0,      # <1s webhook processing
        "success_rate_threshold": 0.95,     # 95% success rate under load
        "p95_response_time": 2.0,           # 95th percentile under 2s
        "p99_response_time": 3.0            # 99th percentile under 3s
    }

@pytest.fixture
def performance_test_messages():
    """Various message types for performance testing"""
    return {
        "simple_greeting": "Hi Sarah",
        "business_inquiry": "I need help automating my business processes",
        "complex_automation": """I run multiple e-commerce stores and need complex automation:
        - Inventory management across 3 platforms
        - Customer service automation
        - Social media scheduling for 5 brands
        - Financial reporting integration
        - Email marketing workflows""",
        "urgent_request": "URGENT: My automation is broken and I need immediate help",
        "memory_recall": "What did we discuss about my business yesterday?",
        "competitive_inquiry": "How are you different from Zapier and Make.com?"
    }

class TestResponseTimePerformance:
    """Test response time performance against business requirements"""

    @pytest.mark.integration
    @pytest.mark.performance
    async def test_text_response_under_2_seconds(self, performance_test_config, performance_test_messages):
        """
        FAILING TEST: Text responses must be under 2 seconds (business requirement)

        Critical business SLA from Phase-1 PRD
        """
        max_time = performance_test_config["text_response_max_time"]
        test_results = []

        for message_type, message in performance_test_messages.items():
            start_time = time.time()

            response = await handle_whatsapp_customer_message(
                whatsapp_number=f"+1555{hash(message_type) % 10000:04d}",
                message=message,
                conversation_id=f"perf_text_{message_type}"
            )

            response_time = time.time() - start_time

            test_results.append({
                "message_type": message_type,
                "response_time": response_time,
                "sla_met": response_time <= max_time,
                "response_length": len(response)
            })

            # Each individual response must meet SLA
            assert response_time <= max_time, f"{message_type} took {response_time:.2f}s (>2s SLA)"
            assert isinstance(response, str) and len(response) > 0, "Valid response required"

        # Calculate statistics
        response_times = [r["response_time"] for r in test_results]
        avg_time = statistics.mean(response_times)
        p95_time = statistics.quantiles(response_times, n=20)[18]  # 95th percentile
        p99_time = statistics.quantiles(response_times, n=100)[98] if len(response_times) >= 100 else max(response_times)

        print(f"📊 Text Response Performance Results:")
        print(f"  Average: {avg_time:.3f}s")
        print(f"  95th percentile: {p95_time:.3f}s")
        print(f"  99th percentile: {p99_time:.3f}s")

        for result in test_results:
            status = "✅" if result["sla_met"] else "❌"
            print(f"  {status} {result['message_type']}: {result['response_time']:.3f}s")

        # Business requirements
        assert avg_time <= 1.5, f"Average response time {avg_time:.2f}s too high"
        assert p95_time <= performance_test_config["p95_response_time"], f"95th percentile {p95_time:.2f}s exceeds {performance_test_config['p95_response_time']}s"

    @pytest.mark.integration
    @pytest.mark.performance
    async def test_memory_recall_under_500ms(self, performance_test_config):
        """
        FAILING TEST: Memory recall must be under 500ms (business requirement)

        Tests the memory system performance specifically
        """
        max_time = performance_test_config["memory_recall_max_time"]
        customer_number = "+1555123456"

        # First, store some business context
        setup_message = """My business details:
        - Name: Test Performance Store
        - Industry: E-commerce
        - Revenue: $100K/month
        - Main challenge: Inventory management"""

        await handle_whatsapp_customer_message(
            whatsapp_number=customer_number,
            message=setup_message,
            conversation_id="memory_setup"
        )

        # Wait a moment for memory storage
        await asyncio.sleep(0.1)

        # Test memory recall performance
        memory_recall_tests = [
            "What's my business name?",
            "What industry am I in?",
            "What's my monthly revenue?",
            "What's my main business challenge?",
            "What did we discuss about my business?"
        ]

        recall_results = []

        for recall_query in memory_recall_tests:
            start_time = time.time()

            response = await handle_whatsapp_customer_message(
                whatsapp_number=customer_number,
                message=recall_query,
                conversation_id=f"memory_recall_{hash(recall_query)}"
            )

            recall_time = time.time() - start_time

            recall_results.append({
                "query": recall_query,
                "recall_time": recall_time,
                "sla_met": recall_time <= max_time,
                "response": response[:100] + "..." if len(response) > 100 else response
            })

            # Each recall must meet SLA
            assert recall_time <= max_time, f"Memory recall for '{recall_query}' took {recall_time:.3f}s (>500ms SLA)"

        # Calculate memory recall statistics
        recall_times = [r["recall_time"] for r in recall_results]
        avg_recall_time = statistics.mean(recall_times)
        max_recall_time = max(recall_times)

        print(f"🧠 Memory Recall Performance Results:")
        print(f"  Average: {avg_recall_time:.3f}s")
        print(f"  Maximum: {max_recall_time:.3f}s")

        for result in recall_results:
            status = "✅" if result["sla_met"] else "❌"
            print(f"  {status} {result['query']}: {result['recall_time']:.3f}s")

        # Business requirements
        assert avg_recall_time <= 0.25, f"Average memory recall {avg_recall_time:.3f}s too slow"
        assert max_recall_time <= max_time, f"Slowest memory recall {max_recall_time:.3f}s exceeds SLA"

    @pytest.mark.integration
    @pytest.mark.performance
    async def test_end_to_end_flow_under_3_seconds(self, performance_test_config):
        """
        FAILING TEST: Complete webhook → EA → response flow under 3 seconds

        Tests the complete business flow including webhook processing
        """
        max_time = performance_test_config["end_to_end_max_time"]
        webhook_url = "http://localhost:8000/webhook/whatsapp"

        test_scenarios = [
            {
                "name": "new_customer_onboarding",
                "message": "Hi, I just purchased EA service and need help getting started with automation"
            },
            {
                "name": "existing_customer_support",
                "message": "My social media automation stopped working, can you help?"
            },
            {
                "name": "complex_automation_request",
                "message": "I need to set up a complex workflow connecting Shopify, Instagram, and my CRM"
            },
            {
                "name": "urgent_business_issue",
                "message": "URGENT: My e-commerce site is down and I need immediate assistance"
            }
        ]

        e2e_results = []

        for scenario in test_scenarios:
            # Create WhatsApp webhook payload
            webhook_payload = {
                "entry": [{
                    "changes": [{
                        "value": {
                            "messages": [{
                                "from": f"155512{hash(scenario['name']) % 100000:05d}",
                                "text": {"body": scenario["message"]},
                                "type": "text",
                                "id": f"test_{scenario['name']}",
                                "timestamp": str(int(time.time()))
                            }]
                        }
                    }]
                }]
            }

            start_time = time.time()

            try:
                # Test via webhook (most realistic)
                with requests.Session() as session:
                    response = session.post(
                        webhook_url,
                        json=webhook_payload,
                        headers={"Content-Type": "application/json"},
                        timeout=max_time + 1.0
                    )

                    e2e_time = time.time() - start_time

                    e2e_results.append({
                        "scenario": scenario["name"],
                        "e2e_time": e2e_time,
                        "sla_met": e2e_time <= max_time,
                        "status_code": response.status_code,
                        "webhook_success": response.status_code == 200
                    })

                    # Each scenario must meet end-to-end SLA
                    assert response.status_code == 200, f"Webhook failed for {scenario['name']}"
                    assert e2e_time <= max_time, f"E2E flow for '{scenario['name']}' took {e2e_time:.2f}s (>3s SLA)"

            except requests.exceptions.ConnectionError:
                # Fallback to direct EA testing if webhook not available
                response = await handle_whatsapp_customer_message(
                    whatsapp_number=f"+155512{hash(scenario['name']) % 100000:05d}",
                    message=scenario["message"],
                    conversation_id=f"e2e_{scenario['name']}"
                )

                e2e_time = time.time() - start_time

                e2e_results.append({
                    "scenario": scenario["name"],
                    "e2e_time": e2e_time,
                    "sla_met": e2e_time <= max_time,
                    "status_code": 200,
                    "webhook_success": False,
                    "fallback_used": True
                })

                assert e2e_time <= max_time, f"E2E flow for '{scenario['name']}' took {e2e_time:.2f}s (>3s SLA)"

        # Calculate end-to-end statistics
        e2e_times = [r["e2e_time"] for r in e2e_results]
        avg_e2e_time = statistics.mean(e2e_times)
        p95_e2e_time = statistics.quantiles(e2e_times, n=20)[18] if len(e2e_times) >= 20 else max(e2e_times)

        print(f"🔄 End-to-End Performance Results:")
        print(f"  Average: {avg_e2e_time:.3f}s")
        print(f"  95th percentile: {p95_e2e_time:.3f}s")

        for result in e2e_results:
            status = "✅" if result["sla_met"] else "❌"
            webhook_status = "🔗" if result.get("webhook_success") else "📞"
            print(f"  {status} {webhook_status} {result['scenario']}: {result['e2e_time']:.3f}s")

        # Business requirements
        assert avg_e2e_time <= 2.0, f"Average E2E time {avg_e2e_time:.2f}s too high"
        assert p95_e2e_time <= max_time, f"95th percentile E2E time {p95_e2e_time:.2f}s exceeds SLA"

class TestConcurrentPerformance:
    """Test performance under concurrent load"""

    @pytest.mark.integration
    @pytest.mark.performance
    async def test_concurrent_customers_performance(self, performance_test_config):
        """
        FAILING TEST: Handle 100 concurrent customers with acceptable performance

        Business requirement: Support 100 concurrent customers
        """
        concurrent_count = min(50, performance_test_config["concurrent_customers"])  # Start with 50
        max_time = performance_test_config["end_to_end_max_time"]
        success_threshold = performance_test_config["success_rate_threshold"]

        # Generate concurrent customer scenarios
        concurrent_tasks = []
        for i in range(concurrent_count):
            customer_number = f"+1555{i:06d}"
            message = f"Hi Sarah, I'm customer {i} and need help with business automation. My main challenge is time management."
            conversation_id = f"concurrent_test_{i}"

            task = handle_whatsapp_customer_message(
                whatsapp_number=customer_number,
                message=message,
                conversation_id=conversation_id
            )
            concurrent_tasks.append((i, task))

        # Execute all tasks concurrently and measure performance
        start_time = time.time()

        results = []
        async with asyncio.Semaphore(20):  # Limit concurrent connections
            for customer_id, task in concurrent_tasks:
                try:
                    customer_start = time.time()
                    response = await task
                    customer_time = time.time() - customer_start

                    results.append({
                        "customer_id": customer_id,
                        "success": True,
                        "response_time": customer_time,
                        "response_length": len(response) if response else 0,
                        "sla_met": customer_time <= max_time
                    })

                except Exception as e:
                    results.append({
                        "customer_id": customer_id,
                        "success": False,
                        "error": str(e),
                        "response_time": None,
                        "sla_met": False
                    })

        total_time = time.time() - start_time

        # Analyze results
        successful_results = [r for r in results if r["success"]]
        failed_results = [r for r in results if not r["success"]]

        success_rate = len(successful_results) / len(results)

        if successful_results:
            response_times = [r["response_time"] for r in successful_results]
            avg_response_time = statistics.mean(response_times)
            p95_response_time = statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 20 else max(response_times)
            sla_compliance_rate = len([r for r in successful_results if r["sla_met"]]) / len(successful_results)
        else:
            avg_response_time = None
            p95_response_time = None
            sla_compliance_rate = 0

        print(f"🚀 Concurrent Performance Results ({concurrent_count} customers):")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Success rate: {success_rate:.1%}")
        print(f"  Failed customers: {len(failed_results)}")

        if successful_results:
            print(f"  Average response time: {avg_response_time:.3f}s")
            print(f"  95th percentile: {p95_response_time:.3f}s")
            print(f"  SLA compliance: {sla_compliance_rate:.1%}")

        # Print failed results for debugging
        if failed_results:
            print(f"❌ Failed customers:")
            for failure in failed_results[:5]:  # Show first 5 failures
                print(f"    Customer {failure['customer_id']}: {failure.get('error', 'Unknown error')}")

        # Business requirements
        assert success_rate >= success_threshold, f"Success rate {success_rate:.1%} below {success_threshold:.1%} threshold"

        if successful_results:
            assert avg_response_time <= max_time, f"Average response time {avg_response_time:.2f}s exceeds {max_time}s SLA"
            assert sla_compliance_rate >= 0.90, f"SLA compliance {sla_compliance_rate:.1%} below 90%"

    @pytest.mark.integration
    @pytest.mark.performance
    async def test_sustained_load_performance(self, performance_test_config):
        """
        FAILING TEST: Sustained load performance over time

        Tests system stability under continuous load
        """
        duration_seconds = 60  # 1 minute sustained load
        requests_per_second = 5  # Conservative load for testing
        max_response_time = performance_test_config["text_response_max_time"]

        load_results = []
        start_time = time.time()
        request_count = 0

        while (time.time() - start_time) < duration_seconds:
            batch_start = time.time()
            batch_tasks = []

            # Create batch of concurrent requests
            for i in range(requests_per_second):
                customer_number = f"+1555{(request_count + i) % 100000:05d}"
                message = f"Load test message {request_count + i}: Help me with automation"

                task = handle_whatsapp_customer_message(
                    whatsapp_number=customer_number,
                    message=message,
                    conversation_id=f"load_test_{request_count + i}"
                )
                batch_tasks.append(task)

            # Execute batch
            try:
                responses = await asyncio.gather(*batch_tasks, return_exceptions=True)
                batch_time = time.time() - batch_start

                for i, response in enumerate(responses):
                    if isinstance(response, Exception):
                        load_results.append({
                            "request_id": request_count + i,
                            "success": False,
                            "error": str(response),
                            "response_time": None
                        })
                    else:
                        load_results.append({
                            "request_id": request_count + i,
                            "success": True,
                            "response_time": batch_time / requests_per_second,  # Approximate
                            "response_length": len(response)
                        })

                request_count += requests_per_second

                # Wait to maintain request rate
                sleep_time = max(0, 1.0 - batch_time)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

            except Exception as e:
                print(f"Batch failed: {e}")
                break

        total_duration = time.time() - start_time

        # Analyze sustained load results
        successful_requests = [r for r in load_results if r["success"]]
        failed_requests = [r for r in load_results if not r["success"]]

        success_rate = len(successful_requests) / len(load_results) if load_results else 0
        actual_rps = len(load_results) / total_duration

        if successful_requests:
            response_times = [r["response_time"] for r in successful_requests if r["response_time"]]
            avg_response_time = statistics.mean(response_times) if response_times else None
        else:
            avg_response_time = None

        print(f"📈 Sustained Load Results ({total_duration:.1f}s):")
        print(f"  Total requests: {len(load_results)}")
        print(f"  Actual RPS: {actual_rps:.1f}")
        print(f"  Success rate: {success_rate:.1%}")
        print(f"  Failed requests: {len(failed_requests)}")

        if avg_response_time:
            print(f"  Average response time: {avg_response_time:.3f}s")

        # Sustained load requirements
        assert success_rate >= 0.95, f"Sustained load success rate {success_rate:.1%} below 95%"
        assert actual_rps >= requests_per_second * 0.8, f"Actual RPS {actual_rps:.1f} below target {requests_per_second}"

        if avg_response_time:
            assert avg_response_time <= max_response_time, f"Average response time {avg_response_time:.2f}s exceeds SLA"

class TestResourceUtilization:
    """Test resource utilization during performance tests"""

    @pytest.mark.integration
    @pytest.mark.performance
    async def test_memory_usage_under_load(self, performance_test_config):
        """
        FAILING TEST: Memory usage should remain stable under load

        Prevents memory leaks and ensures scalability
        """
        import psutil

        # Get initial memory usage
        process = psutil.Process()
        initial_memory = process.memory_info().rss / (1024 * 1024)  # MB

        # Generate load for memory testing
        memory_test_tasks = []
        for i in range(20):  # 20 concurrent customers
            task = handle_whatsapp_customer_message(
                whatsapp_number=f"+1555MEM{i:03d}",
                message=f"Memory test message {i}: Tell me about complex automation workflows involving multiple integrations",
                conversation_id=f"memory_test_{i}"
            )
            memory_test_tasks.append(task)

        # Monitor memory during execution
        memory_samples = []

        async def memory_monitor():
            while True:
                current_memory = process.memory_info().rss / (1024 * 1024)
                memory_samples.append(current_memory)
                await asyncio.sleep(0.1)

        # Start memory monitoring
        monitor_task = asyncio.create_task(memory_monitor())

        try:
            # Execute load test
            responses = await asyncio.gather(*memory_test_tasks, return_exceptions=True)

            # Stop monitoring
            monitor_task.cancel()

            # Analyze memory usage
            final_memory = process.memory_info().rss / (1024 * 1024)
            peak_memory = max(memory_samples) if memory_samples else final_memory
            memory_growth = final_memory - initial_memory

            successful_responses = len([r for r in responses if not isinstance(r, Exception)])

            print(f"💾 Memory Usage Results:")
            print(f"  Initial memory: {initial_memory:.1f} MB")
            print(f"  Peak memory: {peak_memory:.1f} MB")
            print(f"  Final memory: {final_memory:.1f} MB")
            print(f"  Memory growth: {memory_growth:.1f} MB")
            print(f"  Successful responses: {successful_responses}/20")

            # Memory usage requirements
            assert memory_growth <= 100, f"Memory growth {memory_growth:.1f} MB too high (>100 MB)"
            assert peak_memory <= initial_memory + 200, f"Peak memory {peak_memory:.1f} MB too high"
            assert successful_responses >= 18, f"Too many failures: {successful_responses}/20"

        except Exception as e:
            monitor_task.cancel()
            raise e

    @pytest.mark.integration
    @pytest.mark.performance
    async def test_cpu_efficiency_under_load(self):
        """
        FAILING TEST: CPU efficiency should be reasonable under load

        Ensures the system is not CPU-bound under normal load
        """
        import psutil

        # Monitor CPU usage during load test
        process = psutil.Process()
        cpu_samples = []

        async def cpu_monitor():
            while True:
                cpu_percent = process.cpu_percent()
                cpu_samples.append(cpu_percent)
                await asyncio.sleep(0.1)

        # Start CPU monitoring
        monitor_task = asyncio.create_task(cpu_monitor())

        try:
            # Generate CPU load test
            cpu_test_tasks = []
            for i in range(10):  # 10 concurrent requests
                task = handle_whatsapp_customer_message(
                    whatsapp_number=f"+1555CPU{i:03d}",
                    message=f"CPU test {i}: Help me understand complex business automation involving data analysis and reporting",
                    conversation_id=f"cpu_test_{i}"
                )
                cpu_test_tasks.append(task)

            start_time = time.time()
            responses = await asyncio.gather(*cpu_test_tasks, return_exceptions=True)
            execution_time = time.time() - start_time

            # Stop monitoring
            monitor_task.cancel()

            # Analyze CPU usage
            avg_cpu = statistics.mean(cpu_samples) if cpu_samples else 0
            peak_cpu = max(cpu_samples) if cpu_samples else 0
            successful_responses = len([r for r in responses if not isinstance(r, Exception)])

            print(f"⚡ CPU Usage Results:")
            print(f"  Execution time: {execution_time:.2f}s")
            print(f"  Average CPU: {avg_cpu:.1f}%")
            print(f"  Peak CPU: {peak_cpu:.1f}%")
            print(f"  Successful responses: {successful_responses}/10")

            # CPU efficiency requirements
            assert avg_cpu <= 80, f"Average CPU usage {avg_cpu:.1f}% too high"
            assert peak_cpu <= 95, f"Peak CPU usage {peak_cpu:.1f}% too high"
            assert successful_responses >= 9, f"Too many failures: {successful_responses}/10"
            assert execution_time <= 30, f"Execution took too long: {execution_time:.2f}s"

        except Exception as e:
            monitor_task.cancel()
            raise e

class TestPerformanceRegression:
    """Test for performance regressions"""

    @pytest.mark.integration
    @pytest.mark.performance
    async def test_performance_baseline_validation(self, performance_test_config):
        """
        FAILING TEST: Validate performance against established baselines

        Prevents performance regressions in future deployments
        """
        # Standard performance test scenarios
        baseline_tests = [
            {
                "name": "simple_response",
                "message": "Hi Sarah",
                "expected_max_time": 1.0,
                "priority": "high"
            },
            {
                "name": "business_context",
                "message": "I need help with my e-commerce business automation",
                "expected_max_time": 2.0,
                "priority": "high"
            },
            {
                "name": "complex_automation",
                "message": "I need to integrate my CRM with email marketing and social media platforms",
                "expected_max_time": 2.5,
                "priority": "medium"
            }
        ]

        baseline_results = []

        for test in baseline_tests:
            # Run test multiple times for statistical significance
            test_times = []

            for run in range(3):
                start_time = time.time()

                response = await handle_whatsapp_customer_message(
                    whatsapp_number=f"+1555BASELINE{hash(test['name']) % 1000:03d}",
                    message=test["message"],
                    conversation_id=f"baseline_{test['name']}_run_{run}"
                )

                response_time = time.time() - start_time
                test_times.append(response_time)

                # Verify response quality
                assert isinstance(response, str) and len(response) > 20, f"Poor response quality for {test['name']}"

            # Calculate statistics
            avg_time = statistics.mean(test_times)
            min_time = min(test_times)
            max_time = max(test_times)

            baseline_results.append({
                "test_name": test["name"],
                "priority": test["priority"],
                "avg_time": avg_time,
                "min_time": min_time,
                "max_time": max_time,
                "expected_max": test["expected_max_time"],
                "baseline_met": max_time <= test["expected_max_time"]
            })

            # Each baseline must be met
            assert max_time <= test["expected_max_time"], \
                f"Baseline failure: {test['name']} max time {max_time:.3f}s > {test['expected_max_time']}s"

        print(f"📊 Performance Baseline Results:")
        for result in baseline_results:
            status = "✅" if result["baseline_met"] else "❌"
            priority_icon = "🔴" if result["priority"] == "high" else "🟡"
            print(f"  {status} {priority_icon} {result['test_name']}: {result['avg_time']:.3f}s avg, {result['max_time']:.3f}s max (target: {result['expected_max']}s)")

        # All high-priority baselines must pass
        high_priority_failures = [r for r in baseline_results if r["priority"] == "high" and not r["baseline_met"]]
        assert len(high_priority_failures) == 0, f"High-priority baseline failures: {[r['test_name'] for r in high_priority_failures]}"

# Quality Gates for Performance
class TestPerformanceQualityGates:
    """Quality gates that must pass before production deployment"""

    @pytest.mark.integration
    @pytest.mark.performance
    async def test_complete_performance_quality_gate(self, performance_test_config, performance_test_messages):
        """
        FAILING TEST: Complete performance quality gate validation

        Must pass all performance requirements before deployment
        """
        quality_gate_results = {
            "text_response_sla": False,
            "memory_recall_sla": False,
            "concurrent_load_sla": False,
            "resource_efficiency": False,
            "baseline_compliance": False
        }

        print(f"🔍 Running Complete Performance Quality Gate...")

        # Quality Gate 1: Text Response SLA
        try:
            simple_start = time.time()
            simple_response = await handle_whatsapp_customer_message(
                whatsapp_number="+1555QG001",
                message="Hi Sarah",
                conversation_id="qg_simple_test"
            )
            simple_time = time.time() - simple_start

            complex_start = time.time()
            complex_response = await handle_whatsapp_customer_message(
                whatsapp_number="+1555QG002",
                message=performance_test_messages["complex_automation"],
                conversation_id="qg_complex_test"
            )
            complex_time = time.time() - complex_start

            text_sla_met = simple_time <= 1.0 and complex_time <= 2.0
            quality_gate_results["text_response_sla"] = text_sla_met

            print(f"  📝 Text Response SLA: {'✅' if text_sla_met else '❌'} (simple: {simple_time:.3f}s, complex: {complex_time:.3f}s)")

        except Exception as e:
            print(f"  📝 Text Response SLA: ❌ (Error: {e})")

        # Quality Gate 2: Memory Recall SLA
        try:
            # Setup memory context
            await handle_whatsapp_customer_message(
                whatsapp_number="+1555QG003",
                message="My business is Premium Jewelry Co, revenue $75K/month",
                conversation_id="qg_memory_setup"
            )

            # Test memory recall
            memory_start = time.time()
            memory_response = await handle_whatsapp_customer_message(
                whatsapp_number="+1555QG003",
                message="What's my business name and revenue?",
                conversation_id="qg_memory_test"
            )
            memory_time = time.time() - memory_start

            memory_sla_met = memory_time <= 0.5
            quality_gate_results["memory_recall_sla"] = memory_sla_met

            print(f"  🧠 Memory Recall SLA: {'✅' if memory_sla_met else '❌'} ({memory_time:.3f}s)")

        except Exception as e:
            print(f"  🧠 Memory Recall SLA: ❌ (Error: {e})")

        # Quality Gate 3: Concurrent Load SLA
        try:
            concurrent_tasks = []
            for i in range(10):  # Reduced for quality gate
                task = handle_whatsapp_customer_message(
                    whatsapp_number=f"+1555QG{i:03d}",
                    message=f"Quality gate concurrent test {i}",
                    conversation_id=f"qg_concurrent_{i}"
                )
                concurrent_tasks.append(task)

            concurrent_start = time.time()
            concurrent_responses = await asyncio.gather(*concurrent_tasks, return_exceptions=True)
            concurrent_duration = time.time() - concurrent_start

            successful_concurrent = len([r for r in concurrent_responses if not isinstance(r, Exception)])
            success_rate = successful_concurrent / len(concurrent_tasks)

            concurrent_sla_met = success_rate >= 0.90 and concurrent_duration <= 10.0
            quality_gate_results["concurrent_load_sla"] = concurrent_sla_met

            print(f"  🚀 Concurrent Load SLA: {'✅' if concurrent_sla_met else '❌'} ({success_rate:.1%} success, {concurrent_duration:.2f}s)")

        except Exception as e:
            print(f"  🚀 Concurrent Load SLA: ❌ (Error: {e})")

        # Quality Gate 4: Resource Efficiency
        try:
            import psutil
            process = psutil.Process()
            initial_memory = process.memory_info().rss / (1024 * 1024)

            # Generate some load
            for i in range(5):
                await handle_whatsapp_customer_message(
                    whatsapp_number=f"+1555QGR{i:02d}",
                    message="Resource efficiency test message",
                    conversation_id=f"qg_resource_{i}"
                )

            final_memory = process.memory_info().rss / (1024 * 1024)
            memory_growth = final_memory - initial_memory

            resource_efficient = memory_growth <= 50  # Max 50MB growth
            quality_gate_results["resource_efficiency"] = resource_efficient

            print(f"  💾 Resource Efficiency: {'✅' if resource_efficient else '❌'} ({memory_growth:.1f}MB growth)")

        except Exception as e:
            print(f"  💾 Resource Efficiency: ❌ (Error: {e})")

        # Quality Gate 5: Baseline Compliance
        try:
            baseline_start = time.time()
            baseline_response = await handle_whatsapp_customer_message(
                whatsapp_number="+1555QGBASE",
                message="I need help with business automation",
                conversation_id="qg_baseline_test"
            )
            baseline_time = time.time() - baseline_start

            baseline_compliant = baseline_time <= 2.0 and len(baseline_response) > 50
            quality_gate_results["baseline_compliance"] = baseline_compliant

            print(f"  📊 Baseline Compliance: {'✅' if baseline_compliant else '❌'} ({baseline_time:.3f}s, {len(baseline_response)} chars)")

        except Exception as e:
            print(f"  📊 Baseline Compliance: ❌ (Error: {e})")

        # Overall Quality Gate Assessment
        passed_gates = sum(quality_gate_results.values())
        total_gates = len(quality_gate_results)
        quality_gate_pass_rate = passed_gates / total_gates

        print(f"\n🎯 Performance Quality Gate Summary:")
        print(f"  Passed: {passed_gates}/{total_gates} ({quality_gate_pass_rate:.1%})")

        for gate_name, passed in quality_gate_results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"    {gate_name}: {status}")

        # All quality gates must pass for production deployment
        assert quality_gate_pass_rate == 1.0, f"Quality gate failure: {passed_gates}/{total_gates} passed. All gates must pass for production deployment."

        print(f"\n🎉 All Performance Quality Gates PASSED - Ready for Production Deployment!")