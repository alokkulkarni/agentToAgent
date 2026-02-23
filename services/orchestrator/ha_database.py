"""
ha_database.py — Pluggable workflow database backends for HA orchestrator.

Provides factory function `get_workflow_database()` that returns either:
  - The default SQLite WorkflowDatabase (single-node development)
  - PostgreSQLWorkflowDatabase (shared DB for multi-instance HA)

Environment variables:
  WORKFLOW_DB_BACKEND      sqlite | postgresql  (default: sqlite)
  DATABASE_URL             postgresql://user:pass@host:5432/dbname
                           (can also use individual PG_* vars below)
  PG_HOST                  localhost
  PG_PORT                  5432
  PG_DATABASE              orchestrator
  PG_USER                  orchestrator
  PG_PASSWORD              secret
  SQLITE_DB_PATH           /app/data/workflows.db  (overrides default path)

Usage:
    from ha_database import get_workflow_database

    # In app lifespan:
    db = get_workflow_database()
    db.init_database()          # idempotent — creates tables if not present
    db.init_interaction_tables()
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# ---------------------------------------------------------------------------
# Import the existing SQLite implementation from database.py
# ---------------------------------------------------------------------------
from database import (  # noqa: E402  (local import within service)
    WorkflowDatabase,
    WorkflowRecord,
    WorkflowStatus,
    StepRecord,
    StepStatus,
)


# ===========================================================================
# PostgreSQL backend
# ===========================================================================

class PostgreSQLWorkflowDatabase:
    """
    PostgreSQL drop-in replacement for WorkflowDatabase.

    Uses psycopg2 (synchronous) to preserve the same synchronous method
    signatures as the SQLite implementation — no async changes required in
    the callers.

    Tables created are identical in structure to the SQLite schema so that
    migrations between backends are straightforward.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        try:
            import psycopg2  # type: ignore
            import psycopg2.extras  # type: ignore
            self._psycopg2 = psycopg2
        except ImportError:
            raise RuntimeError(
                "psycopg2 is required for WORKFLOW_DB_BACKEND=postgresql. "
                "Install with: pip install psycopg2-binary>=2.9"
            )
        logger.info("PostgreSQLWorkflowDatabase initialised — %s", _redact_dsn(dsn))

    @contextmanager
    def get_connection(self):
        conn = self._psycopg2.connect(
            self._dsn,
            cursor_factory=self._psycopg2.extras.RealDictCursor,
        )
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # DDL
    # ------------------------------------------------------------------

    def init_database(self):
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_id TEXT PRIMARY KEY,
                    task_description TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    total_steps INTEGER DEFAULT 0,
                    completed_steps INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    error_message TEXT,
                    workflow_context TEXT,
                    execution_plan TEXT,
                    results TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS steps (
                    step_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL REFERENCES workflows(workflow_id),
                    step_number INTEGER NOT NULL,
                    capability TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    agent_name TEXT,
                    agent_endpoint TEXT,
                    parameters TEXT,
                    result TEXT,
                    error TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    execution_time REAL,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    requires_human_review INTEGER DEFAULT 0,
                    human_feedback TEXT
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_steps_workflow ON steps(workflow_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(status)")

    def init_interaction_tables(self):
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    message_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL REFERENCES workflows(workflow_id),
                    timestamp TEXT NOT NULL,
                    role TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    requires_response INTEGER DEFAULT 0,
                    parent_message_id TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS interaction_requests (
                    request_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL REFERENCES workflows(workflow_id),
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
                    status TEXT DEFAULT 'pending'
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS thought_trail (
                    id SERIAL PRIMARY KEY,
                    workflow_id TEXT NOT NULL REFERENCES workflows(workflow_id),
                    timestamp TEXT NOT NULL,
                    step_id TEXT,
                    agent TEXT,
                    thought_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    history TEXT
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_conv_workflow ON conversation_messages(workflow_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ir_workflow ON interaction_requests(workflow_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_tt_workflow ON thought_trail(workflow_id)")

    # ------------------------------------------------------------------
    # Workflow CRUD
    # ------------------------------------------------------------------

    def save_workflow(self, workflow: WorkflowRecord):
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO workflows
                    (workflow_id, task_description, status, total_steps, completed_steps,
                     created_at, updated_at, started_at, completed_at, error_message,
                     workflow_context, execution_plan, results)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (workflow_id) DO UPDATE SET
                    task_description = EXCLUDED.task_description,
                    status = EXCLUDED.status,
                    total_steps = EXCLUDED.total_steps,
                    completed_steps = EXCLUDED.completed_steps,
                    updated_at = EXCLUDED.updated_at,
                    started_at = EXCLUDED.started_at,
                    completed_at = EXCLUDED.completed_at,
                    error_message = EXCLUDED.error_message,
                    workflow_context = EXCLUDED.workflow_context,
                    execution_plan = EXCLUDED.execution_plan,
                    results = EXCLUDED.results
            """, (
                workflow.workflow_id,
                workflow.task_description,
                workflow.status.value,
                workflow.total_steps,
                workflow.completed_steps,
                workflow.created_at.isoformat(),
                workflow.updated_at.isoformat(),
                workflow.started_at.isoformat() if workflow.started_at else None,
                workflow.completed_at.isoformat() if workflow.completed_at else None,
                workflow.error_message,
                json.dumps(workflow.workflow_context),
                json.dumps(workflow.execution_plan),
                json.dumps(workflow.results),
            ))

    def update_workflow_state(self, workflow_id: str, state_data: Dict[str, Any]):
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE workflows
                SET status = %s,
                    workflow_context = %s,
                    updated_at = %s
                WHERE workflow_id = %s
            """, (
                state_data.get("status", "running"),
                json.dumps(state_data.get("workflow_context", {})),
                datetime.utcnow().isoformat(),
                workflow_id,
            ))

    def update_workflow_status(self, workflow_id: str, status: WorkflowStatus):
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE workflows SET status = %s, updated_at = %s WHERE workflow_id = %s
            """, (status.value, datetime.utcnow().isoformat(), workflow_id))

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowRecord]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM workflows WHERE workflow_id = %s", (workflow_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_workflow(row)

    def list_workflows(
        self, status: Optional[WorkflowStatus] = None, limit: int = 50
    ) -> List[WorkflowRecord]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            if status:
                cur.execute(
                    "SELECT * FROM workflows WHERE status = %s ORDER BY created_at DESC LIMIT %s",
                    (status.value, limit),
                )
            else:
                cur.execute(
                    "SELECT * FROM workflows ORDER BY created_at DESC LIMIT %s", (limit,)
                )
            return [self._row_to_workflow(row) for row in cur.fetchall()]

    @staticmethod
    def _row_to_workflow(row) -> WorkflowRecord:
        return WorkflowRecord(
            workflow_id=row["workflow_id"],
            task_description=row["task_description"],
            status=WorkflowStatus(row["status"]),
            total_steps=row["total_steps"],
            completed_steps=row["completed_steps"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            error_message=row["error_message"],
            workflow_context=json.loads(row["workflow_context"]) if row["workflow_context"] else {},
            execution_plan=json.loads(row["execution_plan"]) if row["execution_plan"] else {},
            results=json.loads(row["results"]) if row["results"] else [],
        )

    # ------------------------------------------------------------------
    # Step CRUD
    # ------------------------------------------------------------------

    def save_step(self, step: StepRecord):
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO steps
                    (step_id, workflow_id, step_number, capability, description, status,
                     agent_name, agent_endpoint, parameters, result, error,
                     started_at, completed_at, execution_time, retry_count,
                     max_retries, requires_human_review, human_feedback)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (step_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    agent_name = EXCLUDED.agent_name,
                    agent_endpoint = EXCLUDED.agent_endpoint,
                    parameters = EXCLUDED.parameters,
                    result = EXCLUDED.result,
                    error = EXCLUDED.error,
                    started_at = EXCLUDED.started_at,
                    completed_at = EXCLUDED.completed_at,
                    execution_time = EXCLUDED.execution_time,
                    retry_count = EXCLUDED.retry_count,
                    max_retries = EXCLUDED.max_retries,
                    requires_human_review = EXCLUDED.requires_human_review,
                    human_feedback = EXCLUDED.human_feedback
            """, (
                step.step_id,
                step.workflow_id,
                step.step_number,
                step.capability,
                step.description,
                step.status.value,
                step.agent_name,
                step.agent_endpoint,
                json.dumps(step.parameters) if step.parameters else None,
                json.dumps(step.result) if step.result else None,
                step.error,
                step.started_at.isoformat() if step.started_at else None,
                step.completed_at.isoformat() if step.completed_at else None,
                step.execution_time,
                step.retry_count,
                step.max_retries,
                1 if step.requires_human_review else 0,
                json.dumps(step.human_feedback) if step.human_feedback else None,
            ))

    def get_step(self, step_id: str) -> Optional[StepRecord]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM steps WHERE step_id = %s", (step_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_step(row)

    def get_workflow_steps(self, workflow_id: str) -> List[StepRecord]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM steps WHERE workflow_id = %s ORDER BY step_number",
                (workflow_id,),
            )
            return [self._row_to_step(row) for row in cur.fetchall()]

    @staticmethod
    def _row_to_step(row) -> StepRecord:
        return StepRecord(
            step_id=row["step_id"],
            workflow_id=row["workflow_id"],
            step_number=row["step_number"],
            capability=row["capability"],
            description=row["description"],
            status=StepStatus(row["status"]),
            agent_name=row.get("agent_name"),
            agent_endpoint=row.get("agent_endpoint"),
            parameters=json.loads(row["parameters"]) if row["parameters"] else {},
            result=json.loads(row["result"]) if row["result"] else None,
            error=row.get("error"),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            execution_time=row.get("execution_time"),
            retry_count=row.get("retry_count", 0),
            max_retries=row.get("max_retries", 3),
            requires_human_review=bool(row.get("requires_human_review", 0)),
            human_feedback=json.loads(row["human_feedback"]) if row.get("human_feedback") else None,
        )

    # ------------------------------------------------------------------
    # Session history
    # ------------------------------------------------------------------

    def save_session_history(self, session_id: str, history_item: Dict[str, Any]):
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT history FROM sessions WHERE session_id = %s", (session_id,))
            row = cur.fetchone()
            if row:
                history = json.loads(row["history"]) if row["history"] else []
                history.append(history_item)
                cur.execute(
                    "UPDATE sessions SET history = %s, updated_at = %s WHERE session_id = %s",
                    (json.dumps(history), datetime.utcnow().isoformat(), session_id),
                )
            else:
                cur.execute(
                    "INSERT INTO sessions (session_id, created_at, updated_at, history) VALUES (%s,%s,%s,%s)",
                    (
                        session_id,
                        datetime.utcnow().isoformat(),
                        datetime.utcnow().isoformat(),
                        json.dumps([history_item]),
                    ),
                )

    def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT history FROM sessions WHERE session_id = %s", (session_id,))
            row = cur.fetchone()
            if row and row["history"]:
                return json.loads(row["history"])
            return []

    # ------------------------------------------------------------------
    # Conversation messages
    # ------------------------------------------------------------------

    def save_message(self, message):
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO conversation_messages
                    (message_id, workflow_id, timestamp, role, message_type, content,
                     metadata, requires_response, parent_message_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (message_id) DO UPDATE SET
                    content = EXCLUDED.content,
                    metadata = EXCLUDED.metadata
            """, (
                message.message_id,
                message.workflow_id,
                message.timestamp.isoformat(),
                message.role.value,
                message.message_type.value,
                message.content,
                json.dumps(message.metadata),
                1 if message.requires_response else 0,
                message.parent_message_id,
            ))

    def get_conversation(self, workflow_id: str) -> List:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM conversation_messages WHERE workflow_id = %s ORDER BY timestamp",
                (workflow_id,),
            )
            from models import ConversationMessage, MessageRole, MessageType  # noqa
            messages = []
            for row in cur.fetchall():
                messages.append(ConversationMessage(
                    message_id=row["message_id"],
                    workflow_id=row["workflow_id"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    role=MessageRole(row["role"]),
                    message_type=MessageType(row["message_type"]),
                    content=row["content"],
                    metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                    requires_response=bool(row["requires_response"]),
                    parent_message_id=row["parent_message_id"],
                ))
            return messages

    # ------------------------------------------------------------------
    # Interaction requests
    # ------------------------------------------------------------------

    def save_interaction_request(self, request):
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO interaction_requests
                    (request_id, workflow_id, step_id, agent_name, created_at, timeout_at,
                     question, input_type, options, default_value, context, reasoning,
                     partial_results, response, response_received_at, response_metadata, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (request_id) DO UPDATE SET
                    response = EXCLUDED.response,
                    response_received_at = EXCLUDED.response_received_at,
                    response_metadata = EXCLUDED.response_metadata,
                    status = EXCLUDED.status
            """, (
                request.request_id, request.workflow_id, request.step_id,
                request.agent_name,
                request.created_at.isoformat(),
                request.timeout_at.isoformat() if request.timeout_at else None,
                request.question, request.input_type.value,
                json.dumps(request.options) if request.options else None,
                json.dumps(request.default_value) if request.default_value else None,
                json.dumps(request.context),
                request.reasoning,
                json.dumps(request.partial_results) if request.partial_results else None,
                json.dumps(request.response) if request.response else None,
                request.response_received_at.isoformat() if request.response_received_at else None,
                json.dumps(request.response_metadata),
                request.status,
            ))

    def _row_to_interaction(self, row):
        from models import InteractionRequest, InputType  # noqa
        row = dict(row)
        return InteractionRequest(
            request_id=row["request_id"],
            workflow_id=row["workflow_id"],
            step_id=row["step_id"],
            agent_name=row["agent_name"],
            created_at=datetime.fromisoformat(row["created_at"]),
            timeout_at=datetime.fromisoformat(row["timeout_at"]) if row["timeout_at"] else None,
            question=row["question"],
            input_type=InputType(row["input_type"]),
            options=json.loads(row["options"]) if row["options"] else None,
            default_value=json.loads(row["default_value"]) if row["default_value"] else None,
            context=json.loads(row["context"]) if row["context"] else {},
            reasoning=row["reasoning"],
            partial_results=json.loads(row["partial_results"]) if row["partial_results"] else None,
            response=json.loads(row["response"]) if row["response"] else None,
            response_received_at=datetime.fromisoformat(row["response_received_at"]) if row.get("response_received_at") else None,
            response_metadata=json.loads(row["response_metadata"]) if row.get("response_metadata") else {},
            status=row["status"],
        )

    def get_interaction_request(self, request_id: str):
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM interaction_requests WHERE request_id = %s", (request_id,))
            row = cur.fetchone()
            return self._row_to_interaction(row) if row else None

    def get_pending_interaction(self, workflow_id: str):
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM interaction_requests 
                WHERE workflow_id = %s AND status = 'pending'
                ORDER BY created_at DESC LIMIT 1
            """, (workflow_id,))
            row = cur.fetchone()
            return self._row_to_interaction(row) if row else None

    def get_answered_interaction(self, workflow_id: str):
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM interaction_requests 
                WHERE workflow_id = %s AND status = 'answered'
                ORDER BY created_at DESC LIMIT 1
            """, (workflow_id,))
            row = cur.fetchone()
            return self._row_to_interaction(row) if row else None

    def get_all_interaction_requests(self) -> List[Dict]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT request_id, workflow_id, status, question 
                FROM interaction_requests ORDER BY created_at DESC LIMIT 20
            """)
            return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Thought trail
    # ------------------------------------------------------------------

    def save_thought(self, workflow_id: str, thought):
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO thought_trail
                    (workflow_id, timestamp, step_id, agent, thought_type, content, metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (
                workflow_id,
                thought.timestamp.isoformat(),
                thought.step_id,
                thought.agent,
                thought.thought_type,
                thought.content,
                json.dumps(thought.metadata),
            ))

    def get_thought_trail(self, workflow_id: str) -> List:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM thought_trail WHERE workflow_id = %s ORDER BY timestamp",
                (workflow_id,),
            )
            from models import ThoughtTrailEntry  # noqa
            return [
                ThoughtTrailEntry(
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    step_id=row["step_id"],
                    agent=row["agent"],
                    thought_type=row["thought_type"],
                    content=row["content"],
                    metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                )
                for row in cur.fetchall()
            ]

    # ------------------------------------------------------------------
    # Workflow context
    # ------------------------------------------------------------------

    def get_workflow_context(self, workflow_id: str):
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            return None
        from models import WorkflowContext  # noqa
        return WorkflowContext(
            workflow_id=workflow_id,
            original_task=workflow.task_description,
            current_step=workflow.completed_steps + 1 if workflow.completed_steps < workflow.total_steps else None,
            conversation=self.get_conversation(workflow_id),
            thought_trail=self.get_thought_trail(workflow_id),
            step_results=workflow.workflow_context.get("step_results", {}),
            pending_interaction=self.get_pending_interaction(workflow_id),
            variables=workflow.workflow_context.get("variables", {}),
        )


# ===========================================================================
# Helpers
# ===========================================================================

def _redact_dsn(dsn: str) -> str:
    """Remove password from DSN for logging."""
    import re
    return re.sub(r":[^:@]+@", ":***@", dsn)


def _build_pg_dsn() -> str:
    url = _env("DATABASE_URL")
    if url:
        return url
    host = _env("PG_HOST", "localhost")
    port = _env("PG_PORT", "5432")
    db = _env("PG_DATABASE", "orchestrator")
    user = _env("PG_USER", "orchestrator")
    pw = _env("PG_PASSWORD", "orchestrator")
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"


# ===========================================================================
# Factory
# ===========================================================================

_db_singleton = None


def get_workflow_database():
    """
    Return a singleton workflow database instance.

    Controlled by ``WORKFLOW_DB_BACKEND`` environment variable:
      - ``sqlite``       → original WorkflowDatabase (default)
      - ``postgresql``   → PostgreSQLWorkflowDatabase

    Call ``db.init_database()`` and ``db.init_interaction_tables()``
    after obtaining the instance.
    """
    global _db_singleton
    if _db_singleton is not None:
        return _db_singleton

    backend = _env("WORKFLOW_DB_BACKEND", "sqlite").lower()

    if backend == "postgresql":
        dsn = _build_pg_dsn()
        logger.info("Using PostgreSQL workflow database")
        _db_singleton = PostgreSQLWorkflowDatabase(dsn)
    else:
        db_path = _env("SQLITE_DB_PATH", "workflows.db")
        logger.info("Using SQLite workflow database at %s", db_path)
        _db_singleton = WorkflowDatabase(db_path)

    return _db_singleton
