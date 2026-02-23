# Enterprise Deployment Guide

**Complete Enterprise-Ready Deployment for Agent-to-Agent Multi-Agent System**

Version: 2.0  
Last Updated: 2026-02-13

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Pre-Deployment Configuration](#pre-deployment-configuration)
4. [Configuration Files Reference](#configuration-files-reference)
5. [Deployment Methods](#deployment-methods)
6. [Service Discovery and Connection](#service-discovery-and-connection)
7. [Security Configuration](#security-configuration)
8. [Monitoring and Observability](#monitoring-and-observability)
9. [Troubleshooting](#troubleshooting)
10. [Production Checklist](#production-checklist)

---

## Overview

This distributed multi-agent system consists of the following components:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AGENT-TO-AGENT ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐     ┌──────────────────┐     ┌─────────────────────────┐  │
│  │  CLI Chat   │────▶│   Orchestrator   │────▶│    Agent Registry       │  │
│  │  (Client)   │     │   (Port 8100)    │     │    (Port 8000)          │  │
│  └─────────────┘     └────────┬─────────┘     └─────────────────────────┘  │
│                               │                                             │
│                    ┌──────────┼──────────┐                                  │
│                    │          │          │                                  │
│              ┌─────▼─────┐ ┌──▼───┐ ┌────▼────┐                            │
│              │ Research  │ │ Math │ │  Data   │  ... more agents           │
│              │  Agent    │ │Agent │ │Processor│                            │
│              │(Port 8003)│ │(8006)│ │ (8002)  │                            │
│              └─────┬─────┘ └──┬───┘ └─────────┘                            │
│                    │          │                                             │
│              ┌─────▼──────────▼─────┐                                       │
│              │     MCP Gateway      │                                       │
│              │     (Port 8300)      │                                       │
│              └──────────┬───────────┘                                       │
│                         │                                                   │
│              ┌──────────▼───────────┐                                       │
│              │    MCP Registry      │                                       │
│              │     (Port 8200)      │                                       │
│              └──────────┬───────────┘                                       │
│                         │                                                   │
│     ┌───────────────────┼───────────────────┐                              │
│     │                   │                   │                              │
│  ┌──▼──────┐    ┌───────▼───────┐    ┌──────▼────┐                         │
│  │Calculator│    │  Web Search   │    │  Database  │                        │
│  │(Port 8213)│   │  (Port 8212)  │    │(Port 8211) │                        │
│  └──────────┘    └───────────────┘    └───────────┘                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key Principle**: All configuration is externalized. No hardcoded values exist in the codebase.

---

## Pre-Deployment Configuration

### Step 1: Clone and Setup

```bash
git clone <repository-url> agentToAgent
cd agentToAgent

# Create virtual environment (for local development)
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables

Copy and edit the environment template:

```bash
cp .env.example .env
```

Required variables:

```bash
# AWS Credentials (REQUIRED)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1

# Network Configuration
BIND_HOST=0.0.0.0           # Interface to bind (use 0.0.0.0 for Docker)
PUBLIC_HOST=localhost        # Public hostname for service discovery

# Core Service Ports
REGISTRY_PORT=8000
ORCHESTRATOR_PORT=8100
MCP_REGISTRY_PORT=8200
MCP_GATEWAY_PORT=8300

# Agent Ports
CODE_ANALYZER_PORT=8001
DATA_PROCESSOR_PORT=8002
RESEARCH_AGENT_PORT=8003
TASK_EXECUTOR_PORT=8004
OBSERVER_PORT=8005
MATH_AGENT_PORT=8006
```

### Step 3: Configure Enterprise Settings

Edit `shared/config/enterprise_config.json`:

```json
{
  "environment": "production",
  "deployment_id": "prod-cluster-01",
  
  "feature_flags": {
    "enable_guardrails": true,
    "enable_audit_logging": true,
    "enable_security_checks": true,
    "enable_pii_redaction": true,
    "strict_mode": true
  },
  
  "network": {
    "bind_host": "0.0.0.0",
    "public_host": "your-domain.com",
    "use_ssl": true,
    "ssl_cert_path": "/etc/ssl/certs/server.crt",
    "ssl_key_path": "/etc/ssl/private/server.key"
  },
  
  "services": {
    "registry": {
      "host": "registry.internal",
      "port": 8000,
      "protocol": "http"
    },
    "orchestrator": {
      "host": "orchestrator.internal",
      "port": 8100,
      "protocol": "http"
    }
  }
}
```

---

## Configuration Files Reference

### 1. enterprise_config.json

**Location**: `shared/config/enterprise_config.json`

| Section | Description |
|---------|-------------|
| `environment` | `development`, `staging`, `production`, `test` |
| `feature_flags` | Enable/disable major features |
| `compliance` | Audit and compliance settings |
| `llm` | LLM provider configuration |
| `session` | Session management settings |
| `network` | Network and SSL configuration |
| `services` | Core service endpoints |
| `agents` | Agent configurations and ports |
| `mcp_servers` | MCP tool server configurations |
| `workflow` | Workflow execution settings |
| `health_check` | Health monitoring settings |

### 2. security_policies.json

**Location**: `shared/config/security_policies.json`

Defines:
- Role-based access control (RBAC)
- Tool-specific authorization limits
- Rate limiting per tool
- Approval workflows

### 3. guardrails_config.json

**Location**: `shared/config/guardrails_config.json`

Defines:
- PII detection patterns
- Input validation rules (jailbreak prevention)
- Output filters (topic blocking)
- Disclaimers

---

## Deployment Methods

### Method 1: Docker Compose (Recommended)

```bash
# Build and start all services
docker-compose up -d

# Check logs
docker-compose logs -f orchestrator

# Stop services
docker-compose down
```

### Method 2: Kubernetes

```bash
# Apply configurations
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmaps/
kubectl apply -f k8s/secrets/
kubectl apply -f k8s/deployments/
kubectl apply -f k8s/services/

# Verify
kubectl get pods -n agenttoagent
```

### Method 3: Manual (Development)

```bash
# Start services in order
./start_services.sh

# Or start individually
cd services/registry && python app.py &
cd services/orchestrator && python app.py &
cd services/agents/math_agent && python app.py &
# ... etc
```

---

## Service Discovery and Connection

### How Services Find Each Other

All services use the `ConfigManager` to discover other services:

```python
from shared.config import ConfigManager

config = ConfigManager.get_instance()

# Get service URLs
registry_url = config.get_service_url("registry")      # http://localhost:8000
orchestrator_url = config.get_service_url("orchestrator")  # http://localhost:8100
mcp_gateway_url = config.get_service_url("mcp_gateway")    # http://localhost:8300

# Get agent configurations
math_agent_url = config.get_agent_url("math_agent")    # http://localhost:8006
research_url = config.get_agent_url("research_agent")  # http://localhost:8003
```

### Environment Variable Overrides

Environment variables take precedence over config files:

```bash
# Override registry location
export REGISTRY_HOST=registry.mycompany.internal
export REGISTRY_PORT=9000

# Override MCP Gateway
export MCP_GATEWAY_HOST=mcp-gateway.internal
export MCP_GATEWAY_PORT=9300

# Override specific agent
export MATH_AGENT_HOST=math.agents.internal
export MATH_AGENT_PORT=9006
```

### Distributed Deployment Example

For deploying across multiple hosts:

**Host A (Core Services)**:
```bash
export PUBLIC_HOST=core.example.com
export BIND_HOST=0.0.0.0
# Start registry and orchestrator
```

**Host B (Agents)**:
```bash
export PUBLIC_HOST=agents.example.com
export REGISTRY_HOST=core.example.com
export ORCHESTRATOR_HOST=core.example.com
# Start agents
```

**Host C (MCP Tools)**:
```bash
export PUBLIC_HOST=tools.example.com
export MCP_REGISTRY_HOST=core.example.com
# Start MCP servers
```

---

## Security Configuration

### Enable Enterprise Security

1. **Enable all security features** in `enterprise_config.json`:

```json
{
  "feature_flags": {
    "enable_guardrails": true,
    "enable_audit_logging": true,
    "enable_security_checks": true,
    "enable_pii_redaction": true,
    "enable_identity_propagation": true,
    "strict_mode": true
  }
}
```

2. **Configure PII patterns** in `guardrails_config.json`:

```json
{
  "pii_detection": {
    "enabled": true,
    "patterns": {
      "SSN": {
        "regex": "\\b\\d{3}-\\d{2}-\\d{4}\\b",
        "sensitivity": "high",
        "action": "tokenize"
      },
      "CREDIT_CARD": {
        "regex": "\\b\\d{4}[- ]?\\d{4}[- ]?\\d{4}[- ]?\\d{4}\\b",
        "sensitivity": "high",
        "action": "tokenize"
      }
    }
  }
}
```

3. **Configure tool limits** in `security_policies.json`:

```json
{
  "tool_policies": {
    "transfer_funds": {
      "limits": {
        "amount": {"type": "numeric", "max": 2000.0}
      },
      "requires_approval": true,
      "approval_threshold": 500.0,
      "rate_limit": {"requests": 10, "period_seconds": 3600}
    }
  }
}
```

---

## Monitoring and Observability

### Health Endpoints

All services expose health endpoints:

```bash
# Check core services
curl http://localhost:8000/api/health  # Registry
curl http://localhost:8100/health       # Orchestrator
curl http://localhost:8300/health       # MCP Gateway

# Check agents
curl http://localhost:8006/health       # Math Agent
curl http://localhost:8003/health       # Research Agent
```

### Audit Logs

Audit logs are written to the configured `worm_storage_path`:

```bash
# Default location
ls -la ./audit_logs/

# Verify log integrity (blockchain-style chain)
python -c "
from shared.audit import get_audit_logger
audit = get_audit_logger()
result = audit.verify_chain_integrity()
print('Chain Verified:', result['verified'])
"
```

### Log Structure

Each audit log entry contains:

```json
{
  "timestamp": "2026-02-13T18:30:00Z",
  "trace_id": "trace_abc123",
  "workflow_id": "wf_xyz",
  "user_id": "user_456",
  "actor": "MathAgent",
  "event_type": "TOOL_INVOCATION",
  "details": {...},
  "signature": "sha256:...",
  "previous_hash": "sha256:..."
}
```

---

## Troubleshooting

### Service Won't Start

1. **Check port availability**:
   ```bash
   lsof -i :8100  # Check if port is in use
   ```

2. **Verify configuration**:
   ```bash
   python -c "
   from shared.config import ConfigManager
   config = ConfigManager.get_instance()
   print(config.export_config())
   "
   ```

### Services Can't Connect

1. **Verify network configuration**:
   ```bash
   curl http://localhost:8000/api/health
   ```

2. **Check environment variables**:
   ```bash
   env | grep -E "(REGISTRY|ORCHESTRATOR|MCP)"
   ```

3. **Verify service registration**:
   ```bash
   curl http://localhost:8000/api/registry/agents
   ```

### Configuration Not Loading

1. **Check file paths**:
   ```bash
   ls -la shared/config/
   ```

2. **Validate JSON syntax**:
   ```bash
   python -m json.tool shared/config/enterprise_config.json
   ```

---

## Production Checklist

### Pre-Deployment

- [ ] Set `environment` to `"production"` in enterprise_config.json
- [ ] Enable `strict_mode` in feature_flags
- [ ] Configure SSL certificates
- [ ] Set appropriate rate limits
- [ ] Configure audit log storage (S3, compliant storage)
- [ ] Review and customize security policies
- [ ] Configure PII patterns for your domain
- [ ] Set up monitoring and alerting

### Security

- [ ] Rotate AWS credentials regularly
- [ ] Use IAM roles instead of access keys where possible
- [ ] Enable VPC/network isolation
- [ ] Configure firewall rules
- [ ] Enable encryption at rest for audit logs
- [ ] Set up log retention policies

### Operations

- [ ] Configure health check endpoints in load balancer
- [ ] Set up centralized logging
- [ ] Configure alerting for service failures
- [ ] Document runbooks for common issues
- [ ] Set up backup procedures for audit logs
- [ ] Plan disaster recovery

---

## Quick Reference

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BIND_HOST` | Interface to bind | `0.0.0.0` |
| `PUBLIC_HOST` | Public hostname | `localhost` |
| `REGISTRY_HOST` | Registry service host | `localhost` |
| `REGISTRY_PORT` | Registry service port | `8000` |
| `ORCHESTRATOR_HOST` | Orchestrator host | `localhost` |
| `ORCHESTRATOR_PORT` | Orchestrator port | `8100` |
| `MCP_GATEWAY_HOST` | MCP Gateway host | `localhost` |
| `MCP_GATEWAY_PORT` | MCP Gateway port | `8300` |
| `ENABLE_GUARDRAILS` | Enable guardrails | `true` |
| `ENABLE_AUDIT_LOGGING` | Enable audit logs | `true` |
| `STRICT_MODE` | Enable strict security | `false` |

### Service Ports (Default)

| Service | Port |
|---------|------|
| Registry | 8000 |
| Orchestrator | 8100 |
| MCP Registry | 8200 |
| MCP Gateway | 8300 |
| Code Analyzer | 8001 |
| Data Processor | 8002 |
| Research Agent | 8003 |
| Task Executor | 8004 |
| Observer | 8005 |
| Math Agent | 8006 |
| File Ops | 8210 |
| Database | 8211 |
| Web Search | 8212 |
| Calculator | 8213 |

---

**End of Enterprise Deployment Guide**
