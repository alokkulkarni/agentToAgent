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
    WAITING_FOR_INPUT = "waiting_for_input"  # NEW: Paused for user input
    INPUT_RECEIVED = "input_received"  # NEW: User responded, ready to resume
    INPUT_TIMEOUT = "input_timeout"  # NEW: User didn't respond in time


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
    current_step: int = 0
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    workflow_context: Dict[str, Any] = Field(default_factory=dict)
    workflow_state: Dict[str, Any] = Field(default_factory=dict)  # Serialized state for resume
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


# ============================================================================
# INTERACTIVE WORKFLOW MODELS
# ============================================================================

class MessageRole(str, Enum):
    """Role in conversation"""
    USER = "user"
    ORCHESTRATOR = "orchestrator"
    AGENT = "agent"
    SYSTEM = "system"


class MessageType(str, Enum):
    """Type of message"""
    TASK = "task"
    THOUGHT = "thought"
    MESSAGE = "message"
    QUESTION = "question"
    RESPONSE = "response"
    ERROR = "error"
    STATUS = "status"


class InputType(str, Enum):
    """Type of user input requested"""
    TEXT = "text"
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    CONFIRMATION = "confirmation"
    STRUCTURED_DATA = "structured_data"
    FILE_UPLOAD = "file_upload"


class ConversationMessage(BaseModel):
    """Single message in conversation thread"""
    message_id: str = Field(default_factory=lambda: f"msg_{int(datetime.now().timestamp() * 1000)}")
    workflow_id: str
    timestamp: datetime
    role: MessageRole
    message_type: MessageType
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    requires_response: bool = False
    parent_message_id: Optional[str] = None  # For threading


class InteractionRequest(BaseModel):
    """Request for user input mid-workflow"""
    request_id: str = Field(default_factory=lambda: f"req_{int(datetime.now().timestamp() * 1000)}")
    workflow_id: str
    step_id: str
    agent_name: str
    created_at: datetime
    timeout_at: Optional[datetime] = None
    
    # The question/prompt
    question: str
    input_type: InputType
    options: Optional[List[str]] = None
    default_value: Optional[Any] = None
    
    # Context
    context: Dict[str, Any] = Field(default_factory=dict)
    reasoning: Optional[str] = None
    partial_results: Optional[Dict[str, Any]] = None
    
    # Response
    response: Optional[Any] = None
    response_received_at: Optional[datetime] = None
    response_metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Status
    status: str = "pending"  # pending, answered, timeout, cancelled


class ThoughtTrailEntry(BaseModel):
    """Single entry in agent's thought process"""
    timestamp: datetime
    step_id: Optional[str] = None
    agent: Optional[str] = None
    thought_type: str  # reasoning, decision, observation, question
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkflowContext(BaseModel):
    """Complete workflow execution context"""
    workflow_id: str
    original_task: str
    current_step: Optional[int] = None
    
    # Conversation thread
    conversation: List[ConversationMessage] = Field(default_factory=list)
    
    # Thought trail
    thought_trail: List[ThoughtTrailEntry] = Field(default_factory=list)
    
    # Results from completed steps
    step_results: Dict[str, Any] = Field(default_factory=dict)
    
    # Pending interaction
    pending_interaction: Optional[InteractionRequest] = None
    
    # Variables accumulated during execution
    variables: Dict[str, Any] = Field(default_factory=dict)
    
    def add_message(self, role: MessageRole, message_type: MessageType, 
                    content: str, **metadata):
        """Add message to conversation"""
        msg = ConversationMessage(
            workflow_id=self.workflow_id,
            timestamp=datetime.now(),
            role=role,
            message_type=message_type,
            content=content,
            metadata=metadata
        )
        self.conversation.append(msg)
        return msg
    
    def add_thought(self, thought_type: str, content: str, 
                    agent: Optional[str] = None, **metadata):
        """Add entry to thought trail"""
        thought = ThoughtTrailEntry(
            timestamp=datetime.now(),
            step_id=f"step_{self.current_step}" if self.current_step else None,
            agent=agent,
            thought_type=thought_type,
            content=content,
            metadata=metadata
        )
        self.thought_trail.append(thought)
        return thought
    
    def get_conversation_history(self, limit: Optional[int] = None) -> List[Dict]:
        """Get formatted conversation history"""
        messages = self.conversation[-limit:] if limit else self.conversation
        return [
            {
                "role": msg.role,
                "type": msg.message_type,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat(),
                **msg.metadata
            }
            for msg in messages
        ]
    
    def get_thought_summary(self) -> List[str]:
        """Get summary of thought process"""
        return [
            f"[{entry.thought_type}] {entry.content}"
            for entry in self.thought_trail
        ]


class InteractionResponse(BaseModel):
    """User's response to interaction request"""
    request_id: str
    workflow_id: str
    response: Any
    additional_context: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
