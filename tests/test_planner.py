import pytest
import os
from auto_dev_supervisor.core.planner import Planner
from auto_dev_supervisor.domain.model import ProjectSpec, Task, AppType

@pytest.fixture
def sample_spec_path(tmp_path):
    spec_content = """
name: "Test App"
version: "0.1.0"
repository_url: "git@github.com:test/app.git"
branch: "main"
services:
  - name: "backend"
    type: "backend"
    description: "A backend service"
    """
    p = tmp_path / "test_spec.yaml"
    p.write_text(spec_content)
    return str(p)

def test_parse_spec(sample_spec_path):
    planner = Planner()
    spec = planner.parse_spec(sample_spec_path)
    
    assert spec.name == "Test App"
    assert spec.version == "0.1.0"
    assert len(spec.services) == 1
    assert spec.services[0].name == "backend"
    assert spec.services[0].type == AppType.BACKEND

def test_create_initial_tasks(sample_spec_path):
    planner = Planner()
    spec = planner.parse_spec(sample_spec_path)
    tasks = planner.create_initial_tasks(spec)
    
    # 1 setup + 3 per service (scaffold, implement, test) = 4
    assert len(tasks) == 4
    
    task_ids = [t.id for t in tasks]
    assert "setup-repo" in task_ids
    assert "scaffold-backend" in task_ids
    assert "implement-backend" in task_ids
    assert "test-backend" in task_ids
    
    # Check dependencies
    implement_task = next(t for t in tasks if t.id == "implement-backend")
    assert "scaffold-backend" in implement_task.dependencies

def test_get_next_pending_task(sample_spec_path):
    planner = Planner()
    spec = planner.parse_spec(sample_spec_path)
    tasks = planner.create_initial_tasks(spec)
    
    # First task should be setup-repo (no deps)
    next_task = planner.get_next_pending_task(tasks)
    assert next_task.id == "setup-repo"
