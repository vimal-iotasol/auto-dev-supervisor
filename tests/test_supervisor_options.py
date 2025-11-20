import pytest
from unittest.mock import MagicMock
from auto_dev_supervisor.core.supervisor import Supervisor
from auto_dev_supervisor.core.planner import Planner
from auto_dev_supervisor.infra.opendevin import MockOpenDevinClient
from auto_dev_supervisor.infra.docker import DockerManager
from auto_dev_supervisor.infra.git import GitManager
from auto_dev_supervisor.domain.qa import QAManager
from auto_dev_supervisor.domain.model import TaskTestResult, TaskTestType

def test_skip_git_option(tmp_path):
    # Setup mocks
    planner = MagicMock(spec=Planner)
    # Return a single task
    task = MagicMock()
    task.status = "pending"
    task.dependencies = []
    planner.create_initial_tasks.return_value = [task]
    planner.get_next_pending_task.side_effect = [task, None]
    
    opendevin = MockOpenDevinClient()
    
    docker_manager = MagicMock(spec=DockerManager)
    docker_manager.build_services.return_value = True
    docker_manager.run_tests.return_value = TaskTestResult(type=TaskTestType.UNIT, passed=True, details="Pass")
    
    git_manager = MagicMock(spec=GitManager)
    
    qa_manager = QAManager()
    
    # Initialize Supervisor with skip_git=True
    supervisor = Supervisor(
        planner=planner,
        opendevin=opendevin,
        docker_manager=docker_manager,
        git_manager=git_manager,
        qa_manager=qa_manager,
        skip_git=True
    )
    
    # Run (mocking spec parsing)
    spec = MagicMock()
    spec.services = []
    planner.parse_spec.return_value = spec
    
    supervisor.run("spec.yaml")
    
    # Verify git manager was NOT called
    git_manager.commit_changes.assert_not_called()
    git_manager.push_changes.assert_not_called()

def test_no_skip_git_option(tmp_path):
    # Setup mocks (same as above but skip_git=False)
    planner = MagicMock(spec=Planner)
    task = MagicMock()
    task.status = "pending"
    task.dependencies = []
    planner.create_initial_tasks.return_value = [task]
    planner.get_next_pending_task.side_effect = [task, None]
    
    opendevin = MockOpenDevinClient()
    
    docker_manager = MagicMock(spec=DockerManager)
    docker_manager.build_services.return_value = True
    docker_manager.run_tests.return_value = TaskTestResult(type=TaskTestType.UNIT, passed=True, details="Pass")
    
    git_manager = MagicMock(spec=GitManager)
    
    qa_manager = QAManager()
    
    supervisor = Supervisor(
        planner=planner,
        opendevin=opendevin,
        docker_manager=docker_manager,
        git_manager=git_manager,
        qa_manager=qa_manager,
        skip_git=False
    )
    
    spec = MagicMock()
    spec.services = []
    planner.parse_spec.return_value = spec
    
    supervisor.run("spec.yaml")
    
    # Verify git manager WAS called
    git_manager.commit_changes.assert_called()
    git_manager.push_changes.assert_called()
