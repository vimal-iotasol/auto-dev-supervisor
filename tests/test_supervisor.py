import pytest
from unittest.mock import MagicMock, patch
from auto_dev_supervisor.core.supervisor import Supervisor
from auto_dev_supervisor.core.planner import Planner
from auto_dev_supervisor.infra.opendevin import MockOpenDevinClient
from auto_dev_supervisor.infra.docker import DockerManager
from auto_dev_supervisor.infra.git import GitManager
from auto_dev_supervisor.domain.qa import QAManager
from auto_dev_supervisor.domain.model import TaskTestResult, TaskTestType

def test_full_pipeline_simulation(tmp_path):
    # Setup
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text("""
name: "Sim App"
version: "1.0"
repository_url: "http://repo"
services:
  - name: "svc"
    type: "backend"
    description: "desc"
    """)
    
    planner = Planner()
    opendevin = MockOpenDevinClient()
    
    # Mock DockerManager to always succeed
    docker_manager = MagicMock(spec=DockerManager)
    docker_manager.build_services.return_value = True
    docker_manager.run_tests.return_value = TaskTestResult(type=TaskTestType.UNIT, passed=True, details="Pass")
    
    # Mock GitManager
    git_manager = MagicMock(spec=GitManager)
    git_manager.commit_changes.return_value = True
    git_manager.push_changes.return_value = True
    
    qa_manager = QAManager()
    
    supervisor = Supervisor(
        planner=planner,
        opendevin=opendevin,
        docker_manager=docker_manager,
        git_manager=git_manager,
        qa_manager=qa_manager
    )
    
    # Run
    supervisor.run(str(spec_path))
    
    # Verify
    # 1. Tasks should be generated
    # 2. Docker build called
    assert docker_manager.generate_compose_file.called
    
    # 3. Loop should run for each task (4 tasks: setup, scaffold, implement, test)
    # build_services called at least once per task that isn't setup-repo (setup-repo is system, might skip build loop logic depending on impl, 
    # but our planner assigns service_name="system" to setup-repo, and our logic runs loop for all tasks)
    # Actually, setup-repo has service_name="system", so it will run through the loop.
    assert docker_manager.build_services.call_count >= 1
    
    # 4. Commit called
    assert git_manager.commit_changes.call_count >= 1
