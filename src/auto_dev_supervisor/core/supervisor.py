import time
from typing import List
from rich.console import Console
from rich.progress import Progress

from auto_dev_supervisor.domain.model import ProjectSpec, Task, TaskStatus, TaskTestType, TaskTestResult
from auto_dev_supervisor.core.planner import Planner
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
        max_retries: int = 3,
        skip_git: bool = False
    ):
        self.planner = planner
        self.opendevin = opendevin
        self.docker_manager = docker_manager
        self.git_manager = git_manager
        self.qa_manager = qa_manager
        self.max_retries = max_retries
        self.skip_git = skip_git

    def run(self, spec_path: str):
        console.print(f"[bold green]Starting Auto-Dev Supervisor for spec: {spec_path}[/bold green]")
        
        # 1. Parse Spec
        spec = self.planner.parse_spec(spec_path)
        console.print(f"Project: {spec.name} v{spec.version}")
        
        # 2. Plan Tasks
        tasks = self.planner.create_initial_tasks(spec)
        console.print(f"Generated {len(tasks)} tasks.")
        
        # 3. Generate Docker Compose
        self.docker_manager.generate_compose_file(spec)
        
        # 4. Main Loop
        with Progress() as progress:
            task_progress = progress.add_task("[cyan]Processing tasks...", total=len(tasks))
            
            while True:
                current_task = self.planner.get_next_pending_task(tasks)
                if not current_task:
                    if all(t.status == TaskStatus.COMPLETED for t in tasks):
                        console.print("[bold green]All tasks completed successfully![/bold green]")
                        break
                    else:
                        console.print("[bold red]Deadlock detected or tasks failed.[/bold red]")
                        break
                
                self._process_task(current_task, spec, progress)
                progress.update(task_progress, advance=1)

    def _process_task(self, task: Task, spec: ProjectSpec, progress):
        console.print(f"\n[bold]Starting Task: {task.title}[/bold]")
        task.status = TaskStatus.IN_PROGRESS
        
        retries = 0
        while retries < self.max_retries:
            # A. Implement / Execute
            context = f"Task: {task.title}\nDescription: {task.description}\nService: {task.service_name}"
            self.opendevin.execute_task(task, context)
            
            # B. Build & Test
            if not self.docker_manager.build_services():
                console.print("[red]Build failed. Requesting fix...[/red]")
                self.opendevin.fix_issues(task, "Build failed")
                retries += 1
                continue
                
            self.docker_manager.up()
            
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
                
                task.status = TaskStatus.COMPLETED
                return
            else:
                # E. Fix
                console.print("[red]Verification failed. Requesting fix...[/red]")
                failures = "\n".join([r.details for r in test_results if not r.passed])
                self.opendevin.fix_issues(task, failures)
                retries += 1
        
        task.status = TaskStatus.FAILED
        console.print(f"[bold red]Task {task.id} failed after {self.max_retries} retries.[/bold red]")

    def _run_verification(self, task: Task, spec: ProjectSpec) -> List[TaskTestResult]:
        results = []
        
        # Determine relevant service spec
        service_spec = next((s for s in spec.services if s.name == task.service_name), None)
        if not service_spec:
            # System tasks might not have a service spec
            return [TaskTestResult(type=TaskTestType.UNIT, passed=True, details="System task")]

        # 1. Unit Tests
        results.append(self.docker_manager.run_tests(task.service_name, TaskTestType.UNIT))
        
        # 2. Integration Tests (if applicable)
        # Simplified logic: run if explicitly requested or implied
        results.append(self.docker_manager.run_tests(task.service_name, TaskTestType.INTEGRATION))
        
        # 3. ML/Audio QA (if applicable)
        if service_spec.ml_metrics:
            qa_result = self.docker_manager.run_tests(task.service_name, TaskTestType.ML_QA)
            qa_result = self.qa_manager.validate_test_result(qa_result, service_spec.ml_metrics)
            results.append(qa_result)
            
        return results
