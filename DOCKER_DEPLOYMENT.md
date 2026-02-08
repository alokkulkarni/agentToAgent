# Docker Deployment Guide

This guide explains how to deploy the A2A Multi-Agent System using Docker Compose.

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- AWS credentials (for Bedrock LLM access)

## Architecture

The system consists of multiple services with the following startup dependencies:

### Service Layers

1. **Layer 1 - Core Registry** (starts first)
   - `registry` (port 8000) - Agent Registry

2. **Layer 2 - Supporting Services** (parallel)
   - `orchestrator` (port 8100) - Workflow Orchestrator
   - `mcp-registry` (port 8200) - MCP Server Registry

3. **Layer 3 - MCP Servers** (after mcp-registry)
   - `calculator-server` (port 8213) - Math operations
   - `database-server` (port 8211) - Database queries
   - `file-ops-server` (port 8210) - File operations
   - `web-search-server` (port 8212) - Web search

4. **Layer 4 - MCP Gateway** (after all MCP servers)
   - `mcp-gateway` (port 8300) - Routes tool calls to MCP servers

5. **Layer 5 - Agent Services** (after registry and mcp-gateway)
   - `code-analyzer` (port 8001)
   - `data-processor` (port 8002)
   - `research-agent` (port 8003)
   - `task-executor` (port 8004)
   - `observer` (port 8005)
   - `math-agent` (port 8006)

## Configuration

### Environment Variables

The docker-compose now supports **flexible AWS credential management**:

**Option 1: Use Local AWS Credentials (Recommended)**
```bash
# Just configure AWS CLI once
aws configure

# Start services - they automatically use your ~/.aws credentials
docker-compose up -d
```

**Option 2: Use .env File**
Create a `.env` file in the project root:

```bash
# AWS Credentials for Bedrock
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1

# Bedrock Model
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
```

**Option 3: Use Environment Variables**
```bash
export AWS_ACCESS_KEY_ID="your_key"
export AWS_SECRET_ACCESS_KEY="your_secret"
export AWS_REGION="us-east-1"
docker-compose up -d
```

**How It Works:**
- Services mount your `~/.aws` directory (read-only)
- If environment variables are set, they take precedence
- If not set, mounted credentials are used automatically
- Same behavior as shell script deployment!

## Usage

### Start All Services

```bash
docker-compose up -d
```

This will:
1. Build all Docker images (first time only)
2. Start services in the correct dependency order
3. Wait for health checks before starting dependent services

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f registry
docker-compose logs -f orchestrator
docker-compose logs -f math-agent
```

### Check Service Status

```bash
docker-compose ps
```

### Stop All Services

```bash
docker-compose down
```

### Rebuild After Code Changes

```bash
docker-compose down
docker-compose build
docker-compose up -d
```

## Service Health Checks

The system includes health checks for critical services:

- **Registry**: Checks `/health` endpoint every 10s
- **MCP Registry**: Checks root endpoint every 10s

## Testing

### Test Registry

```bash
curl http://localhost:8000/health
```

### Test Orchestrator

```bash
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Add 25 and 17, then square the result"
  }'
```

### Test MCP Gateway

```bash
curl -X POST http://localhost:8300/api/gateway/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "add",
    "parameters": {"a": 25, "b": 17}
  }'
```

## Volumes

The system uses Docker volumes for persistent data:

- `database-data`: SQLite database files
- `workspace-data`: File operations workspace

## Networking

All services run on the `a2a-network` bridge network, allowing them to communicate using service names (e.g., `http://registry:8000`).

## Port Mapping

| Service | Internal Port | External Port | Description |
|---------|--------------|---------------|-------------|
| registry | 8000 | 8000 | Agent Registry |
| orchestrator | 8100 | 8100 | Workflow Orchestrator |
| mcp-registry | 8200 | 8200 | MCP Server Registry |
| file-ops-server | 8210 | 8210 | File Operations MCP |
| database-server | 8211 | 8211 | Database Query MCP |
| web-search-server | 8212 | 8212 | Web Search MCP |
| calculator-server | 8213 | 8213 | Calculator MCP |
| mcp-gateway | 8300 | 8300 | MCP Gateway |
| code-analyzer | 8001 | 8001 | Code Analysis Agent |
| data-processor | 8002 | 8002 | Data Processing Agent |
| research-agent | 8003 | 8003 | Research Agent |
| task-executor | 8004 | 8004 | Task Execution Agent |
| observer | 8005 | 8005 | System Observer Agent |
| math-agent | 8006 | 8006 | Math Operations Agent |

## Troubleshooting

### Services Won't Start

1. Check logs: `docker-compose logs <service-name>`
2. Verify AWS credentials in `.env`
3. Ensure all ports are available: `lsof -i :<port>`

### Build Failures

1. Clean Docker cache: `docker-compose build --no-cache`
2. Remove old images: `docker system prune -a`

### Connection Issues

1. Check service health: `docker-compose ps`
2. Verify network: `docker network inspect agenttoagent_a2a-network`
3. Check service logs for connection errors

## Production Considerations

For production deployment:

1. Use Docker secrets for AWS credentials
2. Configure resource limits in docker-compose.yml
3. Set up monitoring and logging aggregation
4. Use health check restart policies
5. Consider using Docker Swarm or Kubernetes for orchestration
6. Implement proper backup strategies for volumes
7. Set up SSL/TLS for external access
8. Configure firewall rules appropriately

## Development Mode

For development with live code reloading:

```bash
# Mount source code as volumes
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up
```

Create `docker-compose.dev.yml`:

```yaml
version: '3.8'

services:
  orchestrator:
    volumes:
      - ./services/orchestrator:/app
    environment:
      - LOG_LEVEL=debug
  
  # Add similar overrides for other services
```
