# AWS Credentials Configuration Guide

This guide explains how AWS credentials are handled in both shell script and Docker Compose deployments.

## Overview

The A2A Multi-Agent System uses AWS Bedrock for LLM capabilities. Services that require AWS credentials:
- **Orchestrator** (planning and workflow orchestration)
- **MCP Gateway** (tool routing with AI)
- **Code Analyzer Agent** (code analysis)
- **Data Processor Agent** (data analysis)
- **Research Agent** (research and question answering)

## Shell Script Deployment

### How It Works
When using `./start_services.sh`, services inherit AWS credentials from your shell environment:

```bash
# Services automatically use credentials from:
# 1. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
# 2. AWS credentials file (~/.aws/credentials)
# 3. AWS config file (~/.aws/config)
# 4. IAM role (if running on EC2)
```

### Setup
```bash
# Option 1: Export environment variables
export AWS_ACCESS_KEY_ID="your_access_key"
export AWS_SECRET_ACCESS_KEY="your_secret_key"
export AWS_REGION="us-east-1"

# Option 2: Use AWS CLI configuration (recommended)
aws configure
# Then credentials are stored in ~/.aws/credentials

# Start services (they inherit credentials)
./start_services.sh
```

---

## Docker Compose Deployment

The docker-compose.yml now supports **three methods** for AWS credentials:

### Method 1: Mount Local AWS Credentials (Recommended for Development)

**How It Works:**
- Docker containers mount your `~/.aws` directory as read-only
- Services automatically use your local AWS configuration
- **No need to expose credentials in environment variables**

**Setup:**
```bash
# 1. Configure AWS CLI (if not already done)
aws configure

# 2. Simply start docker-compose (it will auto-mount ~/.aws)
docker-compose up -d

# That's it! Services will use your local AWS credentials
```

**Advantages:**
- ✅ Uses your existing AWS configuration
- ✅ No need to duplicate credentials
- ✅ Credentials not exposed in docker-compose.yml
- ✅ Works with AWS profiles
- ✅ Automatically rotates when you update credentials locally

### Method 2: Environment Variables via .env File

**How It Works:**
- Credentials specified in a `.env` file
- Docker Compose reads them and passes to containers

**Setup:**
```bash
# 1. Create .env file in project root
cat > .env << 'EOF'
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
AWS_PROFILE=default
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
EOF

# 2. Start services
docker-compose up -d
```

**Advantages:**
- ✅ Explicit credential management
- ✅ Easy to use different credentials per environment
- ✅ Can be managed by CI/CD systems

**Disadvantages:**
- ⚠️ Credentials stored in plaintext file
- ⚠️ Must remember to add .env to .gitignore

### Method 3: Environment Variables (Shell Export)

**How It Works:**
- Credentials exported in shell before running docker-compose
- Docker Compose reads from environment

**Setup:**
```bash
# 1. Export credentials in your shell
export AWS_ACCESS_KEY_ID="your_access_key"
export AWS_SECRET_ACCESS_KEY="your_secret_key"
export AWS_REGION="us-east-1"

# 2. Start services
docker-compose up -d
```

### Method 4: Production - IAM Roles (EC2/ECS)

**How It Works:**
- Services running on AWS automatically use instance IAM role
- No credentials needed in configuration

**Setup:**
```bash
# 1. Ensure EC2 instance has IAM role with Bedrock permissions
# 2. Remove AWS credential mounts from docker-compose.yml
# 3. Start services (they use IAM role automatically)
docker-compose up -d
```

---

## Configuration Details

### docker-compose.yml Configuration

Each service that needs AWS credentials is configured with:

```yaml
services:
  orchestrator:
    environment:
      # Empty default values - allows mounted credentials to take precedence
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-}
      - AWS_REGION=${AWS_REGION:-us-east-1}
      - AWS_PROFILE=${AWS_PROFILE:-default}
      - BEDROCK_MODEL_ID=${BEDROCK_MODEL_ID:-anthropic.claude-3-5-sonnet-20241022-v2:0}
    volumes:
      # Mount local AWS credentials (read-only)
      - ${HOME}/.aws:/root/.aws:ro
```

**Key Points:**
- `${VAR:-}` syntax provides empty default if not set
- Volume mount allows boto3 to find credentials automatically
- Read-only mount (`:ro`) for security
- All AWS-enabled services follow same pattern

---

## Credential Precedence

AWS SDK (boto3) checks credentials in this order:

1. **Environment variables** (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
2. **Mounted credentials file** (~/.aws/credentials)
3. **IAM instance role** (if on EC2/ECS)

With the updated docker-compose.yml:
- If you set environment variables → They are used
- If you don't set env vars → Mounted ~/.aws credentials are used
- If neither exist → IAM role is used (if available)

---

## Verification

### Test Shell Script Deployment

```bash
# Start services
./start_services.sh

# Test if AWS is working
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Explain what is cloud computing"}' | jq .
```

### Test Docker Compose Deployment

```bash
# Start services
docker-compose up -d

# Check orchestrator can access AWS
docker-compose logs orchestrator | grep -i "bedrock\|aws"

# Test workflow
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Explain what is cloud computing"}' | jq .
```

### Troubleshooting AWS Credentials

```bash
# Check if credentials are mounted in container
docker-compose exec orchestrator ls -la /root/.aws

# Check environment variables in container
docker-compose exec orchestrator env | grep AWS

# View service logs for credential errors
docker-compose logs orchestrator | grep -i "credential\|unauthorized\|forbidden"

# Test AWS access from container
docker-compose exec orchestrator python3 -c "
import boto3
try:
    client = boto3.client('bedrock-runtime', region_name='us-east-1')
    print('✅ AWS credentials working!')
except Exception as e:
    print(f'❌ AWS credentials error: {e}')
"
```

---

## Security Best Practices

### For Development (Local)
✅ **Recommended**: Use Method 1 (mount ~/.aws)
- Credentials stay on your machine
- Easy to manage and rotate
- No risk of committing credentials

### For CI/CD
✅ **Recommended**: Use Method 2 (.env file) with secrets management
- Store credentials in CI/CD secrets
- Generate .env during deployment
- Never commit .env to git

### For Production (AWS)
✅ **Recommended**: Use Method 4 (IAM roles)
- Most secure option
- No credential management needed
- Automatic rotation via AWS
- Remove volume mounts from docker-compose.yml

### For Production (Non-AWS)
✅ **Recommended**: Use secrets management system
- AWS Secrets Manager
- HashiCorp Vault
- Kubernetes Secrets
- Fetch credentials at runtime

---

## Comparison Table

| Method | Security | Ease of Use | Best For |
|--------|----------|-------------|----------|
| Mount ~/.aws | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Local development |
| .env file | ⭐⭐ | ⭐⭐⭐⭐ | CI/CD, testing |
| Shell export | ⭐⭐⭐ | ⭐⭐⭐ | Quick testing |
| IAM roles | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | AWS production |

---

## Migration from Old to New

### Old docker-compose.yml
```yaml
environment:
  - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}  # Required env var
  - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}  # Required env var
# No volume mount
```

**Problem**: Required .env file, couldn't use local AWS config

### New docker-compose.yml
```yaml
environment:
  - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-}  # Optional
  - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-}  # Optional
  - AWS_PROFILE=${AWS_PROFILE:-default}  # New: profile support
volumes:
  - ${HOME}/.aws:/root/.aws:ro  # New: auto-mount credentials
```

**Benefits**: 
- ✅ Works without .env file
- ✅ Uses your existing AWS configuration
- ✅ Still supports .env if you prefer

---

## Summary

**For most users:**
```bash
# Just configure AWS once
aws configure

# Then use either deployment method without additional setup:
./start_services.sh         # Shell script
# OR
docker-compose up -d         # Docker Compose
```

Both now work identically with your local AWS credentials! 🎉

---

**Last Updated**: 2026-02-07  
**Version**: 2.0 (with AWS credentials mounting)
