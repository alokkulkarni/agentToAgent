# MCP Service Port Configuration

## Confirmed Port Assignments

| Service | Port | Configuration File |
|---------|------|--------------------|
| Agent Registry | 8000 | services/registry/.env |
| Orchestrator | 8100 | services/orchestrator/.env |
| MCP Registry | 8200 | services/mcp_registry/.env |
| **MCP Gateway** | **8300** | services/mcp_gateway/.env |
| Math Agent | 8006 | services/agents/math_agent/.env |
| Calculator MCP Server | 9001 | services/mcp_servers/calculator/.env |
| File Operations Server | 8210 | services/mcp_servers/file_ops/.env |
| Database Server | 8211 | services/mcp_servers/database/.env |
| Web Search Server | 8212 | services/mcp_servers/web_search/.env |

## Configuration Files Updated

### 1. MCP Gateway (.env)
```
MCP_GATEWAY_PORT=8300
```

### 2. Math Agent (.env)
```
MCP_GATEWAY_URL=http://localhost:8300
```

### 3. Start Services Script
- MCP Gateway starts on port 8300
- Math Agent starts on port 8006
- Math Agent connects to MCP Gateway at http://localhost:8300

## Verification Commands

```bash
# Check if MCP Gateway is running on correct port
lsof -i :8300

# Test MCP Gateway health
curl http://localhost:8300/health

# Check Math Agent connection
curl http://localhost:8006/health
```

## Service Startup Order

1. Agent Registry (8000)
2. Orchestrator (8100)
3. MCP Registry (8200)
4. MCP Servers (9001, 8210-8212)
5. **MCP Gateway (8300)**
6. All Agents including Math Agent (8006)

This ensures MCP Gateway is available before agents try to connect.
