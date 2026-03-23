# A2A Multi-Agent System

**Agent-to-Agent Communication Framework with LLM-Powered Orchestration**

A distributed multi-agent system that enables autonomous agents to collaborate on complex tasks using LLM-based planning, MCP (Model Context Protocol) for tool integration, and intelligent workflow orchestration.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11–3.13 **or** Docker + Docker Compose
- AWS credentials with access to Amazon Bedrock

### Option 1: Shell Script (Local Development)
```bash
# 1. Configure AWS credentials
aws configure

# 2. Set up Python virtual environment and install dependencies
./setup.sh

# 3. Start all services
./start_services.sh

# 4. Send a test workflow request
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Add 25 and 17, then square the result"}'

# 5. Stop all services when done
./stop_services.sh
```

### Option 2: Docker Compose (Production-Ready)
```bash
# 1. Configure AWS credentials (one-time)
aws configure

# 2. Start all services (automatically uses ~/.aws credentials)
docker-compose up -d

# 3. Check that all containers are healthy
docker-compose ps

# 4. Send a test workflow request
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Add 25 and 17, then square the result"}'

# 5. Follow live logs
docker-compose logs -f orchestrator

# 6. Stop all services when done
docker-compose down
```

> **Tip**: No `.env` file is needed for Docker Compose if you have the AWS CLI configured — credentials are mounted from `~/.aws` automatically.

---

## ✨ Key Features

### Core Capabilities
| Feature | Description |
|---------|-------------|
| 🤖 **Autonomous Agent Collaboration** | Agents self-register, discover each other, and collaborate without manual wiring |
| 🧠 **LLM-Powered Workflow Planning** | Claude 3.5 Sonnet (via AWS Bedrock) generates multi-step execution plans from plain-language descriptions |
| 🔧 **MCP Tool Integration** | Model Context Protocol provides a standardised, extensible way to add new tools |
| ⚡ **Parallel Step Execution** | Independent workflow steps run concurrently (2–5× faster than sequential) |
| 🔄 **Automatic Retry with Backoff** | Exponential backoff (1 s → 2 s → 4 s …) with jitter; configurable per-step |
| 🛡️ **Circuit Breaker Protection** | Automatically opens after 5 consecutive failures; half-open recovery after 60 s |
| 💾 **Workflow Persistence** | SQLite-backed state allows workflows to be resumed after process restarts or failures |
| 🔍 **Dynamic Service Discovery** | Agents and MCP servers register at startup; orchestrator queries live capability lists |
| 📊 **Context Enrichment** | Results from earlier steps are automatically injected into the parameters of later steps |

---

## 📋 Overall System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                         CLIENT / USER                         │
└────────────────────────────┬─────────────────────────────────┘
                             │  POST /api/workflow/execute
                             ↓
             ┌───────────────────────────────┐
             │      Orchestrator (8100)       │
             │  LLM Planning · Parallel Exec  │
             │  Retry · Persistence · Context │
             └───────────────┬───────────────┘
                             │
                   ┌─────────┴──────────┐
                   ↓                    ↓
     ┌─────────────────────┐  ┌───────────────────┐
     │   Registry (8000)    │  │  MCP Gateway (8300)│
     │ Agent Discovery      │  │ Tool Routing       │
     │ Health Checks        │  │ LLM Tool Selection │
     └──────────┬───────────┘  └────────┬──────────┘
                │                       │
        ┌───────┴──────┐        ┌───────┴──────────┐
        ↓              ↓        ↓                   ↓
  ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌──────────┐
  │  Agents  │  │  Agents  │  │ MCP Registry │  │ MCP Tools│
  │ 8001-006 │  │ (cont.)  │  │    (8200)    │  │ 8210-213 │
  └──────────┘  └──────────┘  └──────────────┘  └──────────┘
```

### Service Startup Order
Services must start in the following dependency order (handled automatically by both shell scripts and Docker Compose):

1. **Registry** (8000) — must be ready first
2. **MCP Registry** (8200) — parallel with Orchestrator
3. **Orchestrator** (8100) — depends on Registry
4. **MCP Tool Servers** (8210–8213) — depend on MCP Registry
5. **MCP Gateway** (8300) — depends on all MCP tool servers
6. **Agents** (8001–8006) — depend on Registry (Math Agent also depends on MCP Gateway)

---

## 📊 Service Reference

### Core Services

| Service | Port | Description |
|---------|------|-------------|
| Registry | 8000 | Central agent discovery, heartbeat monitoring, capability indexing |
| Orchestrator | 8100 | LLM-based workflow planning, parallel/sequential execution, persistence |

### MCP Services

| Service | Port | Description |
|---------|------|-------------|
| MCP Registry | 8200 | MCP server and tool discovery, server health tracking |
| MCP Gateway | 8300 | Routes tool calls to the correct MCP server; optional LLM tool selection |

### Agent Services

| Agent | Port | Capabilities |
|-------|------|-------------|
| Code Analyzer | 8001 | `analyze_python_code`, `explain_code`, `suggest_improvements` |
| Data Processor | 8002 | `transform_data`, `analyze_data`, `summarize_data` |
| Research Agent | 8003 | `answer_question`, `generate_report`, `compare_concepts` |
| Task Executor | 8004 | `execute_command`, `file_operations`, `wait_task` |
| Observer | 8005 | `system_monitoring`, `event_logging`, `metrics_reporting`, `agent_statistics` |
| Math Agent | 8006 | `calculate`, `advanced_math`, `solve_equation`, `statistics` |

### MCP Tool Servers

| Server | Port | Tools |
|--------|------|-------|
| File Operations | 8210 | `read_file`, `write_file`, `list_files`, `search_files` |
| Database | 8211 | `query`, `insert`, `update`, `delete`, `create_table` |
| Web Search | 8212 | `search`, `fetch_url` |
| Calculator | 8213 | `add`, `subtract`, `multiply`, `divide`, `power`, `square`, `sqrt`, `abs` |

---

## 🔎 Individual Service Details

### Registry Service (Port 8000)

Central hub for agent self-registration and discovery.

**Features**
- Agents register on startup and send a heartbeat every 30 s
- Stale agents (no heartbeat for 60 s) are automatically removed
- In-memory indexes by capability name and agent role
- Supports role-based and capability-based lookups

**API**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/registry/register` | Register an agent |
| `DELETE` | `/api/registry/unregister/{agent_id}` | Unregister an agent |
| `POST` | `/api/registry/heartbeat/{agent_id}` | Refresh agent heartbeat |
| `GET` | `/api/registry/agents` | List all registered agents |
| `GET` | `/api/registry/agents/{agent_id}` | Get a specific agent |
| `GET` | `/api/registry/discover` | Discover agents by `?capability=` or `?role=` |
| `GET` | `/api/registry/capabilities` | List all capabilities and their agents |
| `GET` | `/api/registry/stats` | Registry statistics |

---

### Orchestrator Service (Port 8100)

Receives plain-language task descriptions, plans multi-step workflows using Claude 3.5 Sonnet, dispatches steps to agents, and aggregates results.

**Features**
- **Workflow phases**: DISCOVER → PLAN (LLM) → EXECUTE → VERIFY → REFLECT
- **Parallel execution**: steps with no inter-dependencies run concurrently (up to `MAX_PARALLEL_STEPS`)
- **Context enrichment**: results from completed steps are automatically substituted into placeholder parameters of later steps
- **Retry**: per-step exponential backoff with configurable `max_retries`
- **Circuit breaker**: per-agent; opens after 5 failures, enters half-open recovery after 60 s
- **Persistence**: every workflow and step is saved to SQLite; failed workflows can be resumed

**API**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/workflow/execute` | Start a new workflow |
| `GET` | `/api/workflow/{workflow_id}` | Get workflow status and results |
| `GET` | `/api/workflows` | List all workflows (with optional status filter) |
| `POST` | `/api/workflow/{workflow_id}/resume` | Resume a failed or paused workflow |
| `GET` | `/health` | Health check |

**Request body for `/api/workflow/execute`**
```json
{
  "task_description": "Add 25 and 17, then square the result"
}
```

---

### MCP Registry (Port 8200)

Discovery service for MCP tool servers.

**Features**
- MCP servers self-register with their list of tools and `base_url`
- Tools are indexed by name for fast lookup
- Supports filtering servers by status

**API**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check |
| `POST` | `/api/mcp/register` | Register an MCP server |
| `DELETE` | `/api/mcp/unregister/{server_id}` | Unregister a server |
| `PUT` | `/api/mcp/heartbeat/{server_id}` | Update server heartbeat |
| `GET` | `/api/mcp/servers` | List all registered MCP servers |
| `GET` | `/api/mcp/servers/{server_id}` | Get a specific server |
| `GET` | `/api/mcp/tools` | List all tools across all servers |
| `GET` | `/api/mcp/tools/{tool_name}` | Find servers that provide a specific tool |
| `GET` | `/api/mcp/discovery` | Full discovery (servers + tool summary) |

---

### MCP Gateway (Port 8300)

Routes tool execution requests to the correct MCP server. Optionally uses Claude 3.5 Sonnet to intelligently select tools from a natural-language query.

**Features**
- Direct tool execution by name: `POST /api/gateway/execute`
- Natural-language query processing with LLM tool selection: `POST /api/gateway/query`
- Prefers a specific server when `prefer_server` is supplied
- Falls back to the first available active server

**API**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check |
| `POST` | `/api/gateway/execute` | Execute a named tool directly |
| `POST` | `/api/gateway/query` | Process a natural-language query (LLM selects and executes tools) |
| `GET` | `/api/gateway/tools` | List all available tools |
| `GET` | `/api/gateway/discovery` | Full discovery from MCP Registry |

**Execute a tool directly**
```json
POST /api/gateway/execute
{
  "tool_name": "add",
  "parameters": { "a": 25, "b": 17 }
}
```

**Natural-language query**
```json
POST /api/gateway/query
{
  "query": "What is 25 plus 17?",
  "context": {},
  "auto_execute": true
}
```

---

### Code Analyzer Agent (Port 8001)

Analyzes Python code using both AST-based static analysis and Claude 3.5 Sonnet.

| Capability | LLM | Description |
|-----------|-----|-------------|
| `analyze_python_code` | No | Static AST analysis of code structure |
| `explain_code` | Yes | Plain-English explanation of what code does |
| `suggest_improvements` | Yes | Recommendations for code quality improvements |

**Task request example**
```json
POST /api/task
{
  "capability": "analyze_python_code",
  "parameters": { "code": "def hello(): return 'world'" }
}
```

---

### Data Processor Agent (Port 8002)

Processes and analyses structured data using Claude 3.5 Sonnet.

| Capability | LLM | Description |
|-----------|-----|-------------|
| `transform_data` | No | Convert data between formats (JSON, CSV, etc.) |
| `analyze_data` | Yes | Extract insights and patterns from data |
| `summarize_data` | Yes | Produce a concise summary of a dataset |

---

### Research Agent (Port 8003)

Answers questions and generates reports using Claude 3.5 Sonnet as its knowledge base.

| Capability | LLM | Description |
|-----------|-----|-------------|
| `answer_question` | Yes | Answer a factual or analytical question |
| `generate_report` | Yes | Produce a structured, detailed report on a topic |
| `compare_concepts` | Yes | Compare and contrast two or more concepts |

---

### Task Executor Agent (Port 8004)

General-purpose worker for lightweight automation tasks.

| Capability | LLM | Description |
|-----------|-----|-------------|
| `execute_command` | No | Execute a system command (sandboxed/simulated) |
| `file_operations` | No | Read or write files |
| `wait_task` | No | Wait for a specified duration (useful for testing pipelines) |

---

### Observer Agent (Port 8005)

Collects and reports system-level metrics and events. Does **not** require an LLM.

| Capability | LLM | Description |
|-----------|-----|-------------|
| `system_monitoring` | No | Monitor system activity and track agent metrics |
| `event_logging` | No | Log and retrieve system-level events |
| `metrics_reporting` | No | Produce a metrics report (latency, success rates, etc.) |
| `agent_statistics` | No | Return statistics about registered agents |

---

### Math Agent (Port 8006)

Performs mathematical operations by delegating to the MCP Calculator server via the MCP Gateway. Does **not** require an LLM.

| Capability | LLM | Description |
|-----------|-----|-------------|
| `calculate` | No | Basic arithmetic: `add`, `subtract`, `multiply`, `divide` |
| `advanced_math` | No | Advanced operations: `square`, `sqrt`, `power` |
| `solve_equation` | No | Solve simple equations |
| `statistics` | No | Statistical measures: `mean`, `median`, `sum` over a list of numbers |

---

### MCP Calculator Server (Port 8213)

Provides pure-Python mathematical computations. No LLM required.

| Tool | Parameters | Description |
|------|-----------|-------------|
| `add` | `a`, `b` | Addition |
| `subtract` | `a`, `b` | Subtraction |
| `multiply` | `a`, `b` | Multiplication |
| `divide` | `a`, `b` | Division (raises error if `b == 0`) |
| `power` | `base`, `exponent` | Exponentiation |
| `square` | `value` | Square a number |
| `sqrt` | `value` | Square root (non-negative only) |
| `abs` | `value` | Absolute value |

---

### MCP Database Server (Port 8211)

SQLite-backed database with pre-seeded sample tables (`users`, `products`).

| Tool | Description |
|------|-------------|
| `query` | Execute a SELECT statement |
| `insert` | Insert a row into a table |
| `update` | Update rows matching a condition |
| `delete` | Delete rows matching a condition |
| `create_table` | Create a new table |

---

### MCP File Operations Server (Port 8210)

Sandboxed file system operations within a configurable workspace directory.

| Tool | Description |
|------|-------------|
| `read_file` | Read the contents of a file |
| `write_file` | Write content to a file |
| `list_files` | List files in a directory |
| `search_files` | Search for files matching a pattern |

---

### MCP Web Search Server (Port 8212)

Simulated web search and URL fetching (mock implementation; replace with a real search API for production).

| Tool | Description |
|------|-------------|
| `search` | Return search results for a query |
| `fetch_url` | Fetch and return the content of a URL |

---

## 🚀 Running the System

### Shell Script Deployment (Local)

```bash
# Step 1 — Install dependencies (one-time)
./setup.sh

# Step 2 — Export AWS credentials (or use `aws configure` beforehand)
export AWS_ACCESS_KEY_ID="your_access_key"
export AWS_SECRET_ACCESS_KEY="your_secret_key"
export AWS_REGION="us-east-1"

# Step 3 — Start all 14 services (Registry, Orchestrator, MCP stack, 6 agents)
./start_services.sh

# Step 4 — Verify services are running
curl http://localhost:8000/health    # Registry
curl http://localhost:8100/health    # Orchestrator
curl http://localhost:8200/          # MCP Registry
curl http://localhost:8300/          # MCP Gateway

# Step 5 — Stop all services
./stop_services.sh
```

The `start_services.sh` script:
1. Creates and activates a Python virtual environment
2. Installs dependencies for every service
3. Starts all services in the correct dependency order
4. Prints all service URLs on success

### Docker Compose Deployment

```bash
# Build and start all containers
docker-compose up -d

# Check container status
docker-compose ps

# Tail logs for a specific service
docker-compose logs -f orchestrator
docker-compose logs -f math-agent

# Rebuild after code changes
docker-compose build --no-cache
docker-compose up -d

# Stop and remove containers
docker-compose down

# Stop and remove containers + persistent volumes
docker-compose down -v
```

Docker Compose starts services in the correct dependency order (health-checks ensure the Registry and MCP Registry are ready before dependent services start). AWS credentials are mounted read-only from `~/.aws`.

### Environment Variables

```bash
# Required — AWS Bedrock access
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0

# Optional — Workflow behaviour
MAX_RETRIES=3                 # Per-step retry limit
MAX_PARALLEL_STEPS=5          # Concurrent step limit
HEARTBEAT_INTERVAL=30         # Agent heartbeat frequency (seconds)
HEARTBEAT_TIMEOUT=60          # Time before stale agent is removed (seconds)
LOG_LEVEL=INFO                # Logging verbosity
```

Copy `.env.example` to `.env` and fill in your values, or export them as shell variables.

---

## 💡 Example Workflows

### Multi-Step Math Calculation
```bash
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Add 25 and 17, then square the result"}'
# Executes: add(25,17)=42 → square(42)=1764
```

### Research and Analysis Pipeline
```bash
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Research cloud computing adoption trends, then analyze the data and generate a report"}'
# Executes: answer_question → analyze_data → generate_report
```

### Code Quality Review
```bash
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Analyze this Python function and suggest improvements: def calc(x): return x*x"}'
# Executes: analyze_python_code → suggest_improvements
```

### Direct MCP Tool Call
```bash
# Call the calculator directly through the MCP Gateway (no LLM planning needed)
curl -X POST http://localhost:8300/api/gateway/execute \
  -H "Content-Type: application/json" \
  -d '{"tool_name": "multiply", "parameters": {"a": 6, "b": 7}}'
```

### Registry Inspection
```bash
# List all registered agents
curl http://localhost:8000/api/registry/agents | jq .

# Find agents that can perform a specific capability
curl "http://localhost:8000/api/registry/discover?capability=calculate" | jq .

# List all available MCP tools
curl http://localhost:8200/api/mcp/tools | jq .
```

---

## 🧪 Testing

### Run the Full Integration Test Suite
```bash
# Requires running services
source venv/bin/activate
python test_distributed_system.py
```

### Run MCP-Specific Tests
```bash
python test_mcp_math_agent.py
python test_workflow_detailed.py
```

See [TESTING_GUIDE.md](TESTING_GUIDE.md) for expected output, troubleshooting steps, and a description of each test case.

---

## 🎯 Use Cases

| Use Case | Agents Involved |
|----------|----------------|
| Automated Research & Reporting | Research Agent → Data Processor → Research Agent |
| Code Quality Assessment | Code Analyzer → Code Analyzer |
| Multi-Step Calculations | Math Agent (× N steps) |
| Data Transformation Pipeline | Data Processor (× N steps) |
| Database Query + Analysis | Math Agent / Task Executor + Data Processor |

---

## 🔒 Security

- AWS credentials are passed via environment variables or IAM roles (never hard-coded)
- Docker volumes mount `~/.aws` as read-only
- MCP tool servers sandbox file operations inside a configurable workspace directory
- Agent heartbeat timeout prevents zombie registrations
- Workflow and step timeouts prevent resource exhaustion

---

## 📈 Performance

| Feature | Impact |
|---------|--------|
| Parallel Execution | 2–5× speedup for independent workflow steps |
| Exponential Backoff | Handles transient failures without overloading agents |
| Circuit Breaker | Stops sending requests to a failing agent, reducing blast radius |
| SQLite Persistence | < 5% overhead; enables cross-restart workflow resumption |
| Connection Pooling | `httpx.AsyncClient` reused across calls per service |

---

## 🛠️ Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11–3.13 |
| Web Framework | FastAPI + Uvicorn |
| HTTP Client | httpx (async) |
| LLM | AWS Bedrock — Claude 3.5 Sonnet |
| Tool Protocol | MCP (Model Context Protocol) |
| Workflow DB | SQLite |
| Containerisation | Docker + Docker Compose |
| Async Runtime | asyncio |

---

## 📝 Project Structure

```
agentToAgent/
├── services/
│   ├── registry/             # Agent registry service
│   ├── orchestrator/         # Workflow orchestrator (+ models, database, retry, executor)
│   ├── mcp_registry/         # MCP tool registry service
│   ├── mcp_gateway/          # MCP gateway / router
│   ├── agents/
│   │   ├── code_analyzer/    # Python code analysis agent
│   │   ├── data_processor/   # Data processing agent
│   │   ├── research_agent/   # Research & report agent
│   │   ├── task_executor/    # General task execution agent
│   │   ├── observer/         # System monitoring agent
│   │   └── math_agent/       # Mathematical operations agent
│   └── mcp_servers/
│       ├── calculator/       # MCP calculator tool server
│       ├── database/         # MCP SQLite database server
│       ├── file_ops/         # MCP file operations server
│       └── web_search/       # MCP web search server
├── shared/
│   └── a2a_protocol/         # Shared Pydantic models and HTTP client
├── tests/                    # Test suite
├── docs/                     # Additional documentation
├── docker-compose.yml        # Container orchestration
├── setup.sh                  # One-time environment setup
├── start_services.sh         # Start all services (local)
├── stop_services.sh          # Stop all services (local)
└── .env.example              # Environment variable template
```

### Adding New Agents

1. Create a directory under `services/agents/<agent_name>/`
2. Implement `app.py` using `shared.a2a_protocol` models
3. Register capabilities with the Registry on startup (see any existing agent for the pattern)
4. Add a `Dockerfile` and entry in `docker-compose.yml`
5. Add the startup command to `start_services.sh`

### Adding New MCP Tools

1. Create a directory under `services/mcp_servers/<tool_name>/`
2. Implement `app.py` — expose `/api/tools/execute` and `/api/mcp/tools` endpoints
3. Register with the MCP Registry on startup
4. Add a `Dockerfile` and entry in `docker-compose.yml`

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Detailed system architecture, component design, data-flow diagrams |
| [QUICK_START.md](QUICK_START.md) | Quick-reference command guide |
| [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) | Docker Compose deployment guide |
| [AWS_CREDENTIALS_GUIDE.md](AWS_CREDENTIALS_GUIDE.md) | AWS credential configuration and IAM best practices |
| [DEPLOYMENT_COMPARISON.md](DEPLOYMENT_COMPARISON.md) | Shell-script vs Docker — trade-offs and recommendations |
| [TESTING_GUIDE.md](TESTING_GUIDE.md) | Test procedures, expected outputs, and troubleshooting |
| [CURL_EXAMPLES.md](CURL_EXAMPLES.md) | Ready-to-run API examples for all services |
| [MCP_CURL_EXAMPLES.md](MCP_CURL_EXAMPLES.md) | MCP-specific API examples |
| [ENHANCEMENTS_COMPLETE.md](ENHANCEMENTS_COMPLETE.md) | Feature guide: persistence, retry, and parallel execution |
| [DOCUMENTATION.md](DOCUMENTATION.md) | Documentation index (organised by role and topic) |

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-new-agent`)
3. Make your changes and add tests
4. Submit a pull request

---

## 📄 License

[Add your license here]

---

**Version**: 2.1  
**Last Updated**: 2026-03-23  
**Status**: Production Ready ✅
