# Interactive Workflow - Context Passing Fix

## Issue Summary
When agents requested user input during workflow execution, the interaction request contained `None` values for critical fields:
- `workflow_id`: None
- `step_id`: None  
- `agent_name`: None

## Root Cause
The `AgentInteractionHelper` was looking for these fields directly in the task request parameters, but the orchestrator was passing them in the nested `context` object.

## Solution

### 1. Fixed Agent Interaction Helper (`shared/agent_interaction.py`)
Updated the `__init__` method to check both locations:
```python
# Try to get workflow_id, step_id, agent_name from direct params or context
self.workflow_id = task_request.get("workflow_id") or self.context.get("workflow_id")
self.step_id = task_request.get("step_id") or self.context.get("step_id") or f"step_{self.context.get('step_number', 0)}"
self.agent_name = task_request.get("agent_name") or self.context.get("agent_name")
```

### 2. Updated Orchestrator Context (`services/orchestrator/app.py`)
Added missing fields to the task context:
```python
context={
    "workflow_id": workflow_id,
    "step_number": step_num,
    "step_id": f"step_{step_num}",  # NEW
    "agent_name": agent_name,        # NEW
    "total_steps": len(plan.get('steps', [])),
    "workflow_context": workflow_context
}
```

## Testing
To test the fix with the Research Agent:

```bash
# Start services
./start_services.sh

# Open websocket_test_client.html in browser
# Use workflow ID: test123
# Submit task:
```

**Example Interactive Task:**
```
Conduct comprehensive competitor analysis for our cloud-based project management SaaS product. Include market positioning, feature comparison, pricing strategies, and identify key differentiators we should focus on.
```

**Expected Behavior:**
1. Research Agent analyzes the task scope
2. Detects it's too broad  
3. Sends interaction request with proper `workflow_id`, `step_id`, and `agent_name`
4. WebSocket client displays choices to user
5. User selects focus area
6. Agent continues with user's guidance

## Files Modified
- `/Users/alokkulkarni/Documents/Development/agentToAgent/shared/agent_interaction.py`
- `/Users/alokkulkarni/Documents/Development/agentToAgent/services/orchestrator/app.py`

## Status
✅ Fixed - Ready for testing
