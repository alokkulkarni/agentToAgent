# Distributed A2A Multi-Agent System - Architecture Guide

## 🏗️ Overview

This is a **fully distributed** A2A Multi-Agent System where each component is a standalone, independently deployable service. Services communicate via HTTP/REST using the A2A protocol.

## 📦 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Registry Service                       │
│                  (Port 8000)                            │
│  - Agent Registration                                   │
│  - Capability Discovery                                 │
│  - Health Monitoring                                    │
└─────────────────┬───────────────────────────────────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
┌───────▼──────────┐   ┌────▼─────────────────────┐
│  Orchestrator    │   │   Agent Services         │
│  Service         │◄──┤   (Ports 8001+)          │
│  (Port 8100)     │   │                          │
│                  │   │  - Code Analyzer (8001)  │
│  Connects to:    │   │  - Data Processor (8002) │
│  - Registry      │   │  - Research Agent (8003) │
│  - Agents (A2A)  │   │  - Task Executor (8004)  │
│                  │   │  - Observer (8005)       │
└──────────────────┘   └──────────────────────────┘
         │
         │ A2A Protocol (HTTP)
         │
         ▼
    User/Client
```

## 🔧 Components

### 1. **Registry Service** (Port 8000)
**Location:** `services/registry/`

Standalone FastAPI service that manages:
- Agent registration and discovery
- Capability tracking
- Heartbeat monitoring
- Agent metadata storage

**Endpoints:**
- `POST /api/registry/register` - Register agent
- `DELETE /api/registry/unregister/{agent_id}` - Unregister
- `POST /api/registry/heartbeat/{agent_id}` - Heartbeat
- `GET /api/registry/discover` - Discover agents
- `GET /api/registry/agents` - List all agents
- `GET /api/registry/capabilities` - List capabilities
- `GET /api/registry/stats` - Get statistics

### 2. **Orchestrator Service** (Port 8100)
**Location:** `services/orchestrator/`

Standalone service that:
- Connects to Registry to discover agents
- Uses Bedrock LLM for task planning
- Orchestrates multi-agent workflows
- Communicates with agents via A2A protocol

**Endpoints:**
- `POST /api/workflow/execute` - Execute workflow
- `GET /api/workflow/{workflow_id}` - Get workflow status
- `GET /api/agents` - List available agents

### 3. **Agent Services** (Ports 8001+)
**Location:** `services/agents/*/`

Each agent is a standalone FastAPI service that:
- Registers with Registry on startup
- Sends periodic heartbeats
- Exposes capabilities via API
- Executes tasks independently

**Agent Endpoints:**
- `GET /health` - Health check
- `GET /api/capabilities` - Get capabilities
- `POST /api/task` - Execute task

#### Available Agents:

**Code Analyzer** (Port 8001)
- `analyze_python_code` - AST-based analysis
- `explain_code` - LLM explanation
- `suggest_improvements` - LLM suggestions

**Data Processor** (Port 8002)
- `transform_data` - Format transformation
- `analyze_data` - LLM analysis
- `summarize_data` - LLM summarization

**Research Agent** (Port 8003)
- `answer_question` - Q&A with LLM
- `generate_report` - Report generation
- `compare_concepts` - Concept comparison

**Task Executor** (Port 8004)
- `execute_command` - Command execution
- `file_operations` - File I/O
- `wait_task` - Timed waiting

**Observer** (Port 8005)
- `system_monitoring` - System status
- `event_logging` - Event tracking
- `metrics_reporting` - Metrics

## 🚀 Deployment Options

### Option 1: Local Development (Individual Processes)

```bash
# Terminal 1 - Start Registry
cd services/registry
python app.py

# Terminal 2 - Start Orchestrator
cd services/orchestrator
python app.py

# Terminal 3 - Start Code Analyzer
cd services/agents/code_analyzer
python app.py

# Add more agents as needed...
```

### Option 2: Using Start Script

```bash
# Start all services
./start_services.sh

# Services will run on:
# - Registry: http://localhost:8000
# - Orchestrator: http://localhost:8100
# - Code Analyzer: http://localhost:8001
```

### Option 3: Docker Compose

```bash
# Build and start all services
docker-compose up --build

# Start in background
docker-compose up -d

# Stop all services
docker-compose down
```

### Option 4: Kubernetes (Production)

```yaml
# Deploy to K8s cluster
kubectl apply -f k8s/

# Services will be:
# - registry-service
# - orchestrator-service
# - code-analyzer-agent
# - etc...
```

## 📝 Configuration

Each service has its own `.env` file:

### Registry (`services/registry/.env`)
```env
REGISTRY_HOST=0.0.0.0
REGISTRY_PORT=8000
HEARTBEAT_TIMEOUT=60
```

### Orchestrator (`services/orchestrator/.env`)
```env
ORCHESTRATOR_NAME=MainOrchestrator
ORCHESTRATOR_PORT=8100
REGISTRY_URL=http://localhost:8000
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
```

### Agent (`services/agents/code_analyzer/.env`)
```env
AGENT_NAME=CodeAnalyzer
AGENT_PORT=8001
REGISTRY_URL=http://localhost:8000
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
```

## 🔄 Service Lifecycle

### 1. **Registry Startup**
```
1. Start FastAPI server
2. Initialize in-memory storage
3. Start heartbeat cleanup task
4. Ready to accept registrations
```

### 2. **Agent Startup**
```
1. Load configuration
2. Initialize capabilities
3. Connect to Registry
4. Register metadata and capabilities
5. Start heartbeat task
6. Ready to receive tasks
```

### 3. **Orchestrator Startup**
```
1. Load configuration
2. Initialize Bedrock client
3. Connect to Registry
4. Register as orchestrator
5. Start heartbeat task
6. Ready to orchestrate workflows
```

## 🔗 Communication Flow

### Registration Flow
```
Agent → POST /api/registry/register → Registry
Registry → Store metadata → Success Response
Agent → Start heartbeat loop
```

### Discovery Flow
```
Orchestrator → GET /api/registry/discover?capability=X → Registry
Registry → Query capability index → Return agents
Orchestrator → Receive agent list with endpoints
```

### Task Execution Flow
```
Client → POST /api/workflow/execute → Orchestrator
Orchestrator → Discover agents → Registry
Orchestrator → Generate plan → Bedrock LLM
Orchestrator → POST /api/task → Agent (via endpoint)
Agent → Execute task → Return result
Orchestrator → Aggregate results → Return to client
```

## 🧪 Testing

### Test Registry
```bash
# Health check
curl http://localhost:8000/health

# Get stats
curl http://localhost:8000/api/registry/stats

# List agents
curl http://localhost:8000/api/registry/agents
```

### Test Agent
```bash
# Health check
curl http://localhost:8001/health

# Get capabilities
curl http://localhost:8001/api/capabilities

# Execute task
curl -X POST http://localhost:8001/api/task \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "test-1",
    "capability": "analyze_python_code",
    "parameters": {
      "code": "def hello(): return \"world\""
    }
  }'
```

### Test Orchestrator
```bash
# List agents
curl http://localhost:8100/api/agents

# Execute workflow
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Analyze Python code and explain it"
  }'
```

## 📊 Monitoring

### Registry Metrics
```bash
# Get registry statistics
curl http://localhost:8000/api/registry/stats | jq
```

### Agent Health
```bash
# Check all agents
for port in 8001 8002 8003; do
  echo "Agent on port $port:"
  curl -s http://localhost:$port/health | jq
done
```

### Workflow Status
```bash
# Get workflow status
curl http://localhost:8100/api/workflow/{workflow_id} | jq
```

## 🔒 Security

### Best Practices
1. **Use HTTPS** in production
2. **API authentication** (JWT tokens)
3. **Rate limiting** on endpoints
4. **Input validation** (Pydantic models)
5. **Network isolation** (VPC/internal networks)
6. **Secrets management** (AWS Secrets Manager, Vault)

### Production Setup
```python
# Add authentication middleware
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

@app.post("/api/task")
async def execute_task(
    task: TaskRequest,
    token: str = Depends(security)
):
    # Verify token
    # Execute task
    pass
```

## 🎯 Scaling

### Horizontal Scaling
```yaml
# Docker Compose with replicas
services:
  code-analyzer:
    deploy:
      replicas: 3
    # Load balancer will distribute
```

### Load Balancing
```
Client → Load Balancer → [Agent Instance 1]
                      → [Agent Instance 2]
                      → [Agent Instance 3]
```

### Database Backend
Replace in-memory storage with:
- **PostgreSQL** for agent registry
- **Redis** for caching and pub/sub
- **MongoDB** for workflow history

## 📦 Adding New Agents

1. **Create agent directory**
```bash
mkdir services/agents/my_agent
```

2. **Create `app.py`**
```python
# Copy from code_analyzer/app.py
# Modify capabilities
# Update agent name and port
```

3. **Create `requirements.txt`**
4. **Create `.env.example`**
5. **Create `Dockerfile`**
6. **Add to `docker-compose.yml`**
7. **Start and test**

## 🌐 API Documentation

Each service provides OpenAPI docs:
- Registry: http://localhost:8000/docs
- Orchestrator: http://localhost:8100/docs
- Agents: http://localhost:8001/docs

## ✨ Benefits of Distributed Architecture

✅ **Independent Deployment** - Deploy/update services separately
✅ **Scalability** - Scale agents independently
✅ **Resilience** - Single agent failure doesn't affect others
✅ **Technology Flexibility** - Use different tech stacks
✅ **Team Autonomy** - Teams own their services
✅ **Resource Optimization** - Allocate resources per service
✅ **Easy Testing** - Test services in isolation
✅ **Production Ready** - Deploy on any cloud platform

---

**Ready to deploy your distributed A2A system!** 🚀
