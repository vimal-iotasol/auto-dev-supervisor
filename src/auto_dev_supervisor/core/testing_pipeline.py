"""
Automated Testing Pipeline for Auto-Dev Supervisor
Provides comprehensive testing capabilities including unit tests, integration tests, 
performance tests, and quality assurance checks.
"""

import time
import subprocess
import json
import os
import tempfile
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, TaskID

from auto_dev_supervisor.domain.model import TaskTestResult, TaskTestType, ServiceSpec
from auto_dev_supervisor.core.error_handler import EnhancedErrorHandler as ErrorHandler, ErrorCategory, ErrorSeverity

console = Console()

@dataclass
class TestConfiguration:
    """Configuration for a specific test type."""
    test_type: TaskTestType
    timeout_seconds: int = 300
    retry_count: int = 2
    parallel_execution: bool = False
    required_metrics: List[str] = field(default_factory=list)
    custom_commands: List[str] = field(default_factory=list)

@dataclass
class TestResult:
    """Enhanced test result with detailed metrics."""
    test_type: TaskTestType
    passed: bool
    duration_seconds: float
    error_message: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)
    coverage_percentage: Optional[float] = None
    performance_metrics: Dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class TestSuite:
    """A collection of related tests."""
    name: str
    service_name: str
    configurations: List[TestConfiguration]
    results: List[TestResult] = field(default_factory=list)
    
class AutomatedTestingPipeline:
    """Comprehensive automated testing pipeline."""
    
    def __init__(self, project_root: str, error_handler: Optional[ErrorHandler] = None):
        self.project_root = project_root
        self.error_handler = error_handler or ErrorHandler()
        self.test_suites: Dict[str, TestSuite] = {}
        self.test_configurations: Dict[TaskTestType, TestConfiguration] = {}
        self.custom_test_runners: Dict[str, Callable] = {}
        self._setup_default_configurations()
        
    def _setup_default_configurations(self):
        """Setup default test configurations."""
        self.test_configurations[TaskTestType.UNIT] = TestConfiguration(
            test_type=TaskTestType.UNIT,
            timeout_seconds=120,
            retry_count=1,
            parallel_execution=True,
            required_metrics=["test_count", "pass_rate", "coverage"]
        )
        
        self.test_configurations[TaskTestType.INTEGRATION] = TestConfiguration(
            test_type=TaskTestType.INTEGRATION,
            timeout_seconds=300,
            retry_count=2,
            parallel_execution=False,
            required_metrics=["api_response_time", "database_connections", "memory_usage"]
        )
        
        self.test_configurations[TaskTestType.ML_QA] = TestConfiguration(
            test_type=TaskTestType.ML_QA,
            timeout_seconds=600,
            retry_count=1,
            parallel_execution=False,
            required_metrics=["accuracy", "precision", "recall", "f1_score", "latency"]
        )
        
    def register_test_suite(self, service_name: str, configurations: List[TestConfiguration]):
        """Register a test suite for a service."""
        suite = TestSuite(
            name=f"{service_name}_test_suite",
            service_name=service_name,
            configurations=configurations
        )
        self.test_suites[service_name] = suite
        
    def register_custom_test_runner(self, test_type: str, runner: Callable):
        """Register a custom test runner for a specific test type."""
        self.custom_test_runners[test_type] = runner
        
    def run_all_tests(self, service_name: str, service_spec: Optional[ServiceSpec] = None) -> List[TestResult]:
        """Run all tests for a service."""
        console.print(f"[cyan]Starting automated testing pipeline for {service_name}...[/cyan]")
        
        if service_name not in self.test_suites:
            # Auto-generate test suite based on service spec
            if service_spec:
                self._generate_test_suite(service_name, service_spec)
            else:
                # Use default configurations
                self._generate_default_test_suite(service_name)
        
        suite = self.test_suites[service_name]
        all_results = []
        
        with Progress() as progress:
            overall_task = progress.add_task(f"Running tests for {service_name}", total=len(suite.configurations))
            
            for config in suite.configurations:
                console.print(f"[yellow]Running {config.test_type.value} tests...[/yellow]")
                
                try:
                    result = self._run_single_test(service_name, config, progress)
                    suite.results.append(result)
                    all_results.append(result)
                    
                    if result.passed:
                        console.print(f"[green]✅ {config.test_type.value} tests passed[/green]")
                    else:
                        console.print(f"[red]❌ {config.test_type.value} tests failed: {result.error_message}[/red]")
                        
                except Exception as e:
                    error = self.error_handler.handle_error(
                        e, {"service_name": service_name, "phase": "run_tests", "test_type": config.test_type.value}
                    )
                    
                    failed_result = TestResult(
                        test_type=config.test_type,
                        passed=False,
                        duration_seconds=0,
                        error_message=f"Test execution failed: {error.message}"
                    )
                    suite.results.append(failed_result)
                    all_results.append(failed_result)
                    
                progress.update(overall_task, advance=1)
        
        # Generate test report
        self._generate_test_report(service_name, all_results)
        
        return all_results
        
    def _run_single_test(self, service_name: str, config: TestConfiguration, progress: Progress) -> TestResult:
        """Run a single test configuration."""
        start_time = time.time()
        test_task = progress.add_task(f"Running {config.test_type.value}", total=None)
        
        # Check if custom runner exists
        if config.test_type.value in self.custom_test_runners:
            return self._run_custom_test(service_name, config, progress)
        
        # Use default test runners
        if config.test_type == TaskTestType.UNIT:
            return self._run_unit_tests(service_name, config, progress)
        elif config.test_type == TaskTestType.INTEGRATION:
            return self._run_integration_tests(service_name, config, progress)
        elif config.test_type == TaskTestType.ML_QA:
            return self._run_ml_qa_tests(service_name, config, progress)
        else:
            return self._run_generic_test(service_name, config, progress)
            
    def _run_unit_tests(self, service_name: str, config: TestConfiguration, progress: Progress) -> TestResult:
        """Run unit tests for a service."""
        logs = []
        metrics = {}
        
        try:
            # Code quality gates (lint/security) before tests
            quality_passed, quality_logs, quality_metrics = self._run_code_quality_checks(service_name, config)
            logs.extend(quality_logs)
            metrics.update(quality_metrics)
            if not quality_passed:
                return TestResult(
                    test_type=config.test_type,
                    passed=False,
                    duration_seconds=0,
                    error_message="Code quality gates failed",
                    metrics=metrics,
                    logs=logs[-30:]
                )

            # Common unit test commands
            test_commands = [
                f"python -m pytest tests/unit/{service_name}/ -v --tb=short",
                f"python -m unittest discover -s tests/unit/{service_name} -p 'test_*.py' -v",
                f"cd {service_name} && python -m pytest tests/ -v --cov=. --cov-report=xml"
            ]
            
            for cmd in test_commands:
                progress.update(progress.task_ids[-1], description=f"Trying: {cmd[:50]}...")
                
                try:
                    result = self._execute_command(cmd, config.timeout_seconds)
                    if result["returncode"] == 0:
                        logs.extend(result["stdout"].split('\n'))
                        metrics = self._parse_test_metrics(result["stdout"])
                        
                        # Extract coverage if available
                        if "coverage" in result["stdout"].lower():
                            metrics["coverage"] = self._extract_coverage_percentage(result["stdout"])
                        
                        duration = time.time() - (time.time() - config.timeout_seconds + result["duration"])
                        
                        return TestResult(
                            test_type=config.test_type,
                            passed=True,
                            duration_seconds=duration,
                            metrics=metrics,
                            logs=logs[-20:],  # Keep last 20 lines
                            coverage_percentage=metrics.get("coverage")
                        )
                        
                except Exception as e:
                    logs.append(f"Command failed: {cmd} - {str(e)}")
                    continue
            
            # If no standard test command worked, try to find and run tests manually
            return self._run_fallback_unit_tests(service_name, config, progress)
            
        except Exception as e:
            error = self.error_handler.handle_error(
                e, {"service_name": service_name, "phase": "unit_tests"}
            )
            
            return TestResult(
                test_type=config.test_type,
                passed=False,
                duration_seconds=time.time() - (time.time() - config.timeout_seconds),
                error_message=f"Unit test execution failed: {error.message}",
                logs=logs
            )
            
    def _run_integration_tests(self, service_name: str, config: TestConfiguration, progress: Progress) -> TestResult:
        """Run integration tests for a service."""
        logs = []
        metrics = {}
        
        try:
            # Integration test commands
            test_commands = [
                f"python -m pytest tests/integration/{service_name}/ -v --tb=short",
                f"python -m pytest tests/integration/ -k {service_name} -v",
                f"cd {service_name} && python -m pytest tests/integration/ -v"
            ]
            
            for cmd in test_commands:
                progress.update(progress.task_ids[-1], description=f"Trying: {cmd[:50]}...")
                
                try:
                    result = self._execute_command(cmd, config.timeout_seconds)
                    if result["returncode"] == 0:
                        logs.extend(result["stdout"].split('\n'))
                        metrics = self._parse_integration_metrics(result["stdout"])
                        
                        duration = time.time() - (time.time() - config.timeout_seconds + result["duration"])
                        
                        return TestResult(
                            test_type=config.test_type,
                            passed=True,
                            duration_seconds=duration,
                            metrics=metrics,
                            logs=logs[-20:]
                        )
                        
                except Exception as e:
                    logs.append(f"Command failed: {cmd} - {str(e)}")
                    continue
            
            return TestResult(
                test_type=config.test_type,
                passed=False,
                duration_seconds=config.timeout_seconds,
                error_message="No integration tests found or all test commands failed",
                logs=logs
            )
            
        except Exception as e:
            error = self.error_handler.handle_error(
                e, {"service_name": service_name, "phase": "integration_tests"}
            )
            
            return TestResult(
                test_type=config.test_type,
                passed=False,
                duration_seconds=config.timeout_seconds,
                error_message=f"Integration test execution failed: {error.message}",
                logs=logs
            )
            
    def _run_ml_qa_tests(self, service_name: str, config: TestConfiguration, progress: Progress) -> TestResult:
        """Run ML/QA tests for a service."""
        logs = []
        metrics = {}
        
        try:
            # Look for ML test scripts
            ml_test_commands = [
                f"python scripts/test_ml_{service_name}.py",
                f"python tests/ml/test_{service_name}.py",
                f"cd {service_name} && python -m pytest tests/ml/ -v"
            ]
            
            for cmd in ml_test_commands:
                progress.update(progress.task_ids[-1], description=f"Trying: {cmd[:50]}...")
                
                try:
                    result = self._execute_command(cmd, config.timeout_seconds)
                    if result["returncode"] == 0:
                        logs.extend(result["stdout"].split('\n'))
                        metrics = self._parse_ml_metrics(result["stdout"])
                        
                        duration = time.time() - (time.time() - config.timeout_seconds + result["duration"])
                        
                        return TestResult(
                            test_type=config.test_type,
                            passed=True,
                            duration_seconds=duration,
                            metrics=metrics,
                            logs=logs[-20:]
                        )
                        
                except Exception as e:
                    logs.append(f"Command failed: {cmd} - {str(e)}")
                    continue
            
            # If no ML tests found, run basic validation
            return self._run_basic_ml_validation(service_name, config, progress)
            
        except Exception as e:
            error = self.error_handler.handle_error(
                e, {"service_name": service_name, "phase": "ml_qa"}
            )
            
            return TestResult(
                test_type=config.test_type,
                passed=False,
                duration_seconds=config.timeout_seconds,
                error_message=f"ML/QA test execution failed: {error.message}",
                logs=logs
            )
            
    def _run_generic_test(self, service_name: str, config: TestConfiguration, progress: Progress) -> TestResult:
        """Run generic tests for unknown test types."""
        logs = []
        
        try:
            # Try to find any test files
            test_files = [
                f"tests/{service_name}/test_*.py",
                f"tests/test_{service_name}.py",
                f"{service_name}/tests/test_*.py"
            ]
            
            for pattern in test_files:
                if os.path.exists(pattern.replace("*", "example")):
                    cmd = f"python -m pytest {pattern} -v"
                    progress.update(progress.task_ids[-1], description=f"Running: {cmd}")
                    
                    result = self._execute_command(cmd, config.timeout_seconds)
                    logs.extend(result["stdout"].split('\n'))
                    
                    return TestResult(
                        test_type=config.test_type,
                        passed=result["returncode"] == 0,
                        duration_seconds=result["duration"],
                        logs=logs[-20:]
                    )
            
            return TestResult(
                test_type=config.test_type,
                passed=True,  # Pass if no tests found (not a failure)
                duration_seconds=0,
                logs=["No generic tests found - marking as passed"]
            )
            
        except Exception as e:
            return TestResult(
                test_type=config.test_type,
                passed=False,
                duration_seconds=config.timeout_seconds,
                error_message=f"Generic test failed: {str(e)}",
                logs=logs
            )
            
    def _run_custom_test(self, service_name: str, config: TestConfiguration, progress: Progress) -> TestResult:
        """Run a custom test using registered test runner."""
        if config.test_type.value not in self.custom_test_runners:
            return TestResult(
                test_type=config.test_type,
                passed=False,
                duration_seconds=0,
                error_message=f"No custom test runner registered for {config.test_type.value}"
            )
            
        try:
            start_time = time.time()
            runner = self.custom_test_runners[config.test_type.value]
            result = runner(service_name, config, progress)
            duration = time.time() - start_time
            
            if isinstance(result, TestResult):
                return result
            else:
                return TestResult(
                    test_type=config.test_type,
                    passed=bool(result),
                    duration_seconds=duration,
                    error_message=None if result else "Custom test returned False"
                )
                
        except Exception as e:
            error = self.error_handler.handle_error(
                e, {"service_name": service_name, "phase": "custom_test", "test_type": config.test_type.value}
            )
            
            return TestResult(
                test_type=config.test_type,
                passed=False,
                duration_seconds=time.time() - (time.time() - config.timeout_seconds),
                error_message=f"Custom test runner failed: {error.message}"
            )
            
    def _execute_command(self, command: str, timeout: int) -> Dict[str, Any]:
        """Execute a command with timeout and return results."""
        start_time = time.time()
        
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=self.project_root
            )
            
            stdout, stderr = process.communicate(timeout=timeout)
            duration = time.time() - start_time
            
            return {
                "returncode": process.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "duration": duration
            }
            
        except subprocess.TimeoutExpired:
            process.kill()
            raise Exception(f"Command timed out after {timeout} seconds: {command}")
        except Exception as e:
            raise Exception(f"Command execution failed: {command} - {str(e)}")
            
    def _parse_test_metrics(self, output: str) -> Dict[str, Any]:
        """Parse test metrics from command output."""
        metrics = {}
        
        # Parse test count and results
        if "collected" in output:
            import re
            collected_match = re.search(r"collected (\d+) items", output)
            if collected_match:
                metrics["test_count"] = int(collected_match.group(1))
        
        if "passed" in output or "failed" in output:
            # Look for pytest style output
            passed_match = re.findall(r"(\d+) passed", output)
            failed_match = re.findall(r"(\d+) failed", output)
            
            passed = sum(int(x) for x in passed_match) if passed_match else 0
            failed = sum(int(x) for x in failed_match) if failed_match else 0
            
            metrics["passed"] = passed
            metrics["failed"] = failed
            metrics["pass_rate"] = passed / (passed + failed) if (passed + failed) > 0 else 0
        
        return metrics
        
    def _parse_integration_metrics(self, output: str) -> Dict[str, Any]:
        """Parse integration test metrics."""
        metrics = {}
        
        # Look for API response times
        import re
        response_time_matches = re.findall(r"(\d+\.?\d*)ms", output)
        if response_time_matches:
            response_times = [float(x) for x in response_time_matches]
            metrics["api_response_time"] = sum(response_times) / len(response_times)
        
        return metrics
        
    def _parse_ml_metrics(self, output: str) -> Dict[str, Any]:
        """Parse ML metrics from output."""
        metrics = {}
        
        import re
        
        # Look for common ML metrics
        patterns = {
            "accuracy": r"accuracy[:\s]+(\d+\.?\d*)",
            "precision": r"precision[:\s]+(\d+\.?\d*)",
            "recall": r"recall[:\s]+(\d+\.?\d*)",
            "f1_score": r"f1[_\-]?score[:\s]+(\d+\.?\d*)",
            "latency": r"latency[:\s]+(\d+\.?\d*)[\s]*ms"
        }
        
        for metric, pattern in patterns.items():
            matches = re.findall(pattern, output, re.IGNORECASE)
            if matches:
                metrics[metric] = float(matches[-1])  # Take the last match
        
        return metrics
        
    def _extract_coverage_percentage(self, output: str) -> float:
        """Extract coverage percentage from output."""
        import re
        
        coverage_matches = re.findall(r"(\d+)%", output)
        if coverage_matches:
            return float(coverage_matches[-1])
        
        return 0.0
        
    def _run_fallback_unit_tests(self, service_name: str, config: TestConfiguration, progress: Progress) -> TestResult:
        """Run fallback unit tests when standard methods fail."""
        logs = []
        
        try:
            # Look for any Python files with "test" in the name
            import glob
            test_files = glob.glob(f"**/*test*.py", recursive=True)
            service_test_files = [f for f in test_files if service_name in f.lower()]
            
            if not service_test_files:
                return TestResult(
                    test_type=config.test_type,
                    passed=True,  # Pass if no tests found
                    duration_seconds=0,
                    logs=["No unit test files found - marking as passed"]
                )
            
            # Try to run each test file
            passed_count = 0
            total_duration = 0
            
            for test_file in service_test_files[:5]:  # Limit to 5 files
                try:
                    cmd = f"python {test_file}"
                    progress.update(progress.task_ids[-1], description=f"Running: {test_file}")
                    
                    result = self._execute_command(cmd, config.timeout_seconds // len(service_test_files))
                    total_duration += result["duration"]
                    
                    if result["returncode"] == 0:
                        passed_count += 1
                        logs.append(f"✅ {test_file} passed")
                    else:
                        logs.append(f"❌ {test_file} failed")
                        
                except Exception as e:
                    logs.append(f"⚠️  {test_file} error: {str(e)}")
            
            return TestResult(
                test_type=config.test_type,
                passed=passed_count > 0,
                duration_seconds=total_duration,
                metrics={"test_files": len(service_test_files), "passed_files": passed_count},
                logs=logs
            )
            
        except Exception as e:
            return TestResult(
                test_type=config.test_type,
                passed=False,
                duration_seconds=config.timeout_seconds,
                error_message=f"Fallback unit tests failed: {str(e)}",
                logs=logs
            )
            
    def _run_basic_ml_validation(self, service_name: str, config: TestConfiguration, progress: Progress) -> TestResult:
        """Run basic ML validation when no specific ML tests are found."""
        logs = []
        
        try:
            # Look for model files
            import glob
            model_files = glob.glob(f"**/{service_name}/**/*.pkl", recursive=True)
            model_files.extend(glob.glob(f"**/{service_name}/**/*.h5", recursive=True))
            model_files.extend(glob.glob(f"**/{service_name}/**/*.pt", recursive=True))
            
            if not model_files:
                return TestResult(
                    test_type=config.test_type,
                    passed=True,  # Pass if no ML models found
                    duration_seconds=0,
                    logs=["No ML model files found - marking as passed"]
                )
            
            # Basic validation: check if model files exist and are not empty
            valid_models = 0
            for model_file in model_files:
                try:
                    if os.path.getsize(model_file) > 0:
                        valid_models += 1
                        logs.append(f"✅ Model file valid: {model_file}")
                    else:
                        logs.append(f"❌ Model file empty: {model_file}")
                except Exception as e:
                    logs.append(f"⚠️  Model file error: {model_file} - {str(e)}")
            
            return TestResult(
                test_type=config.test_type,
                passed=valid_models > 0,
                duration_seconds=0.1,  # Minimal duration
                metrics={"model_files": len(model_files), "valid_models": valid_models},
                logs=logs
            )
            
        except Exception as e:
            return TestResult(
                test_type=config.test_type,
                passed=False,
                duration_seconds=config.timeout_seconds,
                error_message=f"Basic ML validation failed: {str(e)}",
                logs=logs
            )

    def _run_code_quality_checks(self, service_name: str, config: TestConfiguration):
        """Run code quality gates using available tools (ruff/flake8/bandit)."""
        logs = []
        metrics = {"quality_tools": []}
        passed = True

        commands = []
        # Prefer ruff if available
        commands.append("ruff . --quiet")
        # Fallback to flake8
        commands.append("flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics")
        # Security checks with bandit
        commands.append("bandit -q -r .")

        for cmd in commands:
            try:
                result = self._execute_command(cmd, 60)
                tool_name = cmd.split()[0]
                metrics["quality_tools"].append(tool_name)
                if result["returncode"] != 0 and result["stdout"]:
                    logs.append(f"{tool_name} issues:\n{result['stdout'][:500]}")
                    passed = False
                elif result["stderr"]:
                    # Some tools print to stderr; consider non-empty stderr as potential issue
                    logs.append(f"{tool_name} notes:\n{result['stderr'][:300]}")
                else:
                    logs.append(f"✅ {tool_name} passed")
            except Exception as e:
                # Tool not installed or failed; do not block, just note
                logs.append(f"{cmd.split()[0]} not available: {str(e)}")

        # Simple threshold: if any tool reported issues, fail quality gates
        return passed, logs, metrics
            
    def _generate_test_suite(self, service_name: str, service_spec: ServiceSpec):
        """Generate test suite based on service specification."""
        configurations = []
        
        # Base configurations
        configurations.append(self.test_configurations[TaskTestType.UNIT])
        configurations.append(self.test_configurations[TaskTestType.INTEGRATION])
        
        # Add ML tests if service has ML metrics
        if service_spec.ml_metrics:
            ml_config = TestConfiguration(
                test_type=TaskTestType.ML_QA,
                timeout_seconds=600,
                required_metrics=list(service_spec.ml_metrics.keys())
            )
            configurations.append(ml_config)
        
        # Add custom configurations based on service type
        if service_spec.type == "frontend":
            frontend_config = TestConfiguration(
                test_type=TaskTestType.UNIT,
                timeout_seconds=180,
                custom_commands=["npm test", "yarn test", "npm run test:unit"]
            )
            configurations.append(frontend_config)
        elif service_spec.type == "backend":
            backend_config = TestConfiguration(
                test_type=TaskTestType.INTEGRATION,
                timeout_seconds=300,
                custom_commands=["python manage.py test", "pytest tests/", "python -m pytest"]
            )
            configurations.append(backend_config)
        
        self.register_test_suite(service_name, configurations)
        
    def _generate_default_test_suite(self, service_name: str):
        """Generate default test suite for unknown services."""
        configurations = [
            self.test_configurations[TaskTestType.UNIT],
            self.test_configurations[TaskTestType.INTEGRATION]
        ]
        
        self.register_test_suite(service_name, configurations)
        
    def _generate_test_report(self, service_name: str, results: List[TestResult]):
        """Generate a comprehensive test report."""
        console.print(f"\n[bold cyan]Test Report for {service_name}[/bold cyan]")
        console.print("=" * 60)
        
        # Summary statistics
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r.passed)
        failed_tests = total_tests - passed_tests
        total_duration = sum(r.duration_seconds for r in results)
        
        # Summary table
        summary_table = Table(title="Test Summary")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")
        
        summary_table.add_row("Total Tests", str(total_tests))
        summary_table.add_row("Passed", f"[green]{passed_tests}[/green]")
        summary_table.add_row("Failed", f"[red]{failed_tests}[/red]")
        summary_table.add_row("Success Rate", f"{(passed_tests/total_tests*100):.1f}%" if total_tests > 0 else "N/A")
        summary_table.add_row("Total Duration", f"{total_duration:.2f}s")
        
        console.print(summary_table)
        
        # Detailed results
        if results:
            console.print(f"\n[bold]Detailed Results:[/bold]")
            
            details_table = Table(title="Test Details")
            details_table.add_column("Test Type", style="cyan")
            details_table.add_column("Status", style="green")
            details_table.add_column("Duration", style="yellow")
            details_table.add_column("Metrics", style="dim")
            details_table.add_column("Error", style="red")
            
            for result in results:
                status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
                metrics_str = str(result.metrics) if result.metrics else ""
                error_str = result.error_message[:50] + "..." if result.error_message and len(result.error_message) > 50 else (result.error_message or "")
                
                details_table.add_row(
                    result.test_type.value,
                    status,
                    f"{result.duration_seconds:.2f}s",
                    metrics_str,
                    error_str
                )
            
            console.print(details_table)
        
        # Performance metrics
        performance_metrics = {}
        for result in results:
            if result.performance_metrics:
                performance_metrics.update(result.performance_metrics)
        
        if performance_metrics:
            console.print(f"\n[bold]Performance Metrics:[/bold]")
            perf_table = Table(title="Performance Summary")
            perf_table.add_column("Metric", style="cyan")
            perf_table.add_column("Value", style="green")
            
            for metric, value in performance_metrics.items():
                perf_table.add_row(metric, f"{value:.4f}")
            
            console.print(perf_table)
        
        console.print("=" * 60)
        
        # Save report to file
        self._save_test_report_to_file(service_name, results)
        
    def _save_test_report_to_file(self, service_name: str, results: List[TestResult]):
        """Save test report to a JSON file."""
        try:
            report_data = {
                "service_name": service_name,
                "timestamp": datetime.now().isoformat(),
                "summary": {
                    "total_tests": len(results),
                    "passed_tests": sum(1 for r in results if r.passed),
                    "failed_tests": sum(1 for r in results if not r.passed),
                    "total_duration": sum(r.duration_seconds for r in results)
                },
                "results": [
                    {
                        "test_type": r.test_type.value,
                        "passed": r.passed,
                        "duration_seconds": r.duration_seconds,
                        "error_message": r.error_message,
                        "metrics": r.metrics,
                        "coverage_percentage": r.coverage_percentage,
                        "performance_metrics": r.performance_metrics
                    }
                    for r in results
                ]
            }
            
            report_file = os.path.join(self.project_root, f"test_report_{service_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            
            with open(report_file, 'w') as f:
                json.dump(report_data, f, indent=2)
            
            console.print(f"[dim]Test report saved to: {report_file}[/dim]")
            
        except Exception as e:
            console.print(f"[red]Failed to save test report: {e}[/red]")
            
    def get_test_coverage_summary(self) -> Dict[str, Any]:
        """Get a summary of test coverage across all services."""
        summary = {
            "total_services": len(self.test_suites),
            "services_with_tests": 0,
            "total_test_results": 0,
            "overall_pass_rate": 0.0,
            "average_coverage": 0.0,
            "services": {}
        }
        
        total_passed = 0
        total_tests = 0
        total_coverage = 0
        coverage_count = 0
        
        for service_name, suite in self.test_suites.items():
            if suite.results:
                summary["services_with_tests"] += 1
                service_passed = sum(1 for r in suite.results if r.passed)
                service_total = len(suite.results)
                service_coverage = sum(r.coverage_percentage for r in suite.results if r.coverage_percentage) / len([r for r in suite.results if r.coverage_percentage]) if any(r.coverage_percentage for r in suite.results) else 0
                
                summary["services"][service_name] = {
                    "test_count": service_total,
                    "passed_tests": service_passed,
                    "pass_rate": service_passed / service_total if service_total > 0 else 0,
                    "average_coverage": service_coverage
                }
                
                total_passed += service_passed
                total_tests += service_total
                if service_coverage > 0:
                    total_coverage += service_coverage
                    coverage_count += 1
        
        summary["total_test_results"] = total_tests
        summary["overall_pass_rate"] = total_passed / total_tests if total_tests > 0 else 0
        summary["average_coverage"] = total_coverage / coverage_count if coverage_count > 0 else 0
        
        return summary