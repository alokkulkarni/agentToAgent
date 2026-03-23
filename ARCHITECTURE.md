# A2A System Architecture

**Comprehensive System Architecture and Design Documentation**

Last Updated: 2026-03-23

---

## Table of Contents

1. [Overview](#overview)
2. [High-Level Architecture](#high-level-architecture)
3. [Component Details](#component-details)
4. [Service Communication](#service-communication)
5. [Port Allocation](#port-allocation)
6. [Data Flow](#data-flow)
7. [MCP Integration](#mcp-integration)
8. [Workflow Execution](#workflow-execution)
9. [Scalability & Performance](#scalability--performance)

---

## Overview

The A2A (Agent-to-Agent) Multi-Agent System is a distributed framework that enables autonomous agents to collaborate on complex tasks through:

- **Service Discovery**: Dynamic agent and tool registration with heartbeat-based health tracking
- **LLM Planning**: Claude 3.5 Sonnet generates multi-step execution plans from plain-language descriptions
- **MCP Protocol**: Standardised tool integration via Model Context Protocol
- **Workflow Orchestration**: Intelligent task coordination with parallel execution and context enrichment
- **Fault Tolerance**: Per-step retry with exponential backoff and circuit breaker protection

### Key Principles

1. **Loose Coupling**: Services communicate exclusively via REST APIs
2. **Service Discovery**: Dynamic registration and capability-based matching
3. **Fault Tolerance**: Retry mechanisms, circuit breakers, and workflow persistence
4. **Extensibility**: Add new agents and MCP tools without modifying existing services
5. **Observability**: Structured logging, metrics, and health-check endpoints across all services

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                    │
│                          CLIENT / USER                             │
│                                                                    │
└─────────────────────────────┬──────────────────────────────────────┘
                              │
                              ↓
              ┌───────────────────────────────┐
              │      Orchestrator (8100)       │
              │  - Workflow Planning (LLM)     │
              │  - Parallel Step Execution     │
              │  - Context Enrichment          │
              │  - Persistence & Retry         │
              │  - Circuit Breaker             │
              └───────────────┬───────────────┘
                              │
                     ┌────────┴──────────┐
                     ↓                    ↓
       ┌─────────────────────┐  ┌──────────────────────┐
       │   Registry (8000)    │  │   MCP Gateway (8300)  │
       │  - Agent Discovery   │  │  - Tool Routing       │
       │  - Health Checks     │  │  - LLM Tool Selection │
       │  - Capability Index  │  │  - Load Distribution  │
       └──────────┬───────────┘  └──────────┬────────────┘
                  │                         │
          ┌───────┴────────┐        ┌───────┴──────┐
          ↓                ↓        ↓              ↓
    ┌──────────┐    ┌──────────┐  ┌──────────────┐  ┌──────────────┐
    │ Agents   │    │ Agents   │  │ MCP Registry │  │  MCP Tools   │
    │(8001-    │    │(cont.)   │  │   (8200)     │  │ (8210-8213)  │
    │  8006)   │    │          │  │ Tool Disc.   │  │              │
    └──────────┘    └──────────┘  └──────────────┘  └──────────────┘
```

---

## Component Details

### 1. Core Services

#### Registry Service (Port 8000)
**Purpose**: Central service discovery and agent registration

**Capabilities**:
- Agent registration with role and capabilities
- Heartbeat monitoring (60 s timeout; stale agents auto-removed every 30 s)
- In-memory capability and role indexes for fast lookup
- Agent status tracking

**API Endpoints**:
- `GET /health` — Health check
- `POST /api/registry/register` — Register agent
- `DELETE /api/registry/unregister/{agent_id}` — Unregister agent
- `POST /api/registry/heartbeat/{agent_id}` — Refresh heartbeat
- `GET /api/registry/agents` — List all agents
- `GET /api/registry/agents/{agent_id}` — Get specific agent
- `GET /api/registry/discover` — Discover agents by `?capability=` or `?role=`
- `GET /api/registry/capabilities` — List all capabilities and their agents
- `GET /api/registry/stats` — Registry statistics

**Registration Data Model**:
```python
{
    "metadata": {
        "agent_id": "uuid",
        "name": "AgentName",
        "role": "specialized|worker|observer|orchestrator",
        "endpoint": "http://host:port",
        "has_llm": true,
        "capabilities": [
            {
                "name": "capability_name",
                "description": "...",
                "requires_llm": false
            }
        ]
    }
}
```

#### Orchestrator Service (Port 8100)
**Purpose**: Workflow planning and execution coordination

**Capabilities**:
- LLM-based workflow planning (Claude 3.5 Sonnet)
- Context enrichment between steps (placeholder substitution)
- Parallel step execution with semaphore-based concurrency control
- Per-step retry with exponential backoff and jitter
- Circuit breaker per agent (opens after 5 failures, recovers after 60 s)
- Workflow persistence (SQLite — `workflows` and `steps` tables)
- Result aggregation and workflow status tracking

**Workflow Phases**:
1. **DISCOVER** — Query registry for available agents and capabilities
2. **PLAN** — Send agent list to LLM; receive JSON execution plan
3. **EXECUTE** — Run steps (in parallel where dependencies allow)
4. **VERIFY** — Validate step results
5. **REFLECT** — Log execution metadata

**API Endpoints**:
- `GET /health` — Health check
- `POST /api/workflow/execute` — Start a new workflow
- `GET /api/workflow/{workflow_id}` — Get workflow status and results
- `GET /api/workflows` — List all workflows (optional `?status=` filter)
- `POST /api/workflow/{workflow_id}/resume` — Resume a failed workflow

#### MCP Registry (Port 8200)
**Purpose**: MCP tool-server discovery and registration

**Capabilities**:
- MCP server registration with tool definitions
- Tool name index for fast server lookup
- Server health and status tracking
- Detailed tool schema storage (`input_schema` per tool)

**API Endpoints**:
- `GET /` — Health check
- `POST /api/mcp/register` — Register MCP server
- `DELETE /api/mcp/unregister/{server_id}` — Unregister server
- `PUT /api/mcp/heartbeat/{server_id}` — Update server heartbeat
- `GET /api/mcp/servers` — List all registered servers (optional `?status=` filter)
- `GET /api/mcp/servers/{server_id}` — Get specific server
- `GET /api/mcp/tools` — List all tools across all servers
- `GET /api/mcp/tools/{tool_name}` — Find servers that provide a tool
- `GET /api/mcp/discovery` — Full discovery summary

#### MCP Gateway (Port 8300)
**Purpose**: Route tool execution requests to appropriate MCP servers

**Capabilities**:
- Direct tool execution by name
- Optional LLM-based tool selection from natural-language queries (Claude 3.5 Sonnet)
- Preferred-server selection
- Fallback to first available active server
- Error propagation back to caller

**API Endpoints**:
- `GET /` — Health check
- `POST /api/gateway/execute` — Execute a specific tool
- `POST /api/gateway/query` — Process a natural-language query (LLM selects tools)
- `GET /api/gateway/tools` — List all available tools
- `GET /api/gateway/discovery` — Full discovery from MCP Registry

---

### 2. Agent Services

All agents:
- Self-register with the Registry on startup
- Send heartbeats every 30 s
- Expose `POST /api/task` (A2A task endpoint) and `GET /health`
- Use the shared `TaskRequest` / `TaskResponse` Pydantic models

#### Code Analyzer (Port 8001)
**Role**: `specialized` | **LLM**: Yes (Claude 3.5 Sonnet)

| Capability | LLM | Description |
|-----------|-----|-------------|
| `analyze_python_code` | No | AST-based code structure analysis |
| `explain_code` | Yes | Plain-English explanation of code behaviour |
| `suggest_improvements` | Yes | Quality, security, and style recommendations |

#### Data Processor (Port 8002)
**Role**: `specialized` | **LLM**: Yes (Claude 3.5 Sonnet)

| Capability | LLM | Description |
|-----------|-----|-------------|
| `transform_data` | No | Convert data between formats |
| `analyze_data` | Yes | Extract insights and patterns from data |
| `summarize_data` | Yes | Produce a concise dataset summary |

#### Research Agent (Port 8003)
**Role**: `specialized` | **LLM**: Yes (Claude 3.5 Sonnet)

| Capability | LLM | Description |
|-----------|-----|-------------|
| `answer_question` | Yes | Answer factual or analytical questions |
| `generate_report` | Yes | Produce structured reports on topics |
| `compare_concepts` | Yes | Compare and contrast concepts |

#### Task Executor (Port 8004)
**Role**: `worker` | **LLM**: No

| Capability | LLM | Description |
|-----------|-----|-------------|
| `execute_command` | No | Simulate system command execution |
| `file_operations` | No | File read/write operations |
| `wait_task` | No | Wait for a specified duration |

#### Observer (Port 8005)
**Role**: `observer` | **LLM**: No

| Capability | LLM | Description |
|-----------|-----|-------------|
| `system_monitoring` | No | Monitor system activity and track agent metrics |
| `event_logging` | No | Log and retrieve system events |
| `metrics_reporting` | No | Generate metrics reports |
| `agent_statistics` | No | Return statistics about registered agents |

#### Math Agent (Port 8006)
**Role**: `specialized` | **LLM**: No

Delegates all calculations to the MCP Calculator server via the MCP Gateway.

| Capability | LLM | Description |
|-----------|-----|-------------|
| `calculate` | No | Basic arithmetic (`add`, `subtract`, `multiply`, `divide`) |
| `advanced_math` | No | Advanced operations (`square`, `sqrt`, `power`) |
| `solve_equation` | No | Solve simple equations |
| `statistics` | No | Statistical measures (`mean`, `median`, `sum`) over a list |

---

### 3. MCP Tool Servers

All MCP tool servers:
- Self-register with the MCP Registry on startup (with retry / exponential backoff)
- Expose `POST /api/tools/execute` for tool execution
- Expose `GET /api/mcp/tools` for tool listing
- Expose `GET /health` for health checks

#### Calculator Server (Port 8213)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `add` | `a`, `b` | Addition |
| `subtract` | `a`, `b` | Subtraction |
| `multiply` | `a`, `b` | Multiplication |
| `divide` | `a`, `b` | Division (error if `b == 0`) |
| `power` | `base`, `exponent` | Exponentiation |
| `square` | `value` | Square (`value²`) |
| `sqrt` | `value` | Square root (error if negative) |
| `abs` | `value` | Absolute value |

#### Database Server (Port 8211)

SQLite database pre-seeded with `users` and `products` tables.

| Tool | Description |
|------|-------------|
| `query` | Execute a SELECT statement |
| `insert` | Insert a row into a table |
| `update` | Update rows matching a condition |
| `delete` | Delete rows matching a condition |
| `create_table` | Create a new table |

#### File Operations Server (Port 8210)

File system operations sandboxed to a configurable workspace directory (`WORKSPACE_DIR`).

| Tool | Description |
|------|-------------|
| `read_file` | Read contents of a file |
| `write_file` | Write content to a file |
| `list_files` | List files in a directory |
| `search_files` | Search for files matching a pattern |

#### Web Search Server (Port 8212)

Mock web search (placeholder; replace with a real search API for production).

| Tool | Description |
|------|-------------|
| `search` | Return ranked results for a query |
| `fetch_url` | Fetch and return content from a URL |

---

## Service Communication

### Agent Registration Flow
```
Agent (startup)
  → POST /api/registry/register → Registry
  ← 201 Created + { agent_id }

Agent (every 30 s)
  → POST /api/registry/heartbeat/{agent_id} → Registry
  ← 200 OK
```

### Orchestrator → Agent Task Dispatch
```
Orchestrator
  → GET /api/registry/discover?capability=calculate → Registry
  ← [{ agent_id, endpoint, ... }]

Orchestrator
  → POST /api/task → Agent
  ← { task_id, status, result, ... }
```

### Agent → MCP Tool Execution
```
Agent (e.g. Math Agent)
  → POST /api/gateway/execute { tool_name, parameters } → MCP Gateway

MCP Gateway
  → GET /api/mcp/tools/{tool_name} → MCP Registry
  ← [{ server_id, server_url, ... }]

MCP Gateway
  → POST /api/tools/execute { tool_name, parameters } → MCP Server
  ← { success, result, ... }

MCP Gateway → Agent → Orchestrator
```

### MCP Server Registration
```
MCP Server (startup, with retry)
  → POST /api/mcp/register { name, base_url, tools } → MCP Registry
  ← { server_id, ... }
```

---

## Port Allocation

### Core Services (8000–8100)
- **8000** — Registry Service
- **8100** — Orchestrator Service

### Agent Services (8001–8006)
- **8001** — Code Analyzer
- **8002** — Data Processor
- **8003** — Research Agent
- **8004** — Task Executor
- **8005** — Observer
- **8006** — Math Agent

### MCP Services (8200–8300)
- **8200** — MCP Registry
- **8300** — MCP Gateway

### MCP Tool Servers (8210–8213)
- **8210** — File Operations Server
- **8211** — Database Server
- **8212** — Web Search Server
- **8213** — Calculator Server

---

## Data Flow

### Example: "Add 25 and 17, then square the result"

```
1. CLIENT
   ↓ POST /api/workflow/execute { task_description }

2. ORCHESTRATOR — DISCOVER
   ↓ GET /api/registry/agents
   ← [CodeAnalyzer, DataProcessor, ResearchAgent, MathAgent, ...]

3. ORCHESTRATOR — PLAN (LLM)
   → Claude 3.5 Sonnet: "Given these agents, plan this task"
   ← {
       steps: [
         { step: 1, capability: "calculate", parameters: { operation: "add", a: 25, b: 17 } },
         { step: 2, capability: "advanced_math", parameters: { operation: "square", value: "<result_from_step_1>" } }
       ]
     }

4. ORCHESTRATOR — EXECUTE Step 1
   ↓ GET /api/registry/discover?capability=calculate → MathAgent (8006)
   ↓ POST /api/task { capability: "calculate", parameters: { ... } } → MathAgent

5. MATH AGENT
   ↓ POST /api/gateway/execute { tool_name: "add", parameters: { a: 25, b: 17 } } → MCP Gateway

6. MCP GATEWAY
   ↓ GET /api/mcp/tools/add → MCP Registry
   ← CalculatorServer (8213)
   ↓ POST /api/tools/execute → Calculator
   ← { success: true, result: 42 }
   ↑ Return to MathAgent

7. MATH AGENT
   ↑ Return { result: 42 } to Orchestrator

8. ORCHESTRATOR — CONTEXT ENRICHMENT
   → Replace "<result_from_step_1>" with 42

9. ORCHESTRATOR — EXECUTE Step 2
   ↓ POST /api/task { capability: "advanced_math", parameters: { operation: "square", value: 42 } }
   → [MCP flow repeats: square(42) = 1764]
   ← { result: 1764 }

10. ORCHESTRATOR — AGGREGATE
    ↑ Return to CLIENT

11. CLIENT
    ← {
        workflow_id: "...",
        status: "completed",
        steps_completed: 2,
        results: [
          { step: 1, capability: "calculate", result: { result: 42 } },
          { step: 2, capability: "advanced_math", result: { result: 1764 } }
        ]
      }
```

---

## MCP Integration

### MCP Architecture

Model Context Protocol provides standardised tool integration:

```
┌─────────────────────┐
│   MCP Registry      │
│   - Tool Discovery  │
│   - Server Tracking │
│   - Tool Index      │
└──────────┬──────────┘
           │
           ↓
┌─────────────────────┐
│   MCP Gateway       │
│   - Request Routing │
│   - LLM Selection   │
│   - Load Balance    │
└──────────┬──────────┘
           │
     ┌─────┴──────┬───────────┬───────────┐
     ↓            ↓           ↓           ↓
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│Calculator│ │Database │ │File Ops │ │Web Srch │
│ (8213)   │ │ (8211)  │ │ (8210)  │ │ (8212)  │
└─────────┘ └─────────┘ └─────────┘ └─────────┘
```

### MCP Server Registration Payload
```json
POST /api/mcp/register
{
  "name": "CalculatorServer",
  "description": "Provides basic and advanced mathematical operations",
  "base_url": "http://localhost:8213",
  "tools": [
    {
      "name": "add",
      "description": "Add two numbers",
      "input_schema": {
        "type": "object",
        "properties": {
          "a": { "type": "number" },
          "b": { "type": "number" }
        },
        "required": ["a", "b"]
      }
    }
  ]
}
```

### MCP Tool Execution Payload
```json
POST /api/tools/execute
{
  "tool_name": "add",
  "parameters": { "a": 25, "b": 17 }
}
```

---

## Workflow Execution

### Execution Modes

#### 1. Sequential Execution
Steps execute one after another (when each step depends on the previous):
```
Step 1 → Step 2 → Step 3 → Complete
```

#### 2. Parallel Execution
Independent steps execute concurrently (controlled by `MAX_PARALLEL_STEPS` semaphore):
```
Step 1 ────┐
           ├──→ Step 3 → Complete
Step 2 ────┘
```

### Dependency Management

Steps declare explicit dependencies; the executor waits for all dependencies to complete before starting a step:
```json
{
  "step_id": "step_3",
  "dependencies": ["step_1", "step_2"],
  "capability": "generate_report"
}
```

### Context Enrichment

Results from completed steps are automatically substituted into placeholder parameters:

```python
# Step 1 result
{ "result": 42 }

# Step 2 parameters (before enrichment)
{ "operation": "square", "value": "<result_from_step_1>" }

# Step 2 parameters (after enrichment)
{ "operation": "square", "value": 42 }
```

The orchestrator also applies capability-specific logic (e.g., auto-populating `data` for `analyze_data` from the previous `answer_question` result).

### Retry Policy

```python
RetryPolicy(
    max_retries=3,
    initial_delay_seconds=1.0,
    max_delay_seconds=60.0,
    exponential_base=2.0,    # delay doubles each attempt
    jitter=True,             # ± random jitter prevents thundering herd
    retriable_errors=[       # error substrings that trigger a retry
        "timeout", "connection", "network",
        "temporary", "unavailable", "503", "502", "500"
    ]
)
```

### Circuit Breaker

```python
CircuitBreaker(
    failure_threshold=5,       # open after 5 consecutive failures
    recovery_timeout=60.0,     # seconds before entering half-open state
    half_open_attempts=1       # successful calls needed to close circuit
)
```

States: `closed` → (5 failures) → `open` → (60 s) → `half_open` → (success) → `closed`

### Workflow Persistence (SQLite)

```sql
-- Workflow-level tracking
CREATE TABLE workflows (
    workflow_id TEXT PRIMARY KEY,
    status TEXT,
    task_description TEXT,
    total_steps INTEGER,
    completed_steps INTEGER,
    created_at TEXT,
    updated_at TEXT,
    ...
);

-- Step-level tracking
CREATE TABLE steps (
    step_id TEXT PRIMARY KEY,
    workflow_id TEXT,
    status TEXT,
    capability TEXT,
    retry_count INTEGER,
    ...
);
```

---

## Scalability & Performance

### Horizontal Scaling

**Stateless (freely scalable)**:
- All agent services (8001–8006)
- MCP tool servers (8210–8213)
- MCP Gateway (with shared MCP Registry)

**Stateful (require coordination or shared storage)**:
- Registry — single instance, or cluster with shared database
- Orchestrator — single instance per workflow group, or shared SQLite/PostgreSQL
- MCP Registry — single instance, or cluster with shared database

### Performance Optimisations

1. **Parallel Execution** — 2–5× speedup for independent steps
2. **HTTP Connection Pooling** — `httpx.AsyncClient` reused across requests per service
3. **Circuit Breaker** — Prevents repeated calls to failing agents
4. **Retry with Jitter** — Reduces load spikes after transient failures
5. **Asyncio** — Non-blocking I/O throughout all services

### Resource Usage

| Service | Memory | CPU | Network |
|---------|--------|-----|---------|
| Registry | ~50 MB | Low | Medium |
| Orchestrator | ~100 MB | Medium | High |
| Agents (each) | ~80 MB | Medium | Medium |
| MCP Services (each) | ~50 MB | Low | Low |

---

## Deployment Models

### 1. Local Shell Script (Development)
```bash
./setup.sh
./start_services.sh
# All services on localhost, different ports
```

### 2. Docker Compose (Testing / Staging)
```bash
docker-compose up -d
# All services in containers on a shared bridge network
```

### 3. Kubernetes (Production)
```yaml
# Each service as a Deployment
# Service discovery via Kubernetes DNS
# Ingress for external access
# Secrets for AWS credentials
```

---

## Security Considerations

1. **Authentication** — Service-to-service (future enhancement: mutual TLS or JWT tokens)
2. **Authorization** — Capability-based access; the registry enforces which agents can be discovered
3. **Network Isolation** — Docker Compose uses a dedicated bridge network (`a2a-network`)
4. **Secrets Management** — AWS credentials via IAM roles (production) or `~/.aws` mount (development); never committed to source
5. **Sandboxing** — File Operations server restricts all access to a configurable workspace directory
6. **Timeouts** — Per-step and per-workflow timeouts prevent resource exhaustion
7. **Stale Agent Cleanup** — Agents without a heartbeat for 60 s are automatically deregistered

---

## Monitoring & Observability

### Metrics (via Observer Agent)
- Workflow execution time (total and per-step)
- Step success/failure rates
- Agent availability and heartbeat status
- Tool usage counts
- Circuit breaker states

### Logging
- Structured output to stdout/stderr
- Request and response details at each step
- LLM prompt/response sizes
- Retry attempt counts and delay durations

### Health Checks
- All services expose `GET /health` or `GET /`
- Docker Compose uses health-checks to gate service startup order
- Agent heartbeats sent every 30 s; Registry removes stale agents after 60 s

---

**Version**: 2.1  
**Last Updated**: 2026-03-23  
**Status**: Production Ready

---

## Table of Contents

1. [Overview](#overview)
2. [High-Level Architecture](#high-level-architecture)
3. [Component Details](#component-details)
4. [Service Communication](#service-communication)
5. [Port Allocation](#port-allocation)
6. [Data Flow](#data-flow)
7. [MCP Integration](#mcp-integration)
8. [Workflow Execution](#workflow-execution)
9. [Scalability & Performance](#scalability--performance)

---

## Overview

The A2A (Agent-to-Agent) Multi-Agent System is a distributed framework that enables autonomous agents to collaborate on complex tasks through:

- **Service Discovery**: Dynamic agent and tool registration
- **LLM Planning**: Claude 3.5 Sonnet generates execution plans
- **MCP Protocol**: Standardized tool integration
- **Workflow Orchestration**: Intelligent task coordination
- **Parallel Execution**: Concurrent step processing

### Key Principles

1. **Loose Coupling**: Services communicate via REST APIs
2. **Service Discovery**: Dynamic registration and capability matching
3. **Fault Tolerance**: Retry mechanisms and circuit breakers
4. **Extensibility**: Easy to add new agents and tools
5. **Observability**: Comprehensive logging and monitoring

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                   │
│                        CLIENT / USER                              │
│                                                                   │
└────────────────────────────┬──────────────────────────────────────┘
                             │
                             ↓
            ┌────────────────────────────────┐
            │     Orchestrator (8100)         │
            │   - Workflow Planning (LLM)     │
            │   - Step Execution              │
            │   - Context Management          │
            │   - Persistence & Retry         │
            └────────────────┬────────────────┘
                             │
                    ┌────────┴──────────┐
                    ↓                    ↓
      ┌─────────────────────┐  ┌──────────────────┐
      │  Registry (8000)     │  │ MCP Gateway      │
      │  - Agent Discovery   │  │   (8300)         │
      │  - Health Checks     │  │ - Tool Routing   │
      │  - Capability Match  │  │ - LLM Selection  │
      └──────────┬───────────┘  └────────┬─────────┘
                 │                       │
         ┌───────┴────────┐      ┌──────┴──────┐
         ↓                ↓       ↓             ↓
   ┌─────────┐     ┌───────────┐   ┌────────────────┐
   │ Agents  │     │  Agents   │   │ MCP Registry   │
   │ (8001-  │     │  (cont.)  │   │   (8200)       │
   │  8006)  │     │           │   │ - Tool Disc.   │
   └─────────┘     └───────────┘   └────────┬───────┘
                                             │
                                    ┌────────┴────────┐
                                    ↓                  ↓
                              ┌──────────┐      ┌──────────┐
                              │MCP Tools │      │MCP Tools │
                              │(8210-    │      │ (cont.)  │
                              │ 8213)    │      │          │
                              └──────────┘      └──────────┘
```

---

## Component Details

### 1. Core Services

#### Registry Service (Port 8000)
**Purpose**: Central service discovery and agent registration

**Capabilities**:
- Agent registration with capabilities
- Health check monitoring (60s timeout)
- Capability-based agent lookup
- Agent status tracking

**API Endpoints**:
- `POST /api/registry/register` - Register agent
- `GET /api/registry/agents` - List all agents
- `GET /api/registry/capabilities/{capability}` - Find agents by capability
- `POST /api/registry/heartbeat/{agent_id}` - Health check
- `DELETE /api/registry/unregister/{agent_id}` - Unregister

**Data Model**:
```python
{
    "agent_id": "uuid",
    "name": "AgentName",
    "endpoint": "http://host:port",
    "capabilities": [
        {
            "name": "capability_name",
            "description": "...",
            "input_schema": {...}
        }
    ]
}
```

#### Orchestrator Service (Port 8100)
**Purpose**: Workflow planning and execution coordination

**Capabilities**:
- LLM-based workflow planning (Claude 3.5)
- Context enrichment between steps
- Parallel step execution
- Retry with exponential backoff
- Workflow persistence (SQLite)
- Result aggregation

**Workflow Phases**:
1. **DISCOVER** - Find available agents and capabilities
2. **PLAN** - Generate execution plan via LLM
3. **EXECUTE** - Run steps (parallel when possible)
4. **VERIFY** - Validate results
5. **REFLECT** - Analyze execution

**API Endpoints**:
- `POST /api/workflow/execute` - Execute workflow
- `GET /api/workflow/{id}` - Get workflow status
- `GET /api/workflows` - List workflows
- `POST /api/workflow/{id}/resume` - Resume failed workflow

#### MCP Registry (Port 8200)
**Purpose**: MCP tool server discovery and registration

**Capabilities**:
- Tool server registration
- Tool capability listing
- Server health tracking
- Tool discovery by name

**API Endpoints**:
- `POST /api/mcp/register` - Register MCP server
- `GET /api/mcp/servers` - List tool servers
- `GET /api/mcp/tools` - List all tools
- `GET /api/mcp/tools/{tool_name}` - Get tool details
- `DELETE /api/mcp/unregister/{server_id}` - Unregister

#### MCP Gateway (Port 8300)
**Purpose**: Route tool execution requests to appropriate MCP servers

**Capabilities**:
- Tool execution routing
- LLM-based tool selection
- Multiple server fallback
- Load distribution
- Error handling

**API Endpoints**:
- `POST /api/gateway/execute` - Execute tool
- `GET /api/gateway/tools` - List available tools

---

### 2. Agent Services

#### Code Analyzer (Port 8001)
**Capabilities**: `analyze_python_code`, `explain_code`, `suggest_improvements`

Analyzes Python code for quality, security, and best practices using Claude 3.5.

#### Data Processor (Port 8002)
**Capabilities**: `transform_data`, `analyze_data`, `summarize_data`

Processes and analyzes data, provides insights and summaries.

#### Research Agent (Port 8003)
**Capabilities**: `answer_question`, `research`, `generate_report`, `compare_concepts`

Conducts research, answers questions, and generates comprehensive reports.

#### Task Executor (Port 8004)
**Capabilities**: `execute_command`, `file_operations`, `wait_task`

Executes system commands and performs file operations.

#### Observer (Port 8005)
**Capabilities**: `system_monitoring`, `event_logging`, `metrics_reporting`

Monitors system health, logs events, and reports metrics.

#### Math Agent (Port 8006)
**Capabilities**: `calculate`, `advanced_math`, `solve_equation`

Performs mathematical operations by coordinating with MCP Calculator tool.

---

### 3. MCP Tool Servers

#### Calculator Server (Port 8213)
**Tools**: `add`, `subtract`, `multiply`, `divide`, `power`, `square`, `sqrt`, `abs`

Provides mathematical computation capabilities.

#### Database Server (Port 8211)
**Tools**: `query`, `insert`, `update`, `delete`, `create_table`

Executes SQLite database operations.

#### File Operations Server (Port 8210)
**Tools**: `read_file`, `write_file`, `list_files`, `search_files`

Performs file system operations.

#### Web Search Server (Port 8212)
**Tools**: `search`, `get_page_content`

Searches the web and retrieves content.

---

## Service Communication

### Agent-to-Registry
```
Agent → POST /api/registry/register → Registry
      ← 201 Created + agent_id

Agent → POST /api/registry/heartbeat/{id} → Registry (every 30s)
      ← 200 OK
```

### Orchestrator-to-Agent
```
Orchestrator → GET /api/registry/capabilities/{cap} → Registry
             ← Agent list

Orchestrator → POST /api/task → Agent
             ← Task result
```

### Agent-to-MCP
```
Agent → POST /api/gateway/execute → MCP Gateway
      ↓
      GET /api/mcp/tools/{name} → MCP Registry
      ← Server info
      ↓
      POST /api/tools/execute → MCP Server
      ← Tool result
      ↑
      ← Result to Agent
```

---

## Port Allocation

### Core Services (8000-8100)
- **8000**: Registry Service
- **8100**: Orchestrator Service

### Agent Services (8001-8006)
- **8001**: Code Analyzer
- **8002**: Data Processor  
- **8003**: Research Agent
- **8004**: Task Executor
- **8005**: Observer
- **8006**: Math Agent

### MCP Services (8200-8300)
- **8200**: MCP Registry
- **8300**: MCP Gateway

### MCP Tools (8210-8213)
- **8210**: File Operations Server
- **8211**: Database Server
- **8212**: Web Search Server
- **8213**: Calculator Server

---

## Data Flow

### Example: "Add 25 and 17, then square the result"

```
1. CLIENT
   ↓ POST /api/workflow/execute
   
2. ORCHESTRATOR (DISCOVER)
   ↓ GET /api/registry/agents
   ← [CodeAnalyzer, DataProcessor, ResearchAgent, MathAgent, ...]
   
3. ORCHESTRATOR (PLAN via LLM)
   → Claude 3.5: Generate plan for task
   ← Plan: [
       Step 1: Use 'calculate' capability with add(25, 17)
       Step 2: Use 'advanced_math' capability with square(result)
     ]
   
4. ORCHESTRATOR (EXECUTE Step 1)
   ↓ GET /api/registry/capabilities/calculate
   ← MathAgent (8006)
   ↓ POST /api/task → MathAgent
   
5. MATH AGENT
   ↓ POST /api/gateway/execute (tool: add, a:25, b:17)
   
6. MCP GATEWAY
   ↓ GET /api/mcp/tools/add → MCP Registry
   ← CalculatorServer (8213)
   ↓ POST /api/tools/execute → Calculator
   ← {result: 42}
   ↑ Return to MathAgent
   
7. MATH AGENT
   ↑ Return {result: 42} to Orchestrator
   
8. ORCHESTRATOR (Context Enrichment)
   → Replace "<result_from_step_1>" with 42
   
9. ORCHESTRATOR (EXECUTE Step 2)
   ↓ POST /api/task → MathAgent (square, value: 42)
   → [MCP flow repeats]
   ← {result: 1764}
   
10. ORCHESTRATOR (AGGREGATE)
   → Compile results
   ↑ Return to CLIENT
   
11. CLIENT
   ← {
       workflow_id: "...",
       status: "completed",
       steps_completed: 2,
       results: [
         {step: 1, result: 42},
         {step: 2, result: 1764}
       ]
     }
```

---

## MCP Integration

### MCP Architecture

Model Context Protocol (MCP) provides standardized tool integration:

```
┌─────────────────────┐
│   MCP Registry      │
│   - Tool Discovery  │
│   - Server Tracking │
└──────────┬──────────┘
           │
           ↓
┌─────────────────────┐
│   MCP Gateway       │
│   - Request Routing │
│   - Tool Selection  │
│   - Load Balance    │
└──────────┬──────────┘
           │
     ┌─────┴──────┬───────────┬───────────┐
     ↓            ↓           ↓           ↓
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│Calculator│ │Database │ │File Ops │ │Web Srch │
│ Server   │ │ Server  │ │ Server  │ │ Server  │
└─────────┘ └─────────┘ └─────────┘ └─────────┘
```

### Tool Registration

```python
POST /api/mcp/register
{
  "name": "CalculatorServer",
  "description": "Math operations",
  "base_url": "http://localhost:8213",
  "tools": [
    {
      "name": "add",
      "description": "Add two numbers",
      "input_schema": {
        "type": "object",
        "properties": {
          "a": {"type": "number"},
          "b": {"type": "number"}
        },
        "required": ["a", "b"]
      }
    }
  ]
}
```

---

## Workflow Execution

### Execution Modes

#### 1. Sequential Execution
Steps execute one after another:
```
Step 1 → Step 2 → Step 3 → Complete
```

#### 2. Parallel Execution
Independent steps execute concurrently:
```
Step 1 ────┐
           ├──→ Step 3 → Complete
Step 2 ────┘
```

### Dependency Management

Steps can declare dependencies:
```python
{
  "step_id": "step_3",
  "dependencies": ["step_1", "step_2"],
  "capability": "generate_report"
}
```

Orchestrator ensures dependencies are met before execution.

### Context Enrichment

Results from previous steps enrich subsequent steps:

```python
# Step 1 result
{"result": 42}

# Step 2 parameters (before enrichment)
{"operation": "square", "value": "<result_from_step_1>"}

# Step 2 parameters (after enrichment)
{"operation": "square", "value": 42}
```

---

## Scalability & Performance

### Horizontal Scaling

**Stateless Services** (can scale):
- All agent services
- MCP tool servers
- MCP Gateway (with shared registry)

**Stateful Services** (require coordination):
- Registry (single instance or clustered with shared DB)
- Orchestrator (single instance per workflow, or shared DB)
- MCP Registry (single instance or clustered)

### Performance Optimizations

1. **Parallel Execution**: 2-5x speedup for independent steps
2. **Connection Pooling**: HTTP client reuse
3. **Circuit Breaker**: Prevent cascading failures
4. **Retry with Backoff**: Handle transient failures
5. **Result Caching**: LLM response caching (future)

### Resource Usage

| Service | Memory | CPU | Network |
|---------|--------|-----|---------|
| Registry | ~50MB | Low | Medium |
| Orchestrator | ~100MB | Medium | High |
| Agents | ~80MB each | Medium | Medium |
| MCP Services | ~50MB each | Low | Low |

---

## Deployment Models

### 1. Single Machine (Development)
```bash
./start_services.sh
# All services on localhost, different ports
```

### 2. Docker Compose (Testing)
```bash
docker-compose up
# All services in containers, shared network
```

### 3. Kubernetes (Production)
```yaml
# Each service as deployment
# Service discovery via k8s DNS
# Ingress for external access
```

---

## Security Considerations

1. **Authentication**: Service-to-service (future: JWT tokens)
2. **Authorization**: Capability-based access control
3. **Network**: Internal network for service communication
4. **Secrets**: AWS credentials via IAM roles or env vars
5. **Isolation**: Container/process isolation
6. **Timeouts**: Prevent resource exhaustion

---

## Monitoring & Observability

### Metrics
- Workflow execution time
- Step success/failure rates
- Agent availability
- Tool usage statistics
- Circuit breaker states

### Logging
- Structured JSON logs
- Request/response tracing
- Error stack traces
- Performance metrics

### Health Checks
- Agent heartbeats (30s interval)
- Service liveness probes
- Dependency checks

---

**Version**: 2.0  
**Last Updated**: 2026-02-07  
**Status**: Production Ready
