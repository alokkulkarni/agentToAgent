# A2A Multi-Agent System - Quick Start Guide

## Prerequisites
- Python 3.11+ **or** Docker + Docker Compose
- AWS credentials with access to Amazon Bedrock
- (Optional) API keys for Anthropic, OpenAI, or Google Gemini if using those providers via the Model Gateway

## Option 1: Shell Script Deployment (Local)

```bash
# 1. (One-time) Set up Python virtual environment and install all dependencies
./scripts/setup.sh

# 2. Export AWS credentials
export AWS_ACCESS_KEY_ID="your_key"
export AWS_SECRET_ACCESS_KEY="your_secret"
export AWS_REGION="us-east-1"

# 3. Start all services (Registry, Orchestrator, Model Gateway, MCP stack, 6 agents)
./scripts/start_services.sh

# 4. Test the system
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Add 25 and 17, then square the result"}'

# 5. Stop services
./scripts/stop_services.sh
```

## Option 2: Docker Compose Deployment

```bash
# 1. Configure AWS (one time only)
aws configure

# 2. Verify Docker Compose configuration
./scripts/verify_docker_compose.sh

# 3. Start all services (automatically uses your AWS credentials from ~/.aws)
docker-compose up -d

# 4. Check status
docker-compose ps

# 5. View logs
docker-compose logs -f orchestrator
docker-compose logs -f model-gateway

# 6. Test the system
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Add 25 and 17, then square the result"}'

# 7. Stop services
docker-compose down
```

> **AWS Credentials**: Docker Compose mounts `~/.aws` into containers at `/app/.aws`.  
> The env vars `AWS_SHARED_CREDENTIALS_FILE=/app/.aws/credentials` and `AWS_CONFIG_FILE=/app/.aws/config`  
> are set automatically — no manual credential injection needed.

## Service Endpoints

| Service | URL | Purpose |
|---------|-----|---------|
| Registry | http://localhost:8000 | Agent discovery, heartbeat |
| Orchestrator | http://localhost:8100 | Workflow planning and execution |
| MCP Registry | http://localhost:8200 | MCP tool-server discovery |
| MCP Gateway | http://localhost:8300 | MCP tool routing and execution |
| **Model Gateway** | **http://localhost:8400** | **LLM provider abstraction (Bedrock, Anthropic, OpenAI, Gemini)** |
| Code Analyzer | http://localhost:8001 | Code analysis and improvement |
| Data Processor | http://localhost:8002 | Data transformation and analysis |
| Research Agent | http://localhost:8003 | Research, Q&A, web search |
| Task Executor | http://localhost:8004 | Task and file execution |
| Observer | http://localhost:8005 | System monitoring and metrics |
| Math Agent | http://localhost:8006 | Mathematical operations |
| File Ops | http://localhost:8210 | File system operations (MCP) |
| Database | http://localhost:8211 | SQLite database operations (MCP) |
| Web Search | http://localhost:8212 | Web search and URL fetch (MCP) |
| Calculator | http://localhost:8213 | Pure math calculations (MCP) |
| Redis | localhost:6379 | HA shared state, pub/sub (optional) |
| Qdrant | http://localhost:6333 | Vector memory store (optional) |

## Example Workflows

### Math Calculation
```bash
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Calculate 15 + 27, then multiply by 3"
  }' | jq .
```

### Data Analysis
```bash
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Analyze cloud computing trends and provide insights"
  }' | jq .
```

### Code Analysis
```bash
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Analyze a Python function for improvements"
  }' | jq .
```

### Direct Model Gateway Inference (no workflow needed)
```bash
# Call the Model Gateway directly — it auto-selects the best available provider
curl -X POST http://localhost:8400/v1/complete \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Explain circuit breakers in distributed systems"}],
    "tier": "balanced"
  }' | jq .

# List all registered models across all providers
curl http://localhost:8400/v1/models | jq .

# Preview which model would be selected for a given request (no inference)
curl "http://localhost:8400/v1/select?task=coding&tier=premium" | jq .

# Check provider health and circuit breaker states
curl http://localhost:8400/health | jq .
```

## Troubleshooting

### Services won't start
```bash
# Check which ports are already in use
lsof -i :8000-8006
lsof -i :8100
lsof -i :8200-8213
lsof -i :8300

# Check logs (Docker)
docker-compose logs <service-name>

# Restart specific service (Docker)
docker-compose restart <service-name>
```

### Connection errors
```bash
# Test Registry health
curl http://localhost:8000/health

# Check all registered agents
curl http://localhost:8000/api/registry/agents | jq .

# Check MCP servers
curl http://localhost:8200/api/mcp/servers | jq .

# Check available MCP tools
curl http://localhost:8200/api/mcp/tools | jq .
```

### Reset everything
```bash
# Shell script deployment
./scripts/stop_services.sh
rm -rf venv/
./scripts/setup.sh
./scripts/start_services.sh

# Docker deployment
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

### Model Gateway not responding
```bash
# Check health and provider states
curl http://localhost:8400/health | jq .

# Check circuit breaker states
curl http://localhost:8400/v1/admin/circuit-breakers | jq .

# Manually reset a tripped circuit breaker (e.g. bedrock)
curl -X POST http://localhost:8400/v1/admin/circuit-breakers/bedrock/reset

# Verify AWS credentials work for Bedrock
aws bedrock list-foundation-models --region us-east-1 | jq '.modelSummaries | length'
```

## Documentation

| Document | Description |
|----------|-------------|
| [../README.md](../README.md) | Full feature reference and architecture overview |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Detailed system design and component reference |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Docker Compose deployment guide |
| [DEPLOYMENT_AWS.md](DEPLOYMENT_AWS.md) | AWS ECS/EKS deployment guide |
| [DEPLOYMENT_AZURE.md](DEPLOYMENT_AZURE.md) | Azure ACA/AKS deployment guide |
| [AWS_CREDENTIALS_GUIDE.md](AWS_CREDENTIALS_GUIDE.md) | AWS credential configuration |
| [CURL_EXAMPLES.md](CURL_EXAMPLES.md) | REST API usage examples |
| [MCP_CURL_EXAMPLES.md](MCP_CURL_EXAMPLES.md) | MCP tool API examples |
| [INTERACTIVE_WORKFLOW_EXAMPLES.md](INTERACTIVE_WORKFLOW_EXAMPLES.md) | Human-in-the-loop usage examples |
| [COMPONENT_REFERENCE.md](COMPONENT_REFERENCE.md) | Per-component configuration reference |
| [ENTERPRISE_DEPLOYMENT.md](ENTERPRISE_DEPLOYMENT.md) | Enterprise security, HA, and identity setup |

## Support

For issues:
1. Check service logs first (`docker-compose logs <service>`)
2. Verify all services are running (`docker-compose ps` or `ps aux | grep python`)
3. Check Model Gateway health: `curl http://localhost:8400/health | jq .`
4. Ensure AWS credentials are valid (`aws sts get-caller-identity`)
5. Check network connectivity between services

---

**Quick Start Version**: 3.1  
**Last Updated**: 2026-03-23  
**System Status**: ✅ Fully Operational
