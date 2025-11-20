import pytest
from unittest.mock import MagicMock, patch
from auto_dev_supervisor.infra.git import GitManager
from auto_dev_supervisor.domain.model import Task, TaskTestResult, TaskTestType

@pytest.fixture
def mock_git_repo():
    with patch("git.Repo") as mock:
        yield mock

def test_commit_changes_success(mock_git_repo):
    manager = GitManager("/tmp/project", "http://repo")
    manager.repo.is_dirty.return_value = True
    
    task = Task(id="task-1", title="Test Task", description="desc", service_name="svc")
    results = [TaskTestResult(type=TaskTestType.UNIT, passed=True, details="pass")]
    
    success = manager.commit_changes(task, results)
    
    assert success
    manager.repo.git.add.assert_called_with(A=True)
    manager.repo.index.commit.assert_called()
    
    # Check commit message content
    args, _ = manager.repo.index.commit.call_args
    message = args[0]
    assert "feat: Complete task task-1" in message
    assert "Test summary:" in message

def test_commit_changes_no_changes(mock_git_repo):
    manager = GitManager("/tmp/project", "http://repo")
    manager.repo.is_dirty.return_value = False
    
    task = Task(id="task-1", title="Test Task", description="desc", service_name="svc")
    success = manager.commit_changes(task, [])
    
    assert success
    manager.repo.index.commit.assert_not_called()
