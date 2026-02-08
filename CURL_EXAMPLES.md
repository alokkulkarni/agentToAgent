# A2A Protocol - cURL Examples

## Quick Reference for Testing the Orchestrator

### 1. Check Orchestrator Health

```bash
curl http://localhost:8100/health | jq .
```

### 2. List All Registered Agents

```bash
curl http://localhost:8100/api/agents | jq .
```

### 3. Execute a Simple Workflow

```bash
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Research the benefits of microservices architecture",
    "workflow_id": "simple-research-001"
  }' | jq .
```

### 4. Execute a Multi-Step Research and Comparison Workflow

```bash
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Research the benefits of microservices architecture, then research monolithic architecture, and finally create a detailed comparison report of both",
    "workflow_id": "research-comparison-001"
  }' | jq .
```

### 5. Execute a Code Analysis Workflow

```bash
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Analyze this Python code and explain how it works: def factorial(n): return 1 if n <= 1 else n * factorial(n-1)",
    "workflow_id": "code-analysis-001"
  }' | jq .
```

### 6. Execute a Data Processing Workflow

```bash
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Analyze the growth trends in cloud computing adoption over the past 5 years and provide insights",
    "workflow_id": "data-analysis-001"
  }' | jq .
```

### 7. Get Workflow Status (after execution)

```bash
curl http://localhost:8100/api/workflow/research-comparison-001 | jq .
```

## Registry Service Endpoints

### Check Registry Health

```bash
curl http://localhost:8000/health | jq .
```

### List All Agents in Registry

```bash
curl http://localhost:8000/api/registry/agents | jq .
```

### Get Specific Agent Details

```bash
curl http://localhost:8000/api/registry/agents/{agent_id} | jq .
```

### Get Agents by Capability

```bash
curl http://localhost:8000/api/registry/agents/by-capability/answer_question | jq .
```

### Get Agents by Role

```bash
curl http://localhost:8000/api/registry/agents/by-role/specialized | jq .
```

## Agent Service Endpoints (Direct Access)

### ResearchAgent (Port 8001)

```bash
# Health check
curl http://localhost:8001/health | jq .

# Get capabilities
curl http://localhost:8001/api/capabilities | jq .

# Execute task directly
curl -X POST http://localhost:8001/api/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "direct-task-001",
    "capability": "answer_question",
    "parameters": {
      "question": "What are the benefits of microservices?"
    },
    "context": {}
  }' | jq .
```

### CodeAnalyzer Agent (Port 8002)

```bash
# Execute code analysis
curl -X POST http://localhost:8002/api/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "code-task-001",
    "capability": "analyze_python_code",
    "parameters": {
      "code": "def hello(name):\n    return f\"Hello, {name}!\""
    },
    "context": {}
  }' | jq .
```

### DataProcessor Agent (Port 8003)

```bash
# Execute data analysis
curl -X POST http://localhost:8003/api/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "data-task-001",
    "capability": "analyze_data",
    "parameters": {
      "data": "sales: [100, 150, 200, 250, 300]"
    },
    "context": {}
  }' | jq .
```

## Formatted Output Options

### Pretty Print JSON (with jq)
```bash
curl http://localhost:8100/health | jq '.'
```

### Extract Specific Fields
```bash
# Get only agent names
curl http://localhost:8100/api/agents | jq '.agents[].name'

# Get workflow status
curl http://localhost:8100/api/workflow/my-workflow-001 | jq '.status'

# Get execution results
curl http://localhost:8100/api/workflow/my-workflow-001 | jq '.results'
```

### Save Response to File
```bash
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d @request.json \
  -o response.json
```

## Testing Tips

1. **Always check services are running first:**
   ```bash
   curl http://localhost:8000/health && \
   curl http://localhost:8100/health && \
   curl http://localhost:8001/health && \
   curl http://localhost:8002/health && \
   curl http://localhost:8003/health
   ```

2. **Use workflow IDs to track executions:**
   - Use timestamp: `workflow-$(date +%s)`
   - Use descriptive names: `research-microservices-001`

3. **Monitor logs while testing:**
   ```bash
   # In separate terminals
   tail -f logs/orchestrator.log
   tail -f logs/registry.log
   ```

4. **Test incrementally:**
   - Start with simple single-step tasks
   - Progress to multi-step workflows
   - Test error handling with invalid inputs

## Common Issues

### Port Already in Use
```bash
# Find process using port
lsof -ti:8100

# Kill if needed
kill $(lsof -ti:8100)
```

### Services Not Responding
```bash
# Restart all services
./stop_services.sh
./start_services.sh
```

### Invalid JSON
- Use online JSON validators
- Test with simple requests first
- Check quote escaping in shell
