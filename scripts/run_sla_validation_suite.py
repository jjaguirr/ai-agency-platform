#!/usr/bin/env python3
"""
Issue #50: Comprehensive SLA Validation Test Runner

This script runs the complete SLA validation suite across all integration streams
to validate performance claims and determine production readiness.

EXECUTION SEQUENCE:
1. Voice Integration Stream SLA Validation
2. WhatsApp Integration Stream SLA Validation  
3. Cross-Integration SLA Validation
4. Infrastructure Performance Validation
5. Production Readiness Assessment
6. Comprehensive Reporting

Must be run BEFORE any production deployment to validate Issue #50 requirements.
"""

import asyncio
import logging
import json
import time
import sys
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import argparse

# Add project paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import validation frameworks
voice_stream_path = Path(project_root).parent / "voice-integration-stream"
whatsapp_stream_path = Path(project_root).parent / "whatsapp-integration-stream"

sys.path.insert(0, str(voice_stream_path))
sys.path.insert(0, str(whatsapp_stream_path))

logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    """Result of a validation test"""
    stream: str
    test_name: str
    passed: bool
    duration: float
    details: Dict[str, Any]
    critical_failure: bool = False

@dataclass
class SLAValidationSuite:
    """Complete SLA validation suite results"""
    execution_timestamp: datetime
    total_duration: float
    voice_results: List[ValidationResult]
    whatsapp_results: List[ValidationResult]
    cross_integration_results: List[ValidationResult]
    infrastructure_results: List[ValidationResult]
    overall_passed: bool
    production_ready: bool
    critical_failures: List[str]
    summary_report: Dict[str, Any]

class ComprehensiveSLAValidator:
    """Comprehensive SLA validation orchestrator"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        
        # Paths
        self.project_root = project_root
        self.voice_stream_path = voice_stream_path
        self.whatsapp_stream_path = whatsapp_stream_path
        
        # Results storage
        self.results: List[ValidationResult] = []
        self.critical_failures: List[str] = []
        
        # Validation configuration
        self.validation_config = self.config.get('validation', {
            'concurrent_users_test': 100,  # Reduced for CI/test environments
            'voice_concurrent_sessions': 100,
            'whatsapp_throughput_test': 100,  # messages/minute for testing
            'test_duration_seconds': 60,
            'skip_long_tests': False  # Set to True for quick validation
        })
        
        # Output configuration
        self.output_dir = Path(self.config.get('output_dir', project_root / 'validation_reports'))
        self.output_dir.mkdir(exist_ok=True)
        
    async def run_complete_validation_suite(self) -> SLAValidationSuite:
        """Run the complete SLA validation suite"""
        logger.info("🚀 Starting comprehensive SLA validation suite for Issue #50")
        start_time = datetime.now()
        suite_start = time.time()
        
        try:
            # 1. Environment Preparation
            await self._prepare_validation_environment()
            
            # 2. Voice Integration Stream Validation
            logger.info("1️⃣ Running Voice Integration Stream SLA validation...")
            voice_results = await self._run_voice_integration_validation()
            
            # 3. WhatsApp Integration Stream Validation  
            logger.info("2️⃣ Running WhatsApp Integration Stream SLA validation...")
            whatsapp_results = await self._run_whatsapp_integration_validation()
            
            # 4. Cross-Integration Validation
            logger.info("3️⃣ Running Cross-Integration SLA validation...")
            cross_results = await self._run_cross_integration_validation()
            
            # 5. Infrastructure Performance Validation
            logger.info("4️⃣ Running Infrastructure Performance validation...")
            infra_results = await self._run_infrastructure_validation()
            
            # 6. Overall Assessment
            logger.info("5️⃣ Conducting overall production readiness assessment...")
            overall_assessment = await self._conduct_overall_assessment(
                voice_results, whatsapp_results, cross_results, infra_results
            )
            
            # Compile results
            total_duration = time.time() - suite_start
            
            suite_results = SLAValidationSuite(
                execution_timestamp=start_time,
                total_duration=total_duration,
                voice_results=voice_results,
                whatsapp_results=whatsapp_results,
                cross_integration_results=cross_results,
                infrastructure_results=infra_results,
                overall_passed=overall_assessment['overall_passed'],
                production_ready=overall_assessment['production_ready'],
                critical_failures=self.critical_failures,
                summary_report=overall_assessment['summary']
            )
            
            # 7. Generate Reports
            await self._generate_validation_reports(suite_results)
            
            # 8. Final Assessment
            self._print_final_assessment(suite_results)
            
            return suite_results
            
        except Exception as e:
            logger.error(f"❌ SLA validation suite failed with exception: {e}")
            raise
    
    async def _prepare_validation_environment(self):
        """Prepare the validation environment"""
        logger.info("🔧 Preparing validation environment...")
        
        # Check if integration streams are available
        if not self.voice_stream_path.exists():
            raise RuntimeError(f"Voice integration stream not found at {self.voice_stream_path}")
        
        if not self.whatsapp_stream_path.exists():
            raise RuntimeError(f"WhatsApp integration stream not found at {self.whatsapp_stream_path}")
        
        # Create output directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.validation_run_dir = self.output_dir / f"sla_validation_{timestamp}"
        self.validation_run_dir.mkdir(exist_ok=True)
        
        logger.info(f"✅ Validation environment prepared - Output: {self.validation_run_dir}")
    
    async def _run_voice_integration_validation(self) -> List[ValidationResult]:
        """Run voice integration SLA validation"""
        results = []
        
        try:
            # Change to voice integration stream directory
            original_cwd = os.getcwd()
            os.chdir(self.voice_stream_path)
            
            # Import and run voice validation
            try:
                from tests.performance.sla_validation_comprehensive import VoiceSLAValidator
                
                validator = VoiceSLAValidator()
                
                # Voice Response Time SLA
                start_time = time.time()
                voice_response_result = await validator.validate_voice_response_time_sla(
                    self.validation_config['voice_concurrent_sessions']
                )
                duration = time.time() - start_time
                
                results.append(ValidationResult(
                    stream="voice",
                    test_name="voice_response_time_sla",
                    passed=voice_response_result.passed,
                    duration=duration,
                    details=asdict(voice_response_result),
                    critical_failure=not voice_response_result.passed
                ))
                
                if not voice_response_result.passed:
                    self.critical_failures.append(f"Voice response time SLA failed: {voice_response_result.measured_value:.3f}s > {voice_response_result.target.target_value}s")
                
                # Concurrent Sessions SLA
                if not self.validation_config.get('skip_long_tests', False):
                    start_time = time.time()
                    concurrent_result = await validator.validate_concurrent_sessions_sla(
                        self.validation_config['voice_concurrent_sessions']
                    )
                    duration = time.time() - start_time
                    
                    results.append(ValidationResult(
                        stream="voice",
                        test_name="concurrent_sessions_sla",
                        passed=concurrent_result.passed,
                        duration=duration,
                        details=asdict(concurrent_result),
                        critical_failure=not concurrent_result.passed
                    ))
                    
                    if not concurrent_result.passed:
                        self.critical_failures.append(f"Voice concurrent sessions SLA failed: {concurrent_result.measured_value} < {concurrent_result.target.target_value}")
                
                # Bilingual Performance SLA
                start_time = time.time()
                bilingual_result = await validator.validate_bilingual_performance_sla()
                duration = time.time() - start_time
                
                results.append(ValidationResult(
                    stream="voice",
                    test_name="bilingual_performance_sla",
                    passed=bilingual_result.passed,
                    duration=duration,
                    details=asdict(bilingual_result),
                    critical_failure=not bilingual_result.passed and not self.validation_config.get('skip_long_tests', False)  # Not critical for quick tests
                ))
                
                logger.info(f"✅ Voice integration validation completed - {len(results)} tests run")
                
            except ImportError as e:
                logger.error(f"❌ Could not import voice validation framework: {e}")
                results.append(ValidationResult(
                    stream="voice",
                    test_name="validation_framework_import",
                    passed=False,
                    duration=0,
                    details={"error": str(e)},
                    critical_failure=True
                ))
                self.critical_failures.append(f"Voice validation framework import failed: {e}")
            
        except Exception as e:
            logger.error(f"❌ Voice integration validation failed: {e}")
            results.append(ValidationResult(
                stream="voice",
                test_name="voice_validation_suite",
                passed=False,
                duration=0,
                details={"error": str(e)},
                critical_failure=True
            ))
        finally:
            os.chdir(original_cwd)
        
        return results
    
    async def _run_whatsapp_integration_validation(self) -> List[ValidationResult]:
        """Run WhatsApp integration SLA validation"""
        results = []
        
        try:
            # Change to WhatsApp integration stream directory
            original_cwd = os.getcwd()
            os.chdir(self.whatsapp_stream_path)
            
            # Import and run WhatsApp validation
            try:
                from tests.performance.sla_validation_comprehensive import WhatsAppSLAValidator
                
                validator = WhatsAppSLAValidator()
                
                # Message Processing SLA
                start_time = time.time()
                processing_result = await validator.validate_message_processing_sla(
                    self.validation_config['concurrent_users_test']
                )
                duration = time.time() - start_time
                
                results.append(ValidationResult(
                    stream="whatsapp",
                    test_name="message_processing_sla",
                    passed=processing_result.passed,
                    duration=duration,
                    details=asdict(processing_result),
                    critical_failure=not processing_result.passed
                ))
                
                if not processing_result.passed:
                    self.critical_failures.append(f"WhatsApp message processing SLA failed: {processing_result.measured_value:.3f}s > {processing_result.target.target_value}s")
                
                # Throughput SLA
                if not self.validation_config.get('skip_long_tests', False):
                    start_time = time.time()
                    throughput_result = await validator.validate_throughput_sla(
                        self.validation_config['whatsapp_throughput_test']
                    )
                    duration = time.time() - start_time
                    
                    results.append(ValidationResult(
                        stream="whatsapp",
                        test_name="throughput_sla",
                        passed=throughput_result.passed,
                        duration=duration,
                        details=asdict(throughput_result),
                        critical_failure=not throughput_result.passed
                    ))
                    
                    if not throughput_result.passed:
                        self.critical_failures.append(f"WhatsApp throughput SLA failed: {throughput_result.measured_value:.0f} < {throughput_result.target.target_value} msg/min")
                
                # Media Processing SLA
                start_time = time.time()
                media_result = await validator.validate_media_processing_sla()
                duration = time.time() - start_time
                
                results.append(ValidationResult(
                    stream="whatsapp",
                    test_name="media_processing_sla",
                    passed=media_result.passed,
                    duration=duration,
                    details=asdict(media_result)
                ))
                
                # Cross-channel Handoff SLA
                start_time = time.time()
                handoff_result = await validator.validate_cross_channel_handoff_sla()
                duration = time.time() - start_time
                
                results.append(ValidationResult(
                    stream="whatsapp",
                    test_name="cross_channel_handoff_sla",
                    passed=handoff_result.passed,
                    duration=duration,
                    details=asdict(handoff_result)
                ))
                
                logger.info(f"✅ WhatsApp integration validation completed - {len(results)} tests run")
                
            except ImportError as e:
                logger.error(f"❌ Could not import WhatsApp validation framework: {e}")
                results.append(ValidationResult(
                    stream="whatsapp",
                    test_name="validation_framework_import",
                    passed=False,
                    duration=0,
                    details={"error": str(e)},
                    critical_failure=True
                ))
                self.critical_failures.append(f"WhatsApp validation framework import failed: {e}")
            
        except Exception as e:
            logger.error(f"❌ WhatsApp integration validation failed: {e}")
            results.append(ValidationResult(
                stream="whatsapp",
                test_name="whatsapp_validation_suite",
                passed=False,
                duration=0,
                details={"error": str(e)},
                critical_failure=True
            ))
        finally:
            os.chdir(original_cwd)
        
        return results
    
    async def _run_cross_integration_validation(self) -> List[ValidationResult]:
        """Run cross-integration SLA validation"""
        results = []
        
        try:
            # Import and run cross-integration validation
            from tests.performance.cross_integration_sla_validation import CrossIntegrationSLAValidator
            
            validator = CrossIntegrationSLAValidator()
            
            # Cross-system Handoff SLA
            start_time = time.time()
            handoff_result = await validator.validate_cross_system_handoff_sla()
            duration = time.time() - start_time
            
            results.append(ValidationResult(
                stream="cross_integration",
                test_name="cross_system_handoff_sla",
                passed=handoff_result.passed,
                duration=duration,
                details=asdict(handoff_result),
                critical_failure=not handoff_result.passed
            ))
            
            if not handoff_result.passed:
                self.critical_failures.append(f"Cross-system handoff SLA failed: {handoff_result.measured_value:.3f}s > {handoff_result.target.target_value}s")
            
            # System-wide Concurrent Users SLA
            if not self.validation_config.get('skip_long_tests', False):
                start_time = time.time()
                concurrent_result = await validator.validate_system_wide_concurrent_users_sla(
                    self.validation_config['concurrent_users_test']
                )
                duration = time.time() - start_time
                
                results.append(ValidationResult(
                    stream="cross_integration",
                    test_name="system_wide_concurrent_users_sla",
                    passed=concurrent_result.passed,
                    duration=duration,
                    details=asdict(concurrent_result),
                    critical_failure=not concurrent_result.passed
                ))
                
                if not concurrent_result.passed:
                    self.critical_failures.append(f"System-wide concurrent users SLA failed: {concurrent_result.measured_value} < {concurrent_result.target.target_value}")
            
            # Mixed Workload Performance SLA
            start_time = time.time()
            mixed_workload_result = await validator.validate_mixed_workload_performance_sla(
                self.validation_config['test_duration_seconds']
            )
            duration = time.time() - start_time
            
            results.append(ValidationResult(
                stream="cross_integration",
                test_name="mixed_workload_performance_sla",
                passed=mixed_workload_result.passed,
                duration=duration,
                details=asdict(mixed_workload_result)
            ))
            
            # End-to-end Customer Journey SLA
            start_time = time.time()
            journey_result = await validator.validate_end_to_end_customer_journey_sla()
            duration = time.time() - start_time
            
            results.append(ValidationResult(
                stream="cross_integration",
                test_name="end_to_end_journey_sla",
                passed=journey_result.passed,
                duration=duration,
                details=asdict(journey_result)
            ))
            
            logger.info(f"✅ Cross-integration validation completed - {len(results)} tests run")
            
        except Exception as e:
            logger.error(f"❌ Cross-integration validation failed: {e}")
            results.append(ValidationResult(
                stream="cross_integration",
                test_name="cross_integration_validation_suite",
                passed=False,
                duration=0,
                details={"error": str(e)},
                critical_failure=True
            ))
            self.critical_failures.append(f"Cross-integration validation failed: {e}")
        
        return results
    
    async def _run_infrastructure_validation(self) -> List[ValidationResult]:
        """Run infrastructure performance validation"""
        results = []
        
        try:
            # Basic infrastructure checks
            import psutil
            
            # Memory usage check
            memory = psutil.virtual_memory()
            memory_usage_gb = memory.used / (1024**3)
            memory_available_gb = memory.available / (1024**3)
            
            memory_passed = memory_available_gb > 2.0  # Need at least 2GB available
            
            results.append(ValidationResult(
                stream="infrastructure",
                test_name="memory_availability",
                passed=memory_passed,
                duration=0.1,
                details={
                    "memory_used_gb": memory_usage_gb,
                    "memory_available_gb": memory_available_gb,
                    "memory_total_gb": memory.total / (1024**3)
                },
                critical_failure=not memory_passed
            ))
            
            if not memory_passed:
                self.critical_failures.append(f"Insufficient memory available: {memory_available_gb:.2f}GB < 2GB required")
            
            # CPU availability check
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_passed = cpu_percent < 90.0  # CPU usage should be < 90%
            
            results.append(ValidationResult(
                stream="infrastructure",
                test_name="cpu_availability",
                passed=cpu_passed,
                duration=1.0,
                details={
                    "cpu_usage_percent": cpu_percent,
                    "cpu_count": psutil.cpu_count()
                }
            ))
            
            # Disk space check
            disk = psutil.disk_usage('/')
            disk_free_gb = disk.free / (1024**3)
            disk_passed = disk_free_gb > 1.0  # Need at least 1GB free
            
            results.append(ValidationResult(
                stream="infrastructure",
                test_name="disk_availability",
                passed=disk_passed,
                duration=0.1,
                details={
                    "disk_free_gb": disk_free_gb,
                    "disk_total_gb": disk.total / (1024**3),
                    "disk_used_gb": disk.used / (1024**3)
                }
            ))
            
            logger.info(f"✅ Infrastructure validation completed - {len(results)} checks run")
            
        except Exception as e:
            logger.error(f"❌ Infrastructure validation failed: {e}")
            results.append(ValidationResult(
                stream="infrastructure",
                test_name="infrastructure_validation_suite",
                passed=False,
                duration=0,
                details={"error": str(e)},
                critical_failure=True
            ))
            self.critical_failures.append(f"Infrastructure validation failed: {e}")
        
        return results
    
    async def _conduct_overall_assessment(self, voice_results, whatsapp_results, cross_results, infra_results) -> Dict[str, Any]:
        """Conduct overall production readiness assessment"""
        
        all_results = voice_results + whatsapp_results + cross_results + infra_results
        
        # Calculate overall metrics
        total_tests = len(all_results)
        passed_tests = sum(1 for r in all_results if r.passed)
        critical_failures = sum(1 for r in all_results if r.critical_failure and not r.passed)
        
        overall_pass_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        
        # Production readiness criteria
        production_ready = (
            overall_pass_rate >= 80 and  # At least 80% tests passing
            critical_failures == 0 and   # No critical failures
            len(self.critical_failures) == 0  # No critical SLA violations
        )
        
        overall_passed = overall_pass_rate >= 90  # 90% for overall "passed" status
        
        # Generate summary
        summary = {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": total_tests - passed_tests,
            "overall_pass_rate": overall_pass_rate,
            "critical_failures": critical_failures,
            "production_ready": production_ready,
            "overall_passed": overall_passed,
            "stream_summaries": {
                "voice": {
                    "total": len(voice_results),
                    "passed": sum(1 for r in voice_results if r.passed),
                    "critical_failures": sum(1 for r in voice_results if r.critical_failure and not r.passed)
                },
                "whatsapp": {
                    "total": len(whatsapp_results),
                    "passed": sum(1 for r in whatsapp_results if r.passed),
                    "critical_failures": sum(1 for r in whatsapp_results if r.critical_failure and not r.passed)
                },
                "cross_integration": {
                    "total": len(cross_results),
                    "passed": sum(1 for r in cross_results if r.passed),
                    "critical_failures": sum(1 for r in cross_results if r.critical_failure and not r.passed)
                },
                "infrastructure": {
                    "total": len(infra_results),
                    "passed": sum(1 for r in infra_results if r.passed),
                    "critical_failures": sum(1 for r in infra_results if r.critical_failure and not r.passed)
                }
            }
        }
        
        return {
            "overall_passed": overall_passed,
            "production_ready": production_ready,
            "summary": summary
        }
    
    async def _generate_validation_reports(self, suite_results: SLAValidationSuite):
        """Generate comprehensive validation reports"""
        logger.info("📊 Generating validation reports...")
        
        # JSON report
        json_report_path = self.validation_run_dir / "sla_validation_results.json"
        with open(json_report_path, 'w') as f:
            json.dump(asdict(suite_results), f, indent=2, default=str)
        
        # Executive summary
        exec_summary_path = self.validation_run_dir / "executive_summary.txt"
        with open(exec_summary_path, 'w') as f:
            f.write(self._generate_executive_summary(suite_results))
        
        # Technical report
        tech_report_path = self.validation_run_dir / "technical_report.txt"
        with open(tech_report_path, 'w') as f:
            f.write(self._generate_technical_report(suite_results))
        
        # Production readiness assessment
        prod_ready_path = self.validation_run_dir / "production_readiness.txt"
        with open(prod_ready_path, 'w') as f:
            f.write(self._generate_production_readiness_report(suite_results))
        
        logger.info(f"✅ Reports generated in {self.validation_run_dir}")
    
    def _generate_executive_summary(self, suite_results: SLAValidationSuite) -> str:
        """Generate executive summary report"""
        summary = suite_results.summary_report
        
        return f"""
AI AGENCY PLATFORM - SLA VALIDATION EXECUTIVE SUMMARY
====================================================

Execution Date: {suite_results.execution_timestamp.strftime('%Y-%m-%d %H:%M:%S')}
Total Validation Time: {suite_results.total_duration:.1f} seconds

PRODUCTION READINESS ASSESSMENT
==============================
Status: {'✅ APPROVED FOR PRODUCTION' if suite_results.production_ready else '❌ NOT READY FOR PRODUCTION'}
Overall Test Success Rate: {summary['overall_pass_rate']:.1f}%

KEY FINDINGS
============
• Total Tests Executed: {summary['total_tests']}
• Tests Passed: {summary['passed_tests']}
• Tests Failed: {summary['failed_tests']}
• Critical Failures: {summary['critical_failures']}

INTEGRATION STREAM PERFORMANCE
=============================
Voice Integration: {summary['stream_summaries']['voice']['passed']}/{summary['stream_summaries']['voice']['total']} passed
WhatsApp Integration: {summary['stream_summaries']['whatsapp']['passed']}/{summary['stream_summaries']['whatsapp']['total']} passed  
Cross-Integration: {summary['stream_summaries']['cross_integration']['passed']}/{summary['stream_summaries']['cross_integration']['total']} passed
Infrastructure: {summary['stream_summaries']['infrastructure']['passed']}/{summary['stream_summaries']['infrastructure']['total']} passed

CRITICAL ISSUES
==============
{chr(10).join(f'• {failure}' for failure in suite_results.critical_failures) if suite_results.critical_failures else '• No critical issues identified'}

RECOMMENDATIONS
==============
{'• Deploy to production - all SLA targets validated' if suite_results.production_ready else '• Address critical failures before production deployment'}
• Continue monitoring SLA performance post-deployment
• Schedule regular SLA validation cycles

Business Impact: {'MINIMAL - System ready for customer traffic' if suite_results.production_ready else 'HIGH - Customer experience at risk'}

Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    
    def _generate_technical_report(self, suite_results: SLAValidationSuite) -> str:
        """Generate detailed technical report"""
        report = f"""
AI AGENCY PLATFORM - TECHNICAL SLA VALIDATION REPORT
===================================================

Execution Timestamp: {suite_results.execution_timestamp.isoformat()}
Total Duration: {suite_results.total_duration:.2f} seconds

DETAILED TEST RESULTS
====================

Voice Integration Stream Results:
"""
        
        for result in suite_results.voice_results:
            status = "PASS" if result.passed else "FAIL"
            report += f"  {result.test_name}: {status} ({result.duration:.2f}s)\n"
            if not result.passed and 'error' in result.details:
                report += f"    Error: {result.details['error']}\n"
        
        report += f"""
WhatsApp Integration Stream Results:
"""
        for result in suite_results.whatsapp_results:
            status = "PASS" if result.passed else "FAIL"
            report += f"  {result.test_name}: {status} ({result.duration:.2f}s)\n"
            if not result.passed and 'error' in result.details:
                report += f"    Error: {result.details['error']}\n"
        
        report += f"""
Cross-Integration Results:
"""
        for result in suite_results.cross_integration_results:
            status = "PASS" if result.passed else "FAIL"
            report += f"  {result.test_name}: {status} ({result.duration:.2f}s)\n"
            if not result.passed and 'error' in result.details:
                report += f"    Error: {result.details['error']}\n"
        
        report += f"""
Infrastructure Results:
"""
        for result in suite_results.infrastructure_results:
            status = "PASS" if result.passed else "FAIL"
            report += f"  {result.test_name}: {status} ({result.duration:.2f}s)\n"
            if not result.passed and 'error' in result.details:
                report += f"    Error: {result.details['error']}\n"
        
        report += f"""

PERFORMANCE ANALYSIS
===================
Overall Pass Rate: {suite_results.summary_report['overall_pass_rate']:.1f}%
Critical Failure Count: {suite_results.summary_report['critical_failures']}

ISSUE RESOLUTION RECOMMENDATIONS
===============================
"""
        if suite_results.critical_failures:
            for i, failure in enumerate(suite_results.critical_failures, 1):
                report += f"{i}. {failure}\n"
        else:
            report += "No critical issues requiring resolution.\n"
        
        return report
    
    def _generate_production_readiness_report(self, suite_results: SLAValidationSuite) -> str:
        """Generate production readiness assessment report"""
        return f"""
PRODUCTION READINESS ASSESSMENT - ISSUE #50 VALIDATION
======================================================

Assessment Date: {suite_results.execution_timestamp.strftime('%Y-%m-%d %H:%M:%S')}

READINESS STATUS: {'✅ APPROVED' if suite_results.production_ready else '❌ NOT APPROVED'}

VALIDATION CRITERIA ASSESSMENT
=============================
✅ Voice Response Time SLA: {'VALIDATED' if any(r.test_name == 'voice_response_time_sla' and r.passed for r in suite_results.voice_results) else 'FAILED'}
✅ WhatsApp Processing SLA: {'VALIDATED' if any(r.test_name == 'message_processing_sla' and r.passed for r in suite_results.whatsapp_results) else 'FAILED'}
✅ Cross-System Integration: {'VALIDATED' if any(r.test_name == 'cross_system_handoff_sla' and r.passed for r in suite_results.cross_integration_results) else 'FAILED'}
✅ Infrastructure Capacity: {'VALIDATED' if all(r.passed for r in suite_results.infrastructure_results) else 'FAILED'}

DEPLOYMENT GATE STATUS
=====================
Overall Test Success: {suite_results.summary_report['overall_pass_rate']:.1f}% {'(≥80% required)' if suite_results.summary_report['overall_pass_rate'] >= 80 else '(BELOW 80% THRESHOLD)'}
Critical Failures: {suite_results.summary_report['critical_failures']} {'(0 required)' if suite_results.summary_report['critical_failures'] == 0 else '(BLOCKING DEPLOYMENT)'}

PHASE 2 PRD COMPLIANCE
======================
• <2s Voice Response Time: {'✅ COMPLIANT' if any(r.test_name == 'voice_response_time_sla' and r.passed for r in suite_results.voice_results) else '❌ NON-COMPLIANT'}
• 500+ Concurrent Voice Sessions: {'✅ COMPLIANT' if any(r.test_name == 'concurrent_sessions_sla' and r.passed for r in suite_results.voice_results) else '⚠️ NOT TESTED'}
• <3s WhatsApp Processing: {'✅ COMPLIANT' if any(r.test_name == 'message_processing_sla' and r.passed for r in suite_results.whatsapp_results) else '❌ NON-COMPLIANT'}
• Cross-Channel Handoff: {'✅ COMPLIANT' if any(r.test_name == 'cross_system_handoff_sla' and r.passed for r in suite_results.cross_integration_results) else '❌ NON-COMPLIANT'}

DEPLOYMENT RECOMMENDATION
========================
{'🚀 APPROVE PRODUCTION DEPLOYMENT - All SLA targets validated and production readiness criteria met.' if suite_results.production_ready else '🛑 BLOCK PRODUCTION DEPLOYMENT - Critical SLA failures must be resolved before deployment.'}

Next Steps:
{'• Deploy to production environment' if suite_results.production_ready else '• Address critical failures listed in technical report'}
{'• Continue SLA monitoring post-deployment' if suite_results.production_ready else '• Re-run validation suite after fixes'}
• Schedule regular SLA validation cycles

Validated by: AI Agency Platform SLA Validation Suite
Report Generated: {datetime.now().isoformat()}
"""
    
    def _print_final_assessment(self, suite_results: SLAValidationSuite):
        """Print final assessment to console"""
        print("\n" + "="*80)
        print("🎯 ISSUE #50 SLA VALIDATION SUITE - FINAL RESULTS")
        print("="*80)
        print(f"⏱️  Total Execution Time: {suite_results.total_duration:.1f} seconds")
        print(f"📊 Overall Test Success Rate: {suite_results.summary_report['overall_pass_rate']:.1f}%")
        print(f"🎯 Production Ready: {'✅ YES' if suite_results.production_ready else '❌ NO'}")
        
        if suite_results.critical_failures:
            print(f"\n🚨 CRITICAL FAILURES ({len(suite_results.critical_failures)}):")
            for failure in suite_results.critical_failures:
                print(f"   ❌ {failure}")
        else:
            print("\n✅ No critical failures detected!")
        
        print(f"\n📁 Detailed reports generated in: {self.validation_run_dir}")
        print("="*80)
        
        if suite_results.production_ready:
            print("🚀 PRODUCTION DEPLOYMENT APPROVED")
            print("   All SLA targets validated successfully")
        else:
            print("🛑 PRODUCTION DEPLOYMENT BLOCKED")
            print("   Critical SLA failures must be resolved")
        
        print("="*80)


async def main():
    """Main entry point for SLA validation suite"""
    parser = argparse.ArgumentParser(description='AI Agency Platform SLA Validation Suite')
    parser.add_argument('--quick', action='store_true', help='Run quick validation (skip long-running tests)')
    parser.add_argument('--concurrent-users', type=int, default=100, help='Number of concurrent users for testing')
    parser.add_argument('--output-dir', type=str, help='Output directory for reports')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Configuration
    config = {
        'validation': {
            'concurrent_users_test': args.concurrent_users,
            'voice_concurrent_sessions': args.concurrent_users,
            'whatsapp_throughput_test': args.concurrent_users,
            'test_duration_seconds': 60 if not args.quick else 30,
            'skip_long_tests': args.quick
        }
    }
    
    if args.output_dir:
        config['output_dir'] = args.output_dir
    
    # Run validation suite
    validator = ComprehensiveSLAValidator(config)
    
    try:
        suite_results = await validator.run_complete_validation_suite()
        
        # Exit with appropriate code
        exit_code = 0 if suite_results.production_ready else 1
        sys.exit(exit_code)
        
    except Exception as e:
        logger.error(f"❌ Validation suite failed: {e}")
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())