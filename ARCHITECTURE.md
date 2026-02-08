# A2A System Architecture

**Comprehensive System Architecture and Design Documentation**

Last Updated: 2026-02-07

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
