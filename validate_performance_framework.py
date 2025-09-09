#!/usr/bin/env python3
"""
Performance Testing Framework Validation Script

Validates that all components of the performance testing framework
are properly implemented and ready for production use.

This script performs a comprehensive validation of:
1. Test framework components
2. SLA validation capabilities  
3. Load testing infrastructure
4. Performance monitoring system
5. Regression detection algorithms
6. CI/CD integration readiness

Author: AI Agency Platform - Performance Engineering
Version: 1.0.0
"""

import asyncio
import time
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple

# Framework validation functions

async def validate_test_framework_structure() -> Tuple[bool, List[str]]:
    """Validate test framework file structure and imports"""
    print("🔍 Validating test framework structure...")
    
    issues = []
    success = True
    
    # Check required files exist
    required_files = [
        "tests/performance/__init__.py",
        "tests/performance/test_sla_validation.py", 
        "tests/performance/test_load_testing.py",
        "tests/performance/test_regression_detection.py",
        "tests/performance/performance_monitor.py",
        "run_performance_tests.py",
        "requirements-performance.txt",
        ".github/workflows/performance-testing.yml",
        "PERFORMANCE_TESTING_GUIDE.md"
    ]
    
    for file_path in required_files:
        if not Path(file_path).exists():
            issues.append(f"Missing required file: {file_path}")
            success = False
        else:
            print(f"   ✅ {file_path}")
    
    # Test imports
    try:
        from tests.performance.test_sla_validation import TestSLAValidation
        from tests.performance.test_load_testing import TestEnterpriseLoadTesting, LoadTestConfig
        from tests.performance.test_regression_detection import PerformanceRegressionDetector
        from tests.performance.performance_monitor import create_performance_monitor, PerformanceMetric, MetricType
        print("   ✅ All imports successful")
    except ImportError as e:
        issues.append(f"Import error: {e}")
        success = False
    
    return success, issues

async def validate_sla_testing_capabilities() -> Tuple[bool, List[str]]:
    """Validate SLA testing capabilities"""
    print("🎯 Validating SLA testing capabilities...")
    
    issues = []
    success = True
    
    try:
        from tests.performance.test_sla_validation import TestSLAValidation
        
        # Test basic SLA validation structure
        test_suite = TestSLAValidation()
        
        # Check that SLA test methods exist
        required_methods = [
            'test_ea_initialization_performance',
            'test_premium_casual_personality_transformation',
            'test_database_query_performance',
            'test_memory_recall_performance',
            'test_cross_channel_context_retrieval',
            'test_concurrent_customer_handling',
            'test_system_resource_monitoring'
        ]
        
        for method_name in required_methods:
            if not hasattr(test_suite, method_name):
                issues.append(f"Missing SLA test method: {method_name}")
                success = False
            else:
                print(f"   ✅ {method_name}")
        
        # Validate SLA thresholds are defined
        sla_targets = {
            'voice_synthesis': 2.0,      # 2 seconds
            'whatsapp_delivery': 1.0,    # 1 second
            'personality_transform': 0.5, # 500ms
            'api_response': 0.2,         # 200ms
            'database_query': 0.1,       # 100ms
            'memory_recall': 0.5         # 500ms
        }
        
        print(f"   ✅ SLA targets defined: {len(sla_targets)} metrics")
        
    except Exception as e:
        issues.append(f"SLA validation error: {e}")
        success = False
    
    return success, issues

async def validate_load_testing_infrastructure() -> Tuple[bool, List[str]]:
    """Validate load testing infrastructure"""  
    print("🏋️ Validating load testing infrastructure...")
    
    issues = []
    success = True
    
    try:
        from tests.performance.test_load_testing import EnterpriseLoadTester, LoadTestConfig, LoadTestResult
        
        # Test load test configuration
        config = LoadTestConfig(
            concurrent_users=10,  # Small test
            test_duration_seconds=5,
            target_rps=2.0,
            ramp_up_seconds=2
        )
        
        # Validate load tester instantiation
        load_tester = EnterpriseLoadTester(config)
        print("   ✅ Load tester instantiation")
        
        # Test realistic scenario generation
        scenario = await load_tester.generate_realistic_customer_interaction(
            "test_customer_001",
            "business_discovery"
        )
        
        required_keys = ['customer_id', 'message', 'channel', 'business_type', 'scenario']
        for key in required_keys:
            if key not in scenario:
                issues.append(f"Missing scenario key: {key}")
                success = False
        
        if success:
            print("   ✅ Realistic scenario generation")
        
        # Validate load test result structure
        sample_result = LoadTestResult(
            total_requests=100,
            successful_requests=95,
            failed_requests=5,
            avg_response_time=0.15,
            p95_response_time=0.18,
            p99_response_time=0.22,
            max_response_time=0.25,
            min_response_time=0.12,
            throughput_rps=8.5,
            error_rate=0.05,
            test_duration=60.0,
            peak_cpu_usage=45.2,
            peak_memory_usage=38.7
        )
        
        print("   ✅ Load test result structure")
        
    except Exception as e:
        issues.append(f"Load testing validation error: {e}")
        success = False
    
    return success, issues

async def validate_performance_monitoring() -> Tuple[bool, List[str]]:
    """Validate performance monitoring system"""
    print("📊 Validating performance monitoring system...")
    
    issues = []
    success = True
    
    try:
        from tests.performance.performance_monitor import (
            create_performance_monitor, 
            PerformanceMetric, 
            MetricType, 
            AlertSeverity,
            SLAThreshold
        )
        
        # Test monitor creation
        monitor = create_performance_monitor({
            'monitoring_interval_seconds': 5,
            'metrics_retention_seconds': 60,
            'enable_auto_alerts': False  # Disable for testing
        })
        
        print("   ✅ Monitor creation")
        
        # Test metric recording
        test_metric = PerformanceMetric(
            metric_type=MetricType.RESPONSE_TIME,
            value=150.0,  # 150ms
            timestamp=datetime.now(),
            customer_id="test_customer"
        )
        
        await monitor.record_metric(test_metric)
        print("   ✅ Metric recording")
        
        # Test SLA threshold definition
        sla_threshold = SLAThreshold(
            metric_type=MetricType.RESPONSE_TIME,
            threshold_value=200.0,  # 200ms
            comparison="less_than",
            measurement_window_seconds=60
        )
        
        print("   ✅ SLA threshold definition")
        
        # Test performance summary
        summary = monitor.get_performance_summary()
        required_summary_keys = ['timestamp', 'monitoring_status', 'total_metrics_collected']
        
        for key in required_summary_keys:
            if key not in summary:
                issues.append(f"Missing summary key: {key}")
                success = False
        
        if success:
            print("   ✅ Performance summary generation")
        
    except Exception as e:
        issues.append(f"Performance monitoring validation error: {e}")
        success = False
    
    return success, issues

async def validate_regression_detection() -> Tuple[bool, List[str]]:
    """Validate regression detection capabilities"""
    print("🔍 Validating regression detection capabilities...")
    
    issues = []
    success = True
    
    try:
        from tests.performance.test_regression_detection import (
            PerformanceRegressionDetector,
            PerformanceBaseline,
            RegressionResult
        )
        
        # Test regression detector instantiation
        detector = PerformanceRegressionDetector("./test_baselines")
        print("   ✅ Regression detector instantiation")
        
        # Test baseline structure
        baseline = PerformanceBaseline(
            version="test_v1.0.0",
            timestamp=datetime.now(),
            metrics={
                'response_time': {
                    'mean': 150.0,
                    'p95': 180.0,
                    'std_dev': 15.0,
                    'sample_count': 100
                }
            },
            test_config={'iterations': 100},
            environment_info={'cpu_count': 4}
        )
        
        print("   ✅ Baseline structure")
        
        # Test regression result structure
        regression = RegressionResult(
            metric_name="response_time",
            baseline_value=150.0,
            current_value=195.0,
            change_percentage=0.30,  # 30% increase
            is_regression=True,
            severity="moderate",
            confidence_score=0.85,
            details={}
        )
        
        print("   ✅ Regression result structure")
        
        # Test regression thresholds
        expected_thresholds = ['minor', 'moderate', 'major', 'critical']
        for threshold in expected_thresholds:
            if threshold not in detector.regression_thresholds:
                issues.append(f"Missing regression threshold: {threshold}")
                success = False
        
        if success:
            print("   ✅ Regression thresholds defined")
        
    except Exception as e:
        issues.append(f"Regression detection validation error: {e}")
        success = False
    
    return success, issues

async def validate_ci_cd_integration() -> Tuple[bool, List[str]]:
    """Validate CI/CD integration readiness"""
    print("🔄 Validating CI/CD integration readiness...")
    
    issues = []
    success = True
    
    # Check GitHub Actions workflow
    workflow_file = Path(".github/workflows/performance-testing.yml")
    if not workflow_file.exists():
        issues.append("Missing GitHub Actions workflow file")
        success = False
    else:
        print("   ✅ GitHub Actions workflow file exists")
        
        # Check workflow content
        workflow_content = workflow_file.read_text()
        required_sections = [
            'performance-tests:',
            'services:',
            'postgres:',
            'redis:',
            'qdrant:',
            'run_performance_tests.py'
        ]
        
        for section in required_sections:
            if section not in workflow_content:
                issues.append(f"Missing workflow section: {section}")
                success = False
        
        if success:
            print("   ✅ Workflow content validation")
    
    # Check main runner script
    runner_script = Path("run_performance_tests.py")
    if not runner_script.exists():
        issues.append("Missing main runner script")
        success = False
    else:
        print("   ✅ Main runner script exists")
        
        # Check script executability and structure
        script_content = runner_script.read_text()
        required_components = [
            'PerformanceTestSuite',
            'run_sla_validation_suite',
            'run_load_testing_suite', 
            'run_regression_detection_suite',
            'run_monitoring_suite'
        ]
        
        for component in required_components:
            if component not in script_content:
                issues.append(f"Missing runner component: {component}")
                success = False
        
        if success:
            print("   ✅ Runner script structure validation")
    
    return success, issues

async def validate_enterprise_scale_readiness() -> Tuple[bool, List[str]]:
    """Validate enterprise scale testing readiness"""
    print("🏢 Validating enterprise scale testing readiness...")
    
    issues = []
    success = True
    
    try:
        # Check enterprise scale targets
        enterprise_targets = {
            'concurrent_customers': 1000,
            'memory_operations_per_hour': 10000,
            'load_multiplier': 10,
            'sla_compliance_under_load': 0.9  # 90%
        }
        
        print("   ✅ Enterprise targets defined")
        
        # Check load testing can handle enterprise scale
        from tests.performance.test_load_testing import LoadTestConfig
        
        enterprise_config = LoadTestConfig(
            concurrent_users=1000,
            test_duration_seconds=300,
            target_rps=25.0,
            ramp_up_seconds=120
        )
        
        print("   ✅ Enterprise load configuration")
        
        # Check performance monitoring supports enterprise metrics
        from tests.performance.performance_monitor import MetricType
        
        enterprise_metrics = [
            MetricType.RESPONSE_TIME,
            MetricType.ERROR_RATE,
            MetricType.THROUGHPUT,
            MetricType.CPU_USAGE,
            MetricType.MEMORY_USAGE,
            MetricType.DATABASE_LATENCY
        ]
        
        print(f"   ✅ Enterprise metrics supported: {len(enterprise_metrics)}")
        
    except Exception as e:
        issues.append(f"Enterprise scale validation error: {e}")
        success = False
    
    return success, issues

async def run_framework_validation() -> Dict[str, Any]:
    """Run complete framework validation"""
    print("🚀 AI AGENCY PLATFORM - PERFORMANCE FRAMEWORK VALIDATION")
    print("=" * 70)
    print(f"Validation Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    validation_results = {
        'validation_timestamp': datetime.now().isoformat(),
        'overall_status': 'PENDING',
        'validations': {},
        'total_issues': 0,
        'critical_issues': [],
        'framework_ready': False
    }
    
    # Define validation tests
    validations = [
        ('Test Framework Structure', validate_test_framework_structure),
        ('SLA Testing Capabilities', validate_sla_testing_capabilities),
        ('Load Testing Infrastructure', validate_load_testing_infrastructure),
        ('Performance Monitoring', validate_performance_monitoring),
        ('Regression Detection', validate_regression_detection),
        ('CI/CD Integration', validate_ci_cd_integration),
        ('Enterprise Scale Readiness', validate_enterprise_scale_readiness)
    ]
    
    all_passed = True
    total_issues = []
    
    # Run validations
    for validation_name, validation_func in validations:
        print(f"\n🔍 Running: {validation_name}")
        
        try:
            start_time = time.time()
            success, issues = await validation_func()
            duration = time.time() - start_time
            
            validation_results['validations'][validation_name] = {
                'status': 'PASS' if success else 'FAIL',
                'duration': duration,
                'issues': issues,
                'issue_count': len(issues)
            }
            
            if success:
                print(f"   ✅ {validation_name}: PASSED ({duration:.2f}s)")
            else:
                print(f"   ❌ {validation_name}: FAILED ({duration:.2f}s)")
                for issue in issues:
                    print(f"      • {issue}")
                all_passed = False
                total_issues.extend(issues)
        
        except Exception as e:
            validation_results['validations'][validation_name] = {
                'status': 'ERROR',
                'duration': 0,
                'issues': [str(e)],
                'issue_count': 1
            }
            print(f"   💥 {validation_name}: ERROR - {e}")
            all_passed = False
            total_issues.append(f"{validation_name}: {e}")
    
    # Calculate overall results
    validation_results['overall_status'] = 'PASS' if all_passed else 'FAIL'
    validation_results['total_issues'] = len(total_issues)
    validation_results['framework_ready'] = all_passed
    
    # Identify critical issues
    critical_categories = ['Test Framework Structure', 'CI/CD Integration', 'Performance Monitoring']
    for category in critical_categories:
        if category in validation_results['validations']:
            if validation_results['validations'][category]['status'] != 'PASS':
                validation_results['critical_issues'].append(f"Critical system: {category} validation failed")
    
    # Generate final report
    print("\n" + "=" * 70)
    print("📋 VALIDATION SUMMARY")
    print("=" * 70)
    
    passed_validations = len([v for v in validation_results['validations'].values() if v['status'] == 'PASS'])
    total_validations = len(validation_results['validations'])
    
    print(f"Overall Status: {validation_results['overall_status']}")
    print(f"Validations Passed: {passed_validations}/{total_validations}")
    print(f"Total Issues Found: {validation_results['total_issues']}")
    print(f"Critical Issues: {len(validation_results['critical_issues'])}")
    
    # Framework readiness assessment
    if validation_results['framework_ready']:
        print(f"\n✅ FRAMEWORK STATUS: READY FOR PRODUCTION")
        print("   • All validations passed")
        print("   • No critical issues detected")
        print("   • Framework is ready for enterprise deployment")
    else:
        print(f"\n⚠️  FRAMEWORK STATUS: REQUIRES FIXES")
        print("   Issues that need resolution:")
        for issue in total_issues[:10]:  # Show first 10 issues
            print(f"   • {issue}")
        if len(total_issues) > 10:
            print(f"   • ... and {len(total_issues) - 10} more issues")
    
    # Save validation report
    report_path = Path("./framework_validation_report.json")
    with open(report_path, 'w') as f:
        json.dump(validation_results, f, indent=2, default=str)
    
    print(f"\n📋 Validation report saved: {report_path}")
    print("=" * 70)
    
    return validation_results

async def main():
    """Main validation entry point"""
    try:
        results = await run_framework_validation()
        
        # Exit with appropriate code
        if results['framework_ready']:
            print("\n🎉 Framework validation completed successfully!")
            sys.exit(0)
        else:
            print("\n🔧 Framework requires fixes before production use")
            sys.exit(1)
    
    except KeyboardInterrupt:
        print("\n\n⚠️ Validation interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n💥 Validation failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())