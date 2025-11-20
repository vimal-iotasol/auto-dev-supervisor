from abc import ABC, abstractmethod
from typing import List
from auto_dev_supervisor.domain.model import Task, TaskTestResult, TaskTestType

class OpenDevinClient(ABC):
    @abstractmethod
    def execute_task(self, task: Task, context: str) -> str:
        """
        Ask OpenDevin to execute a task.
        Returns a summary of what was done.
        """
        pass

    @abstractmethod
    def fix_issues(self, task: Task, errors: str) -> str:
        """
        Ask OpenDevin to fix issues based on error logs.
        """
        pass

class MockOpenDevinClient(OpenDevinClient):
    def execute_task(self, task: Task, context: str) -> str:
        print(f"[MockOpenDevin] Executing task: {task.title}")
        print(f"[MockOpenDevin] Context: {context[:50]}...")
        return f"Executed {task.id} successfully."

    def fix_issues(self, task: Task, errors: str) -> str:
        print(f"[MockOpenDevin] Fixing issues for: {task.title}")
        print(f"[MockOpenDevin] Errors: {errors[:50]}...")
        return f"Fixed issues for {task.id}."
