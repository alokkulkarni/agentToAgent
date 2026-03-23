# A2A Multi-Agent System - Quick Start Guide

## Prerequisites
- Python 3.11–3.13 **or** Docker + Docker Compose
- AWS credentials with access to Amazon Bedrock

## Option 1: Shell Script Deployment (Local)

```bash
# 1. (One-time) Set up Python virtual environment and install all dependencies
./setup.sh

# 2. Export AWS credentials
export AWS_ACCESS_KEY_ID="your_key"
export AWS_SECRET_ACCESS_KEY="your_secret"
export AWS_REGION="us-east-1"

# 3. Start all services (Registry, Orchestrator, MCP stack, 6 agents)
./start_services.sh

# 4. Test the system
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Add 25 and 17, then square the result"}'

# 5. Stop services
./stop_services.sh
```

## Option 2: Docker Compose Deployment

```bash
# 1. Configure AWS (one time only)
aws configure

# 2. Verify Docker Compose configuration
./verify_docker_compose.sh

# 3. Start all services (automatically uses your AWS credentials from ~/.aws)
docker-compose up -d

# 4. Check status
docker-compose ps

# 5. View logs
docker-compose logs -f registry
docker-compose logs -f orchestrator

# 6. Test the system
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Add 25 and 17, then square the result"}'

# 7. Stop services
docker-compose down
```

**Note**: Docker services automatically use your local AWS credentials from `~/.aws/credentials`.  
No need to create a `.env` file if you already have the AWS CLI configured!

## Service Endpoints

| Service | URL | Purpose |
|---------|-----|---------|
| Registry | http://localhost:8000 | Agent discovery |
| Orchestrator | http://localhost:8100 | Workflow execution |
| MCP Registry | http://localhost:8200 | MCP server discovery |
| MCP Gateway | http://localhost:8300 | Tool routing |
| Code Analyzer | http://localhost:8001 | Code analysis |
| Data Processor | http://localhost:8002 | Data processing |
| Research Agent | http://localhost:8003 | Research tasks |
| Task Executor | http://localhost:8004 | Task execution |
| Observer | http://localhost:8005 | System monitoring |
| Math Agent | http://localhost:8006 | Math operations |
| File Ops | http://localhost:8210 | File operations |
| Database | http://localhost:8211 | Database queries |
| Web Search | http://localhost:8212 | Web search |
| Calculator | http://localhost:8213 | Math calculations |

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

### Direct MCP Tool Call (no workflow needed)
```bash
curl -X POST http://localhost:8300/api/gateway/execute \
  -H "Content-Type: application/json" \
  -d '{"tool_name": "add", "parameters": {"a": 10, "b": 32}}' | jq .
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
./stop_services.sh
rm -rf venv/
./setup.sh
./start_services.sh

# Docker deployment
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

## Documentation

| Document | Description |
|----------|-------------|
| [README.md](README.md) | Full feature reference and architecture overview |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Detailed system design |
| [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) | Docker Compose deployment guide |
| [AWS_CREDENTIALS_GUIDE.md](AWS_CREDENTIALS_GUIDE.md) | AWS credential configuration |
| [TESTING_GUIDE.md](TESTING_GUIDE.md) | Test procedures and expected output |
| [CURL_EXAMPLES.md](CURL_EXAMPLES.md) | API usage examples |

## Support

For issues:
1. Check service logs first
2. Verify all services are running (`docker-compose ps` or `ps aux | grep python`)
3. Ensure AWS credentials are valid (`aws sts get-caller-identity`)
4. Check network connectivity between services

---

**Quick Start Version**: 2.1  
**Last Updated**: 2026-03-23  
**System Status**: ✅ Fully Operational
