"""
Database models for workflow persistence
"""
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class WorkflowStatus(str, Enum):
    """Workflow execution status"""
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class StepStatus(str, Enum):
    """Step execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"


class WorkflowRecord(BaseModel):
    """Workflow execution record"""
    workflow_id: str
    task_description: str
    status: WorkflowStatus
    total_steps: int = 0
    completed_steps: int = 0
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    workflow_context: Dict[str, Any] = Field(default_factory=dict)
    execution_plan: Dict[str, Any] = Field(default_factory=dict)
    results: List[Dict[str, Any]] = Field(default_factory=list)


class StepRecord(BaseModel):
    """Workflow step execution record"""
    step_id: str
    workflow_id: str
    step_number: int
    capability: str
    agent: Optional[str] = None
    agent_endpoint: Optional[str] = None
    status: StepStatus
    parameters: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    dependencies: List[str] = Field(default_factory=list)  # Step IDs this step depends on
    execution_time_ms: Optional[float] = None


class RetryPolicy(BaseModel):
    """Retry configuration for steps"""
    max_retries: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retriable_errors: List[str] = Field(default_factory=lambda: [
        "timeout", "connection", "network", "temporary", "unavailable", "503", "502", "500"
    ])


class WorkflowConfig(BaseModel):
    """Workflow execution configuration"""
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    enable_parallel_execution: bool = True
    max_parallel_steps: int = 5
    step_timeout_seconds: int = 300
    workflow_timeout_seconds: int = 3600
    enable_persistence: bool = True
    auto_resume: bool = True
