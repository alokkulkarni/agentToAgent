# Interactive Workflows - Complete Guide

## 🎯 Overview

The A2A Multi-Agent System supports **fully interactive workflows** where agents can have multi-turn conversations with users, asking clarifying questions and refining their understanding before providing complete responses.

## 🚀 Quick Start

### 1. Start Services
```bash
./start_services.sh
```

### 2. Choose Your Method

#### Option A: WebSocket (Recommended)
```bash
# See quick reference
./QUICK_START_WEBSOCKET.sh
```

#### Option B: Python Script
```bash
python3 examples/websocket_interactive_workflow.py
```

#### Option C: REST Polling
```bash
./examples/rest_interactive_workflow.sh
```

## 📚 Documentation

### Core Documentation

| Document | Description | Key Topics |
|----------|-------------|------------|
| **[WEBSOCKET_GUIDE.md](WEBSOCKET_GUIDE.md)** | Complete WebSocket API reference | Message types, examples, troubleshooting |
| **[MULTI_STEP_INTERACTIONS.md](MULTI_STEP_INTERACTIONS.md)** | Architecture & implementation details | System design, interaction flow, fixes |
| **[WORKFLOW_RESUME_FIX_COMPLETE.md](WORKFLOW_RESUME_FIX_COMPLETE.md)** | Summary of all fixes and improvements | Bug fixes, test results, conclusions |
| **[QUICK_START_WEBSOCKET.sh](QUICK_START_WEBSOCKET.sh)** | Quick reference card | Copy-paste commands |

### Examples

| File | Type | Description |
|------|------|-------------|
| `examples/websocket_interactive_workflow.py` | Python | Full WebSocket client implementation |
| `examples/rest_interactive_workflow.sh` | Shell | REST API polling simulation |

## 🔑 Key Concepts

### Multi-Step Interactions

Agents can ask **multiple sequential questions**:

```
Agent: "Which cloud providers should I focus on?"
User:  "AWS, Azure, Google Cloud"

Agent: "Should I include pricing comparison?"  ⭐ Follow-up question
User:  "Yes, include pricing"

Agent: "What time frame for the analysis?"     ⭐ Another question
User:  "Last 12 months"

Agent: [Generates comprehensive report with all context]
```

### Request IDs

Each question gets a **unique request_id**:

```
Question 1 → req_001
Question 2 → req_002  ⭐ NEW ID
Question 3 → req_003  ⭐ NEW ID
```

### Communication Methods

| Method | Use Case | Pros | Cons |
|--------|----------|------|------|
| **WebSocket** | Production apps | Real-time, efficient | Requires WS library |
| **REST Polling** | Testing, scripts | Simple (curl) | Polling overhead |

## 🔧 How It Works

### 1. Workflow Starts
```bash
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"workflow_id": "test_001", "task_description": "Research cloud competitors"}'
```

### 2. Agent Asks Question
```json
{
  "type": "user_input_required",
  "interaction": {
    "request_id": "req_001",
    "question": "Which aspect should I focus on?",
    "options": ["Pricing", "Services", "Market share"]
  }
}
```

### 3. User Responds
```json
{
  "type": "user_response",
  "request_id": "req_001",
  "response": "Focus on AWS, Azure, and Google Cloud"
}
```

### 4. Workflow Resumes
```json
{
  "type": "workflow_resuming"
}
```

### 5. Agent May Ask Another Question
```json
{
  "type": "user_input_required",
  "interaction": {
    "request_id": "req_002",  ⭐ NEW request_id
    "question": "Include pricing comparison?"
  }
}
```

### 6. Cycle Continues Until Complete
```json
{
  "type": "workflow_completed",
  "result": {...}
}
```

## 💻 Code Examples

### Python WebSocket Client

```python
import websockets
import asyncio
import json

async def interactive_workflow():
    uri = "ws://localhost:8100/ws/workflow/my_workflow_id"
    
    async with websockets.connect(uri) as websocket:
        async for message in websocket:
            data = json.loads(message)
            
            if data["type"] == "user_input_required":
                request_id = data["interaction"]["request_id"]
                question = data["interaction"]["question"]
                
                # Get user input
                response = input(f"{question}: ")
                
                # Send response
                await websocket.send(json.dumps({
                    "type": "user_response",
                    "request_id": request_id,
                    "response": response
                }))
            
            elif data["type"] == "workflow_completed":
                print("Done!")
                break

asyncio.run(interactive_workflow())
```

### Shell Script with websocat

```bash
WORKFLOW_ID="test_$(date +%s)"

# Start workflow
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d "{\"workflow_id\":\"$WORKFLOW_ID\",\"task_description\":\"Research cloud competitors\"}"

# Connect WebSocket
websocat "ws://localhost:8100/ws/workflow/$WORKFLOW_ID"

# When you see user_input_required, type:
{"type":"user_response","request_id":"req_XXX","response":"Your answer"}
```

## 🐛 Troubleshooting

### Issue: Workflow hangs after first response

**Problem**: Using REST API without polling for new interactions  
**Solution**: Use WebSocket or poll `/api/workflow/{id}/status` for new request_ids

### Issue: "No pending interaction requests found"

**Problem**: Workflow already processed the interaction  
**Solution**: Get latest status to see if there's a NEW request_id

### Issue: WebSocket connection refused

**Problem**: Services not running  
**Solution**: 
```bash
./start_services.sh
curl http://localhost:8100/health  # Verify orchestrator is up
```

### Issue: Agent keeps asking same question

**Problem**: Response not reaching agent properly  
**Solution**: Check request_id matches exactly; verify workflow status shows "running" not "waiting_for_input"

## 📊 System Status

### Check Orchestrator
```bash
curl http://localhost:8100/health
```

### Check Workflow Status
```bash
curl http://localhost:8100/api/workflow/test_001/status | jq
```

### View Pending Interactions
```bash
curl http://localhost:8100/api/workflow/test_001/status | jq '.pending_interactions'
```

## 🎓 Learn More

### Beginner

1. Read: [QUICK_START_WEBSOCKET.sh](QUICK_START_WEBSOCKET.sh)
2. Run: `./examples/rest_interactive_workflow.sh`
3. Observe: Watch the interaction flow

### Intermediate

1. Read: [WEBSOCKET_GUIDE.md](WEBSOCKET_GUIDE.md)
2. Run: `python3 examples/websocket_interactive_workflow.py`
3. Modify: Change the auto-responses to manual input

### Advanced

1. Read: [MULTI_STEP_INTERACTIONS.md](MULTI_STEP_INTERACTIONS.md)
2. Study: `services/orchestrator/websocket_handler.py`
3. Build: Custom UI with WebSocket integration

## 🔐 Production Considerations

### Security
- Use WSS (WebSocket Secure) in production
- Implement authentication/authorization
- Validate all user inputs
- Rate-limit interaction requests

### Scalability
- WebSocket connections are stateful
- Consider connection pooling
- Use load balancer with sticky sessions
- Monitor connection count

### Reliability
- Implement reconnection logic
- Handle network interruptions
- Store interaction history
- Support workflow resume after disconnect

## 🚢 Deployment

### Docker
```bash
docker-compose up orchestrator
```

### Kubernetes
```yaml
apiVersion: v1
kind: Service
metadata:
  name: orchestrator
spec:
  ports:
  - port: 8100
    protocol: TCP
  type: LoadBalancer
```

### Environment Variables
```bash
ORCHESTRATOR_URL=http://localhost:8100
WEBSOCKET_URL=ws://localhost:8100
```

## 📞 Support

### Documentation
- [WEBSOCKET_GUIDE.md](WEBSOCKET_GUIDE.md) - API reference
- [MULTI_STEP_INTERACTIONS.md](MULTI_STEP_INTERACTIONS.md) - Architecture
- [WORKFLOW_RESUME_FIX_COMPLETE.md](WORKFLOW_RESUME_FIX_COMPLETE.md) - Recent fixes

### Examples
- `examples/websocket_interactive_workflow.py` - Python example
- `examples/rest_interactive_workflow.sh` - Shell script example

### Logs
```bash
# View orchestrator logs
tail -f /tmp/services.log | grep -E "RESUMING|user_input|PAUSED"

# View agent logs
tail -f logs/research_agent.log
```

## ✅ Feature Checklist

- [x] Multi-step sequential interactions
- [x] WebSocket bidirectional communication
- [x] Real-time workflow updates
- [x] Automatic request_id generation
- [x] Workflow pause/resume
- [x] State persistence
- [x] Multiple concurrent workflows
- [x] Connection management
- [x] Error handling
- [x] Comprehensive logging

## 🎉 Success Criteria

Your interactive workflow is working correctly when:

✅ Workflow pauses when agent needs input  
✅ You receive request_id for EACH question  
✅ Workflow resumes after each response  
✅ Agent can ask multiple follow-up questions  
✅ Workflow completes with all context  
✅ All interactions logged properly  

## 📝 Summary

The A2A Multi-Agent System provides a **production-ready** framework for building interactive, conversational workflows where agents can:

- Ask clarifying questions
- Gather context iteratively
- Verify assumptions
- Refine understanding
- Provide comprehensive responses

All while maintaining **real-time communication** with users through WebSocket or REST APIs.

---

**Get Started**: Run `./QUICK_START_WEBSOCKET.sh` to see examples  
**Documentation**: See [WEBSOCKET_GUIDE.md](WEBSOCKET_GUIDE.md) for complete API reference  
**Support**: Check logs in `/tmp/services.log` for debugging  
