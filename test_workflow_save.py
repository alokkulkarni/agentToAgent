#!/usr/bin/env python3
"""
Test workflow save functionality
"""
import sys
sys.path.insert(0, 'services/orchestrator')

from database import WorkflowDatabase
from models import WorkflowRecord, WorkflowStatus
from datetime import datetime

# Test the new update_workflow_state method
db = WorkflowDatabase("test_workflows.db")

# Test update_workflow_state
print("Testing update_workflow_state...")
workflow_id = "test_workflow_123"
db.update_workflow_state(workflow_id, {
    "status": "waiting_for_input",
    "current_step": 2,
    "plan": {"steps": []},
    "workflow_context": {"test": "data"},
    "workflow_state": {"paused": True}
})
print("✓ update_workflow_state succeeded")

# Test save_workflow with proper WorkflowRecord
print("\nTesting save_workflow with WorkflowRecord...")
workflow = WorkflowRecord(
    workflow_id="test_workflow_456",
    task_description="Test task",
    status=WorkflowStatus.RUNNING,
    total_steps=3,
    completed_steps=1,
    created_at=datetime.utcnow(),
    updated_at=datetime.utcnow(),
    workflow_context={},
    execution_plan={},
    results=[]
)
db.save_workflow(workflow)
print("✓ save_workflow succeeded")

print("\n✅ All tests passed!")

# Clean up
import os
os.remove("test_workflows.db")
