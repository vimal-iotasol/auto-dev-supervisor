import pytest
from unittest.mock import MagicMock, patch
from auto_dev_supervisor.infra.docker import DockerManager
from auto_dev_supervisor.domain.model import ProjectSpec, ServiceSpec, AppType, TaskTestType

@pytest.fixture
def mock_docker_client():
    with patch("docker.from_env") as mock:
        yield mock

def test_generate_compose_file(tmp_path):
    manager = DockerManager(str(tmp_path))
    spec = ProjectSpec(
        name="test-project",
        version="0.1.0",
        repository_url="http://repo",
        services=[
            ServiceSpec(name="api", type=AppType.BACKEND, description="desc")
        ]
    )
    
    manager.generate_compose_file(spec)
    
    compose_path = tmp_path / "docker-compose.yml"
    assert compose_path.exists()
    content = compose_path.read_text()
    assert "services:" in content
    assert "api:" in content
    assert "image: test-project-api:0.1.0" in content

def test_run_tests_success(mock_docker_client):
    manager = DockerManager("/tmp/project")
    
    # Mock container execution
    mock_container = MagicMock()
    mock_container.exec_run.return_value = MagicMock(exit_code=0, output=b"Tests passed")
    mock_docker_client.return_value.containers.get.return_value = mock_container
    
    result = manager.run_tests("api", TaskTestType.UNIT)
    
    assert result.passed
    assert result.type == TaskTestType.UNIT
    assert "Tests passed" in result.details

def test_run_tests_failure(mock_docker_client):
    manager = DockerManager("/tmp/project")
    
    mock_container = MagicMock()
    mock_container.exec_run.return_value = MagicMock(exit_code=1, output=b"Tests failed")
    mock_docker_client.return_value.containers.get.return_value = mock_container
    
    result = manager.run_tests("api", TaskTestType.UNIT)
    
    assert not result.passed
    assert "Tests failed" in result.details
