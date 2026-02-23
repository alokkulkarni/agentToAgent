# A2A System Deployment Guide

**Complete deployment instructions for production and development environments**

Version: 2.0  
Last Updated: 2026-02-08

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Prerequisites](#prerequisites)
3. [Deployment Methods](#deployment-methods)
4. [Configuration](#configuration)
5. [Verification](#verification)
6. [Troubleshooting](#troubleshooting)
7. [Production Considerations](#production-considerations)

---

## Quick Start

### 30-Second Deployment

```bash
# 1. Clone and configure
git clone <repository-url> agentToAgent
cd agentToAgent
cp .env.example .env
# Edit .env with your AWS credentials

# 2. Deploy with Docker (recommended)
docker-compose up -d

# 3. Verify
curl http://localhost:8100/health
```

---

## Prerequisites

### Required
- **Docker** 20.10+ and **Docker Compose** 2.0+
  ```bash
  docker --version
  docker-compose --version
  ```

- **AWS Account** with Bedrock access
  - Claude 3.5 Sonnet model enabled
  - IAM user with Bedrock permissions
  
### Optional (for shell script deployment)
- **Python** 3.11+
- **pip** package manager
- **Virtual environment** support

---

## Deployment Methods

### Method 1: Docker Compose (Production-Ready) ✅ RECOMMENDED

**Best for**: Production deployments, multi-environment setups

**Features**:
- ✅ Complete isolation
- ✅ Automatic restart policies
- ✅ Health checks
- ✅ Volume persistence
- ✅ Network isolation
- ✅ Scalable
- ✅ Easy rollback

#### Step-by-Step

1. **Configure AWS Credentials**
   ```bash
   # Option A: AWS CLI (recommended)
   aws configure
   # Enter: Access Key, Secret Key, Region (us-east-1), Format (json)
   
   # Option B: Environment variables
   export AWS_ACCESS_KEY_ID="your_key"
   export AWS_SECRET_ACCESS_KEY="your_secret"
   export AWS_REGION="us-east-1"
   ```

2. **Configure Application**
   ```bash
   # Copy example configuration
   cp .env.example .env
   
   # Edit .env file
   nano .env  # or vim, code, etc.
   
   # Minimum required:
   # AWS_ACCESS_KEY_ID=your_actual_key
   # AWS_SECRET_ACCESS_KEY=your_actual_secret
   # AWS_REGION=us-east-1
   ```

3. **Build and Start Services**
   ```bash
   # Build all images
   docker-compose build
   
   # Start all services in background
   docker-compose up -d
   
   # View logs
   docker-compose logs -f
   
   # View specific service logs
   docker-compose logs -f orchestrator
   ```

4. **Verify Deployment**
   ```bash
   # Check all services are running
   docker-compose ps
   
   # Test health endpoints
   curl http://localhost:8000/health  # Registry
   curl http://localhost:8100/health  # Orchestrator
   curl http://localhost:8200/        # MCP Registry
   curl http://localhost:8300/health  # MCP Gateway
   
   # Test workflow execution
   curl -X POST http://localhost:8100/api/workflow/execute \
     -H "Content-Type: application/json" \
     -d '{
       "task_description": "Add 15 and 27, then square the result"
     }'
   ```

5. **Management Commands**
   ```bash
   # Stop all services
   docker-compose stop
   
   # Start stopped services
   docker-compose start
   
   # Restart services
   docker-compose restart
   
   # Stop and remove containers
   docker-compose down
   
   # Remove volumes (WARNING: deletes data)
   docker-compose down -v
   
   # View resource usage
   docker stats
   
   # Scale specific services
   docker-compose up -d --scale research-agent=3
   ```

---

### Method 2: Shell Scripts (Development)

**Best for**: Local development, testing, debugging

**Features**:
- ✅ Fast iteration
- ✅ Easy debugging
- ✅ Direct log access
- ✅ Quick restarts
- ❌ Less isolation
- ❌ Manual management

#### Step-by-Step

1. **Setup Environment**
   ```bash
   # Configure AWS
   aws configure
   
   # Run setup script
   chmod +x setup.sh
   ./setup.sh
   
   # This will:
   # - Create virtual environment
   # - Install Python dependencies
   # - Verify AWS credentials
   ```

2. **Start Services**
   ```bash
   # Make scripts executable
   chmod +x start_services.sh stop_services.sh
   
   # Start all services
   ./start_services.sh
   
   # Services start in order:
   # 1. Registry (8000)
   # 2. MCP Registry (8200) & Orchestrator (8100)
   # 3. MCP Servers (8210-8213)
   # 4. MCP Gateway (8300)
   # 5. Agents (8001-8006)
   ```

3. **Verify Services**
   ```bash
   # All services should be running
   ps aux | grep python | grep -E "(registry|orchestrator|agent|mcp)"
   
   # Test endpoints
   curl http://localhost:8000/health
   curl http://localhost:8100/health
   ```

4. **Stop Services**
   ```bash
   # Stop all services gracefully
   ./stop_services.sh
   
   # Force kill if needed
   pkill -f "python.*services"
   ```

---

## Configuration

### Environment Variables

See `.env.example` for all available options. Key configurations:

#### AWS Credentials (Required)
```bash
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
```

#### Workflow Features (Optional)
```bash
# Enable advanced features
ENABLE_PERSISTENCE=true    # Save workflows to database
ENABLE_RETRY=true          # Auto-retry failed steps
MAX_RETRIES=3              # Retry attempts
ENABLE_PARALLEL=true       # Parallel execution
MAX_PARALLEL_STEPS=5       # Concurrent steps limit
```

#### Performance Tuning
```bash
MAX_CONCURRENT_TASKS=10    # Max simultaneous workflows
WORKFLOW_TIMEOUT=3600      # Workflow timeout (seconds)
STEP_TIMEOUT=300           # Step timeout (seconds)
```

### Port Configuration

| Service | Port | Customizable | Environment Variable |
|---------|------|--------------|---------------------|
| Registry | 8000 | ✅ | REGISTRY_PORT |
| Orchestrator | 8100 | ✅ | ORCHESTRATOR_PORT |
| MCP Registry | 8200 | ✅ | MCP_REGISTRY_PORT |
| MCP Gateway | 8300 | ✅ | MCP_GATEWAY_PORT |
| Agents | 8001-8006 | ✅ | *_AGENT_PORT |
| MCP Tools | 8210-8213 | ✅ | *_PORT |

---

## Verification

### Health Checks

```bash
# Automated health check script
./verify_deployment.sh

# Manual health checks
for port in 8000 8100 8200 8300; do
  echo "Checking port $port..."
  curl -f http://localhost:$port/health || echo "FAILED: $port"
done
```

### Service Discovery

```bash
# List registered agents
curl http://localhost:8000/api/registry/agents | jq .

# List MCP tools
curl http://localhost:8200/servers | jq .

# Check orchestrator status
curl http://localhost:8100/health | jq .
```

### Workflow Testing

```bash
# Simple math workflow
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Calculate (25 + 17) squared",
    "workflow_id": "test_math_001"
  }' | jq .

# Research workflow
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Research cloud computing trends and analyze the data",
    "workflow_id": "test_research_001"
  }' | jq .
```

### Interactive Workflow (WebSocket)

```bash
# Open the WebSocket test client
open examples/websocket_test_client.html

# Or use wscat
wscat -c ws://localhost:8100/ws/workflow/test123
```

---

## Troubleshooting

### Common Issues

#### 1. AWS Credentials Not Found

**Error**: `Unable to locate credentials`

**Solution**:
```bash
# Verify AWS configuration
aws configure list

# Test Bedrock access
aws bedrock list-foundation-models --region us-east-1

# For Docker, ensure credentials are mounted
# Check docker-compose.yml has:
volumes:
  - ${HOME}/.aws:/root/.aws:ro
```

#### 2. Port Already in Use

**Error**: `Address already in use`

**Solution**:
```bash
# Find process using port
lsof -i :8100

# Kill the process
kill -9 <PID>

# Or change port in .env
ORCHESTRATOR_PORT=8101
```

#### 3. Services Not Healthy

**Error**: `Health check failed`

**Solution**:
```bash
# Check logs
docker-compose logs <service-name>

# Common fixes:
# - Wait longer (services need 30-60s to start)
# - Check dependencies are running
# - Verify network connectivity
docker-compose ps
docker network ls
```

#### 4. MCP Tools Not Working

**Error**: `404 Not Found` or `Connection failed`

**Solution**:
```bash
# Verify MCP servers are registered
curl http://localhost:8200/servers | jq .

# Restart MCP services
docker-compose restart calculator-server database-server

# Check MCP Gateway connectivity
curl http://localhost:8300/health
```

#### 5. Workflow Fails with 500 Error

**Error**: `Internal Server Error`

**Solution**:
```bash
# Check orchestrator logs
docker-compose logs orchestrator | tail -50

# Common causes:
# - LLM not accessible (check AWS)
# - Agent not responding (check agent logs)
# - Database locked (restart orchestrator)
```

### Debug Mode

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# Restart with debug logs
docker-compose down
docker-compose up

# Or for shell scripts
LOG_LEVEL=DEBUG ./start_services.sh
```

### Container Debugging

```bash
# Enter running container
docker-compose exec orchestrator bash

# Check environment
docker-compose exec orchestrator env

# Test internal connectivity
docker-compose exec orchestrator curl http://registry:8000/health

# View container resource usage
docker stats
```

---

## Production Considerations

### Security

1. **Credentials Management**
   ```bash
   # Use AWS IAM roles (recommended for production)
   # Avoid hardcoding credentials in .env
   
   # For ECS/EKS:
   # - Attach IAM role to task/pod
   # - Remove AWS credentials from environment
   
   # For EC2:
   # - Use instance IAM role
   # - Install AWS CLI and configure
   ```

2. **Network Security**
   ```yaml
   # docker-compose.yml - restrict external access
   services:
     orchestrator:
       ports:
         - "127.0.0.1:8100:8100"  # localhost only
   ```

3. **Secrets Management**
   ```bash
   # Use Docker secrets (Swarm mode)
   docker secret create aws_key aws_credentials.txt
   
   # Or AWS Secrets Manager
   # Or HashiCorp Vault
   ```

### High Availability

1. **Service Replication**
   ```bash
   # Scale agents for load balancing
   docker-compose up -d --scale research-agent=3 --scale data-processor=3
   ```

2. **Data Persistence**
   ```yaml
   # docker-compose.yml
   volumes:
     workflow-data:
       driver: local
       driver_opts:
         type: nfs
         o: addr=nfs-server,rw
         device: ":/data/workflows"
   ```

3. **Health Monitoring**
   ```bash
   # Use external monitoring (Prometheus, Datadog, etc.)
   # Integrate with alerting systems
   ```

### Performance Optimization

1. **Resource Limits**
   ```yaml
   # docker-compose.yml
   services:
     orchestrator:
       deploy:
         resources:
           limits:
             cpus: '2'
             memory: 2G
           reservations:
             cpus: '1'
             memory: 1G
   ```

2. **Connection Pooling**
   ```bash
   # Increase concurrent task limit
   MAX_CONCURRENT_TASKS=20
   MAX_PARALLEL_STEPS=10
   ```

3. **Database Optimization**
   ```bash
   # Use PostgreSQL for production (instead of SQLite)
   # Enable connection pooling
   # Add database indexes
   ```

### Backup and Recovery

```bash
# Backup workflow database
docker-compose exec orchestrator sqlite3 /app/workflows.db ".backup /tmp/backup.db"
docker cp orchestrator:/tmp/backup.db ./backups/

# Restore from backup
docker cp ./backups/backup.db orchestrator:/tmp/restore.db
docker-compose exec orchestrator cp /tmp/restore.db /app/workflows.db
docker-compose restart orchestrator
```

### Logging

```bash
# Centralized logging
# Forward logs to ELK, Splunk, CloudWatch, etc.

# docker-compose.yml
services:
  orchestrator:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Updates and Rollback

```bash
# Update deployment
git pull
docker-compose build
docker-compose up -d

# Rollback to previous version
git checkout <previous-commit>
docker-compose build
docker-compose up -d

# Or use image tags
docker-compose -f docker-compose.prod.yml up -d
```

---

## Deployment Checklist

### Pre-Deployment
- [ ] AWS credentials configured
- [ ] Bedrock access verified
- [ ] Ports available (8000-8006, 8100, 8200, 8210-8213, 8300)
- [ ] Docker/Python installed
- [ ] Configuration file updated (.env)

### Deployment
- [ ] Services built (docker-compose build)
- [ ] Services started (docker-compose up -d)
- [ ] All containers running (docker-compose ps)
- [ ] Health checks passing
- [ ] Service discovery working

### Post-Deployment
- [ ] Test workflows executed successfully
- [ ] Logs reviewed for errors
- [ ] Monitoring configured
- [ ] Backups scheduled
- [ ] Documentation updated

---

## Support

### Getting Help

1. Check logs: `docker-compose logs <service>`
2. Review documentation: `README.md`, `ARCHITECTURE.md`, `TROUBLESHOOTING.md`
3. Test components individually
4. Check network connectivity
5. Verify AWS access

### Useful Commands

```bash
# Complete system restart
docker-compose down && docker-compose up -d

# View all logs
docker-compose logs -f

# Check resource usage
docker stats

# Clean up everything
docker-compose down -v --rmi all

# Export logs for debugging
docker-compose logs > system-logs.txt
```

---

**Status**: Production Ready ✅  
**Last Tested**: 2026-02-08  
**Compatible With**: Docker 20.10+, Python 3.11+
