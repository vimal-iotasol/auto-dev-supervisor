import pytest
from unittest.mock import MagicMock, patch
from auto_dev_supervisor.infra.llm import GenAIOpenDevinClient
from auto_dev_supervisor.domain.model import Task

@pytest.fixture
def mock_openai():
    with patch("auto_dev_supervisor.infra.llm.OpenAI") as mock:
        yield mock

def test_execute_task_success(mock_openai, tmp_path):
    # Setup
    client = GenAIOpenDevinClient(api_key="fake-key")
    task = Task(id="t1", title="Test Task", description="Desc", service_name="svc")
    
    # Mock response
    mock_response = MagicMock()
    mock_response.choices[0].message.content = """
Here is the code:
file.py
```python
print("Hello")
```
    """
    client.client.chat.completions.create.return_value = mock_response
    
    # Execute
    with patch("auto_dev_supervisor.infra.llm.open", new_callable=MagicMock) as mock_open:
        # We need to mock os.makedirs too
        with patch("os.makedirs"):
            # And we need to mock the file handle returned by open
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file
            
            result = client.execute_task(task, "context")
            
            # Verify
            assert "Here is the code" in result
            mock_open.assert_called_with("file.py", "w")
            mock_file.write.assert_called_with('print("Hello")')

def test_fix_issues_success(mock_openai):
    client = GenAIOpenDevinClient(api_key="fake-key")
    task = Task(id="t1", title="Test Task", description="Desc", service_name="svc")
    
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Fixed code"
    client.client.chat.completions.create.return_value = mock_response
    
    result = client.fix_issues(task, "error log")
    
    assert result == "Fixed code"
    # Check that the prompt contains error info
    call_args = client.client.chat.completions.create.call_args
    assert "error log" in call_args.kwargs['messages'][1]['content']
