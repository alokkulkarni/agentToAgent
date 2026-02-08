"""
Database operations for workflow persistence
"""
import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import os

from .models import (
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
    
    def save_workflow(self, workflow: WorkflowRecord):
        """Save or update workflow record"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO workflows 
                (workflow_id, task_description, status, total_steps, completed_steps,
                 created_at, updated_at, started_at, completed_at, error_message,
                 workflow_context, execution_plan, results)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                json.dumps(workflow.results)
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
            
            return WorkflowRecord(
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
