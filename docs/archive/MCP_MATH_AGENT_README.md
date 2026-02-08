# MCP (Model Context Protocol) System with Math Agent

## Overview

This is a distributed MCP system that includes:

1. **MCP Registry** - Service discovery for MCP servers
2. **MCP Gateway** - Central gateway to route tool execution requests to MCP servers
3. **MCP Servers** - Individual servers exposing tools (Calculator, Filesystem, Web Search)
4. **Math Agent** - An A2A agent that uses MCP Gateway to provide mathematical capabilities

## Architecture

```
┌─────────────────┐      ┌─────────────────┐
│ Agent Registry  │      │  MCP Registry   │
│   (Port 8000)   │      │   (Port 9001)   │
└────────┬────────┘      └────────┬────────┘
         │                        │
         │                        │
         │                        ▼
         │               ┌─────────────────┐
         │               │  MCP Gateway    │◄────┐
         │               │   (Port 9000)   │     │
         │               └────────┬────────┘     │
         │                        │              │
         │                        │ Executes     │
         │                        ▼              │
         │               ┌─────────────────┐     │
         │               │  MCP Servers    │     │
         │               │                 │     │
         │               │ Calculator 9100 │     │
         │               │ Filesystem 9101 │     │
         │               │ Web Search 9102 │     │
         │               └─────────────────┘     │
         │                                       │
         │                                       │ Uses MCP Tools
         ▼                                       │
┌─────────────────┐                             │
│   Math Agent    │─────────────────────────────┘
│   (Port 8006)   │
└─────────────────┘
         │
         │ Registers with
         ▼
  [A2A Protocol]
```

## Components

### 1. MCP Registry (Port 9001)
- Service discovery for MCP servers
- Maintains list of available MCP servers and their tools
- Servers auto-register on startup

### 2. MCP Gateway (Port 9000)
- Central gateway for tool execution
- Routes requests to appropriate MCP servers
- Provides unified API for all tools

### 3. MCP Servers

#### Calculator Server (Port 9100)
Tools:
- `add(a, b)` - Addition
- `subtract(a, b)` - Subtraction
- `multiply(a, b)` - Multiplication
- `divide(a, b)` - Division
- `square(value)` - Square a number
- `sqrt(value)` - Square root
- `power(value, exponent)` - Power operation
- `mean(numbers)` - Calculate mean
- `median(numbers)` - Calculate median
- `sum(numbers)` - Sum of numbers

#### Filesystem Server (Port 9101)
Tools:
- `read_file(path)` - Read file contents
- `write_file(path, content)` - Write to file
- `list_directory(path)` - List directory contents

#### Web Search Server (Port 9102)
Tools:
- `search(query)` - Web search

### 4. Math Agent (Port 8006)
An A2A agent that provides mathematical capabilities by using the MCP Gateway.

**Capabilities:**
- `calculate` - Basic arithmetic (add, subtract, multiply, divide)
- `advanced_math` - Advanced operations (square, sqrt, power)
- `solve_equation` - Solve equations
- `statistics` - Statistical calculations (mean, median, sum)

**Integration:**
- Registers with Agent Registry (Port 8000)
- Uses MCP Gateway (Port 9000) to execute mathematical operations
- Follows A2A protocol for task execution

## Setup and Usage

### 1. Start MCP Services and Math Agent

```bash
./start_mcp_services.sh
```

This will start:
- Agent Registry (localhost:8000)
- MCP Registry (localhost:9001)
- MCP Gateway (localhost:9000)
- Calculator Server (localhost:9100)
- Filesystem Server (localhost:9101)
- Web Search Server (localhost:9102)
- Math Agent (localhost:8006)

### 2. Stop Services

```bash
./stop_mcp_services.sh
```

### 3. Run Tests

```bash
python test_mcp_math_agent.py
```

## API Examples

### Direct MCP Gateway Call

```bash
# Add two numbers
curl -X POST http://localhost:9000/api/mcp/execute \
  -H "Content-Type: application/json" \
  -d '{
    "server_name": "calculator",
    "tool_name": "add",
    "arguments": {"a": 10, "b": 5}
  }'
```

### Math Agent via A2A Protocol

```bash
# Basic calculation
curl -X POST http://localhost:8006/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "calc-001",
    "capability": "calculate",
    "parameters": {
      "operation": "add",
      "a": 25,
      "b": 17
    }
  }'

# Advanced math
curl -X POST http://localhost:8006/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "calc-002",
    "capability": "advanced_math",
    "parameters": {
      "operation": "power",
      "value": 2,
      "exponent": 10
    }
  }'

# Statistics
curl -X POST http://localhost:8006/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "calc-003",
    "capability": "statistics",
    "parameters": {
      "operation": "mean",
      "numbers": [10, 20, 30, 40, 50]
    }
  }'
```

### Query MCP Registry

```bash
# List all MCP servers
curl http://localhost:9001/api/mcp/servers | jq .

# Get specific server details
curl http://localhost:9001/api/mcp/servers/calculator | jq .
```

### Query Agent Registry

```bash
# List all agents (including Math Agent)
curl http://localhost:8000/api/registry/agents | jq .
```

## Environment Configuration

Each service uses environment variables for configuration. Copy `.env.example` to `.env` and customize:

### Math Agent (.env)
```bash
AGENT_NAME=MathAgent
AGENT_PORT=8006
REGISTRY_URL=http://localhost:8000
MCP_GATEWAY_URL=http://localhost:9000
LOG_LEVEL=INFO
```

### MCP Gateway (.env)
```bash
GATEWAY_PORT=9000
MCP_REGISTRY_URL=http://localhost:9001
LOG_LEVEL=INFO
```

### MCP Servers (.env)
```bash
SERVER_NAME=calculator
SERVER_PORT=9100
MCP_REGISTRY_URL=http://localhost:9001
LOG_LEVEL=INFO
```

## Benefits of This Architecture

1. **Separation of Concerns**: Math Agent focuses on A2A protocol, MCP servers focus on tool execution
2. **Reusability**: MCP tools can be used by multiple agents or directly via gateway
3. **Scalability**: Each component runs independently and can be scaled separately
4. **Flexibility**: Easy to add new MCP servers or agents
5. **Service Discovery**: Automatic registration and discovery of services
6. **Modular**: Clean separation between agent layer and tool layer

## Integration with Orchestrator

The Math Agent can be discovered and used by the Orchestrator:

```bash
# Orchestrator can find Math Agent via Agent Registry
# Orchestrator can delegate mathematical tasks to Math Agent
# Math Agent uses MCP Gateway transparently

curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Calculate the sum of 25 and 17, then square the result",
    "workflow_id": "math-workflow-001"
  }'
```

## Testing

The test suite validates:
1. Service health checks
2. Agent and MCP server registration
3. Direct MCP Gateway tool execution
4. Math Agent task execution via A2A protocol
5. End-to-end integration (Agent → MCP Gateway → MCP Server)

## Troubleshooting

### Port Already in Use
```bash
# Stop all services
./stop_mcp_services.sh

# Check for lingering processes
lsof -i :8000 -i :8006 -i :9000 -i :9001 -i :9100 -i :9101 -i :9102
```

### Agent Not Registering
- Check Agent Registry is running: `curl http://localhost:8000/health`
- Check network connectivity
- Verify .env configuration

### MCP Tools Not Working
- Check MCP Registry is running: `curl http://localhost:9001/health`
- Verify MCP servers are registered: `curl http://localhost:9001/api/mcp/servers`
- Check MCP Gateway logs

## Future Enhancements

1. Add more MCP servers (Database, API clients, etc.)
2. Create more specialized agents using MCP tools
3. Add authentication and authorization
4. Implement rate limiting and quotas
5. Add monitoring and metrics
6. Support for remote MCP servers
