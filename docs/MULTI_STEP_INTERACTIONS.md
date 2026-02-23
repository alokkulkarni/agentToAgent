# Multi-Step Interactive Workflows - Complete Guide

## Problem Statement

Agents in multi-agent workflows often need to ask **multiple sequential questions** to gather enough information before providing a complete response. The initial REST-only implementation had a critical limitation:

- ❌ **User received only ONE request_id**
- ❌ **No way to respond to follow-up questions**
- ❌ **Workflow would hang waiting for input that couldn't be provided**

## Solution: WebSocket-Based Interactive Workflows

The orchestrator implements **bidirectional WebSocket communication** to enable:

✅ **Unlimited sequential interactions** - Agent can ask as many questions as needed  
✅ **Real-time notifications** - User receives new request_ids automatically  
✅ **Streaming updates** - See workflow progress in real-time  
✅ **Full conversation flow** - Natural back-and-forth dialogue  

## Architecture

```
┌──────────┐                ┌──────────────┐                ┌─────────┐
│  Client  │◄──WebSocket───►│ Orchestrator │◄───REST───────►│  Agent  │
└──────────┘                └──────────────┘                └─────────┘
     │                             │                              │
     │  1. Connect WS              │                              │
     │────────────────────────────►│                              │
     │                             │                              │
     │  2. Create Workflow         │                              │
     │────────────REST────────────►│                              │
     │                             │                              │
     │                             │  3. Execute Step             │
     │                             │─────────────────────────────►│
     │                             │                              │
     │                             │  4. Needs Input (Q1)         │
     │                             │◄─────────────────────────────│
     │                             │                              │
     │  5. user_input_required     │                              │
     │◄────────WS─────────────────│                              │
     │     (request_id: req_001)   │                              │
     │                             │                              │
     │  6. user_response           │                              │
     │     (req_001, "Answer 1")   │                              │
     │────────────WS──────────────►│                              │
     │                             │                              │
     │                             │  7. Resume with Answer 1     │
     │                             │─────────────────────────────►│
     │                             │                              │
     │                             │  8. Needs MORE Input (Q2) ⭐ │
     │                             │◄─────────────────────────────│
     │                             │                              │
     │  9. user_input_required     │                              │
     │◄────────WS─────────────────│                              │
     │     (request_id: req_002) ⭐│                              │
     │                             │                              │
     │  10. user_response          │                              │
     │      (req_002, "Answer 2")  │                              │
     │────────────WS──────────────►│                              │
     │                             │                              │
     │                             │  11. Resume with Answer 2    │
     │                             │─────────────────────────────►│
     │                             │                              │
     │                             │  12. Complete                │
     │                             │◄─────────────────────────────│
     │                             │                              │
     │  13. workflow_completed     │                              │
     │◄────────WS─────────────────│                              │
     └─────────────────────────────┴──────────────────────────────┘
```

## Implementation Details

### 1. WebSocket Endpoint

```python
@app.websocket("/ws/workflow/{workflow_id}")
async def websocket_endpoint(websocket: WebSocket, workflow_id: str):
    """
    Enables bidirectional communication for interactive workflows.
    Automatically sends new interaction requests as they occur.
    """
    await ws_handler.handle_connection(websocket, workflow_id)
```

### 2. Interaction Flow

When an agent needs input:

```python
# In workflow execution (app.py)
if response.result.get("status") == "user_input_required":
    # Create interaction request
    interaction = await _handle_additional_input_request(...)
    
    # Save to database
    db.update_workflow_state(workflow_id, {...})
    
    # Broadcast via WebSocket to ALL connected clients
    await ws_handler.connection_manager.broadcast_to_workflow(workflow_id, {
        "type": "user_input_required",
        "interaction": {
            "request_id": "req_XXX",  # NEW request_id for each question
            "question": "What aspect should I focus on?",
            "options": [...],
            ...
        }
    })
```

When user responds:

```python
# User sends via WebSocket
{
    "type": "user_response",
    "request_id": "req_XXX",
    "response": "Focus on AWS, Azure, GCP"
}

# Orchestrator handles it
@app.post("/api/workflow/{workflow_id}/respond")
async def respond_to_interaction(...):
    # Mark interaction as answered
    interaction_mgr.submit_response(request_id, response)
    
    # Resume workflow
    asyncio.create_task(ws_handler._resume_workflow(workflow_id))
    
    # If agent needs MORE input, new request_id is generated and broadcast
```

### 3. Key Components

#### InteractionManager (`interaction.py`)
- Creates and tracks interaction requests
- Maintains request state: `pending` → `answered` → `completed`
- Supports multiple sequential interactions per workflow

#### WebSocketMessageHandler (`websocket_handler.py`)
- Manages WebSocket connections
- Broadcasts messages to all clients watching a workflow
- Handles user responses and triggers workflow resumption

#### Resume Workflow (`app.py`)
- Retrieves answered interaction requests
- Injects user responses into workflow context
- Re-executes paused steps
- Handles additional input requests (creates new interaction)

## Usage Examples

### Method 1: WebSocket (Python)

```bash
python3 examples/websocket_interactive_workflow.py
```

See `examples/websocket_interactive_workflow.py` for full implementation.

### Method 2: REST API with Polling

```bash
./examples/rest_interactive_workflow.sh
```

This simulates WebSocket behavior by polling for status changes.

### Method 3: websocat (CLI)

```bash
# Terminal 1: Start workflow
WORKFLOW_ID="test_$(date +%s)"
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d "{
    \"workflow_id\": \"$WORKFLOW_ID\",
    \"task_description\": \"Research cloud competitors\",
    \"async_mode\": true
  }"

# Terminal 2: Connect WebSocket
websocat "ws://localhost:8100/ws/workflow/$WORKFLOW_ID"

# You'll receive messages and can respond:
# Receive: {"type": "user_input_required", "interaction": {"request_id": "req_001", ...}}
# Send: {"type": "user_response", "request_id": "req_001", "response": "AWS, Azure, GCP"}
#
# Receive: {"type": "user_input_required", "interaction": {"request_id": "req_002", ...}}
# Send: {"type": "user_response", "request_id": "req_002", "response": "Compare pricing"}
```

## Fixes Applied

### Issue 1: WorkflowRecord Attribute Access ✅
**Problem**: Treating Pydantic models as dicts  
**Fix**: Changed `.get()` to proper attribute access

### Issue 2: Async/Await Mismatch ✅
**Problem**: Awaiting non-async functions  
**Fix**: Removed incorrect `await` keywords

### Issue 3: Resume Function Not Called ✅
**Problem**: WebSocket handler wasn't calling actual resume logic  
**Fix**: Passed `resume_workflow` function to handler

### Issue 4: Interaction State Management ✅
**Problem**: Looking for "pending" instead of "answered" requests  
**Fix**: Created `get_answered_request()` method

### Issue 5: Missing Context Fields ✅
**Problem**: KeyError on `capability_outputs`, `step_results`  
**Fix**: Added safety checks and initialization

### Issue 6: Plan Loading ✅
**Problem**: execution_plan was empty  
**Fix**: Load from `workflow_context['plan']`

### Issue 7: Agent Info Persistence ✅
**Problem**: agent_endpoint and agent_name not saved  
**Fix**: Save to workflow_state and load from multiple locations

### Issue 8: Pause Step Tracking ✅
**Problem**: pause_step was 0 or missing  
**Fix**: Load from nested workflow_state in workflow_context

### Issue 9: KeyError on Cleanup ✅
**Problem**: Deleting non-existent keys  
**Fix**: Use `.pop()` with default value

## Testing Multi-Step Interactions

### Expected Behavior

```
1. Workflow starts
2. Agent asks Question 1 → User responds
3. Agent asks Question 2 → User responds  ⭐ NEW request_id
4. Agent asks Question 3 → User responds  ⭐ NEW request_id
5. Agent completes with all information
```

### Test Script

```bash
# Start services
./start_services.sh

# Run WebSocket test
python3 examples/websocket_interactive_workflow.py

# Or use REST polling
./examples/rest_interactive_workflow.sh
```

### Verification

Check logs for:
```
⏸️  Step X PAUSED - Awaiting user input
Question: [First question]

📨 RECEIVED RESPONSE
🔄 RESUMING WORKFLOW

⏸️  Agent needs additional input, pausing again...
Question: [Second question]  ⭐ Different question!

📨 RECEIVED RESPONSE
🔄 RESUMING WORKFLOW

✅ WORKFLOW COMPLETED
```

## WebSocket Message Flow

### Complete Sequence

```json
// 1. Connection
{"type": "connection_established", "workflow_id": "test_001"}

// 2. Progress updates
{"type": "step_started", "step": {"step_number": 1, ...}}
{"type": "step_completed", "step": {"step_number": 1, ...}}

// 3. First interaction
{"type": "user_input_required", "interaction": {"request_id": "req_001", "question": "Q1?"}}

// 4. User responds
// Client sends: {"type": "user_response", "request_id": "req_001", "response": "A1"}

// 5. Resume notification
{"type": "workflow_resuming"}

// 6. SECOND interaction ⭐
{"type": "user_input_required", "interaction": {"request_id": "req_002", "question": "Q2?"}}

// 7. User responds again
// Client sends: {"type": "user_response", "request_id": "req_002", "response": "A2"}

// 8. Resume again
{"type": "workflow_resuming"}

// 9. THIRD interaction ⭐
{"type": "user_input_required", "interaction": {"request_id": "req_003", "question": "Q3?"}}

// 10. User responds again
// Client sends: {"type": "user_response", "request_id": "req_003", "response": "A3"}

// 11. Final resume
{"type": "workflow_resuming"}

// 12. Completion
{"type": "workflow_completed", "result": {...}}
```

## Key Features

✅ **Unlimited Sequential Interactions** - Agent can ask as many questions as needed  
✅ **Real-Time Updates** - All clients receive updates instantly  
✅ **Multiple Clients** - Multiple UIs/dashboards can watch same workflow  
✅ **Bidirectional** - Client can send messages anytime (cancel, get status, etc.)  
✅ **Persistent** - Connection survives across multiple interactions  
✅ **Scalable** - WebSocket manager handles connection lifecycle  

## Comparison: REST vs WebSocket

| Feature | REST API (Polling) | WebSocket |
|---------|-------------------|-----------|
| **Multi-step interactions** | ⚠️ Requires polling | ✅ Automatic notifications |
| **Latency** | ❌ 1-3s polling interval | ✅ <100ms real-time |
| **Network overhead** | ❌ High (repeated requests) | ✅ Low (single connection) |
| **Server load** | ❌ Continuous polling | ✅ Event-driven |
| **Implementation** | ✅ Simple (curl) | ⚠️ Requires WS library |
| **Best for** | Testing, simple workflows | Production, complex interactions |

## Conclusion

The WebSocket implementation enables **true conversational workflows** where:
- Agents can iteratively refine understanding through multiple questions
- Users receive each new question automatically with a new request_id
- No polling required - all updates are pushed in real-time
- Complete workflow conversation is captured and logged

This architecture supports complex multi-agent workflows where agents need to:
1. Ask clarifying questions
2. Request additional context
3. Verify understanding
4. Confirm assumptions

All while maintaining a natural, interactive dialogue with the user.

## Resources

- **WebSocket Guide**: `WEBSOCKET_GUIDE.md` - Complete WebSocket API documentation
- **Python Example**: `examples/websocket_interactive_workflow.py` - Full implementation
- **Shell Script**: `examples/rest_interactive_workflow.sh` - REST API polling simulation
- **Architecture**: `ARCHITECTURE.md` - System design and components

## Next Steps

1. ✅ Multi-step interactions working
2. ✅ WebSocket notifications implemented
3. ✅ Resume workflow logic fixed
4. 🔄 Build UI dashboard (future enhancement)
5. 🔄 Add conversation history export (future enhancement)
6. 🔄 Support for file/media interactions (future enhancement)
