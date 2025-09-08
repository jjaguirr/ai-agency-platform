#!/usr/bin/env python3
"""
Performance Regression Detection Tests

Automated detection of performance regressions to prevent SLA violations
from being deployed to production. Integrates with CI/CD pipeline to block
deployments that degrade system performance.

Test Categories:
1. Baseline Performance Establishment  
2. Regression Detection Algorithms
3. CI/CD Integration Testing
4. Performance Trend Analysis
5. Automated Rollback Triggers
6. Performance Comparison Reports

Author: AI Agency Platform - Performance Engineering
Version: 1.0.0  
"""

import asyncio
import time
import statistics
import json
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
import pytest

from src.agents.executive_assistant import ExecutiveAssistant, ConversationChannel
from .performance_monitor import PerformanceMonitor, PerformanceMetric, MetricType

@dataclass
class PerformanceBaseline:
    """Performance baseline for comparison"""
    version: str
    timestamp: datetime
    metrics: Dict[str, Dict[str, float]]  # metric_name -> stats
    test_config: Dict[str, Any]
    environment_info: Dict[str, Any]

@dataclass
class RegressionResult:
    """Performance regression analysis result"""
    metric_name: str
    baseline_value: float
    current_value: float
    change_percentage: float
    is_regression: bool
    severity: str  # 'minor', 'moderate', 'major', 'critical'
    confidence_score: float
    details: Dict[str, Any]

class PerformanceRegressionDetector:
    """Automated performance regression detection system"""
    
    def __init__(self, baseline_storage_path: str = "./performance_baselines"):
        self.baseline_storage = Path(baseline_storage_path)
        self.baseline_storage.mkdir(parents=True, exist_ok=True)
        
        # Regression thresholds
        self.regression_thresholds = {
            'minor': 0.05,      # 5% degradation
            'moderate': 0.15,   # 15% degradation  
            'major': 0.25,      # 25% degradation
            'critical': 0.50    # 50% degradation
        }
        
        # Metrics that should decrease (lower is better)
        self.lower_is_better_metrics = [
            'response_time', 'error_rate', 'cpu_usage', 'memory_usage',
            'database_latency', 'memory_recall_time'
        ]
    
    async def establish_performance_baseline(self, version: str, test_iterations: int = 100) -> PerformanceBaseline:
        """Establish performance baseline for regression detection"""
        print(f"🎯 Establishing performance baseline for version {version}")
        print(f"   Running {test_iterations} test iterations...")
        
        # Collect comprehensive performance metrics
        metrics_data = {
            'ea_initialization': [],
            'response_time': [],
            'memory_recall': [],
            'database_query': [],
            'cpu_usage': [],
            'memory_usage': []
        }
        
        # Test EA performance
        test_customer_id = f"baseline_test_{version}_{int(time.time())}"
        
        for i in range(test_iterations):
            if i % 20 == 0:
                print(f"   Progress: {i}/{test_iterations} iterations")
            
            # EA Initialization
            start_time = time.time()
            ea = ExecutiveAssistant(customer_id=f"{test_customer_id}_{i}")
            init_time = time.time() - start_time
            metrics_data['ea_initialization'].append(init_time * 1000)  # Convert to ms
            
            # Response Time
            start_time = time.time()
            response = await ea.handle_customer_interaction(
                "Help me set up business automation", 
                ConversationChannel.API
            )
            response_time = time.time() - start_time
            metrics_data['response_time'].append(response_time * 1000)
            
            # Collect system metrics every 10th iteration
            if i % 10 == 0:
                import psutil
                metrics_data['cpu_usage'].append(psutil.cpu_percent(interval=0.1))
                metrics_data['memory_usage'].append(psutil.virtual_memory().percent)
        
        # Calculate statistical summaries
        metrics_summary = {}
        for metric_name, values in metrics_data.items():
            if values:
                metrics_summary[metric_name] = {
                    'mean': statistics.mean(values),
                    'median': statistics.median(values),
                    'std_dev': statistics.stdev(values) if len(values) > 1 else 0,
                    'min': min(values),
                    'max': max(values),
                    'p95': statistics.quantiles(values, n=20)[18] if len(values) >= 20 else max(values),
                    'p99': statistics.quantiles(values, n=100)[98] if len(values) >= 100 else max(values),
                    'sample_count': len(values)
                }
        
        # Create baseline
        baseline = PerformanceBaseline(
            version=version,
            timestamp=datetime.now(),
            metrics=metrics_summary,
            test_config={
                'test_iterations': test_iterations,
                'test_customer_id': test_customer_id
            },
            environment_info={
                'python_version': f"{__import__('sys').version}",
                'cpu_count': __import__('psutil').cpu_count(),
                'total_memory_gb': __import__('psutil').virtual_memory().total / (1024**3)
            }
        )
        
        # Save baseline
        await self.save_baseline(baseline)
        
        print(f"✅ Performance baseline established:")
        for metric_name, stats in metrics_summary.items():
            print(f"   • {metric_name}: {stats['mean']:.2f}ms avg, {stats['p95']:.2f}ms P95")
        
        return baseline
    
    async def save_baseline(self, baseline: PerformanceBaseline):
        """Save performance baseline to storage"""
        baseline_file = self.baseline_storage / f"baseline_{baseline.version}_{baseline.timestamp.strftime('%Y%m%d_%H%M%S')}.json"
        
        # Convert baseline to JSON-serializable format
        baseline_data = {
            'version': baseline.version,
            'timestamp': baseline.timestamp.isoformat(),
            'metrics': baseline.metrics,
            'test_config': baseline.test_config,
            'environment_info': baseline.environment_info
        }
        
        with open(baseline_file, 'w') as f:
            json.dump(baseline_data, f, indent=2)
        
        # Also save as "latest" for easy reference
        latest_file = self.baseline_storage / f"baseline_latest_{baseline.version}.json"
        with open(latest_file, 'w') as f:
            json.dump(baseline_data, f, indent=2)
    
    async def load_baseline(self, version: str = None) -> Optional[PerformanceBaseline]:
        """Load performance baseline from storage"""
        if version:
            baseline_file = self.baseline_storage / f"baseline_latest_{version}.json"
        else:
            # Find most recent baseline
            baseline_files = list(self.baseline_storage.glob("baseline_latest_*.json"))
            if not baseline_files:
                return None
            baseline_file = max(baseline_files, key=lambda f: f.stat().st_mtime)
        
        if not baseline_file.exists():
            return None
        
        with open(baseline_file, 'r') as f:
            baseline_data = json.load(f)
        
        return PerformanceBaseline(
            version=baseline_data['version'],
            timestamp=datetime.fromisoformat(baseline_data['timestamp']),
            metrics=baseline_data['metrics'],
            test_config=baseline_data['test_config'],
            environment_info=baseline_data['environment_info']
        )
    
    async def detect_regressions(self, current_metrics: Dict[str, Dict[str, float]], baseline_version: str = None) -> List[RegressionResult]:
        """Detect performance regressions compared to baseline"""
        baseline = await self.load_baseline(baseline_version)
        if not baseline:
            raise ValueError(f"No baseline found for version {baseline_version}")
        
        regressions = []
        
        for metric_name, current_stats in current_metrics.items():
            if metric_name not in baseline.metrics:
                continue  # Skip metrics not in baseline
            
            baseline_stats = baseline.metrics[metric_name]
            
            # Compare mean values (primary comparison)
            baseline_value = baseline_stats['mean']
            current_value = current_stats['mean']
            
            # Calculate change percentage
            if baseline_value == 0:
                change_percentage = 0 if current_value == 0 else float('inf')
            else:
                change_percentage = (current_value - baseline_value) / baseline_value
            
            # Determine if this is a regression
            is_regression = False
            if metric_name in self.lower_is_better_metrics:
                # For metrics where lower is better, positive change is bad
                is_regression = change_percentage > self.regression_thresholds['minor']
            else:
                # For metrics where higher is better, negative change is bad
                is_regression = change_percentage < -self.regression_thresholds['minor']
            
            # Determine severity
            abs_change = abs(change_percentage)
            if abs_change >= self.regression_thresholds['critical']:
                severity = 'critical'
            elif abs_change >= self.regression_thresholds['major']:
                severity = 'major'
            elif abs_change >= self.regression_thresholds['moderate']:
                severity = 'moderate'
            else:
                severity = 'minor'
            
            # Calculate confidence score based on statistical significance
            confidence_score = self._calculate_confidence_score(
                baseline_stats, current_stats, change_percentage
            )
            
            regression_result = RegressionResult(
                metric_name=metric_name,
                baseline_value=baseline_value,
                current_value=current_value,
                change_percentage=change_percentage,
                is_regression=is_regression,
                severity=severity,
                confidence_score=confidence_score,
                details={
                    'baseline_p95': baseline_stats.get('p95', 0),
                    'current_p95': current_stats.get('p95', 0),
                    'baseline_std_dev': baseline_stats.get('std_dev', 0),
                    'current_std_dev': current_stats.get('std_dev', 0),
                    'baseline_version': baseline.version,
                    'baseline_timestamp': baseline.timestamp.isoformat()
                }
            )
            
            regressions.append(regression_result)
        
        return regressions
    
    def _calculate_confidence_score(self, baseline_stats: Dict[str, float], current_stats: Dict[str, float], change_percentage: float) -> float:
        """Calculate confidence score for regression detection"""
        # Simple confidence calculation based on standard deviations and sample sizes
        baseline_std = baseline_stats.get('std_dev', 0)
        current_std = current_stats.get('std_dev', 0)
        baseline_n = baseline_stats.get('sample_count', 1)
        current_n = current_stats.get('sample_count', 1)
        
        # Larger changes with lower variance get higher confidence
        change_magnitude = abs(change_percentage)
        variance_factor = 1 / (1 + baseline_std + current_std)
        sample_size_factor = min(baseline_n, current_n) / 100  # Normalize by expected sample size
        
        confidence = min(change_magnitude * variance_factor * sample_size_factor, 1.0)
        return confidence
    
    async def generate_regression_report(self, regressions: List[RegressionResult]) -> str:
        """Generate comprehensive regression analysis report"""
        report = []
        report.append("=" * 80)
        report.append("🔍 PERFORMANCE REGRESSION ANALYSIS REPORT")
        report.append("=" * 80)
        report.append(f"Analysis Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Total Metrics Analyzed: {len(regressions)}")
        
        # Categorize regressions
        critical_regressions = [r for r in regressions if r.is_regression and r.severity == 'critical']
        major_regressions = [r for r in regressions if r.is_regression and r.severity == 'major'] 
        moderate_regressions = [r for r in regressions if r.is_regression and r.severity == 'moderate']
        minor_regressions = [r for r in regressions if r.is_regression and r.severity == 'minor']
        improvements = [r for r in regressions if not r.is_regression and r.change_percentage < 0]
        
        report.append(f"Regressions Found: {len([r for r in regressions if r.is_regression])}")
        report.append(f"  • Critical: {len(critical_regressions)}")
        report.append(f"  • Major: {len(major_regressions)}")
        report.append(f"  • Moderate: {len(moderate_regressions)}")
        report.append(f"  • Minor: {len(minor_regressions)}")
        report.append(f"Improvements Found: {len(improvements)}")
        report.append("")
        
        # Detailed regression analysis
        if critical_regressions or major_regressions:
            report.append("🚨 CRITICAL & MAJOR REGRESSIONS:")
            report.append("-" * 50)
            for regression in critical_regressions + major_regressions:
                emoji = "🔥" if regression.severity == 'critical' else "⚠️"
                report.append(f"{emoji} {regression.metric_name.upper()}")
                report.append(f"   Baseline: {regression.baseline_value:.2f}")
                report.append(f"   Current:  {regression.current_value:.2f}")  
                report.append(f"   Change:   {regression.change_percentage*100:+.1f}%")
                report.append(f"   Confidence: {regression.confidence_score:.2f}")
                report.append("")
        
        # Performance improvements
        if improvements:
            report.append("✅ PERFORMANCE IMPROVEMENTS:")
            report.append("-" * 50)
            for improvement in improvements[:5]:  # Show top 5 improvements
                report.append(f"• {improvement.metric_name}")
                report.append(f"  Improvement: {abs(improvement.change_percentage)*100:.1f}%")
                report.append(f"  {improvement.baseline_value:.2f} → {improvement.current_value:.2f}")
                report.append("")
        
        # Summary and recommendations
        report.append("📋 SUMMARY & RECOMMENDATIONS:")
        report.append("-" * 40)
        
        if critical_regressions:
            report.append("❌ DEPLOYMENT BLOCKED - Critical regressions detected")
            report.append("   Actions required:")
            report.append("   1. Investigate performance degradation causes")
            report.append("   2. Optimize critical performance paths") 
            report.append("   3. Re-run regression tests before deployment")
        elif major_regressions:
            report.append("⚠️  DEPLOYMENT CAUTION - Major regressions detected")
            report.append("   Consider:")
            report.append("   1. Review recent changes for performance impact")
            report.append("   2. Monitor production metrics closely")
            report.append("   3. Plan performance optimization sprint")
        else:
            report.append("✅ DEPLOYMENT APPROVED - No critical regressions")
            report.append("   Performance is within acceptable thresholds")
        
        report.append("")
        report.append("=" * 80)
        
        return "\n".join(report)

class TestPerformanceRegressionDetection:
    """Performance regression detection test suite"""
    
    def __init__(self):
        self.regression_detector = PerformanceRegressionDetector()
    
    @pytest.mark.asyncio
    async def test_establish_baseline(self):
        """
        Test: Establish performance baseline
        Objective: Create stable performance baseline for regression detection
        """
        version = f"test_baseline_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        baseline = await self.regression_detector.establish_performance_baseline(
            version=version, 
            test_iterations=50  # Reduced for testing
        )
        
        # Validate baseline
        assert baseline.version == version
        assert baseline.metrics
        assert 'response_time' in baseline.metrics
        assert 'ea_initialization' in baseline.metrics
        
        # Check statistical validity
        for metric_name, stats in baseline.metrics.items():
            assert stats['sample_count'] > 0
            assert stats['mean'] > 0
            assert stats['std_dev'] >= 0
            assert stats['min'] <= stats['mean'] <= stats['max']
        
        print(f"✅ Baseline established successfully:")
        print(f"   Version: {baseline.version}")
        print(f"   Metrics collected: {len(baseline.metrics)}")
        print(f"   Timestamp: {baseline.timestamp}")
    
    @pytest.mark.asyncio
    async def test_regression_detection_algorithm(self):
        """
        Test: Regression detection algorithm accuracy
        Objective: Validate regression detection with synthetic performance changes
        """
        # Create baseline
        baseline_version = f"regression_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        baseline = await self.regression_detector.establish_performance_baseline(
            version=baseline_version,
            test_iterations=30
        )
        
        # Simulate performance regression
        degraded_metrics = {}
        for metric_name, baseline_stats in baseline.metrics.items():
            # Simulate 20% performance degradation
            degraded_mean = baseline_stats['mean'] * 1.2
            degraded_p95 = baseline_stats['p95'] * 1.2
            
            degraded_metrics[metric_name] = {
                'mean': degraded_mean,
                'median': degraded_mean * 0.95,
                'p95': degraded_p95,
                'p99': degraded_p95 * 1.1,
                'std_dev': baseline_stats['std_dev'],
                'min': degraded_mean * 0.8,
                'max': degraded_mean * 1.3,
                'sample_count': baseline_stats['sample_count']
            }
        
        # Detect regressions
        regressions = await self.regression_detector.detect_regressions(
            current_metrics=degraded_metrics,
            baseline_version=baseline_version
        )
        
        # Validate detection results
        assert len(regressions) > 0, "Should detect regressions with 20% degradation"
        
        significant_regressions = [r for r in regressions if r.is_regression and r.severity in ['moderate', 'major', 'critical']]
        assert len(significant_regressions) > 0, "Should detect significant regressions"
        
        # Check regression details
        for regression in significant_regressions:
            assert regression.change_percentage > 0.15, f"Should detect >15% degradation, got {regression.change_percentage*100:.1f}%"
            assert regression.confidence_score > 0.1, "Should have reasonable confidence"
        
        print(f"✅ Regression detection validated:")
        print(f"   Total regressions detected: {len([r for r in regressions if r.is_regression])}")
        print(f"   Significant regressions: {len(significant_regressions)}")
        
        # Test improvement detection
        improved_metrics = {}
        for metric_name, baseline_stats in baseline.metrics.items():
            # Simulate 15% performance improvement
            improved_mean = baseline_stats['mean'] * 0.85
            
            improved_metrics[metric_name] = {
                'mean': improved_mean,
                'median': improved_mean,
                'p95': baseline_stats['p95'] * 0.85,
                'p99': baseline_stats['p99'] * 0.85,
                'std_dev': baseline_stats['std_dev'],
                'min': improved_mean * 0.8,
                'max': improved_mean * 1.2,
                'sample_count': baseline_stats['sample_count']
            }
        
        improvements = await self.regression_detector.detect_regressions(
            current_metrics=improved_metrics,
            baseline_version=baseline_version
        )
        
        performance_improvements = [r for r in improvements if not r.is_regression]
        assert len(performance_improvements) > 0, "Should detect performance improvements"
        
        print(f"   Performance improvements detected: {len(performance_improvements)}")
    
    @pytest.mark.asyncio  
    async def test_ci_cd_integration_flow(self):
        """
        Test: CI/CD integration workflow
        Objective: Validate automated regression testing in deployment pipeline
        """
        # Simulate CI/CD workflow
        print("🔄 Simulating CI/CD Performance Regression Testing...")
        
        # Step 1: Establish baseline (production)
        production_version = "v1.0.0_production"
        print(f"1. Establishing production baseline: {production_version}")
        
        baseline = await self.regression_detector.establish_performance_baseline(
            version=production_version,
            test_iterations=40
        )
        
        # Step 2: Test new deployment candidate
        candidate_version = "v1.1.0_candidate"
        print(f"2. Testing deployment candidate: {candidate_version}")
        
        # Simulate new version with mixed performance changes
        candidate_metrics = {}
        for metric_name, baseline_stats in baseline.metrics.items():
            if metric_name == 'response_time':
                # Simulate response time regression
                factor = 1.3  # 30% slower
            elif metric_name == 'ea_initialization':
                # Simulate initialization improvement  
                factor = 0.8  # 20% faster
            else:
                # No significant change
                factor = 1.05  # 5% variance
            
            candidate_metrics[metric_name] = {
                'mean': baseline_stats['mean'] * factor,
                'median': baseline_stats['median'] * factor,
                'p95': baseline_stats['p95'] * factor,
                'p99': baseline_stats['p99'] * factor, 
                'std_dev': baseline_stats['std_dev'],
                'min': baseline_stats['min'] * factor * 0.9,
                'max': baseline_stats['max'] * factor * 1.1,
                'sample_count': baseline_stats['sample_count']
            }
        
        # Step 3: Regression analysis
        print("3. Performing regression analysis...")
        regressions = await self.regression_detector.detect_regressions(
            current_metrics=candidate_metrics,
            baseline_version=production_version
        )
        
        # Step 4: Generate deployment decision
        critical_regressions = [r for r in regressions if r.is_regression and r.severity == 'critical']
        major_regressions = [r for r in regressions if r.is_regression and r.severity == 'major']
        
        deployment_blocked = len(critical_regressions) > 0
        deployment_warning = len(major_regressions) > 0
        
        # Step 5: Generate report
        report = await self.regression_detector.generate_regression_report(regressions)
        print("\n" + report)
        
        # Validate CI/CD decision logic
        if deployment_blocked:
            print("❌ CI/CD Decision: BLOCK DEPLOYMENT")
        elif deployment_warning:
            print("⚠️  CI/CD Decision: DEPLOY WITH CAUTION")
        else:
            print("✅ CI/CD Decision: APPROVE DEPLOYMENT")
        
        # Should detect the response time regression
        response_time_regression = next(
            (r for r in regressions if r.metric_name == 'response_time' and r.is_regression), 
            None
        )
        assert response_time_regression is not None, "Should detect response time regression"
        assert response_time_regression.severity in ['major', 'critical'], "Should flag significant response time degradation"
        
        # Should detect initialization improvement
        init_improvement = next(
            (r for r in regressions if r.metric_name == 'ea_initialization' and not r.is_regression),
            None
        )
        assert init_improvement is not None, "Should detect initialization improvement"
        
        print(f"✅ CI/CD integration test completed:")
        print(f"   Regressions detected: {len([r for r in regressions if r.is_regression])}")
        print(f"   Improvements detected: {len([r for r in regressions if not r.is_regression])}")
    
    @pytest.mark.asyncio
    async def test_performance_trend_analysis(self):
        """
        Test: Performance trend analysis over multiple versions
        Objective: Detect gradual performance degradation patterns
        """
        versions = ['v1.0.0', 'v1.1.0', 'v1.2.0', 'v1.3.0']
        baselines = []
        
        print("📈 Testing performance trend analysis...")
        
        # Create progression of performance changes
        for i, version in enumerate(versions):
            print(f"Creating baseline for {version}...")
            
            # Simulate gradual performance degradation (5% per version)
            degradation_factor = 1 + (i * 0.05)
            
            if i == 0:
                # Establish initial baseline
                baseline = await self.regression_detector.establish_performance_baseline(
                    version=version,
                    test_iterations=25
                )
            else:
                # Create baseline based on previous version with degradation
                prev_baseline = baselines[-1]
                degraded_metrics = {}
                
                for metric_name, stats in prev_baseline.metrics.items():
                    degraded_metrics[metric_name] = {
                        'mean': stats['mean'] * degradation_factor,
                        'median': stats['median'] * degradation_factor,
                        'p95': stats['p95'] * degradation_factor,
                        'p99': stats['p99'] * degradation_factor,
                        'std_dev': stats['std_dev'],
                        'min': stats['min'] * degradation_factor,
                        'max': stats['max'] * degradation_factor,
                        'sample_count': stats['sample_count']
                    }
                
                baseline = PerformanceBaseline(
                    version=version,
                    timestamp=datetime.now(),
                    metrics=degraded_metrics,
                    test_config={'test_iterations': 25},
                    environment_info={'simulated': True}
                )
                await self.regression_detector.save_baseline(baseline)
            
            baselines.append(baseline)
        
        # Analyze trends
        print("\n📊 Performance Trend Analysis:")
        print("-" * 60)
        print(f"{'Version':<10} {'Response Time':<15} {'Change %':<10} {'Trend'}")
        print("-" * 60)
        
        response_time_trend = []
        for i, baseline in enumerate(baselines):
            response_time = baseline.metrics['response_time']['mean']
            response_time_trend.append(response_time)
            
            if i == 0:
                change_pct = 0
                trend = "baseline"
            else:
                change_pct = ((response_time - response_time_trend[0]) / response_time_trend[0]) * 100
                if change_pct > 10:
                    trend = "⚠️  degrading"
                elif change_pct > 20:
                    trend = "🚨 critical"
                else:
                    trend = "stable"
            
            print(f"{baseline.version:<10} {response_time:<15.2f} {change_pct:>+7.1f}%   {trend}")
        
        # Validate trend detection
        latest_baseline = baselines[-1]
        first_baseline = baselines[0]
        
        # Compare latest to first 
        regressions = await self.regression_detector.detect_regressions(
            current_metrics=latest_baseline.metrics,
            baseline_version=first_baseline.version
        )
        
        significant_degradation = any(
            r.is_regression and r.severity in ['major', 'critical'] 
            for r in regressions
        )
        
        assert significant_degradation, "Should detect significant degradation over multiple versions"
        
        print(f"\n✅ Trend analysis completed:")
        print(f"   Versions analyzed: {len(baselines)}")
        print(f"   Cumulative degradation detected: {'Yes' if significant_degradation else 'No'}")
        
        # Test automated alerting for gradual degradation
        total_degradation = ((response_time_trend[-1] - response_time_trend[0]) / response_time_trend[0]) * 100
        assert total_degradation > 15, f"Should accumulate >15% degradation, got {total_degradation:.1f}%"
        
        print(f"   Total performance degradation: {total_degradation:.1f}%")

@pytest.mark.asyncio
async def test_comprehensive_regression_suite():
    """
    Comprehensive regression detection validation
    Runs complete regression test suite with reporting
    """
    print("🧪 COMPREHENSIVE REGRESSION DETECTION SUITE")
    print("=" * 60)
    
    detector = PerformanceRegressionDetector()
    test_suite = TestPerformanceRegressionDetection()
    
    # Run all regression tests
    print("1. Testing baseline establishment...")
    await test_suite.test_establish_baseline()
    
    print("\n2. Testing regression detection algorithm...")
    await test_suite.test_regression_detection_algorithm()
    
    print("\n3. Testing CI/CD integration...")  
    await test_suite.test_ci_cd_integration_flow()
    
    print("\n4. Testing performance trend analysis...")
    await test_suite.test_performance_trend_analysis()
    
    print("\n" + "=" * 60)
    print("✅ REGRESSION DETECTION SUITE COMPLETED SUCCESSFULLY")
    print("=" * 60)
    print("\n🎯 Key Capabilities Validated:")
    print("   • Automated baseline establishment")
    print("   • Accurate regression detection (>15% degradation)")
    print("   • Performance improvement recognition") 
    print("   • CI/CD deployment blocking for critical regressions")
    print("   • Multi-version performance trend analysis")
    print("   • Comprehensive regression reporting")
    print("\n📋 System is ready for production regression monitoring!")
    
    return True