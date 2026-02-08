# WebSocket Quick Start Guide

## 🚀 Get Started in 3 Minutes

### Prerequisites
- Orchestrator service running
- Agents registered and healthy

---

## Step 1: Install Dependencies

```bash
cd services/orchestrator
pip install websockets==12.0
```

---

## Step 2: Start Services

```bash
# Terminal 1: Start all services
./start_services.sh

# Wait for all services to be healthy
# You should see:
# ✓ Registry running on http://localhost:8000
# ✓ Orchestrator running on http://localhost:8100
# ✓ All agents registered
```

---

## Step 3: Test WebSocket Connection

### Option A: HTML Test Client (Easiest)

```bash
# Open the test client
open services/orchestrator/websocket_test_client.html

# Or serve it:
cd services/orchestrator
python -m http.server 8080
# Then open: http://localhost:8080/websocket_test_client.html
```

**In the UI**:
1. Click "Connect"
2. Enter task: "Add 25 and 17, then square the result"
3. Click "Execute Workflow"
4. Watch real-time updates!
5. When prompted, click your choice
6. Workflow completes!

### Option B: Using websocat (CLI)

```bash
# Install websocat
brew install websocat  # macOS
# or: cargo install websocat

# Connect
websocat ws://localhost:8100/ws/workflow/test_123

# You'll see:
# {"type": "connection_established", "workflow_id": "test_123", ...}

# Submit workflow via curl in another terminal
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Analyze sample data",
    "workflow_id": "test_123"
  }'

# Watch updates stream in websocat terminal!
```

### Option C: JavaScript Code

```javascript
const ws = new WebSocket('ws://localhost:8100/ws/workflow/my_workflow');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data.type, data);
  
  if (data.type === 'user_input_required') {
    // Show question to user
    const answer = prompt(data.interaction.question);
    
    // Send response
    ws.send(JSON.stringify({
      type: 'user_response',
      request_id: data.interaction.request_id,
      response: answer
    }));
  }
};

// Submit workflow
fetch('http://localhost:8100/api/workflow/execute', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    task_description: 'Analyze this code',
    workflow_id: 'my_workflow'
  })
});
```

### Option D: Python Client

```python
import asyncio
import websockets
import json

async def test_workflow():
    uri = "ws://localhost:8100/ws/workflow/test_workflow"
    
    async with websockets.connect(uri) as ws:
        print("✓ Connected!")
        
        async for message in ws:
            data = json.loads(message)
            print(f"📨 {data['type']}")
            
            if data['type'] == 'user_input_required':
                print(f"❓ {data['interaction']['question']}")
                for i, opt in enumerate(data['interaction']['options'], 1):
                    print(f"  {i}. {opt}")
                
                choice = input("Choose: ")
                selected = data['interaction']['options'][int(choice)-1]
                
                await ws.send(json.dumps({
                    'type': 'user_response',
                    'request_id': data['interaction']['request_id'],
                    'response': selected
                }))

asyncio.run(test_workflow())
```

---

## Message Types Reference

### Client → Server
- `ping` - Keep alive
- `get_status` - Request status
- `user_response` - Answer question
- `cancel_workflow` - Cancel execution
- `get_conversation` - Get history

### Server → Client
- `connection_established` - Connected
- `workflow_status` - Current state
- `step_started` - Step began
- `step_completed` - Step finished
- `user_input_required` - Need answer ⭐
- `response_received` - Got answer
- `workflow_resuming` - Continuing
- `workflow_completed` - Done!
- `error` - Something failed

---

## Example Interactive Workflow

### Test Task: Math Workflow

```bash
Task: "Add 25 and 17, then square the result"

Timeline:
├─ 00:00 - Workflow starts
├─ 00:01 - Step 1: Calculate 25 + 17
│  └─ Result: 42
├─ 00:02 - Step 2: Square 42
│  └─ Agent detects: Multiple squaring methods
│  └─ ❓ PAUSE: "Which method? (power function / multiply)"
├─ 00:10 - User responds: "power function"
├─ 00:11 - Workflow resumes
├─ 00:12 - Step 2 completes
│  └─ Result: 1764
└─ 00:13 - ✅ Workflow complete!
```

### Test Task: Code Analysis

```bash
Task: "Analyze this Python code and suggest improvements"

Timeline:
├─ 00:00 - Workflow starts
├─ 00:01 - Step 1: Code analysis begins
│  └─ Found 10 issues (3 critical, 5 high, 2 medium)
│  └─ ❓ PAUSE: "How should I proceed?"
│     • Fix all automatically
│     • Fix only critical/high
│     • Show details first
├─ 00:08 - User: "Fix only critical/high"
├─ 00:09 - Workflow resumes
├─ 00:10 - Applies 8 fixes (skips 2 medium)
└─ 00:15 - ✅ Complete with detailed report
```

---

## Troubleshooting

### Connection Refused
```bash
# Check orchestrator is running
curl http://localhost:8100/health

# If not running:
cd services/orchestrator
python app.py
```

### Module Not Found: websockets
```bash
pip install websockets==12.0
```

### No Interaction Happening
```bash
# Check agents are upgraded
ls -lh services/agents/*/app.py

# Should see recent timestamps
# Code analyzer, data processor, research agent should be ~15KB

# If old versions, agents need upgrading
```

### WebSocket Handler Not Initialized
```bash
# Check database tables exist
cd services/orchestrator
python -c "from database import WorkflowDatabase; db = WorkflowDatabase(); db.init_interaction_tables()"
```

---

## Files Added

```
services/orchestrator/
├── websocket_handler.py           # WebSocket management (NEW)
├── websocket_test_client.html     # Test UI (NEW)
├── app.py                          # Updated with WebSocket endpoint
└── requirements.txt                # Added websockets==12.0

shared/
└── agent_interaction.py            # Agent interaction helpers (from agents upgrade)

services/agents/
├── code_analyzer/app.py            # Upgraded for interaction
├── data_processor/app.py           # Upgraded for interaction
└── research_agent/app.py           # Upgraded for interaction
```

---

## What You Get

✅ **Real-Time Updates**: See workflow progress instantly  
✅ **Interactive**: AI asks questions when needed  
✅ **Bidirectional**: Server and client both initiate communication  
✅ **Multi-Client**: Multiple users can watch same workflow  
✅ **Persistent**: Connections survive across steps  
✅ **Graceful**: Handles disconnects and reconnects  
✅ **REST Alternative**: Can use HTTP POST for responses too  

---

## Production Considerations

Before deploying:
- [ ] Add authentication (JWT tokens)
- [ ] Enable SSL/TLS (wss://)
- [ ] Set connection limits
- [ ] Add rate limiting
- [ ] Configure timeouts
- [ ] Add metrics/monitoring
- [ ] Test load balancing
- [ ] Document security model

---

**That's it! You now have a fully interactive AI collaboration system!** 🎉

For more details, see `WEBSOCKET_IMPLEMENTATION.md`
