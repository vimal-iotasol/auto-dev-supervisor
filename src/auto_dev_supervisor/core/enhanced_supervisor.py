"""
Enhanced Supervisor with Advanced Iterative Error Resolution
"""

import time
import json
from typing import List, Dict, Any, Optional
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

class EnhancedSupervisor:
    """
    Enhanced Supervisor with:
    - Advanced iterative error resolution
    - Context-aware error fixing
    - Automatic retry with exponential backoff
    - Multi-strategy recovery approaches
    - Detailed error analytics
    """
    
    def __init__(
        self, 
        planner: Planner,
        opendevin: OpenDevinClient,
        docker_manager: DockerManager,
        git_manager: GitManager,
        qa_manager: QAManager,
        project_root: str = ".",
        max_retries: int = 5,  # Increased from 3
        skip_git: bool = False,
        skip_docker: bool = False,
        enable_advanced_recovery: bool = True,
        recovery_strategies: Optional[List[str]] = None
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
        self.enable_advanced_recovery = enable_advanced_recovery
        self.recovery_strategies = recovery_strategies or [
            "simple_retry", "context_enhancement", "alternative_approach", 
            "simplification", "decomposition", "external_consultation"
        ]
        
        self.error_handler = ErrorHandler()
        self.progress_monitor = ProgressMonitor(self.error_handler)
        self.testing_pipeline = AutomatedTestingPipeline(project_root=self.project_root, error_handler=self.error_handler)
        
        # Enhanced error tracking
        self.error_history = []
        self.recovery_success_rate = {}
        self.task_failure_patterns = {}
        
    def run(self, spec_path: str):
        console.print(f"[bold green]Starting Enhanced Auto-Dev Supervisor for spec: {spec_path}[/bold green]")
        
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
            
            # 5. Enhanced Main Loop with Iterative Error Resolution
            self._run_enhanced_main_loop(tasks, spec)
            
        except Exception as e:
            error = self.error_handler.handle_error(
                e, {"phase": "supervisor_run", "spec_path": spec_path}
            )
            console.print(f"[bold red]Enhanced Supervisor failed: {error.message}[/bold red]")
            self.progress_monitor.error_occurred(f"Enhanced Supervisor failed: {error.message}")
            raise
        finally:
            self.progress_monitor.stop_monitoring()
            self._print_recovery_analytics()
    
    def _run_enhanced_main_loop(self, tasks: List[Task], spec: ProjectSpec):
        """Enhanced main loop with advanced error resolution"""
        with Progress() as progress:
            task_progress = progress.add_task("[cyan]Processing tasks with enhanced recovery...", total=len(tasks))
            
            iteration = 0
            max_iterations = len(tasks) * 3  # Allow for multiple recovery attempts
            
            while iteration < max_iterations:
                current_task = self.planner.get_next_pending_task(tasks)
                if not current_task:
                    if all(t.status == TaskStatus.COMPLETED for t in tasks):
                        console.print("[bold green]All tasks completed successfully![/bold green]")
                        self.progress_monitor.milestone_reached("all_tasks_completed", "All tasks finished successfully")
                        break
                    else:
                        failed_tasks = [t for t in tasks if t.status == TaskStatus.FAILED]
                        console.print(f"[bold red]Some tasks failed after maximum recovery attempts. Failed: {len(failed_tasks)}[/bold red]")
                        self._suggest_manual_intervention(failed_tasks)
                        break
                
                self._process_task_with_enhanced_recovery(current_task, spec, progress, iteration)
                progress.update(task_progress, advance=1)
                iteration += 1
                
    def _process_task_with_enhanced_recovery(self, task: Task, spec: ProjectSpec, progress, iteration: int):
        """Process a single task with enhanced error recovery"""
        console.print(f"\n[bold]Starting Task: {task.title}[/bold]")
        console.print(f"[dim]Task ID: {task.id}, Service: {task.service_name}, Iteration: {iteration}[/dim]")
        task.status = TaskStatus.IN_PROGRESS
        
        # Notify progress monitor
        self.progress_monitor.task_started(task)
        
        # Track this task's error history
        task_error_history = []
        
        for attempt in range(self.max_retries):
            try:
                console.print(f"[yellow]Attempt {attempt + 1}/{self.max_retries}[/yellow]")
                
                # Execute task with context enhancement based on previous failures
                result = self._execute_task_with_context(task, spec, task_error_history)
                
                if result.startswith("Error"):
                    error_info = self._analyze_task_error(task, result, attempt)
                    task_error_history.append(error_info)
                    
                    if self.enable_advanced_recovery and attempt < self.max_retries - 1:
                        recovery_strategy = self._select_recovery_strategy(task, error_info, task_error_history)
                        console.print(f"[yellow]Applying recovery strategy: {recovery_strategy}[/yellow]")
                        
                        recovery_result = self._apply_recovery_strategy(task, recovery_strategy, error_info)
                        if recovery_result.get("success"):
                            console.print(f"[green]Recovery successful: {recovery_result.get('message')}[/green]")
                            self.progress_monitor.recovery_successful(recovery_result.get('message'), task.id, task.service_name)
                            
                            # Retry with recovered context
                            continue
                        else:
                            console.print(f"[red]Recovery failed: {recovery_result.get('message')}[/red]")
                    
                    # Exponential backoff before next attempt
                    if attempt < self.max_retries - 1:
                        backoff_time = min(2 ** attempt, 30)  # Max 30 seconds
                        console.print(f"[yellow]Waiting {backoff_time}s before retry...[/yellow]")
                        time.sleep(backoff_time)
                    
                    self.progress_monitor.retry_attempted(task.id, attempt + 1)
                    continue
                
                # Success - process the result
                self._handle_task_success(task, spec, result)
                return
                
            except Exception as e:
                error = self.error_handler.handle_error(
                    e, {"task_id": task.id, "service_name": task.service_name, "phase": "enhanced_task_processing", "attempt": attempt + 1}
                )
                console.print(f"[red]Task processing error: {error.message}[/red]")
                
                error_info = {
                    "error": e,
                    "message": error.message,
                    "attempt": attempt,
                    "phase": "task_processing"
                }
                task_error_history.append(error_info)
                
                if attempt < self.max_retries - 1:
                    # Try simpler recovery approach
                    console.print("[yellow]Attempting basic recovery...[/yellow]")
                    time.sleep(1)  # Brief pause
                    continue
        
        # Task failed after all retries
        task.status = TaskStatus.FAILED
        console.print(f"[bold red]Task {task.id} failed after {self.max_retries} attempts.[/bold red]")
        self.progress_monitor.task_failed(task, f"Failed after {self.max_retries} attempts with strategies: {[e.get('strategy', 'unknown') for e in task_error_history]}")
        
        # Store failure pattern for future learning
        self._record_failure_pattern(task, task_error_history)
    
    def _execute_task_with_context(self, task: Task, spec: ProjectSpec, error_history: List[Dict]) -> str:
        """Execute task with enhanced context from previous errors"""
        # Enrich context with service type and template guidance
        service_spec = next((s for s in spec.services if s.name == task.service_name), None)
        template_hint = ""
        if service_spec:
            template_hint = f"\nServiceType: {service_spec.type.value}\nTemplateHint: Use best practices for {service_spec.type.value} services."
        
        # Add error context if available
        error_context = ""
        if error_history:
            recent_errors = error_history[-3:]  # Last 3 errors
            error_context = f"\nPrevious attempts failed with these errors:\n"
            for i, error in enumerate(recent_errors, 1):
                error_context += f"Attempt {i}: {error.get('message', 'Unknown error')}\n"
            error_context += "Please avoid these issues in your implementation.\n"
        
        context = f"Task: {task.title}\nDescription: {task.description}\nService: {task.service_name}{template_hint}{error_context}"
        
        return self.opendevin.execute_task(task, context)
    
    def _analyze_task_error(self, task: Task, error_result: str, attempt: int) -> Dict[str, Any]:
        """Analyze task error and categorize it"""
        error_info = {
            "attempt": attempt,
            "raw_error": error_result,
            "message": error_result,
            "category": "unknown",
            "severity": "medium",
            "strategy_applied": None
        }
        
        # Categorize error
        if "API" in error_result or "rate limit" in error_result.lower():
            error_info["category"] = "api_error"
            error_info["severity"] = "high"
        elif "docker" in error_result.lower() or "container" in error_result.lower():
            error_info["category"] = "docker_error"
            error_info["severity"] = "medium"
        elif "syntax" in error_result.lower() or "compilation" in error_result.lower():
            error_info["category"] = "code_error"
            error_info["severity"] = "high"
        elif "test" in error_result.lower() or "verification" in error_result.lower():
            error_info["category"] = "test_error"
            error_info["severity"] = "medium"
        
        return error_info
    
    def _select_recovery_strategy(self, task: Task, error_info: Dict, error_history: List[Dict]) -> str:
        """Select appropriate recovery strategy based on error type and history"""
        error_category = error_info.get("category", "unknown")
        
        # Strategy selection based on error category
        strategy_map = {
            "api_error": ["simple_retry", "alternative_approach"],
            "docker_error": ["context_enhancement", "simplification"],
            "code_error": ["context_enhancement", "alternative_approach", "decomposition"],
            "test_error": ["context_enhancement", "simplification", "alternative_approach"],
            "unknown": ["simple_retry", "context_enhancement"]
        }
        
        available_strategies = strategy_map.get(error_category, strategy_map["unknown"])
        
        # Remove already tried strategies
        tried_strategies = [e.get("strategy_applied") for e in error_history if e.get("strategy_applied")]
        available_strategies = [s for s in available_strategies if s not in tried_strategies]
        
        return available_strategies[0] if available_strategies else "external_consultation"
    
    def _apply_recovery_strategy(self, task: Task, strategy: str, error_info: Dict) -> Dict[str, Any]:
        """Apply selected recovery strategy"""
        recovery_result = {"success": False, "message": "Strategy not implemented"}
        
        try:
            if strategy == "simple_retry":
                # Just retry with same context (already handled by caller)
                recovery_result = {"success": True, "message": "Simple retry - will re-execute with same context"}
                
            elif strategy == "context_enhancement":
                # Provide more detailed context to the LLM
                enhanced_context = self._create_enhanced_context(task, error_info)
                result = self.opendevin.fix_issues(task, enhanced_context)
                if not result.startswith("Error"):
                    recovery_result = {"success": True, "message": "Context enhancement successful"}
                else:
                    recovery_result = {"success": False, "message": f"Context enhancement failed: {result}"}
                    
            elif strategy == "alternative_approach":
                # Ask for alternative implementation approach
                alt_context = self._create_alternative_context(task, error_info)
                result = self.opendevin.execute_task(task, alt_context)
                if not result.startswith("Error"):
                    recovery_result = {"success": True, "message": "Alternative approach successful"}
                else:
                    recovery_result = {"success": False, "message": f"Alternative approach failed: {result}"}
                    
            elif strategy == "simplification":
                # Ask for simplified version first
                simple_context = self._create_simplified_context(task, error_info)
                result = self.opendevin.execute_task(task, simple_context)
                if not result.startswith("Error"):
                    recovery_result = {"success": True, "message": "Simplification successful"}
                else:
                    recovery_result = {"success": False, "message": f"Simplification failed: {result}"}
                    
            elif strategy == "decomposition":
                # Break task into smaller sub-tasks
                recovery_result = self._apply_decomposition_strategy(task, error_info)
                
            elif strategy == "external_consultation":
                # Log for external intervention
                recovery_result = {"success": False, "message": "Requires external intervention - task too complex"}
        
        except Exception as e:
            recovery_result = {"success": False, "message": f"Recovery strategy failed: {str(e)}"}
        
        error_info["strategy_applied"] = strategy
        return recovery_result
    
    def _create_enhanced_context(self, task: Task, error_info: Dict) -> str:
        """Create enhanced context for error fixing"""
        return f"""
        Previous implementation failed with error: {error_info.get('message', 'Unknown error')}
        
        Task: {task.title}
        Description: {task.description}
        Service: {task.service_name}
        
        Please fix the implementation to avoid this error. Consider:
        1. The specific error message and its root cause
        2. Best practices for the service type
        3. Common patterns that cause this type of error
        4. Defensive programming techniques
        
        Output the corrected code in full.
        """
    
    def _create_alternative_context(self, task: Task, error_info: Dict) -> str:
        """Create context for alternative approach"""
        return f"""
        The previous approach for task '{task.title}' failed.
        
        Error: {error_info.get('message', 'Unknown error')}
        
        Please try a completely different approach to implement this task. Consider:
        1. Different architectural patterns
        2. Alternative libraries or frameworks
        3. Simplified functionality that achieves the same goal
        4. Different code organization or structure
        
        Task: {task.title}
        Description: {task.description}
        Service: {task.service_name}
        
        Output the alternative implementation.
        """
    
    def _create_simplified_context(self, task: Task, error_info: Dict) -> str:
        """Create context for simplified approach"""
        return f"""
        The previous implementation was too complex and failed.
        
        Error: {error_info.get('message', 'Unknown error')}
        
        Please create a much simpler version of this task. Focus on:
        1. Core functionality only
        2. Minimal dependencies
        3. Basic error handling
        4. Simple, readable code
        
        Task: {task.title}
        Description: {task.description}
        Service: {task.service_name}
        
        Output the simplified implementation.
        """
    
    def _apply_decomposition_strategy(self, task: Task, error_info: Dict) -> Dict[str, Any]:
        """Break complex task into simpler sub-tasks"""
        try:
            # For now, implement a simple decomposition
            # In a full implementation, this would create actual sub-tasks
            console.print(f"[yellow]Attempting task decomposition for: {task.title}[/yellow]")
            
            # Try to implement just the core part of the task
            core_context = self._create_simplified_context(task, error_info)
            result = self.opendevin.execute_task(task, core_context)
            
            if not result.startswith("Error"):
                return {"success": True, "message": "Core functionality implemented via decomposition"}
            else:
                return {"success": False, "message": f"Decomposition failed: {result}"}
                
        except Exception as e:
            return {"success": False, "message": f"Decomposition strategy error: {str(e)}"}
    
    def _handle_task_success(self, task: Task, spec: ProjectSpec, result: str):
        """Handle successful task completion"""
        console.print(f"[green]Task execution successful[/green]")
        
        # B. Build & Test
        if task.service_name == "system":
            console.print("[yellow]System task. Skipping build and verification.[/yellow]")
            task.status = TaskStatus.COMPLETED
            self.progress_monitor.task_completed(task)
            return
        
        if self.skip_docker:
            console.print("[yellow]Docker operations skipped.[/yellow]")
            if not self.skip_git and not task.id.startswith("implement-") and not task.id.startswith("test-"):
                self.git_manager.commit_changes(task, [TaskTestResult(type=TaskTestType.UNIT, passed=True, details="Skipped Docker")])
                self.git_manager.push_changes()
            self.progress_monitor.task_completed(task)
            task.status = TaskStatus.COMPLETED
            return
        
        try:
            if not self.docker_manager.build_services(task.service_name):
                error = self.error_handler.handle_error(
                    Exception(f"Build failed for {task.service_name}"),
                    {"task_id": task.id, "service_name": task.service_name, "phase": "docker_build"}
                )
                console.print(f"[red]Build failed for {task.service_name}.[/red]")
                
                # Try to fix build issues
                build_logs = self.docker_manager.get_last_error()
                fix_result = self.opendevin.fix_issues(task, build_logs or "Build failed")
                if fix_result.startswith("Error"):
                    raise Exception(f"Build fix failed: {fix_result}")
                
                # Retry build after fix
                if not self.docker_manager.build_services(task.service_name):
                    raise Exception("Build still failed after fix attempt")
            
            self.docker_manager.up()
        except Exception as e:
            error = self.error_handler.handle_error(
                e, {"task_id": task.id, "service_name": task.service_name, "phase": "docker_operations"}
            )
            console.print(f"[red]Docker operation failed: {error.message}[/red]")
            raise
        
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
                console.print("[yellow]Verification passed. Skipping git commit.[/yellow]")
            
            self.progress_monitor.task_completed(task)
            task.status = TaskStatus.COMPLETED
        else:
            # E. Fix
            console.print("[red]Verification failed. Requesting fix...[/red]")
            failures = "\n".join([r.details for r in test_results if not r.passed])
            
            error = self.error_handler.handle_error(
                Exception(f"Verification failed: {failures}"),
                {"task_id": task.id, "service_name": task.service_name, "phase": "verification", "failures": failures}
            )
            
            self.progress_monitor.error_occurred(f"Verification failed: {failures}", task.id, task.service_name, "TEST_FAILURE")
            
            # Try to fix verification issues
            fix_result = self.opendevin.fix_issues(task, failures)
            if fix_result.startswith("Error"):
                raise Exception(f"Verification fix failed: {fix_result}")
            
            # Retry verification after fix
            console.print("[yellow]Retrying verification after fix...[/yellow]")
            test_results = self._run_verification(task, spec)
            all_passed = all(r.passed for r in test_results)
            
            if all_passed:
                console.print("[green]Verification passed after fix![/green]")
                if not self.skip_git:
                    self.git_manager.commit_changes(task, test_results)
                    self.git_manager.push_changes()
                self.progress_monitor.task_completed(task)
                task.status = TaskStatus.COMPLETED
            else:
                raise Exception("Verification still failed after fix attempt")
    
    def _record_failure_pattern(self, task: Task, error_history: List[Dict]):
        """Record failure patterns for future learning"""
        pattern_key = f"{task.service_name}:{task.title}"
        
        if pattern_key not in self.task_failure_patterns:
            self.task_failure_patterns[pattern_key] = {
                "count": 0,
                "errors": [],
                "successful_strategies": []
            }
        
        pattern = self.task_failure_patterns[pattern_key]
        pattern["count"] += 1
        pattern["errors"].extend([e.get("message", "Unknown error") for e in error_history])
        
        # Track successful recovery strategies
        successful_strategies = [e.get("strategy_applied") for e in error_history if e.get("recovery_successful")]
        pattern["successful_strategies"].extend(successful_strategies)
    
    def _suggest_manual_intervention(self, failed_tasks: List[Task]):
        """Suggest manual intervention for failed tasks"""
        console.print("\n[bold yellow]⚠️  Manual Intervention Required[/bold yellow]")
        console.print("The following tasks failed after maximum recovery attempts:")
        
        for task in failed_tasks:
            console.print(f"  • {task.title} ({task.id})")
            
            # Show failure patterns if available
            pattern_key = f"{task.service_name}:{task.title}"
            if pattern_key in self.task_failure_patterns:
                pattern = self.task_failure_patterns[pattern_key]
                console.print(f"    Failed {pattern['count']} times. Common errors: {set(pattern['errors'][-3:])}")
        
        console.print("\n[yellow]Suggestions:[/yellow]")
        console.print("1. Check the error logs above for specific issues")
        console.print("2. Verify your project specification YAML file")
        console.print("3. Ensure all dependencies are available")
        console.print("4. Try running with a different LLM provider")
        console.print("5. Consider simplifying the task requirements")
    
    def _print_recovery_analytics(self):
        """Print recovery analytics at the end"""
        if self.task_failure_patterns:
            console.print("\n[bold blue]📊 Recovery Analytics[/bold blue]")
            
            total_failures = sum(p["count"] for p in self.task_failure_patterns.values())
            console.print(f"Total task failures: {total_failures}")
            
            if total_failures > 0:
                console.print("Most problematic tasks:")
                sorted_patterns = sorted(self.task_failure_patterns.items(), key=lambda x: x[1]["count"], reverse=True)
                for task_key, pattern in sorted_patterns[:5]:
                    console.print(f"  • {task_key}: {pattern['count']} failures")
                    if pattern["successful_strategies"]:
                        console.print(f"    Successful strategies: {set(pattern['successful_strategies'])}")
    
    def _run_verification(self, task: Task, spec: ProjectSpec) -> List[TaskTestResult]:
        """Run verification using the testing pipeline"""
        # Use the same verification logic as the original supervisor
        # This is a placeholder - in a full implementation, this would be enhanced
        results = []
        
        try:
            service_spec = next((s for s in spec.services if s.name == task.service_name), None)
            if not service_spec:
                return [TaskTestResult(type=TaskTestType.UNIT, passed=True, details="System task")]
            
            # Use automated testing pipeline
            test_results = self.testing_pipeline.run_all_tests(task.service_name, service_spec)
            
            for test_result in test_results:
                task_result = TaskTestResult(
                    type=test_result.test_type,
                    passed=test_result.passed,
                    details=self._format_test_details(test_result)
                )
                results.append(task_result)
                
        except Exception as e:
            error = self.error_handler.handle_error(
                e, {"task_id": task.id, "service_name": task.service_name, "phase": "verification"}
            )
            results.append(TaskTestResult(
                type=TaskTestType.UNIT, 
                passed=False, 
                details=f"Verification error: {error.message}"
            ))
        
        return results
    
    def _format_test_details(self, test_result) -> str:
        """Format test result details"""
        details_parts = []
        
        if test_result.passed:
            details_parts.append("✅ Tests passed")
        else:
            details_parts.append("❌ Tests failed")
            
        if hasattr(test_result, 'duration_seconds') and test_result.duration_seconds:
            details_parts.append(f"Duration: {test_result.duration_seconds:.2f}s")
            
        if hasattr(test_result, 'metrics') and test_result.metrics:
            metrics_str = ", ".join([f"{k}: {v}" for k, v in test_result.metrics.items() if v is not None])
            if metrics_str:
                details_parts.append(f"Metrics: {metrics_str}")
                
        if hasattr(test_result, 'coverage_percentage') and test_result.coverage_percentage:
            details_parts.append(f"Coverage: {test_result.coverage_percentage:.1f}%")
            
        if hasattr(test_result, 'error_message') and test_result.error_message:
            details_parts.append(f"Error: {test_result.error_message}")
            
        return " | ".join(details_parts)
