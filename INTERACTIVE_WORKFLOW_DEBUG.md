# Interactive Workflow Debugging Guide

## Current Issue

When submitting a response to an interaction request via REST API, the request fails with:
```
{"detail":"Failed to submit response"}
```

## Debugging Steps Added

### 1. Enhanced Logging in Orchestrator

Added debug logging to `/api/workflow/{workflow_id}/respond` endpoint to trace:
- Workflow ID
- Request ID
- Response content
- Submit result

### 2. Enhanced Logging in Interaction Manager

Added logging to `submit_response()` method to show:
- Request lookup status
- Available request IDs (if not found)
- Request status

### 3. Database Helper Method

Added `get_all_interaction_requests()` to list all recent requests for debugging.

## How to Debug

### Step 1: Restart Services

```bash
./stop_services.sh
./start_services.sh
```

### Step 2: Run a Workflow That Requires Input

```bash
python3 test_interactive_workflow.py
```

### Step 3: Capture the Request ID

From the workflow output, note the `request_id` (e.g., `req_1770556458340`)

### Step 4: Run the Debug Script

```bash
python3 test_respond_debug.py
```

Enter the captured request_id when prompted.

### Step 5: Check Orchestrator Logs

Look for these log messages:

```
📨 RECEIVED RESPONSE:
   Workflow ID: test_001
   Request ID: req_1770556458340
   Response: Focus on AWS, Azure, Google Cloud
   Submitting response to interaction manager...
   Submit result: True/False
```

In the interaction manager logs:

```
submit_response called for request_id: req_1770556458340
Found request with status: pending
OR
Interaction request not found: req_1770556458340
Available requests: ['req_xxx', 'req_yyy']
```

## Common Issues

### Issue 1: Request ID Not Found

**Symptom**: `Interaction request not found`

**Possible Causes**:
1. Wrong request_id provided
2. Database not persisting requests
3. Request expired/timed out

**Solution**: Check the available requests in the log output

### Issue 2: Request Not Pending

**Symptom**: `Interaction request not pending (status: answered)`

**Cause**: Request already has a response

**Solution**: Run a new workflow to create a new request

### Issue 3: Database Connection Issues

**Symptom**: Various database errors

**Solution**: Check that `workflow.db` exists and has correct schema

## Next Steps

Once we identify the issue from the logs, we can:

1. Fix request ID generation/storage
2. Fix database persistence
3. Fix status management
4. Fix response validation

## Testing Workflow Resume

After a successful response submission, the workflow should automatically resume:

1. Response is saved to database
2. WebSocket notification sent (if connected)
3. Workflow resumes from paused step
4. User response is injected into agent context
5. Remaining steps execute

## Manual Database Inspection

If needed, inspect the database directly:

```python
import sqlite3
import json

conn = sqlite3.connect('services/orchestrator/workflow.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# List all interaction requests
cursor.execute("""
    SELECT request_id, workflow_id, status, question, created_at
    FROM interaction_requests 
    ORDER BY created_at DESC 
    LIMIT 10
""")

for row in cursor.fetchall():
    print(f"ID: {row['request_id']}")
    print(f"Workflow: {row['workflow_id']}")
    print(f"Status: {row['status']}")
    print(f"Question: {row['question'][:50]}...")
    print("-" * 80)

conn.close()
```
