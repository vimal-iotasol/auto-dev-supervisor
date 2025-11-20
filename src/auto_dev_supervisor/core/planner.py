import yaml
from typing import List, Dict
from auto_dev_supervisor.domain.model import ProjectSpec, Task, TaskStatus, ServiceSpec

class Planner:
    def parse_spec(self, yaml_path: str) -> ProjectSpec:
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f)
        return ProjectSpec(**data)

    def create_initial_tasks(self, spec: ProjectSpec) -> List[Task]:
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

    def get_next_pending_task(self, tasks: List[Task]) -> Task | None:
        # Simple topological sort or just find first pending with satisfied deps
        completed_ids = {t.id for t in tasks if t.status == TaskStatus.COMPLETED}
        
        for task in tasks:
            if task.status == TaskStatus.PENDING:
                if all(dep in completed_ids for dep in task.dependencies):
                    return task
        return None
