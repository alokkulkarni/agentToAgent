"""
Database operations for workflow persistence
"""
import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import os

from models import (
    WorkflowRecord, StepRecord, WorkflowStatus, StepStatus
)


class WorkflowDatabase:
    """SQLite database for workflow persistence"""
    
    def __init__(self, db_path: str = "workflows.db"):
        self.db_path = db_path
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """Get database connection with automatic commit/rollback"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def init_database(self):
        """Initialize database schema"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Workflows table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_id TEXT PRIMARY KEY,
                    task_description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_steps INTEGER DEFAULT 0,
                    completed_steps INTEGER DEFAULT 0,
                    current_step INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    error_message TEXT,
                    workflow_context TEXT,
                    workflow_state TEXT,
                    execution_plan TEXT,
                    results TEXT
                )
            """)
            
            # Steps table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS steps (
                    step_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    step_number INTEGER NOT NULL,
                    capability TEXT NOT NULL,
                    agent TEXT,
                    agent_endpoint TEXT,
                    status TEXT NOT NULL,
                    parameters TEXT,
                    result TEXT,
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    dependencies TEXT,
                    execution_time_ms REAL,
                    FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id)
                )
            """)
            
            # Create indexes
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_workflows_status 
                ON workflows(status)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_steps_workflow 
                ON steps(workflow_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_steps_status 
                ON steps(status)
            """)
        
        # Initialize interaction tables
        self.init_interaction_tables()
    
    def save_workflow(self, workflow: WorkflowRecord):
        """Save or update workflow record"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO workflows 
                (workflow_id, task_description, status, total_steps, completed_steps, current_step,
                 created_at, updated_at, started_at, completed_at, error_message,
                 workflow_context, workflow_state, execution_plan, results)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                workflow.workflow_id,
                workflow.task_description,
                workflow.status.value if isinstance(workflow.status, WorkflowStatus) else workflow.status,
                workflow.total_steps,
                workflow.completed_steps,
                workflow.current_step,
                workflow.created_at.isoformat(),
                workflow.updated_at.isoformat(),
                workflow.started_at.isoformat() if workflow.started_at else None,
                workflow.completed_at.isoformat() if workflow.completed_at else None,
                workflow.error_message,
                json.dumps(workflow.workflow_context),
                json.dumps(workflow.workflow_state),
                json.dumps(workflow.execution_plan),
                json.dumps(workflow.results)
            ))
    
    def update_workflow_state(self, workflow_id: str, state_data: Dict[str, Any]):
        """Update workflow state during execution (for pausing, etc.)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE workflows 
                SET status = ?,
                    workflow_context = ?,
                    updated_at = ?
                WHERE workflow_id = ?
            """, (
                state_data.get("status", "running"),
                json.dumps(state_data),
                datetime.utcnow().isoformat(),
                workflow_id
            ))
    
    def update_workflow_status(self, workflow_id: str, status: str):
        """Update workflow status"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE workflows 
                SET status = ?,
                    updated_at = ?
                WHERE workflow_id = ?
            """, (
                status,
                datetime.utcnow().isoformat(),
                workflow_id
            ))
    
    def get_workflow(self, workflow_id: str) -> Optional[WorkflowRecord]:
        """Get workflow by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM workflows WHERE workflow_id = ?
            """, (workflow_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            # Handle old rows that might not have current_step or workflow_state
            current_step = row['current_step'] if 'current_step' in row.keys() else 0
            workflow_state = row['workflow_state'] if 'workflow_state' in row.keys() else None
            
            return WorkflowRecord(
                workflow_id=row['workflow_id'],
                task_description=row['task_description'],
                status=WorkflowStatus(row['status']),
                total_steps=row['total_steps'],
                completed_steps=row['completed_steps'],
                current_step=current_step,
                created_at=datetime.fromisoformat(row['created_at']),
                updated_at=datetime.fromisoformat(row['updated_at']),
                started_at=datetime.fromisoformat(row['started_at']) if row['started_at'] else None,
                completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
                error_message=row['error_message'],
                workflow_context=json.loads(row['workflow_context']) if row['workflow_context'] else {},
                workflow_state=json.loads(workflow_state) if workflow_state else {},
                execution_plan=json.loads(row['execution_plan']) if row['execution_plan'] else {},
                results=json.loads(row['results']) if row['results'] else []
            )
    
    def save_step(self, step: StepRecord):
        """Save or update step record"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO steps
                (step_id, workflow_id, step_number, capability, agent, agent_endpoint,
                 status, parameters, result, error_message, retry_count, max_retries,
                 created_at, updated_at, started_at, completed_at, dependencies, execution_time_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                step.step_id,
                step.workflow_id,
                step.step_number,
                step.capability,
                step.agent,
                step.agent_endpoint,
                step.status.value,
                json.dumps(step.parameters),
                json.dumps(step.result) if step.result else None,
                step.error_message,
                step.retry_count,
                step.max_retries,
                step.created_at.isoformat(),
                step.updated_at.isoformat(),
                step.started_at.isoformat() if step.started_at else None,
                step.completed_at.isoformat() if step.completed_at else None,
                json.dumps(step.dependencies),
                step.execution_time_ms
            ))
    
    def get_step(self, step_id: str) -> Optional[StepRecord]:
        """Get step by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM steps WHERE step_id = ?", (step_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return StepRecord(
                step_id=row['step_id'],
                workflow_id=row['workflow_id'],
                step_number=row['step_number'],
                capability=row['capability'],
                agent=row['agent'],
                agent_endpoint=row['agent_endpoint'],
                status=StepStatus(row['status']),
                parameters=json.loads(row['parameters']) if row['parameters'] else {},
                result=json.loads(row['result']) if row['result'] else None,
                error_message=row['error_message'],
                retry_count=row['retry_count'],
                max_retries=row['max_retries'],
                created_at=datetime.fromisoformat(row['created_at']),
                updated_at=datetime.fromisoformat(row['updated_at']),
                started_at=datetime.fromisoformat(row['started_at']) if row['started_at'] else None,
                completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
                dependencies=json.loads(row['dependencies']) if row['dependencies'] else [],
                execution_time_ms=row['execution_time_ms']
            )
    
    def get_workflow_steps(self, workflow_id: str) -> List[StepRecord]:
        """Get all steps for a workflow"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM steps 
                WHERE workflow_id = ? 
                ORDER BY step_number
            """, (workflow_id,))
            
            steps = []
            for row in cursor.fetchall():
                steps.append(StepRecord(
                    step_id=row['step_id'],
                    workflow_id=row['workflow_id'],
                    step_number=row['step_number'],
                    capability=row['capability'],
                    agent=row['agent'],
                    agent_endpoint=row['agent_endpoint'],
                    status=StepStatus(row['status']),
                    parameters=json.loads(row['parameters']) if row['parameters'] else {},
                    result=json.loads(row['result']) if row['result'] else None,
                    error_message=row['error_message'],
                    retry_count=row['retry_count'],
                    max_retries=row['max_retries'],
                    created_at=datetime.fromisoformat(row['created_at']),
                    updated_at=datetime.fromisoformat(row['updated_at']),
                    started_at=datetime.fromisoformat(row['started_at']) if row['started_at'] else None,
                    completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
                    dependencies=json.loads(row['dependencies']) if row['dependencies'] else [],
                    execution_time_ms=row['execution_time_ms']
                ))
            
            return steps
    
    def list_workflows(self, status: Optional[WorkflowStatus] = None, limit: int = 100) -> List[WorkflowRecord]:
        """List workflows with optional status filter"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if status:
                cursor.execute("""
                    SELECT * FROM workflows 
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (status.value, limit))
            else:
                cursor.execute("""
                    SELECT * FROM workflows 
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))
            
            workflows = []
            for row in cursor.fetchall():
                workflows.append(WorkflowRecord(
                    workflow_id=row['workflow_id'],
                    task_description=row['task_description'],
                    status=WorkflowStatus(row['status']),
                    total_steps=row['total_steps'],
                    completed_steps=row['completed_steps'],
                    created_at=datetime.fromisoformat(row['created_at']),
                    updated_at=datetime.fromisoformat(row['updated_at']),
                    started_at=datetime.fromisoformat(row['started_at']) if row['started_at'] else None,
                    completed_at=datetime.fromisoformat(row['completed_at']) if row['completed_at'] else None,
                    error_message=row['error_message'],
                    workflow_context=json.loads(row['workflow_context']) if row['workflow_context'] else {},
                    execution_plan=json.loads(row['execution_plan']) if row['execution_plan'] else {},
                    results=json.loads(row['results']) if row['results'] else []
                ))
            
            return workflows


# ============================================================================
# INTERACTIVE WORKFLOW DATABASE OPERATIONS
# ============================================================================

    def init_interaction_tables(self):
        """Initialize tables for interactive workflows"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Conversation messages table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    message_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    role TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    requires_response INTEGER DEFAULT 0,
                    parent_message_id TEXT,
                    FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id)
                )
            """)
            
            # Interaction requests table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS interaction_requests (
                    request_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    timeout_at TEXT,
                    question TEXT NOT NULL,
                    input_type TEXT NOT NULL,
                    options TEXT,
                    default_value TEXT,
                    context TEXT,
                    reasoning TEXT,
                    partial_results TEXT,
                    response TEXT,
                    response_received_at TEXT,
                    response_metadata TEXT,
                    status TEXT DEFAULT 'pending',
                    FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id)
                )
            """)
            
            # Thought trail table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS thought_trail (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    step_id TEXT,
                    agent TEXT,
                    thought_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id)
                )
            """)
            
            # Create indexes
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversation_workflow 
                ON conversation_messages(workflow_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_interaction_workflow 
                ON interaction_requests(workflow_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_thought_workflow 
                ON thought_trail(workflow_id)
            """)
    
    def save_message(self, message: 'ConversationMessage'):
        """Save conversation message"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO conversation_messages
                (message_id, workflow_id, timestamp, role, message_type, content,
                 metadata, requires_response, parent_message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                message.message_id,
                message.workflow_id,
                message.timestamp.isoformat(),
                message.role.value,
                message.message_type.value,
                message.content,
                json.dumps(message.metadata),
                1 if message.requires_response else 0,
                message.parent_message_id
            ))
    
    def get_conversation(self, workflow_id: str) -> List['ConversationMessage']:
        """Get full conversation history for workflow"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM conversation_messages 
                WHERE workflow_id = ?
                ORDER BY timestamp
            """, (workflow_id,))
            
            from models import ConversationMessage, MessageRole, MessageType
            messages = []
            for row in cursor.fetchall():
                messages.append(ConversationMessage(
                    message_id=row['message_id'],
                    workflow_id=row['workflow_id'],
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    role=MessageRole(row['role']),
                    message_type=MessageType(row['message_type']),
                    content=row['content'],
                    metadata=json.loads(row['metadata']) if row['metadata'] else {},
                    requires_response=bool(row['requires_response']),
                    parent_message_id=row['parent_message_id']
                ))
            
            return messages
    
    def save_interaction_request(self, request: 'InteractionRequest'):
        """Save interaction request"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO interaction_requests
                (request_id, workflow_id, step_id, agent_name, created_at, timeout_at,
                 question, input_type, options, default_value, context, reasoning,
                 partial_results, response, response_received_at, response_metadata, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                request.request_id,
                request.workflow_id,
                request.step_id,
                request.agent_name,
                request.created_at.isoformat(),
                request.timeout_at.isoformat() if request.timeout_at else None,
                request.question,
                request.input_type.value,
                json.dumps(request.options) if request.options else None,
                json.dumps(request.default_value) if request.default_value else None,
                json.dumps(request.context),
                request.reasoning,
                json.dumps(request.partial_results) if request.partial_results else None,
                json.dumps(request.response) if request.response else None,
                request.response_received_at.isoformat() if request.response_received_at else None,
                json.dumps(request.response_metadata),
                request.status
            ))
    
    def get_interaction_request(self, request_id: str) -> Optional['InteractionRequest']:
        """Get interaction request by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM interaction_requests WHERE request_id = ?
            """, (request_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            from models import InteractionRequest, InputType
            return InteractionRequest(
                request_id=row['request_id'],
                workflow_id=row['workflow_id'],
                step_id=row['step_id'],
                agent_name=row['agent_name'],
                created_at=datetime.fromisoformat(row['created_at']),
                timeout_at=datetime.fromisoformat(row['timeout_at']) if row['timeout_at'] else None,
                question=row['question'],
                input_type=InputType(row['input_type']),
                options=json.loads(row['options']) if row['options'] else None,
                default_value=json.loads(row['default_value']) if row['default_value'] else None,
                context=json.loads(row['context']) if row['context'] else {},
                reasoning=row['reasoning'],
                partial_results=json.loads(row['partial_results']) if row['partial_results'] else None,
                response=json.loads(row['response']) if row['response'] else None,
                response_received_at=datetime.fromisoformat(row['response_received_at']) if row['response_received_at'] else None,
                response_metadata=json.loads(row['response_metadata']) if row['response_metadata'] else {},
                status=row['status']
            )
    
    def get_pending_interaction(self, workflow_id: str) -> Optional['InteractionRequest']:
        """Get pending interaction request for workflow"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM interaction_requests 
                WHERE workflow_id = ? AND status = 'pending'
                ORDER BY created_at DESC
                LIMIT 1
            """, (workflow_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            from models import InteractionRequest, InputType
            return InteractionRequest(
                request_id=row['request_id'],
                workflow_id=row['workflow_id'],
                step_id=row['step_id'],
                agent_name=row['agent_name'],
                created_at=datetime.fromisoformat(row['created_at']),
                timeout_at=datetime.fromisoformat(row['timeout_at']) if row['timeout_at'] else None,
                question=row['question'],
                input_type=InputType(row['input_type']),
                options=json.loads(row['options']) if row['options'] else None,
                default_value=json.loads(row['default_value']) if row['default_value'] else None,
                context=json.loads(row['context']) if row['context'] else {},
                reasoning=row['reasoning'],
                partial_results=json.loads(row['partial_results']) if row['partial_results'] else None,
                response=json.loads(row['response']) if row['response'] else None,
                response_received_at=datetime.fromisoformat(row['response_received_at']) if row['response_received_at'] else None,
                response_metadata=json.loads(row['response_metadata']) if row['response_metadata'] else {},
                status=row['status']
            )
    
    def get_answered_interaction(self, workflow_id: str) -> Optional['InteractionRequest']:
        """Get answered (but not completed) interaction request for workflow"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM interaction_requests 
                WHERE workflow_id = ? AND status = 'answered'
                ORDER BY created_at DESC
                LIMIT 1
            """, (workflow_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            from models import InteractionRequest, InputType
            return InteractionRequest(
                request_id=row['request_id'],
                workflow_id=row['workflow_id'],
                step_id=row['step_id'],
                agent_name=row['agent_name'],
                created_at=datetime.fromisoformat(row['created_at']),
                timeout_at=datetime.fromisoformat(row['timeout_at']) if row['timeout_at'] else None,
                question=row['question'],
                input_type=InputType(row['input_type']),
                options=json.loads(row['options']) if row['options'] else None,
                default_value=json.loads(row['default_value']) if row['default_value'] else None,
                context=json.loads(row['context']) if row['context'] else {},
                reasoning=row['reasoning'],
                partial_results=json.loads(row['partial_results']) if row['partial_results'] else None,
                response=json.loads(row['response']) if row['response'] else None,
                response_received_at=datetime.fromisoformat(row['response_received_at']) if row['response_received_at'] else None,
                response_metadata=json.loads(row['response_metadata']) if row['response_metadata'] else {},
                status=row['status']
            )
    
    def get_all_interaction_requests(self) -> List[Dict]:
        """Get all interaction requests for debugging"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT request_id, workflow_id, status, question 
                FROM interaction_requests 
                ORDER BY created_at DESC 
                LIMIT 20
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def save_thought(self, workflow_id: str, thought: 'ThoughtTrailEntry'):
        """Save thought trail entry"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO thought_trail
                (workflow_id, timestamp, step_id, agent, thought_type, content, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                workflow_id,
                thought.timestamp.isoformat(),
                thought.step_id,
                thought.agent,
                thought.thought_type,
                thought.content,
                json.dumps(thought.metadata)
            ))
    
    def get_thought_trail(self, workflow_id: str) -> List['ThoughtTrailEntry']:
        """Get thought trail for workflow"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM thought_trail 
                WHERE workflow_id = ?
                ORDER BY timestamp
            """, (workflow_id,))
            
            from models import ThoughtTrailEntry
            thoughts = []
            for row in cursor.fetchall():
                thoughts.append(ThoughtTrailEntry(
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    step_id=row['step_id'],
                    agent=row['agent'],
                    thought_type=row['thought_type'],
                    content=row['content'],
                    metadata=json.loads(row['metadata']) if row['metadata'] else {}
                ))
            
            return thoughts
    
    def get_workflow_context(self, workflow_id: str) -> Optional['WorkflowContext']:
        """Get complete workflow context"""
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            return None
        
        from models import WorkflowContext
        context = WorkflowContext(
            workflow_id=workflow_id,
            original_task=workflow.task_description,
            current_step=workflow.completed_steps + 1 if workflow.completed_steps < workflow.total_steps else None,
            conversation=self.get_conversation(workflow_id),
            thought_trail=self.get_thought_trail(workflow_id),
            step_results=workflow.workflow_context.get('step_results', {}),
            pending_interaction=self.get_pending_interaction(workflow_id),
            variables=workflow.workflow_context.get('variables', {})
        )
        
        return context

