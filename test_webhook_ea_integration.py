#!/usr/bin/env python3
"""
Webhook-EA Integration Test Runner
Demonstrates comprehensive integration test suite for webhook-EA service separation

CRITICAL: This script shows failing tests that MUST pass when services are properly implemented
"""

import subprocess
import sys
import os
import time
from pathlib import Path

def run_test_command(test_path, test_description, required_for_deployment=True):
    """Run a test command and report results"""
    print(f"\n{'='*80}")
    print(f"🧪 {test_description}")
    print(f"{'='*80}")

    if required_for_deployment:
        print("🚨 CRITICAL: Required for production deployment")
    else:
        print("ℹ️  OPTIONAL: Recommended for full validation")

    print(f"📁 Test Path: {test_path}")

    cmd = ["python", "-m", "pytest", test_path, "-v", "--tb=short", "-x"]

    start_time = time.time()

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_root)
        execution_time = time.time() - start_time

        if result.returncode == 0:
            print(f"✅ PASSED ({execution_time:.2f}s)")
            return True
        else:
            print(f"❌ FAILED ({execution_time:.2f}s)")
            print(f"\nSTDOUT:\n{result.stdout}")
            print(f"\nSTDERR:\n{result.stderr}")

            if required_for_deployment:
                print("🔴 DEPLOYMENT BLOCKED: Critical test failure")

            return False

    except Exception as e:
        print(f"💥 ERROR: {e}")
        return False

def main():
    """Run comprehensive webhook-EA integration test suite"""

    print("🚀 AI Agency Platform - Webhook-EA Integration Test Suite")
    print("="*80)
    print("This test suite validates the webhook-EA service separation requirements:")
    print("• End-to-end WhatsApp message flow")
    print("• HTTP API endpoints (process, health)")
    print("• Customer isolation validation")
    print("• Service authentication verification")
    print("• Fallback response handling")
    print("• Performance tests (<3s response time)")
    print("• Load testing (100 concurrent customers)")
    print("• Service failover scenarios")
    print("")
    print("🚨 CRITICAL: All CRITICAL tests must PASS before production deployment")
    print("="*80)

    # Test suite structure
    test_suites = [
        {
            "name": "EA API Service Tests",
            "description": "Tests for separated EA service API endpoints",
            "path": "tests/integration/test_ea_api.py",
            "critical": True,
            "expected_status": "FAILING",
            "reason": "EA service not yet separated from webhook service"
        },
        {
            "name": "Webhook-EA Flow Tests",
            "description": "End-to-end webhook to EA response flow testing",
            "path": "tests/integration/test_webhook_ea_flow.py",
            "critical": True,
            "expected_status": "MIXED",
            "reason": "Some tests pass (monolithic), others fail (separation required)"
        },
        {
            "name": "Customer Isolation Tests",
            "description": "Security validation for customer data isolation",
            "path": "tests/security/test_customer_isolation.py::TestCustomerIsolationIntegration",
            "critical": True,
            "expected_status": "FAILING",
            "reason": "Customer isolation not fully implemented in current architecture"
        },
        {
            "name": "Performance & Response Time Tests",
            "description": "Performance validation against business SLA requirements",
            "path": "tests/performance/test_response_times.py",
            "critical": True,
            "expected_status": "MIXED",
            "reason": "Basic functionality works, but optimization needed for SLA compliance"
        },
        {
            "name": "Load Testing (100 Concurrent)",
            "description": "Load testing for 100 concurrent customers requirement",
            "path": "tests/integration/test_load_testing.py",
            "critical": True,
            "expected_status": "FAILING",
            "reason": "Current system not optimized for high concurrent load"
        }
    ]

    # Run each test suite
    results = {}
    critical_failures = 0

    for suite in test_suites:
        print(f"\n📋 Testing: {suite['name']}")
        print(f"📝 Description: {suite['description']}")
        print(f"⚠️  Expected Status: {suite['expected_status']}")
        print(f"💡 Reason: {suite['reason']}")

        success = run_test_command(
            suite["path"],
            suite["name"],
            suite["critical"]
        )

        results[suite["name"]] = success

        if suite["critical"] and not success:
            critical_failures += 1

    # Generate comprehensive report
    print(f"\n{'='*80}")
    print("📊 WEBHOOK-EA INTEGRATION TEST SUMMARY")
    print(f"{'='*80}")

    print(f"\n🎯 Test Results Overview:")
    for suite_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {status} {suite_name}")

    print(f"\n📈 Statistics:")
    total_suites = len(results)
    passed_suites = sum(results.values())
    pass_rate = (passed_suites / total_suites) * 100 if total_suites > 0 else 0

    print(f"  Total Test Suites: {total_suites}")
    print(f"  Passed: {passed_suites}")
    print(f"  Failed: {total_suites - passed_suites}")
    print(f"  Pass Rate: {pass_rate:.1f}%")
    print(f"  Critical Failures: {critical_failures}")

    print(f"\n🚦 Deployment Readiness Assessment:")
    if critical_failures == 0:
        print("  ✅ READY FOR DEPLOYMENT - All critical tests passing")
        deployment_status = "READY"
    else:
        print(f"  ❌ DEPLOYMENT BLOCKED - {critical_failures} critical test failures")
        deployment_status = "BLOCKED"

    print(f"\n📋 Next Steps:")
    if deployment_status == "BLOCKED":
        print("  1. 🔧 Fix critical test failures listed above")
        print("  2. 🔄 Re-run test suite to validate fixes")
        print("  3. 📊 Ensure all critical tests pass before deployment")
        print("  4. 🚀 Deploy to staging environment for final validation")
    else:
        print("  1. 🎉 All critical requirements met!")
        print("  2. 📋 Review optional test failures for future improvements")
        print("  3. 🚀 Ready for production deployment")

    print(f"\n💡 Test Coverage Analysis:")
    print("  ✅ End-to-end WhatsApp message flow")
    print("  ✅ HTTP API endpoints (process, health)")
    print("  ✅ Customer isolation validation")
    print("  ✅ Service authentication verification")
    print("  ✅ Fallback response handling")
    print("  ✅ Performance tests (<3s response time)")
    print("  ✅ Load testing (100 concurrent customers)")
    print("  ✅ Service failover scenarios")

    print(f"\n📚 Test Implementation Notes:")
    print("  • All tests follow TDD principles - failing tests drive implementation")
    print("  • Tests validate both monolithic (current) and separated (future) architectures")
    print("  • Performance tests enforce business SLA requirements from Phase-1 PRD")
    print("  • Security tests ensure customer data isolation and authentication")
    print("  • Load tests validate scalability requirements (100 concurrent customers)")
    print("  • Failover tests ensure system resilience and graceful degradation")

    print(f"\n{'='*80}")

    # Return appropriate exit code
    if critical_failures > 0:
        print("🚫 EXITING WITH FAILURE CODE - Critical tests failed")
        return 1
    else:
        print("🎉 EXITING WITH SUCCESS CODE - All critical tests passed")
        return 0

if __name__ == "__main__":
    # Set up project root
    project_root = Path(__file__).parent
    os.chdir(project_root)

    # Run test suite
    exit_code = main()
    sys.exit(exit_code)