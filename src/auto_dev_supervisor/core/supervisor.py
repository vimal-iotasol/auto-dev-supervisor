import time
from typing import List
from rich.console import Console
from rich.progress import Progress

from auto_dev_supervisor.domain.model import ProjectSpec, Task, TaskStatus, TaskTestType, TaskTestResult
from auto_dev_supervisor.core.planner import Planner
from auto_dev_supervisor.core.error_handler import EnhancedErrorHandler as ErrorHandler, ErrorCategory, ErrorSeverity
from auto_dev_supervisor.core.progress_monitor import ProgressMonitor
from auto_dev_supervisor.core.testing_pipeline import AutomatedTestingPipeline
from auto_dev_supervisor.infra.opendevin import OpenDevinClient
from auto_dev_supervisor.infra.docker import DockerManager
from auto_dev_supervisor.infra.git import GitManager
from auto_dev_supervisor.domain.qa import QAManager

console = Console()

class Supervisor:
    def __init__(
        self, 
        planner: Planner,
        opendevin: OpenDevinClient,
        docker_manager: DockerManager,
        git_manager: GitManager,
        qa_manager: QAManager,
        project_root: str = ".",
        max_retries: int = 3,
        skip_git: bool = False,
        skip_docker: bool = False
    ):
        self.planner = planner
        self.opendevin = opendevin
        self.docker_manager = docker_manager
        self.git_manager = git_manager
        self.qa_manager = qa_manager
        self.project_root = project_root
        self.max_retries = max_retries
        self.skip_git = skip_git
        self.skip_docker = skip_docker
        self.error_handler = ErrorHandler()
        self.progress_monitor = ProgressMonitor(self.error_handler)
        self.testing_pipeline = AutomatedTestingPipeline(project_root=self.project_root, error_handler=self.error_handler)

    def run(self, spec_path: str):
        console.print(f"[bold green]Starting Auto-Dev Supervisor for spec: {spec_path}[/bold green]")
        
        try:
            # 1. Parse Spec
            spec = self.planner.parse_spec(spec_path)
            console.print(f"Project: {spec.name} v{spec.version}")
            
            # 2. Plan Tasks
            tasks = self.planner.create_initial_tasks(spec)
            console.print(f"Generated {len(tasks)} tasks.")
            
            # 3. Generate Docker Compose
            self.docker_manager.generate_compose_file(spec)
            
            # 4. Start Progress Monitoring
            self.progress_monitor.start_monitoring(len(tasks))
            self.progress_monitor.milestone_reached("project_setup", f"Generated {len(tasks)} tasks for {spec.name}")
            
            # 5. Main Loop
            with Progress() as progress:
                task_progress = progress.add_task("[cyan]Processing tasks...", total=len(tasks))
                
                while True:
                    current_task = self.planner.get_next_pending_task(tasks)
                    if not current_task:
                        if all(t.status == TaskStatus.COMPLETED for t in tasks):
                            console.print("[bold green]All tasks completed successfully![/bold green]")
                            self.progress_monitor.milestone_reached("all_tasks_completed", "All tasks finished successfully")
                            break
                        else:
                            console.print("[bold red]Deadlock detected or tasks failed.[/bold red]")
                            self.progress_monitor.milestone_reached("deadlock_detected", "Some tasks failed or deadlock detected")
                            break
                    
                    self._process_task(current_task, spec, progress)
                    progress.update(task_progress, advance=1)
                    
        except Exception as e:
            error = self.error_handler.handle_error(
                e, {"phase": "supervisor_run", "spec_path": spec_path}
            )
            console.print(f"[bold red]Supervisor failed: {error.message}[/bold red]")
            self.progress_monitor.error_occurred(f"Supervisor failed: {error.message}")
            raise
        finally:
            # Always stop monitoring
            self.progress_monitor.stop_monitoring()

    def _process_task(self, task: Task, spec: ProjectSpec, progress):
        console.print(f"\n[bold]Starting Task: {task.title}[/bold]")
        console.print(f"[dim]Task ID: {task.id}, Service: {task.service_name}[/dim]")
        task.status = TaskStatus.IN_PROGRESS
        
        # Notify progress monitor
        self.progress_monitor.task_started(task)
        
        retries = 0
        while retries < self.max_retries:
            try:
                # A. Implement / Execute
                console.print(f"[yellow]Executing task with OpenDevin client...[/yellow]")
                # Enrich context with service type and template guidance
                service_spec = next((s for s in spec.services if s.name == task.service_name), None)
                template_hint = ""
                if service_spec:
                    template_hint = f"\nServiceType: {service_spec.type.value}\nTemplateHint: Use best practices for {service_spec.type.value} services."
                context = f"Task: {task.title}\nDescription: {task.description}\nService: {task.service_name}{template_hint}"
                result = self.opendevin.execute_task(task, context)
                console.print(f"[dim]OpenDevin execution result length: {len(result)} characters[/dim]")
                
                if result.startswith("Error"):
                    error = self.error_handler.handle_error(
                        Exception(result), {"task_id": task.id, "service_name": task.service_name, "phase": "execute_task", "attempt": retries + 1}
                    )
                    console.print(f"[red]Task execution failed: {error.message}[/red]")
                    
                    # Attempt recovery
                    recovery_result = self.error_handler.attempt_recovery(error)
                    if recovery_result.success:
                        console.print(f"[green]Recovery successful: {recovery_result.message}[/green]")
                        self.progress_monitor.recovery_successful(recovery_result.message, task.id, task.service_name)
                        if recovery_result.alternative_action:
                            # Use alternative action if provided
                            result = recovery_result.alternative_action()
                            if result and not result.startswith("Error"):
                                console.print("[green]Alternative action succeeded[/green]")
                            else:
                                self.progress_monitor.retry_attempted(task.id, retries + 1)
                                retries += 1
                                continue
                        else:
                            self.progress_monitor.retry_attempted(task.id, retries + 1)
                            retries += 1
                            continue
                    else:
                        self.progress_monitor.retry_attempted(task.id, retries + 1)
                        retries += 1
                        continue

                # B. Build & Test
                if task.service_name == "system":
                    # System tasks (like repo setup) don't need docker build/test
                    console.print("[yellow]System task. Skipping build and verification.[/yellow]")
                    task.status = TaskStatus.COMPLETED
                    return

                if self.skip_docker:
                    console.print("[yellow]Docker operations skipped (Run without Docker enabled).[/yellow]")
                    if not task.id.startswith("implement-") and not task.id.startswith("test-"):
                        if not self.skip_git:
                            self.git_manager.commit_changes(task, [TaskTestResult(type=TaskTestType.UNIT, passed=True, details="Skipped Docker")])
                            self.git_manager.push_changes()
                    self.progress_monitor.task_completed(task)
                    task.status = TaskStatus.COMPLETED
                    return

                try:
                    if not self.docker_manager.build_services(task.service_name):
                        error = self.error_handler.handle_error(
                            Exception(f"Build failed for {task.service_name}"),
                            {"task_id": task.id, "service_name": task.service_name, "phase": "docker_build", "attempt": retries + 1}
                        )
                        console.print(f"[red]Build failed for {task.service_name}. Requesting fix...[/red]")
                        
                        # Attempt Docker recovery
                        recovery_result = self.error_handler.attempt_recovery(error)
                        if recovery_result.success:
                            console.print(f"[green]Docker recovery successful: {recovery_result.message}[/green]")
                            self.progress_monitor.recovery_successful(recovery_result.message, task.id, task.service_name)
                            if recovery_result.alternative_action:
                                recovery_result.alternative_action()
                                continue
                        
                        build_logs = self.docker_manager.get_last_error()
                        self.opendevin.fix_issues(task, build_logs or "Build failed")
                        retries += 1
                        continue
                        
                    self.docker_manager.up()
                except Exception as e:
                    error = self.error_handler.handle_error(
                        e, {"task_id": task.id, "service_name": task.service_name, "phase": "docker_up"}
                    )
                    console.print(f"[red]Docker operation failed: {error.message}[/red]")
                    self.progress_monitor.error_occurred(f"Docker operation failed: {error.message}", task.id, task.service_name, "DOCKER")
                    retries += 1
                    continue
                
                # For scaffold tasks, we only build containers and skip verification
                if task.id.startswith("scaffold-"):
                    console.print("[yellow]Scaffold task. Skipping verification for this step.[/yellow]")
                    if not self.skip_git:
                        console.print("[green]Scaffold completed. Committing...[/green]")
                        self.git_manager.commit_changes(task, [TaskTestResult(type=TaskTestType.UNIT, passed=True, details="Scaffold")])
                        self.git_manager.push_changes()
                    self.progress_monitor.task_completed(task)
                    task.status = TaskStatus.COMPLETED
                    return

                # C. Verify
                test_results = self._run_verification(task, spec)
                all_passed = all(r.passed for r in test_results)
                
                if all_passed:
                    # D. Commit & Push
                    if not self.skip_git:
                        console.print("[green]Verification passed. Committing...[/green]")
                        self.git_manager.commit_changes(task, test_results)
                        self.git_manager.push_changes()
                    else:
                        console.print("[yellow]Verification passed. Skipping git commit (skip_git=True).[/yellow]")
                    
                    self.progress_monitor.task_completed(task)
                    task.status = TaskStatus.COMPLETED
                    return
                else:
                    # E. Fix
                    console.print("[red]Verification failed. Requesting fix...[/red]")
                    failures = "\n".join([r.details for r in test_results if not r.passed])
                    
                    error = self.error_handler.handle_error(
                        Exception(f"Verification failed: {failures}"),
                        {"task_id": task.id, "service_name": task.service_name, "phase": "verification", "failures": failures}
                    )
                    
                    self.progress_monitor.error_occurred(f"Verification failed: {failures}", task.id, task.service_name, "TEST_FAILURE")
                    self.opendevin.fix_issues(task, failures)
                    retries += 1
                    
            except Exception as e:
                error = self.error_handler.handle_error(
                    e, {"task_id": task.id, "service_name": task.service_name, "phase": "code_generation", "attempt": retries + 1}
                )
                console.print(f"[red]Task processing error: {error.message}[/red]")
                self.progress_monitor.error_occurred(f"Task processing error: {error.message}", task.id, task.service_name, "CODE_GENERATION")
                
                # Attempt recovery for code generation errors
                recovery_result = self.error_handler.attempt_recovery(error)
                if recovery_result.success:
                    console.print(f"[green]Recovery successful: {recovery_result.message}[/green]")
                    self.progress_monitor.recovery_successful(recovery_result.message, task.id, task.service_name)
                    if recovery_result.alternative_action:
                        try:
                            recovery_result.alternative_action()
                            continue
                        except Exception as recovery_exception:
                            console.print(f"[red]Recovery action failed: {str(recovery_exception)}[/red]")
                            self.progress_monitor.error_occurred(f"Recovery failed: {str(recovery_exception)}", task.id, task.service_name, "RECOVERY")
                
                self.progress_monitor.retry_attempted(task.id, retries + 1)
                retries += 1
        
        task.status = TaskStatus.FAILED
        console.print(f"[bold red]Task {task.id} failed after {self.max_retries} retries.[/bold red]")
        self.progress_monitor.task_failed(task, f"Failed after {self.max_retries} retries")
        
        # Log final error statistics
        error_stats = self.error_handler.get_error_statistics()
        if error_stats.get("total_errors", 0) > 0:
            failed_errors = error_stats["total_errors"] - error_stats.get("recovered_errors", 0)
            console.print(f"[yellow]Error statistics: {error_stats['total_errors']} errors, "
                         f"{error_stats.get('recovered_errors', 0)} recovered, "
                         f"{failed_errors} failed[/yellow]")

    def _run_verification(self, task: Task, spec: ProjectSpec) -> List[TaskTestResult]:
        """Enhanced verification using the automated testing pipeline."""
        results = []
        
        try:
            # Determine relevant service spec
            service_spec = next((s for s in spec.services if s.name == task.service_name), None)
            if not service_spec:
                # System tasks might not have a service spec
                return [TaskTestResult(type=TaskTestType.UNIT, passed=True, details="System task")]

            # Use automated testing pipeline for comprehensive testing
            self.progress_monitor.milestone_reached("testing_start", f"Starting automated tests for {task.service_name}")
            
            try:
                # Run the automated testing pipeline
                test_results = self.testing_pipeline.run_all_tests(task.service_name, service_spec)
                
                # Convert test results to TaskTestResult format
                for test_result in test_results:
                    # Map TestResult to TaskTestResult
                    task_result = TaskTestResult(
                        type=test_result.test_type,
                        passed=test_result.passed,
                        details=self._format_test_details(test_result)
                    )
                    results.append(task_result)
                    
                    # Update progress monitor
                    if test_result.passed:
                        self.progress_monitor.milestone_reached(
                            f"test_passed_{test_result.test_type.value}",
                            f"{test_result.test_type.value} tests passed for {task.service_name}"
                        )
                    else:
                        self.progress_monitor.error_occurred(
                            f"{test_result.test_type.value} tests failed: {test_result.error_message}",
                            task.id, task.service_name, "TEST_FAILURE"
                        )
                
                # Get test coverage summary
                coverage_summary = self.testing_pipeline.get_test_coverage_summary()
                if coverage_summary["services"].get(task.service_name):
                    service_coverage = coverage_summary["services"][task.service_name]
                    self.progress_monitor.milestone_reached(
                        "test_coverage",
                        f"Test coverage for {task.service_name}: {service_coverage['pass_rate']:.1f}% pass rate"
                    )
                
            except Exception as e:
                error = self.error_handler.handle_error(
                    e, {"task_id": task.id, "service_name": task.service_name, "phase": "automated_testing"}
                )
                
                # Fallback to original Docker-based testing
                console.print(f"[yellow]Automated testing pipeline failed, falling back to Docker tests: {error.message}[/yellow]")
                results.extend(self._run_fallback_verification(task, service_spec))
                
        except Exception as e:
            error = self.error_handler.handle_error(
                e, {"task_id": task.id, "service_name": task.service_name, "phase": "verification"}
            )
            results.append(TaskTestResult(
                type=TaskTestType.UNIT, 
                passed=False, 
                details=f"Verification error: {error.message}"
            ))
            self.progress_monitor.error_occurred(f"Verification error: {error.message}", task.id, task.service_name, "VERIFICATION")
            
        return results
        
    def _run_fallback_verification(self, task: Task, service_spec: ServiceSpec) -> List[TaskTestResult]:
        """Fallback verification using Docker-based testing."""
        results = []
        
        # 1. Unit Tests
        try:
            unit_result = self.docker_manager.run_tests(task.service_name, TaskTestType.UNIT)
            results.append(unit_result)
        except Exception as e:
            error = self.error_handler.handle_error(
                e, {"task_id": task.id, "service_name": task.service_name, "phase": "unit_tests"}
            )
            results.append(TaskTestResult(
                type=TaskTestType.UNIT, 
                passed=False, 
                details=f"Unit test error: {error.message}"
            ))
        
        # 2. Integration Tests (if applicable)
        try:
            integration_result = self.docker_manager.run_tests(task.service_name, TaskTestType.INTEGRATION)
            results.append(integration_result)
        except Exception as e:
            error = self.error_handler.handle_error(
                e, {"task_id": task.id, "service_name": task.service_name, "phase": "integration_tests"}
            )
            results.append(TaskTestResult(
                type=TaskTestType.INTEGRATION, 
                passed=False, 
                details=f"Integration test error: {error.message}"
            ))
        
        # 3. ML/Audio QA (if applicable)
        if service_spec.ml_metrics:
            try:
                qa_result = self.docker_manager.run_tests(task.service_name, TaskTestType.ML_QA)
                qa_result = self.qa_manager.validate_test_result(qa_result, service_spec.ml_metrics)
                results.append(qa_result)
            except Exception as e:
                error = self.error_handler.handle_error(
                    e, {"task_id": task.id, "service_name": task.service_name, "phase": "ml_qa"}
                )
                results.append(TaskTestResult(
                    type=TaskTestType.ML_QA, 
                    passed=False, 
                    details=f"ML QA error: {error.message}"
                ))
        
        return results
        
    def _format_test_details(self, test_result) -> str:
        """Format test result details for TaskTestResult."""
        details_parts = []
        
        if test_result.passed:
            details_parts.append("✅ Tests passed")
        else:
            details_parts.append("❌ Tests failed")
            
        if test_result.duration_seconds:
            details_parts.append(f"Duration: {test_result.duration_seconds:.2f}s")
            
        if test_result.metrics:
            metrics_str = ", ".join([f"{k}: {v}" for k, v in test_result.metrics.items() if v is not None])
            if metrics_str:
                details_parts.append(f"Metrics: {metrics_str}")
                
        if test_result.coverage_percentage:
            details_parts.append(f"Coverage: {test_result.coverage_percentage:.1f}%")
            
        if test_result.error_message:
            details_parts.append(f"Error: {test_result.error_message}")
            
        return " | ".join(details_parts)
