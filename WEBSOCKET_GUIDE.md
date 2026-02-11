# WebSocket Interactive Workflow Guide

## Overview

The orchestrator supports **bidirectional communication** via WebSocket, enabling:
- Real-time workflow progress updates
- Multiple sequential user interactions
- Streaming responses from agents
- Dynamic workflow control

## Quick Start

### Prerequisites

Install WebSocket client tools:
```bash
# Option 1: websocat (recommended)
brew install websocat  # macOS
# or
cargo install websocat  # Any platform with Rust

# Option 2: wscat (Node.js based)
npm install -g wscat

# Option 3: Python websockets library
pip install websockets
```

## Using WebSocket for Interactive Workflows

### Method 1: Using websocat (Recommended)

```bash
# 1. Start workflow (REST API)
WORKFLOW_ID="my_workflow_$(date +%s)"
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d "{
    \"workflow_id\": \"$WORKFLOW_ID\",
    \"task_description\": \"Research cloud computing competitors\",
    \"async_mode\": true
  }"

# 2. Connect to WebSocket
websocat "ws://localhost:8100/ws/workflow/$WORKFLOW_ID"

# You'll receive messages like:
# {"type": "connection_established", "workflow_id": "my_workflow_123", ...}
# {"type": "step_started", "step": {...}, ...}
# {"type": "user_input_required", "interaction": {"request_id": "req_123", "question": "...", ...}, ...}

# 3. When you receive "user_input_required", respond with:
# (Type this JSON and press Enter)
{
  "type": "user_response",
  "request_id": "req_123",
  "response": "Focus on AWS, Azure, and Google Cloud"
}

# 4. You'll automatically receive the next interaction request if agent needs more input
# {"type": "user_input_required", "interaction": {"request_id": "req_456", "question": "...", ...}, ...}

# 5. Respond again:
{
  "type": "user_response",
  "request_id": "req_456",
  "response": "Compare pricing and services"
}

# 6. Continue until workflow completes:
# {"type": "workflow_completed", "result": {...}, ...}
```

### Method 2: Using wscat

```bash
# Connect to workflow
wscat -c "ws://localhost:8100/ws/workflow/my_workflow_123"

# Then send/receive messages as shown above
```

### Method 3: Using Python Script

```bash
# Run the example script
python3 examples/websocket_interactive_workflow.py
```

## WebSocket Message Types

### Messages FROM Orchestrator (Server → Client)

#### 1. Connection Established
```json
{
  "type": "connection_established",
  "workflow_id": "workflow_123",
  "message": "Connected to workflow workflow_123",
  "timestamp": "2026-02-08T15:00:00.000Z"
}
```

#### 2. Workflow Status
```json
{
  "type": "workflow_status",
  "workflow_id": "workflow_123",
  "status": "running",
  "current_step": 2,
  "total_steps": 4,
  "timestamp": "2026-02-08T15:00:01.000Z"
}
```

#### 3. Step Started
```json
{
  "type": "step_started",
  "workflow_id": "workflow_123",
  "step": {
    "step_number": 2,
    "capability": "analyze_data",
    "description": "Analyze the gathered information",
    "agent": "DataProcessor"
  },
  "timestamp": "2026-02-08T15:00:02.000Z"
}
```

#### 4. Step Completed
```json
{
  "type": "step_completed",
  "workflow_id": "workflow_123",
  "step": {
    "step_number": 2,
    "capability": "analyze_data",
    "description": "Analyze the gathered information"
  },
  "result": {"analysis": "..."},
  "timestamp": "2026-02-08T15:00:05.000Z"
}
```

#### 5. **User Input Required** ⭐ (Most Important)
```json
{
  "type": "user_input_required",
  "workflow_id": "workflow_123",
  "interaction": {
    "request_id": "req_1770562702309",
    "workflow_id": "workflow_123",
    "step_number": 4,
    "agent": "ResearchAgent",
    "capability": "generate_report",
    "question": "Which aspect should I focus on?",
    "reasoning": "The topic is broad and needs clarification",
    "input_type": "single_choice",
    "options": [
      "Pricing models",
      "Service offerings",
      "Market share",
      "All aspects"
    ],
    "placeholder": "Enter your response..."
  },
  "timestamp": "2026-02-08T15:00:06.000Z"
}
```

#### 6. Response Received
```json
{
  "type": "response_received",
  "request_id": "req_1770562702309",
  "response": "Focus on AWS, Azure, Google Cloud",
  "timestamp": "2026-02-08T15:00:10.000Z"
}
```

#### 7. Workflow Resuming
```json
{
  "type": "workflow_resuming",
  "workflow_id": "workflow_123",
  "timestamp": "2026-02-08T15:00:11.000Z"
}
```

#### 8. Workflow Completed
```json
{
  "type": "workflow_completed",
  "workflow_id": "workflow_123",
  "status": "completed",
  "result": {
    "workflow_id": "workflow_123",
    "status": "completed",
    "steps_completed": 4,
    "total_steps": 4,
    "results": [...]
  },
  "timestamp": "2026-02-08T15:00:20.000Z"
}
```

#### 9. Error
```json
{
  "type": "error",
  "message": "Error description",
  "timestamp": "2026-02-08T15:00:15.000Z"
}
```

### Messages TO Orchestrator (Client → Server)

#### 1. User Response ⭐
```json
{
  "type": "user_response",
  "request_id": "req_1770562702309",
  "response": "Focus on AWS, Azure, and Google Cloud",
  "additional_context": {
    "reason": "Most popular providers"
  }
}
```

#### 2. Get Status
```json
{
  "type": "get_status"
}
```

#### 3. Get Conversation History
```json
{
  "type": "get_conversation"
}
```

#### 4. Cancel Workflow
```json
{
  "type": "cancel_workflow"
}
```

#### 5. Ping (Keep-alive)
```json
{
  "type": "ping"
}
```

## Complete Interactive Workflow Example

### Scenario: Multi-Question Research Workflow

```bash
# 1. Create workflow
WORKFLOW_ID="research_$(date +%s)"
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d "{
    \"workflow_id\": \"$WORKFLOW_ID\",
    \"task_description\": \"Research and compare cloud computing competitors\",
    \"async_mode\": true
  }"

# 2. Connect via WebSocket
websocat "ws://localhost:8100/ws/workflow/$WORKFLOW_ID"

# Expected flow:
```

**Orchestrator →** Connection established
```json
{"type": "connection_established", "workflow_id": "research_123"}
```

**Orchestrator →** Step 1 started
```json
{"type": "step_started", "step": {"step_number": 1, "description": "Research competitors"}}
```

**Orchestrator →** Step 1 completed
```json
{"type": "step_completed", "step": {"step_number": 1}}
```

**Orchestrator →** Step 2 started
```json
{"type": "step_started", "step": {"step_number": 2}}
```

**Orchestrator →** **FIRST USER INPUT REQUEST**
```json
{
  "type": "user_input_required",
  "interaction": {
    "request_id": "req_001",
    "question": "I've detected some issues with the data. How would you like me to proceed?",
    "options": ["Continue", "Exclude problematic data", "Show issues first"]
  }
}
```

**You →** Respond to first question
```json
{
  "type": "user_response",
  "request_id": "req_001",
  "response": "Continue with analysis"
}
```

**Orchestrator →** Response received
```json
{"type": "response_received", "request_id": "req_001"}
```

**Orchestrator →** Workflow resuming
```json
{"type": "workflow_resuming"}
```

**Orchestrator →** **SECOND USER INPUT REQUEST** ⭐ (Sequential question)
```json
{
  "type": "user_input_required",
  "interaction": {
    "request_id": "req_002",
    "question": "Which aspect should I focus on?",
    "options": ["Pricing", "Services", "Market share", "All aspects"]
  }
}
```

**You →** Respond to second question
```json
{
  "type": "user_response",
  "request_id": "req_002",
  "response": "Focus on AWS, Azure, and Google Cloud"
}
```

**Orchestrator →** **THIRD USER INPUT REQUEST** ⭐ (Another follow-up)
```json
{
  "type": "user_input_required",
  "interaction": {
    "request_id": "req_003",
    "question": "Should I include pricing comparison?",
    "input_type": "text"
  }
}
```

**You →** Respond to third question
```json
{
  "type": "user_response",
  "request_id": "req_003",
  "response": "Yes, include pricing"
}
```

**Orchestrator →** Workflow completed
```json
{
  "type": "workflow_completed",
  "status": "completed",
  "result": {...}
}
```

## Key Features

### 1. Automatic Request ID Generation
Each time an agent needs input, a **NEW request_id** is automatically generated and sent via WebSocket.

### 2. Sequential Interactions
You can have unlimited sequential interactions:
- Agent asks Question 1 → User responds
- Agent asks Question 2 → User responds
- Agent asks Question 3 → User responds
- ... until agent has all needed information

### 3. Real-time Updates
All workflow progress is streamed in real-time:
- Step started/completed
- Agent thinking/processing
- Errors and warnings
- Final results

### 4. Bidirectional Communication
- **Push**: Orchestrator sends updates without client polling
- **Pull**: Client can request status/conversation at any time

## Comparison: REST vs WebSocket

| Feature | REST API | WebSocket |
|---------|----------|-----------|
| Multiple interactions | ❌ One request_id only | ✅ Unlimited sequential |
| Real-time updates | ❌ Must poll | ✅ Automatic push |
| Connection overhead | ❌ Per-request | ✅ Single connection |
| Bidirectional | ❌ Request-response only | ✅ Full duplex |
| **Best for** | Simple single-question workflows | Complex multi-step interactions |

## Troubleshooting

### Issue: Not receiving interaction requests
**Solution**: Ensure WebSocket connection is established BEFORE workflow starts:
```bash
# Wrong order:
curl POST /api/workflow/execute  # Workflow starts
websocat ws://...  # Too late, missed first interaction

# Correct order:
websocat ws://... &  # Connect first
curl POST /api/workflow/execute  # Then start
```

### Issue: Connection closes unexpectedly
**Solution**: Send periodic ping messages:
```json
{"type": "ping"}
```

### Issue: Multiple clients for same workflow
All connected clients receive the same updates. Perfect for:
- User interface + monitoring dashboard
- Multiple team members observing workflow
- Logging/audit systems

## Advanced Usage

### Custom User Interface
```python
import asyncio
import websockets

class WorkflowUI:
    async def connect_and_interact(self, workflow_id):
        async with websockets.connect(f"ws://localhost:8100/ws/workflow/{workflow_id}") as ws:
            async for message in ws:
                data = json.loads(message)
                
                if data["type"] == "user_input_required":
                    # Show question to user in UI
                    question = data["interaction"]["question"]
                    options = data["interaction"]["options"]
                    
                    # Get user input from UI
                    user_response = self.show_question_dialog(question, options)
                    
                    # Send response
                    await ws.send(json.dumps({
                        "type": "user_response",
                        "request_id": data["interaction"]["request_id"],
                        "response": user_response
                    }))
```

## Summary

✅ **Use WebSocket** for:
- Interactive workflows with multiple questions
- Real-time monitoring
- Complex multi-agent coordination
- Production applications

✅ **Use REST** for:
- Simple single-question workflows
- Testing/debugging
- Scripting/automation
- When WebSocket not available

The orchestrator's WebSocket implementation enables **true conversational workflows** where agents can iteratively refine their understanding through multiple user interactions.
