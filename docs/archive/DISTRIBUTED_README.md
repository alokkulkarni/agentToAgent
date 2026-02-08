# 🚀 Quick Start - Distributed A2A System

## Overview

This is a **fully distributed A2A Multi-Agent System** where:
- ✅ **Registry** runs as standalone service (Port 8000)
- ✅ **Orchestrator** runs as standalone service (Port 8100)
- ✅ **Each Agent** runs as standalone service (Ports 8001+)
- ✅ All communicate via **A2A Protocol over HTTP/REST**
- ✅ Each can be **deployed independently**

## 🏗️ Architecture

```
Registry (8000)  ←→  Orchestrator (8100)  ←→  Client
    ↕                      ↕
Agents (8001-8005)   (Discovery & Tasks)
```

## ⚡ Quick Start (3 Minutes)

### Step 1: Configure Environment

```bash
# Registry service (no AWS needed)
cp services/registry/.env.example services/registry/.env

# Orchestrator service (needs AWS)
cp services/orchestrator/.env.example services/orchestrator/.env
# Edit and add your AWS credentials

# Code Analyzer agent (needs AWS)
cp services/agents/code_analyzer/.env.example services/agents/code_analyzer/.env
# Edit and add your AWS credentials
```

### Step 2: Start Services

**Option A: Using start script (Recommended)**
```bash
./start_services.sh
```

**Option B: Manual (separate terminals)**
```bash
# Terminal 1: Registry
cd services/registry && python app.py

# Terminal 2: Orchestrator  
cd services/orchestrator && python app.py

# Terminal 3: Code Analyzer Agent
cd services/agents/code_analyzer && python app.py
```

**Option C: Docker Compose**
```bash
docker-compose up --build
```

### Step 3: Verify System

```bash
# Test all services
python test_distributed_system.py
```

## 📊 What You Get

### Services Running:

1. **Registry Service** (http://localhost:8000)
   - Agent registration
   - Capability discovery
   - Health monitoring

2. **Orchestrator Service** (http://localhost:8100)
   - Workflow orchestration
   - LLM-powered planning
   - Multi-agent coordination

3. **Code Analyzer Agent** (http://localhost:8001)
   - Python code analysis
   - Code explanation (LLM)
   - Improvement suggestions (LLM)

## 🧪 Test It Out

### 1. Check Registry
```bash
curl http://localhost:8000/health | jq
curl http://localhost:8000/api/registry/agents | jq
```

### 2. Call Agent Directly
```bash
curl -X POST http://localhost:8001/api/task \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "test-1",
    "capability": "analyze_python_code",
    "parameters": {
      "code": "def hello(): return '\''world'\''"
    }
  }' | jq
```

### 3. Execute Workflow via Orchestrator
```bash
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Analyze a Python function"
  }' | jq
```

## 📚 API Documentation

Each service provides interactive docs:
- Registry: http://localhost:8000/docs
- Orchestrator: http://localhost:8100/docs  
- Code Analyzer: http://localhost:8001/docs

## 🎯 Adding More Agents

### 1. Copy agent template
```bash
cp -r services/agents/code_analyzer services/agents/my_agent
```

### 2. Modify configuration
```bash
# Edit services/agents/my_agent/.env
AGENT_NAME=MyAgent
AGENT_PORT=8006  # Use unique port
```

### 3. Update capabilities in `app.py`
```python
capabilities=[
    AgentCapability(
        name="my_capability",
        description="What my agent does"
    )
]
```

### 4. Start the agent
```bash
cd services/agents/my_agent
python app.py
```

The agent will:
- ✅ Automatically register with Registry
- ✅ Send heartbeats
- ✅ Be discovered by Orchestrator
- ✅ Accept tasks via A2A protocol

## 🔧 Configuration

### Registry
- No AWS credentials needed
- Runs on port 8000
- In-memory storage (can add database)

### Orchestrator & Agents
- **Required:** AWS credentials
- **Required:** Bedrock access enabled
- **Model:** Claude 3.5 Sonnet (configurable)

### Ports
- 8000: Registry
- 8100: Orchestrator
- 8001: Code Analyzer
- 8002: Data Processor
- 8003: Research Agent
- 8004: Task Executor
- 8005: Observer

## 🐳 Docker Deployment

```bash
# Build and run
docker-compose up --build

# Run in background
docker-compose up -d

# View logs
docker-compose logs -f orchestrator

# Stop all
docker-compose down
```

## 📈 Scaling

### Horizontal Scaling
```bash
# Start multiple instances of same agent
cd services/agents/code_analyzer

# Instance 1 (port 8001)
AGENT_PORT=8001 python app.py &

# Instance 2 (port 8011)
AGENT_PORT=8011 python app.py &

# Instance 3 (port 8021)
AGENT_PORT=8021 python app.py &
```

All instances register independently. Orchestrator can use any available instance.

## 🔍 Monitoring

### Service Health
```bash
# Check all services
for port in 8000 8100 8001; do
  echo "Port $port:"
  curl -s http://localhost:$port/health | jq .status
done
```

### Registry Stats
```bash
curl http://localhost:8000/api/registry/stats | jq
```

### Active Workflows
```bash
curl http://localhost:8100/api/workflow/{workflow_id} | jq
```

## 🚨 Troubleshooting

### Services won't start
```bash
# Check ports are free
lsof -i :8000
lsof -i :8100
lsof -i :8001

# Kill if needed
kill -9 <PID>
```

### Agent not registering
```bash
# Check Registry is running
curl http://localhost:8000/health

# Check agent logs for errors
# Verify REGISTRY_URL in agent's .env
```

### Bedrock errors
```bash
# Verify AWS credentials
aws sts get-caller-identity

# Check Bedrock access
aws bedrock list-foundation-models --region us-east-1
```

## 📖 Documentation

- `DISTRIBUTED_ARCHITECTURE.md` - Complete architecture guide
- `README.md` - Original README
- `TECHNICAL_DOCS.md` - Technical details
- Each service has `/docs` endpoint

## ✨ Benefits

✅ **Independent Deployment** - Update one service without touching others
✅ **Scalability** - Run multiple instances of any service
✅ **Resilience** - Service failures are isolated
✅ **Flexibility** - Add agents without code changes
✅ **Production Ready** - Deploy on any cloud platform
✅ **Team Autonomy** - Teams can own their services
✅ **Easy Testing** - Test services in isolation

## 🎓 What's Different from Monolith?

### Before (Monolithic):
```python
# All in one process
registry = AgentRegistry()
orchestrator = Orchestrator(registry)
agent = Agent(registry)
# All share same memory/process
```

### Now (Distributed):
```
Registry Service (Process 1, Port 8000)
Orchestrator Service (Process 2, Port 8100)
Agent Service (Process 3, Port 8001)
# Communicate via HTTP/A2A Protocol
```

## 🔐 Production Checklist

- [ ] Add HTTPS/TLS
- [ ] Implement authentication (JWT)
- [ ] Add rate limiting
- [ ] Use external database for Registry
- [ ] Set up monitoring (Prometheus)
- [ ] Configure logging (ELK stack)
- [ ] Use secrets manager
- [ ] Set up CI/CD pipelines
- [ ] Configure auto-scaling
- [ ] Add load balancers

## 🌟 Next Steps

1. **Run the system**: `./start_services.sh`
2. **Test it**: `python test_distributed_system.py`
3. **Add an agent**: Copy code_analyzer template
4. **Build workflows**: Use orchestrator API
5. **Deploy**: Use Docker or K8s

---

**Your distributed A2A system is ready!** 🎉

For detailed documentation, see `DISTRIBUTED_ARCHITECTURE.md`
