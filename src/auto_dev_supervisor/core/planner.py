import yaml
from typing import List, Dict
from rich.console import Console
from auto_dev_supervisor.core.error_handler import EnhancedErrorHandler as ErrorHandler, ErrorCategory, ErrorSeverity
from auto_dev_supervisor.domain.model import ProjectSpec, Task, TaskStatus, ServiceSpec, AppType

console = Console()

class Planner:
    def __init__(self):
        self.error_handler = ErrorHandler()

    def parse_spec(self, yaml_path: str) -> ProjectSpec:
        try:
            with open(yaml_path, "r") as f:
                data = yaml.safe_load(f)
            # Flexible schema adapter
            if "name" not in data and "project_name" in data:
                data["name"] = data["project_name"]
            if "version" not in data:
                data["version"] = "1.0.0"
            if "repository_url" not in data:
                data["repository_url"] = data.get("repo_url", "local")
            if "branch" not in data:
                data["branch"] = "main"

            if "services" not in data:
                services = []
                docker_cfg = data.get("docker", {})
                compose_services = docker_cfg.get("compose_services", [])
                # Map compose services to ServiceSpec entries
                def _type_for(name: str) -> AppType:
                    n = name.lower()
                    if n in ["app", "backend", "api", "worker"]:
                        return AppType.BACKEND
                    if n in ["web", "frontend"]:
                        return AppType.FRONTEND
                    if n in ["ml", "ai"]:
                        return AppType.ML
                    if n in ["audio", "tts"]:
                        return AppType.AUDIO
                    return AppType.OTHER

                deps_map = {}
                for item in compose_services:
                    if isinstance(item, dict):
                        for name, image in item.items():
                            services.append(ServiceSpec(
                                name=name,
                                type=_type_for(name),
                                description=f"Service '{name}' from compose ({image})",
                                dependencies=[]
                            ))
                    elif isinstance(item, str):
                        name = item.split(":")[0]
                        services.append(ServiceSpec(
                            name=name,
                            type=_type_for(name),
                            description=f"Service '{name}' from compose",
                            dependencies=[]
                        ))
                # Simple inferred deps
                names = {s.name for s in services}
                def _svc(n):
                    return next((s for s in services if s.name == n), None)
                if "web" in names and "app" in names:
                    _svc("web").dependencies.append("app")
                if "worker" in names and "app" in names:
                    _svc("worker").dependencies.append("app")
                data["services"] = services

            return ProjectSpec(**data)
        except FileNotFoundError as e:
            error = self.error_handler.handle_error(
                e, {"yaml_path": yaml_path, "phase": "parse_spec"}
            )
            raise Exception(f"Specification file not found: {error.message}")
        except yaml.YAMLError as e:
            error = self.error_handler.handle_error(
                e, {"yaml_path": yaml_path, "phase": "parse_yaml"}
            )
            raise Exception(f"Invalid YAML specification: {error.message}")
        except Exception as e:
            error = self.error_handler.handle_error(
                e, {"yaml_path": yaml_path, "phase": "parse_spec"}
            )
            raise Exception(f"Failed to parse specification: {error.message}")

    def create_initial_tasks(self, spec: ProjectSpec) -> List[Task]:
        try:
            tasks = []
            
            # 1. Setup Repo Task
            tasks.append(Task(
                id="setup-repo",
                title="Initialize Repository",
                description=f"Clone or create repository at {spec.repository_url}",
                service_name="system"
            ))

            # 2. Create Service Tasks
            for service in spec.services:
                # Scaffold Task
                scaffold_task_id = f"scaffold-{service.name}"
                tasks.append(Task(
                    id=scaffold_task_id,
                    title=f"Scaffold {service.name}",
                    description=f"Create initial structure for {service.name}. Type: {service.type}. Desc: {service.description}",
                    service_name=service.name,
                    dependencies=["setup-repo"] + [f"scaffold-{dep}" for dep in service.dependencies]
                ))
                
                # Implement Task
                implement_task_id = f"implement-{service.name}"
                tasks.append(Task(
                    id=implement_task_id,
                    title=f"Implement {service.name}",
                    description=f"Implement core logic for {service.name}",
                    service_name=service.name,
                    dependencies=[scaffold_task_id]
                ))
                
                # Test Task
                test_task_id = f"test-{service.name}"
                tasks.append(Task(
                    id=test_task_id,
                    title=f"Test {service.name}",
                    description=f"Run tests for {service.name}",
                    service_name=service.name,
                    dependencies=[implement_task_id]
                ))

            return tasks
        except Exception as e:
            error = self.error_handler.handle_error(
                e, {"spec_name": spec.name, "phase": "create_tasks"}
            )
            raise Exception(f"Failed to create tasks: {error.message}")

    def get_next_pending_task(self, tasks: List[Task]) -> Task | None:
        try:
            # Simple topological sort or just find first pending with satisfied deps
            completed_ids = {t.id for t in tasks if t.status == TaskStatus.COMPLETED}
            
            for task in tasks:
                if task.status == TaskStatus.PENDING:
                    if all(dep in completed_ids for dep in task.dependencies):
                        return task
            return None
        except Exception as e:
            error = self.error_handler.handle_error(
                e, {"phase": "get_next_pending_task"}
            )
            console.print(f"[red]Error getting next task: {error.message}[/red]")
            return None
