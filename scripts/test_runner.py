#!/usr/bin/env python3
"""
Modern AI Agent Test Runner
Orchestrates different types of testing for Executive Assistant
"""

import asyncio
import argparse
import sys
import os
import subprocess
from pathlib import Path
from typing import List, Dict, Any
import json
import time


class AIAgentTestRunner:
    """Advanced test runner for AI agent testing."""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.test_results = {}
        
    def run_unit_tests(self, verbose: bool = True) -> Dict[str, Any]:
        """Run unit tests with AI evaluation."""
        print("🧪 Running Unit Tests with AI Evaluation...")
        
        cmd = [
            "pytest", 
            "tests/unit/",
            "-m", "not real_api",
            "--cov=src/agents",
            "--cov-report=term-missing"
        ]
        
        if verbose:
            cmd.append("-v")
        
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)
        
        return {
            "type": "unit",
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode
        }
    
    def run_integration_tests(self, with_services: bool = False) -> Dict[str, Any]:
        """Run integration tests with optional real services."""
        print("🔧 Running Integration Tests...")
        
        cmd = ["pytest", "tests/integration/"]
        
        if not with_services:
            cmd.extend(["-m", "not real_api"])
            print("   Using mocked services (faster)")
        else:
            print("   Using real services (requires Docker)")
            # Check if Docker services are running
            if not self._check_docker_services():
                print("❌ Docker services not available, skipping real service tests")
                return {"type": "integration", "success": False, "error": "Docker services unavailable"}
        
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)
        
        return {
            "type": "integration",
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode
        }
    
    def run_scenario_tests(self, personas: List[str] = None) -> Dict[str, Any]:
        """Run scenario-driven acceptance tests."""
        print("🎭 Running Scenario-Driven Tests...")
        
        cmd = ["pytest", "tests/acceptance/", "-m", "agent_test"]
        
        if personas:
            # Filter tests by persona
            persona_filter = " or ".join([f"persona_{p}" for p in personas])
            cmd.extend(["-k", persona_filter])
            print(f"   Testing personas: {', '.join(personas)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)
        
        return {
            "type": "scenario",
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode
        }
    
    def run_conversation_evaluation_tests(self) -> Dict[str, Any]:
        """Run tests using AI evaluation frameworks (AnyAgent, Inspect AI)."""
        print("🤖 Running AI Evaluation Tests...")
        
        cmd = [
            "pytest", 
            "tests/",
            "-m", "evaluation",
            "--tb=long"  # Detailed tracebacks for AI evaluation debugging
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)
        
        return {
            "type": "ai_evaluation",
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode
        }
    
    def run_performance_benchmarks(self) -> Dict[str, Any]:
        """Run performance benchmark tests."""
        print("⚡ Running Performance Benchmarks...")
        
        cmd = [
            "pytest",
            "tests/",
            "-m", "performance",
            "--benchmark-only",
            "--benchmark-sort=mean"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)
        
        return {
            "type": "performance",
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode
        }
    
    def run_cross_channel_tests(self) -> Dict[str, Any]:
        """Run cross-channel conversation continuity tests."""
        print("📱 Running Cross-Channel Continuity Tests...")
        
        cmd = [
            "pytest",
            "tests/",
            "-m", "cross_channel",
            "-v"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)
        
        return {
            "type": "cross_channel",
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode
        }
    
    def run_all_tests(self, with_services: bool = False, include_slow: bool = False) -> Dict[str, Any]:
        """Run comprehensive test suite."""
        print("🚀 Running Complete AI Agent Test Suite...")
        print("=" * 60)
        
        results = {}
        start_time = time.time()
        
        # 1. Unit Tests (Fast)
        results["unit"] = self.run_unit_tests()
        
        # 2. Integration Tests
        results["integration"] = self.run_integration_tests(with_services=with_services)
        
        # 3. AI Evaluation Tests
        results["ai_evaluation"] = self.run_conversation_evaluation_tests()
        
        # 4. Scenario Tests
        results["scenarios"] = self.run_scenario_tests()
        
        # 5. Cross-Channel Tests
        results["cross_channel"] = self.run_cross_channel_tests()
        
        # 6. Performance Tests (if requested)
        if include_slow:
            results["performance"] = self.run_performance_benchmarks()
        
        total_time = time.time() - start_time
        
        # Summary
        successful_suites = sum(1 for r in results.values() if r["success"])
        total_suites = len(results)
        
        print("\n" + "=" * 60)
        print("📊 TEST SUITE SUMMARY")
        print("=" * 60)
        print(f"Total Test Suites: {total_suites}")
        print(f"Successful Suites: {successful_suites}")
        print(f"Success Rate: {successful_suites/total_suites*100:.1f}%")
        print(f"Total Time: {total_time:.2f} seconds")
        
        # Detailed Results
        for suite_name, result in results.items():
            status = "✅ PASS" if result["success"] else "❌ FAIL"
            print(f"{status} {suite_name.upper()}")
            
            if not result["success"] and result.get("stderr"):
                print(f"   Error: {result['stderr'][:200]}...")
        
        return {
            "summary": {
                "total_suites": total_suites,
                "successful_suites": successful_suites,
                "success_rate": successful_suites/total_suites,
                "total_time": total_time,
                "overall_success": successful_suites == total_suites
            },
            "results": results
        }
    
    def _check_docker_services(self) -> bool:
        """Check if required Docker services are running."""
        try:
            result = subprocess.run(
                ["docker", "compose", "ps", "--services", "--filter", "status=running"],
                capture_output=True, text=True, cwd=self.project_root
            )
            
            running_services = result.stdout.strip().split('\n')
            required_services = ['postgres', 'redis']  # Minimum required for testing
            
            return all(service in running_services for service in required_services)
        
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    
    def generate_test_report(self, results: Dict[str, Any], output_file: str = "test_report.json"):
        """Generate comprehensive test report."""
        report_path = self.project_root / output_file
        
        with open(report_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"📄 Test report saved to: {report_path}")
        
        # Generate HTML report if possible
        try:
            self._generate_html_report(results, report_path.with_suffix('.html'))
        except Exception as e:
            print(f"   Could not generate HTML report: {e}")
    
    def _generate_html_report(self, results: Dict[str, Any], output_path: Path):
        """Generate HTML test report."""
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>AI Agent Test Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .summary {{ background: #f5f5f5; padding: 20px; border-radius: 8px; }}
                .suite {{ margin: 20px 0; padding: 15px; border-left: 4px solid #ccc; }}
                .pass {{ border-left-color: #4CAF50; }}
                .fail {{ border-left-color: #f44336; }}
                .timestamp {{ color: #666; font-size: 0.9em; }}
            </style>
        </head>
        <body>
            <h1>🤖 AI Agent Test Report</h1>
            <div class="timestamp">Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}</div>
            
            <div class="summary">
                <h2>Summary</h2>
                <p><strong>Success Rate:</strong> {results['summary']['success_rate']*100:.1f}%</p>
                <p><strong>Total Time:</strong> {results['summary']['total_time']:.2f} seconds</p>
                <p><strong>Overall Success:</strong> {"✅ PASS" if results['summary']['overall_success'] else "❌ FAIL"}</p>
            </div>
            
            <h2>Test Suite Results</h2>
        """
        
        for suite_name, result in results['results'].items():
            status_class = "pass" if result['success'] else "fail"
            status_icon = "✅" if result['success'] else "❌"
            
            html_content += f"""
            <div class="suite {status_class}">
                <h3>{status_icon} {suite_name.upper()}</h3>
                <p><strong>Status:</strong> {"PASS" if result['success'] else "FAIL"}</p>
                <p><strong>Return Code:</strong> {result.get('return_code', 'N/A')}</p>
            </div>
            """
        
        html_content += """
        </body>
        </html>
        """
        
        with open(output_path, 'w') as f:
            f.write(html_content)
    
    def watch_mode(self):
        """Run tests in watch mode for development."""
        print("👀 Starting Test Watch Mode...")
        print("   Tests will re-run when files change")
        print("   Press Ctrl+C to stop")
        
        try:
            subprocess.run([
                "pytest-watch", 
                "--",
                "tests/unit/",
                "-m", "not real_api",
                "--tb=short"
            ], cwd=self.project_root)
        except KeyboardInterrupt:
            print("\n   Watch mode stopped")
        except FileNotFoundError:
            print("   pytest-watch not installed. Install with: pip install pytest-watch")


def main():
    """Main CLI interface."""
    parser = argparse.ArgumentParser(description="AI Agent Test Runner")
    parser.add_argument("--suite", choices=["unit", "integration", "scenarios", "evaluation", "performance", "cross-channel", "all"], 
                       default="unit", help="Test suite to run")
    parser.add_argument("--with-services", action="store_true", help="Use real services (Docker required)")
    parser.add_argument("--include-slow", action="store_true", help="Include slow performance tests")
    parser.add_argument("--personas", nargs="+", help="Specific customer personas to test")
    parser.add_argument("--report", help="Generate test report file")
    parser.add_argument("--watch", action="store_true", help="Run in watch mode")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    runner = AIAgentTestRunner()
    
    if args.watch:
        runner.watch_mode()
        return
    
    # Run selected test suite
    if args.suite == "unit":
        results = {"unit": runner.run_unit_tests(verbose=args.verbose)}
    elif args.suite == "integration":
        results = {"integration": runner.run_integration_tests(with_services=args.with_services)}
    elif args.suite == "scenarios":
        results = {"scenarios": runner.run_scenario_tests(personas=args.personas)}
    elif args.suite == "evaluation":
        results = {"evaluation": runner.run_conversation_evaluation_tests()}
    elif args.suite == "performance":
        results = {"performance": runner.run_performance_benchmarks()}
    elif args.suite == "cross-channel":
        results = {"cross-channel": runner.run_cross_channel_tests()}
    elif args.suite == "all":
        results = runner.run_all_tests(
            with_services=args.with_services, 
            include_slow=args.include_slow
        )
    
    # Generate report if requested
    if args.report:
        runner.generate_test_report(results, args.report)
    
    # Exit with appropriate code
    if args.suite == "all":
        success = results["summary"]["overall_success"]
    else:
        success = list(results.values())[0]["success"]
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()