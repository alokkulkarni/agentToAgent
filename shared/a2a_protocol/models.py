"""
Shared A2A Protocol Models
Used by all services for consistent communication
"""
from enum import Enum
from typing import Any, Dict, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


class MessageType(str, Enum):
    """A2A Message Types"""
    REGISTER = "register"
    UNREGISTER = "unregister"
    DISCOVER = "discover"
    TASK_REQUEST = "task_request"
    TASK_RESPONSE = "task_response"
    TASK_STATUS = "task_status"
    HEARTBEAT = "heartbeat"
    EVENT = "event"
    ERROR = "error"


class AgentRole(str, Enum):
    """Agent Roles"""
    ORCHESTRATOR = "orchestrator"
    SPECIALIZED = "specialized"
    WORKER = "worker"
    OBSERVER = "observer"


class TaskStatus(str, Enum):
    """Task Execution Status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentCapability(BaseModel):
    """Agent Capability Definition"""
    name: str
    description: str
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    version: str = "1.0.0"
    requires_llm: bool = False


class AgentMetadata(BaseModel):
    """Agent Metadata for Registration"""
    agent_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    role: AgentRole
    capabilities: List[AgentCapability] = []
    status: str = "idle"
    version: str = "1.0.0"
    has_llm: bool = False
    endpoint: str = ""  # HTTP endpoint for the agent
    created_at: datetime = Field(default_factory=datetime.utcnow)


class A2AMessage(BaseModel):
    """A2A Protocol Message"""
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    message_type: MessageType
    sender_id: str
    receiver_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    correlation_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskRequest(BaseModel):
    """Task Request"""
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    capability: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=5, ge=1, le=10)
    timeout_seconds: Optional[int] = None
    context: Dict[str, Any] = Field(default_factory=dict)


class TaskResponse(BaseModel):
    """Task Response"""
    task_id: str
    status: TaskStatus
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: Optional[float] = None
    agent_id: str
    llm_usage: Optional[Dict[str, int]] = None


class RegistrationRequest(BaseModel):
    """Agent Registration Request"""
    metadata: AgentMetadata


class RegistrationResponse(BaseModel):
    """Agent Registration Response"""
    success: bool
    agent_id: str
    message: str


class DiscoveryRequest(BaseModel):
    """Discovery Request"""
    capability: Optional[str] = None
    role: Optional[AgentRole] = None


class DiscoveryResponse(BaseModel):
    """Discovery Response"""
    agents: List[AgentMetadata]
