# Deployment Method Comparison

## Shell Script vs Docker Compose

This document compares the two deployment methods to show they now behave identically.

---

## Setup Comparison

### Shell Script Deployment
```bash
# Prerequisites
1. Python 3.11+
2. AWS credentials configured

# Setup (one time)
./setup.sh

# Start services
./start_services.sh

# Stop services
./stop_services.sh
```

### Docker Compose Deployment
```bash
# Prerequisites
1. Docker + Docker Compose
2. AWS credentials configured

# Start services
docker-compose up -d

# Stop services
docker-compose down
```

---

## AWS Credentials

### ✅ BOTH NOW IDENTICAL

| Aspect | Shell Script | Docker Compose |
|--------|-------------|----------------|
| AWS CLI config | ✅ Automatic | ✅ Automatic (mounted) |
| Environment vars | ✅ Supported | ✅ Supported |
| .env file | ❌ N/A | ✅ Supported |
| IAM roles | ✅ Automatic | ✅ Automatic |
| Profile support | ✅ Yes | ✅ Yes |

**Conclusion**: Both use your local AWS credentials without extra setup!

---

## Service Architecture

### ✅ IDENTICAL

Both deployments start services in the same order:

```
Layer 1: Registry (8000)
    ↓
Layer 2: Orchestrator (8100), MCP Registry (8200)
    ↓
Layer 3: MCP Servers (8210-8213)
    ↓
Layer 4: MCP Gateway (8300)
    ↓
Layer 5: Agents (8001-8006)
```

---

## Port Allocation

### ✅ IDENTICAL

| Service | Port | Both Methods |
|---------|------|--------------|
| Registry | 8000 | ✅ |
| Code Analyzer | 8001 | ✅ |
| Data Processor | 8002 | ✅ |
| Research Agent | 8003 | ✅ |
| Task Executor | 8004 | ✅ |
| Observer | 8005 | ✅ |
| Math Agent | 8006 | ✅ |
| Orchestrator | 8100 | ✅ |
| MCP Registry | 8200 | ✅ |
| File Ops Server | 8210 | ✅ |
| Database Server | 8211 | ✅ |
| Web Search Server | 8212 | ✅ |
| Calculator Server | 8213 | ✅ |
| MCP Gateway | 8300 | ✅ |

---

## Testing

### ✅ IDENTICAL API

Both deployments expose the same endpoints:

```bash
# Test workflow (same for both)
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Add 25 and 17, then square the result"
  }'

# Expected result: Same for both
# Step 1: 25 + 17 = 42
# Step 2: 42² = 1764
```

---

## Logs & Monitoring

### Shell Script
```bash
# View all logs in terminal output
./start_services.sh

# Individual service logs in /tmp/*.log
tail -f /tmp/orchestrator.log
```

### Docker Compose
```bash
# View all logs
docker-compose logs -f

# Individual service logs
docker-compose logs -f orchestrator
```

---

## Advantages Comparison

### Shell Script Advantages

1. **Faster startup** - No container overhead
2. **Direct debugging** - Python debuggers work directly
3. **Easier development** - Edit code, restart service
4. **Native performance** - No virtualization layer

### Docker Compose Advantages

1. **Isolation** - Services in separate containers
2. **Consistency** - Same environment everywhere
3. **Easy cleanup** - `docker-compose down` removes everything
4. **Production-ready** - Can deploy to any Docker environment
5. **Rollback** - Easy to revert to previous images
6. **Resource limits** - Can set CPU/memory limits
7. **Scaling** - Can run multiple instances

---

## Use Cases

### Choose Shell Script When:
- ✅ Developing locally
- ✅ Need fast iteration cycles
- ✅ Debugging Python code
- ✅ Limited Docker resources
- ✅ Learning the system

### Choose Docker Compose When:
- ✅ Testing full system
- ✅ Need consistent environment
- ✅ Preparing for production
- ✅ Multiple developers
- ✅ CI/CD pipelines
- ✅ Deploying to cloud

---

## Migration Between Methods

### Shell Script → Docker Compose
```bash
# 1. Stop shell services
./stop_services.sh

# 2. Start Docker services
docker-compose up -d

# Same AWS credentials work automatically!
```

### Docker Compose → Shell Script
```bash
# 1. Stop Docker services
docker-compose down

# 2. Start shell services
./start_services.sh

# Same AWS credentials work automatically!
```

---

## Configuration Files

### Shell Script
- `start_services.sh` - Startup script
- `stop_services.sh` - Shutdown script
- `setup.sh` - Initial setup
- `services/*/app.py` - Service code
- `services/*/.env` - Service config

### Docker Compose
- `docker-compose.yml` - Service definitions
- `.env` (optional) - Environment variables
- `services/*/Dockerfile` - Container builds
- `services/*/app.py` - Service code (same)
- `services/*/.env` - Service config (same)

---

## Troubleshooting

### Both Methods

```bash
# Check if ports are available
lsof -i :8000-8006
lsof -i :8100
lsof -i :8200-8213
lsof -i :8300

# Test registry
curl http://localhost:8000/health

# Test orchestrator
curl http://localhost:8100/

# Check agents registered
curl http://localhost:8000/api/registry/agents | jq .

# Check MCP servers registered
curl http://localhost:8200/api/mcp/servers | jq .
```

### Shell Script Specific
```bash
# Check service process
ps aux | grep python | grep app.py

# Check specific service
lsof -i :8100 | grep LISTEN

# Restart specific service
kill <PID>
cd services/orchestrator
source ../../venv/bin/activate
python app.py &
```

### Docker Compose Specific
```bash
# Check container status
docker-compose ps

# Restart specific service
docker-compose restart orchestrator

# View service logs
docker-compose logs orchestrator

# Execute commands in container
docker-compose exec orchestrator bash
```

---

## Performance Comparison

### Startup Time
- **Shell Script**: ~5-10 seconds
- **Docker Compose**: ~15-30 seconds (first time: 2-5 minutes for building)

### Memory Usage
- **Shell Script**: ~2-3 GB total
- **Docker Compose**: ~3-4 GB total (includes container overhead)

### CPU Usage
- **Both**: Similar (~10-20% idle, spikes during workflow execution)

---

## Recommendation

### Development Phase
```bash
# Use shell script for speed
./start_services.sh
```

### Testing Phase
```bash
# Use Docker to test full system
docker-compose up -d
```

### Production
```bash
# Use Docker with orchestration (Kubernetes/ECS)
# Or use managed services
```

---

## Summary

| Feature | Shell Script | Docker Compose | Winner |
|---------|-------------|----------------|--------|
| Setup complexity | Low | Low | Tie ✅ |
| Startup speed | Fast | Medium | Shell Script |
| AWS credentials | Automatic | Automatic | Tie ✅ |
| Isolation | No | Yes | Docker |
| Debugging | Easy | Medium | Shell Script |
| Production ready | No | Yes | Docker |
| Resource usage | Lower | Higher | Shell Script |
| Consistency | Medium | High | Docker |
| Portability | Low | High | Docker |

**Best Practice**: 
- Use **shell script** for active development
- Use **Docker Compose** for testing and deployment

Both are now equally easy to set up and use! 🎉

---

**Last Updated**: 2026-02-07  
**Status**: Both methods fully aligned and tested
