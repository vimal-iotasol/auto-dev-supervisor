from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class AppType(str, Enum):
    BACKEND = "backend"
    FRONTEND = "frontend"
    ML = "ml"
    AUDIO = "audio"
    OTHER = "other"

class MLMetric(BaseModel):
    name: str
    threshold: float
    operator: str = ">"  # >, <, >=, <=

class ServiceSpec(BaseModel):
    name: str
    type: AppType
    description: str
    dependencies: List[str] = []
    ml_metrics: List[MLMetric] = []
    docker_image_base: str = "python:3.11-slim"

class ProjectSpec(BaseModel):
    name: str
    version: str
    repository_url: str
    branch: str = "main"
    services: List[ServiceSpec]

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class Task(BaseModel):
    id: str
    title: str
    description: str
    service_name: str
    dependencies: List[str] = []
    status: TaskStatus = TaskStatus.PENDING
    logs: List[str] = []

class TaskTestType(str, Enum):
    UNIT = "unit"
    INTEGRATION = "integration"
    E2E = "e2e"
    ML_QA = "ml_qa"

class TaskTestResult(BaseModel):
    type: TaskTestType
    passed: bool
    details: str
    metrics: Dict[str, float] = {}
