import docker
import yaml
import os
from typing import Dict, List, Optional
from auto_dev_supervisor.domain.model import ProjectSpec, ServiceSpec, TaskTestResult, TaskTestType

class DockerManager:
    def __init__(self, project_root: str):
        self.client = docker.from_env()
        self.project_root = project_root
        self.compose_file = os.path.join(project_root, "docker-compose.yml")

    def generate_compose_file(self, spec: ProjectSpec):
        services = {}
        for service in spec.services:
            service_config = {
                "build": {
                    "context": ".",
                    "dockerfile": f"Dockerfile.{service.name}"
                },
                "image": f"{spec.name}-{service.name}:{spec.version}",
                "volumes": [".:/app"],
                "environment": ["ENV=test"]
            }
            
            if service.dependencies:
                service_config["depends_on"] = service.dependencies
                
            services[service.name] = service_config

        compose_data = {
            "version": "3.8",
            "services": services
        }

        with open(self.compose_file, "w") as f:
            yaml.dump(compose_data, f)

    def build_services(self) -> bool:
        try:
            # In a real scenario, we might use subprocess to call 'docker-compose build'
            # or use the python-on-whales library for better compose support.
            # For this implementation, we'll simulate building via the low-level API or assume docker-compose is installed.
            import subprocess
            result = subprocess.run(
                ["docker-compose", "build"], 
                cwd=self.project_root, 
                capture_output=True, 
                text=True
            )
            if result.returncode != 0:
                print(f"Build failed: {result.stderr}")
                return False
            return True
        except Exception as e:
            print(f"Build error: {e}")
            return False

    def up(self) -> bool:
        try:
            import subprocess
            result = subprocess.run(
                ["docker-compose", "up", "-d"], 
                cwd=self.project_root, 
                capture_output=True, 
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def down(self):
        import subprocess
        subprocess.run(["docker-compose", "down"], cwd=self.project_root)

    def run_tests(self, service_name: str, test_type: TaskTestType) -> TaskTestResult:
        container_name = f"{os.path.basename(self.project_root)}_{service_name}_1"
        # Note: Docker Compose container naming can vary. 
        # A more robust way is to use `docker-compose ps -q service_name`
        
        cmd = ""
        if test_type == TaskTestType.UNIT:
            cmd = "pytest tests/unit"
        elif test_type == TaskTestType.INTEGRATION:
            cmd = "pytest tests/integration"
        elif test_type == TaskTestType.ML_QA:
            cmd = "python scripts/run_ml_qa.py"
            
        try:
            container = self.client.containers.get(container_name)
            exec_result = container.exec_run(cmd)
            
            passed = exec_result.exit_code == 0
            output = exec_result.output.decode("utf-8")
            
            return TaskTestResult(
                type=test_type,
                passed=passed,
                details=output
            )
        except Exception as e:
            return TaskTestResult(
                type=test_type,
                passed=False,
                details=str(e)
            )

    def get_logs(self, service_name: str) -> str:
        try:
            import subprocess
            result = subprocess.run(
                ["docker-compose", "logs", service_name],
                cwd=self.project_root,
                capture_output=True,
                text=True
            )
            return result.stdout
        except Exception:
            return ""
