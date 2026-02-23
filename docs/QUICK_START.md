# A2A Multi-Agent System - Quick Start Guide

## Prerequisites
- Python 3.11+ OR Docker + Docker Compose
- AWS credentials for Bedrock LLM

## Option 1: Shell Script Deployment (Local)

```bash
# 1. Clone and setup
cd agentToAgent
./setup.sh

# 2. Configure AWS credentials
export AWS_ACCESS_KEY_ID="your_key"
export AWS_SECRET_ACCESS_KEY="your_secret"
export AWS_REGION="us-east-1"

# 3. Start all services
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

# 2. Verify configuration
./verify_docker_compose.sh

# 3. Start all services (automatically uses your AWS credentials)
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

**Note**: Docker services automatically use your local AWS credentials from `~/.aws/credentials`  
No need to create a `.env` file if you already have AWS CLI configured!

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

## Troubleshooting

### Services won't start
```bash
# Check ports
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
# Test registry
curl http://localhost:8000/health

# Check agent registration
curl http://localhost:8000/api/registry/agents | jq .

# Check MCP servers
curl http://localhost:8200/api/mcp/servers | jq .
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

- **COMPLETE_SUMMARY.md** - Full list of changes
- **DOCKER_DEPLOYMENT.md** - Detailed Docker guide
- **DOCKER_COMPOSE_UPDATES.md** - Docker compose changes
- **README.md** - System overview
- **TESTING_GUIDE.md** - Test procedures

## Support

For issues:
1. Check logs first
2. Verify all services are running
3. Ensure AWS credentials are valid
4. Check network connectivity between services

---

**Quick Start Version**: 1.0  
**Last Updated**: February 7, 2026  
**System Status**: ✅ Fully Operational
