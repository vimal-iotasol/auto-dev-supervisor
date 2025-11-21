import docker
import yaml
import os
import subprocess
from typing import Dict, List, Optional
from auto_dev_supervisor.domain.model import ProjectSpec, ServiceSpec, TaskTestResult, TaskTestType
from auto_dev_supervisor.core.error_handler import EnhancedErrorHandler, ErrorCategory, ErrorSeverity

class DockerManager:
    def __init__(self, project_root: str):
        try:
            self.client = docker.from_env()
        except Exception as e:
            self.client = None
            print(f"[Docker] Failed to initialize client: {e}")
        self.project_root = project_root
        self.compose_file = os.path.join(project_root, "docker-compose.yml")
        self.last_error: str = ""
        # Lazy connectivity; avoid pinging here to prevent GUI startup failures

    def _sanitize_name(self, name: str) -> str:
        return name.lower().replace(" ", "-")

    def generate_compose_file(self, spec: ProjectSpec):
        services = {}
        for service in spec.services:
            service_config = {
                "build": {
                    "context": ".",
                    "dockerfile": f"Dockerfile.{service.name}"
                },
                "image": f"{self._sanitize_name(spec.name)}-{service.name}:{spec.version}",
                "volumes": [".:/app"],
                "environment": ["ENV=test"],
                "container_name": f"{os.path.basename(os.path.abspath(self.project_root))}_{service.name}_1"
            }
            # Basic resource management for local compose
            service_config["mem_limit"] = "512m"
            service_config["cpus"] = "0.75"
            
            if service.dependencies:
                service_config["depends_on"] = service.dependencies
                
            services[service.name] = service_config

        compose_data = {
            "services": services
        }

        with open(self.compose_file, "w") as f:
            yaml.dump(compose_data, f)

    def get_last_error(self) -> str:
        return self.last_error

    def build_services(self, service_name: Optional[str] = None) -> bool:
        try:
            # In a real scenario, we might use subprocess to call 'docker-compose build'
            # or use the python-on-whales library for better compose support.
            # For this implementation, we'll simulate building via the low-level API or assume docker-compose is installed.
            cmd = ["docker-compose", "build"]
            if service_name:
                cmd.append(service_name)
                
            # Use binary mode (text=False) to avoid UnicodeDecodeError on Windows
            result = subprocess.run(
                cmd, 
                cwd=self.project_root, 
                capture_output=True
            )
            if result.returncode != 0:
                stderr = result.stderr.decode('utf-8', errors='replace') if result.stderr else ""
                self.last_error = stderr or "Unknown Docker build error"
                print(f"Build failed: {self.last_error}")
                return False
            return True
        except Exception as e:
            self.last_error = str(e)
            print(f"Build error: {e}")
            return False

    def up(self) -> bool:
        try:
            # Use binary mode (text=False) to avoid UnicodeDecodeError on Windows
            result = subprocess.run(
                ["docker-compose", "up", "-d"], 
                cwd=self.project_root, 
                capture_output=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def is_available(self) -> (bool, str):
        try:
            if self.client is None:
                self.client = docker.from_env()
            self.client.ping()
            return True, "Docker is available"
        except Exception as e:
            return False, str(e)

    def down(self):
        # Use binary mode (text=False) to avoid UnicodeDecodeError on Windows
        subprocess.run(["docker-compose", "down"], cwd=self.project_root, capture_output=True)

    def run_tests(self, service_name: str, test_type: TaskTestType) -> TaskTestResult:
        # Resolve container ID via compose for robustness
        try:
            ps = subprocess.run([
                "docker-compose", "ps", "-q", service_name
            ], cwd=self.project_root, capture_output=True)
            container_id = ps.stdout.decode('utf-8', errors='replace').strip()
        except Exception:
            container_id = ""
        
        cmd = ""
        if test_type == TaskTestType.UNIT:
            cmd = "pytest tests/unit"
        elif test_type == TaskTestType.INTEGRATION:
            cmd = "pytest tests/integration"
        elif test_type == TaskTestType.ML_QA:
            cmd = "python scripts/run_ml_qa.py"
            
        try:
            target = container_id if container_id else f"{os.path.basename(self.project_root)}_{service_name}_1"
            container = self.client.containers.get(target)
            exec_result = container.exec_run(cmd)
            
            passed = exec_result.exit_code == 0
            # exec_run returns bytes, so we decode safely
            output = exec_result.output.decode("utf-8", errors="replace")
            
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
            # Use binary mode (text=False) to avoid UnicodeDecodeError on Windows
            result = subprocess.run(
                ["docker-compose", "logs", service_name],
                cwd=self.project_root,
                capture_output=True
            )
            return result.stdout.decode('utf-8', errors='replace') if result.stdout else ""
        except Exception:
            return ""
