# A2A Multi-Agent System

**Agent-to-Agent Communication Framework with LLM-Powered Orchestration**

A distributed multi-agent system that enables autonomous agents to collaborate on complex tasks using LLM-based planning, MCP (Model Context Protocol) for tool integration, and intelligent workflow orchestration.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+ OR Docker + Docker Compose
- AWS credentials for Bedrock LLM

### Option 1: Shell Script (Fast Development)
```bash
# Configure AWS
aws configure

# Setup and start
./setup.sh
./start_services.sh

# Test
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Add 25 and 17, then square the result"}'
```

### Option 2: Docker Compose (Production-Ready)
```bash
# Configure AWS
aws configure

# Start all services
docker-compose up -d

# Test
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Add 25 and 17, then square the result"}'
```

---

## ✨ Key Features

### Core Capabilities
- **🤖 Autonomous Agent Collaboration** - Agents discover and communicate automatically
- **🧠 LLM-Powered Planning** - Claude 3.5 Sonnet generates optimal execution plans
- **🔧 MCP Tool Integration** - Extensible tool ecosystem via Model Context Protocol
- **⚡ Parallel Execution** - Independent tasks run concurrently (2-5x faster)
- **🔄 Automatic Retry** - Exponential backoff with circuit breaker protection
- **💾 Workflow Persistence** - Resume workflows after failures
- **🔍 Service Discovery** - Dynamic agent registration and capability matching

### Agent Types
- **Code Analyzer** - Code quality analysis and suggestions
- **Data Processor** - Data transformation and analysis
- **Research Agent** - Information gathering and synthesis
- **Task Executor** - Command execution and automation
- **Observer** - System monitoring and metrics
- **Math Agent** - Mathematical operations via MCP

### MCP Tools
- **Calculator** - Basic and advanced math operations
- **Database Query** - SQLite database operations
- **File Operations** - File read/write/search
- **Web Search** - Internet search capabilities

---

## 📋 System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Orchestrator (8100)                      │
│              LLM-Based Workflow Planning & Execution         │
└─────────────────────────────────────────────────────────────┘
                            ↓ ↑
┌─────────────────────────────────────────────────────────────┐
│                    Registry (8000)                           │
│                  Agent Service Discovery                     │
└─────────────────────────────────────────────────────────────┘
                            ↓ ↑
┌───────────────┬───────────────┬────────────────┬────────────┐
│ Code Analyzer │ Data Processor│ Research Agent │   Math     │
│    (8001)     │    (8002)     │    (8003)      │  (8006)    │
└───────────────┴───────────────┴────────────────┴────────────┘
                                                       ↓ ↑
┌─────────────────────────────────────────────────────────────┐
│                   MCP Gateway (8300)                         │
│               Tool Request Router & Executor                 │
└─────────────────────────────────────────────────────────────┘
                            ↓ ↑
┌─────────────────────────────────────────────────────────────┐
│                 MCP Registry (8200)                          │
│                Tool Service Discovery                        │
└─────────────────────────────────────────────────────────────┘
                            ↓ ↑
┌──────────┬─────────────┬────────────────┬──────────────────┐
│Calculator│  Database   │  File Ops      │   Web Search     │
│  (8213)  │   (8211)    │   (8210)       │    (8212)        │
└──────────┴─────────────┴────────────────┴──────────────────┘
```

---

## 📊 Service Ports

| Service | Port | Type | Description |
|---------|------|------|-------------|
| Registry | 8000 | Core | Agent discovery |
| Orchestrator | 8100 | Core | Workflow execution |
| MCP Registry | 8200 | MCP | Tool discovery |
| MCP Gateway | 8300 | MCP | Tool routing |
| Code Analyzer | 8001 | Agent | Code analysis |
| Data Processor | 8002 | Agent | Data processing |
| Research Agent | 8003 | Agent | Research tasks |
| Task Executor | 8004 | Agent | Task execution |
| Observer | 8005 | Agent | Monitoring |
| Math Agent | 8006 | Agent | Math operations |
| File Ops | 8210 | Tool | File operations |
| Database | 8211 | Tool | Database queries |
| Web Search | 8212 | Tool | Web search |
| Calculator | 8213 | Tool | Math calculations |

---

## 📚 Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture and design
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Deployment guide (Shell & Docker)
- **[TESTING.md](TESTING.md)** - Testing guide and examples
- **[ENHANCEMENTS.md](ENHANCEMENTS.md)** - New features (persistence, retry, parallel)
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Common issues and solutions
- **[QUICK_START.md](QUICK_START.md)** - Quick reference guide

---

## 🔧 Configuration

### Environment Variables
```bash
# AWS Bedrock Configuration
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0

# Workflow Configuration (Optional)
MAX_RETRIES=3
ENABLE_PARALLEL=true
MAX_PARALLEL_STEPS=5
ENABLE_PERSISTENCE=true
```

---

## 💡 Example Workflows

### Mathematical Operations
```bash
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Add 25 and 17, then square the result"
  }'

# Result: Step 1: 42, Step 2: 1764
```

### Data Analysis
```bash
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Analyze cloud computing adoption trends over 5 years"
  }'

# Result: Research → Analysis → Report (3 steps)
```

### Code Analysis
```bash
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Analyze Python code for quality and security issues"
  }'
```

---

## 🎯 Use Cases

- **Automated Research & Analysis** - Multi-step research with data analysis
- **Code Quality Assessment** - Automated code review workflows
- **Data Processing Pipelines** - Complex data transformation workflows
- **Mathematical Computations** - Multi-step calculations with dependencies
- **Report Generation** - Gather data, analyze, and generate reports

---

## 🔒 Security

- AWS credentials via IAM roles (production) or local config (development)
- Service-to-service communication via internal network
- Tool access controlled via MCP registry
- Workflow isolation and timeout protection

---

## 📈 Performance

- **Parallel Execution**: 2-5x faster for independent steps
- **Automatic Retry**: 95%+ success rate for transient failures
- **Circuit Breaker**: Prevents cascading failures
- **Persistence Overhead**: <5% for workflow tracking

---

## 🛠️ Technology Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI + Uvicorn
- **LLM**: AWS Bedrock (Claude 3.5 Sonnet)
- **Protocol**: MCP (Model Context Protocol)
- **Database**: SQLite (workflow persistence)
- **Deployment**: Docker Compose
- **Async**: asyncio + httpx

---

## 📝 Development

### Project Structure
```
agentToAgent/
├── services/
│   ├── registry/          # Agent service discovery
│   ├── orchestrator/      # Workflow orchestration
│   ├── mcp_registry/      # MCP tool discovery
│   ├── mcp_gateway/       # MCP tool routing
│   ├── agents/            # Specialized agents
│   │   ├── code_analyzer/
│   │   ├── data_processor/
│   │   ├── research_agent/
│   │   ├── task_executor/
│   │   ├── observer/
│   │   └── math_agent/
│   └── mcp_servers/       # MCP tool servers
│       ├── calculator/
│       ├── database/
│       ├── file_ops/
│       └── web_search/
├── shared/                # Shared utilities
├── docker-compose.yml     # Container orchestration
├── start_services.sh      # Shell script deployment
└── stop_services.sh       # Shutdown script
```

### Adding New Agents

1. Create agent directory in `services/agents/`
2. Implement capabilities and register with registry
3. Add to `start_services.sh` and `docker-compose.yml`
4. Document capabilities and API

### Adding New MCP Tools

1. Create tool server in `services/mcp_servers/`
2. Implement tool operations
3. Register with MCP registry
4. Add to MCP gateway routing

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

---

## 📄 License

[Add your license here]

---

## 🔗 Links

- [Architecture Documentation](ARCHITECTURE.md)
- [Deployment Guide](DEPLOYMENT.md)
- [API Documentation](TESTING.md)
- [Enhancement Features](ENHANCEMENTS.md)

---

**Version**: 2.0  
**Last Updated**: 2026-02-07  
**Status**: Production Ready ✅
