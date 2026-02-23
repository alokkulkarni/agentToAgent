# 🚀 A2A System - Quick Reference Card

## Start Services
```bash
./start_services.sh
```

## Stop Services
```bash
./stop_services.sh
```

## Test System
```bash
# Comprehensive test suite
bash run_all_tests.sh

# Interactive workflow test
python3 test_interactive_complete.py

# WebSocket test
python3 test_websocket_interactive.py
```

## Basic Usage

### Simple Task
```bash
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Calculate 25 + 17"}'
```

### Interactive Task
```bash
# 1. Start workflow
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Research cloud computing trends",
    "workflow_id": "research_001"
  }'

# 2. Check status (will show waiting_for_input if paused)
curl http://localhost:8100/api/workflow/research_001/status

# 3. Respond to input request
curl -X POST http://localhost:8100/api/workflow/research_001/respond \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "req_xxx",
    "response": "Focus on AWS, Azure, and Google Cloud"
  }'

# 4. Check status again
curl http://localhost:8100/api/workflow/research_001/status
```

## WebSocket Connection

```javascript
// Connect
const ws = new WebSocket('ws://localhost:8100/ws/workflow/my_workflow_id');

// Listen for events
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'user_input_required') {
    // Show question to user
    console.log('Question:', data.interaction.question);
    
    // Get user response
    const response = prompt(data.interaction.question);
    
    // Send response
    ws.send(JSON.stringify({
      type: 'user_response',
      request_id: data.interaction.request_id,
      response: response
    }));
  }
};
```

## Service Endpoints

| Service | Port | URL |
|---------|------|-----|
| Registry | 8000 | http://localhost:8000 |
| Orchestrator | 8100 | http://localhost:8100 |
| MCP Registry | 8200 | http://localhost:8200 |
| MCP Gateway | 8300 | http://localhost:8300 |
| Calculator | 8213 | http://localhost:8213 |
| Code Analyzer | 8001 | http://localhost:8001 |
| Data Processor | 8002 | http://localhost:8002 |
| Research Agent | 8003 | http://localhost:8003 |
| Task Executor | 8004 | http://localhost:8004 |
| Observer | 8005 | http://localhost:8005 |
| Math Agent | 8006 | http://localhost:8006 |

## Available Capabilities

### Math & Calculations
- `calculate` - Basic math (add, subtract, multiply, divide)
- `advanced_math` - Power, sqrt, trigonometry
- `solve_equation` - Solve mathematical equations
- `statistics` - Mean, median, standard deviation

### Research & Knowledge
- `answer_question` - Answer questions using LLM
- `generate_report` - Create detailed reports
- `compare_concepts` - Compare and contrast

### Data Processing
- `transform_data` - Convert between formats
- `analyze_data` - Extract insights
- `summarize_data` - Summarize large datasets

### Code Analysis
- `analyze_python_code` - AST analysis
- `explain_code` - Explain functionality
- `suggest_improvements` - Code optimization

### System
- `execute_command` - Run system commands
- `file_operations` - File read/write
- `system_monitoring` - Monitor metrics

## Example Tasks

### Math
```
"Calculate 25 + 17, then square the result"
```

### Research  
```
"Research cloud computing trends and generate a report"
```

### Interactive
```
"Research and analyze potential competitors in the market"
```

### Data Analysis
```
"Analyze the growth trends in cloud computing adoption"
```

### Code
```
"Analyze this Python code and suggest improvements: [code]"
```

## Troubleshooting

### Services won't start
```bash
# Check if ports are in use
lsof -i :8000
lsof -i :8100

# Kill processes if needed
kill <PID>
```

### Database issues
```bash
# Check database
sqlite3 services/orchestrator/workflows.db ".tables"

# Reset database
rm services/orchestrator/workflows.db
# Restart services (will recreate)
```

### Agent not responding
```bash
# Check agent health
curl http://localhost:8001/health  # Code Analyzer
curl http://localhost:8002/health  # Data Processor
curl http://localhost:8003/health  # Research Agent

# Check registry
curl http://localhost:8000/api/registry/agents
```

### WebSocket connection fails
```bash
# Check if orchestrator is running
curl http://localhost:8100/health

# Check WebSocket endpoint
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  http://localhost:8100/ws/workflow/test
```

## Logs

### View Service Logs
Services print to stdout/stderr. If running in background:
```bash
# Check process output
ps aux | grep python.*services

# Or run in foreground for one service
cd services/orchestrator
python3 app.py
```

### Database Queries
```bash
sqlite3 services/orchestrator/workflows.db

# List workflows
SELECT workflow_id, status, created_at FROM workflows;

# Check interactions
SELECT request_id, question, status FROM interaction_requests;

# View conversation
SELECT role, content FROM conversation_messages WHERE workflow_id='xxx';
```

## Configuration

### AWS Credentials
```bash
aws configure
# Or set environment variables:
export AWS_ACCESS_KEY_ID=xxx
export AWS_SECRET_ACCESS_KEY=xxx
export AWS_DEFAULT_REGION=us-east-1
```

### Change LLM Model
Edit `services/orchestrator/app.py`:
```python
BEDROCK_MODEL_ID = "anthropic.claude-3-5-sonnet-20241022-v2:0"
```

## Documentation

| File | Description |
|------|-------------|
| README.md | Main documentation |
| FINAL_REPORT.md | Complete implementation summary |
| SYSTEM_COMPLETE.md | Detailed completion report |
| INTERACTIVE_WORKFLOW_GUIDE.md | User guide |
| WEBSOCKET_QUICK_START.md | WebSocket tutorial |
| INTERACTIVE_WORKFLOW_EXAMPLES.md | Example tasks |
| TESTING_GUIDE.md | Testing procedures |

## Support

For issues:
1. Check logs for errors
2. Verify services are running
3. Test with simple task first
4. Check database for state
5. Review documentation

---

**Version**: 2.0  
**Last Updated**: February 8, 2026  
**Status**: Production Ready ✅
