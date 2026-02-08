# AWS Credentials Configuration - Summary of Changes

**Date**: 2026-02-07  
**Issue**: Docker Compose deployment couldn't use local AWS credentials like shell script deployment

## Problem

### Before:
```yaml
# Old docker-compose.yml
environment:
  - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}      # REQUIRED
  - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}  # REQUIRED
```

**Issues:**
- ❌ Required creating `.env` file with credentials
- ❌ Couldn't use existing `~/.aws/credentials` configuration
- ❌ Different behavior from shell script deployment
- ❌ Users had to duplicate credentials

## Solution

### After:
```yaml
# New docker-compose.yml
environment:
  - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-}    # Optional (empty default)
  - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-}  # Optional
  - AWS_PROFILE=${AWS_PROFILE:-default}         # NEW: Profile support
volumes:
  - ${HOME}/.aws:/root/.aws:ro                  # NEW: Mount credentials
```

**Benefits:**
- ✅ Automatically uses local `~/.aws/credentials`
- ✅ Same behavior as shell script deployment
- ✅ No need to duplicate credentials
- ✅ Still supports `.env` file if preferred
- ✅ Works with AWS profiles
- ✅ Read-only mount for security

## Services Updated

Updated 5 services that use AWS Bedrock:

1. **orchestrator** (port 8100) - Workflow orchestration with LLM
2. **mcp-gateway** (port 8300) - Tool routing with AI
3. **code-analyzer** (port 8001) - Code analysis agent
4. **data-processor** (port 8002) - Data analysis agent
5. **research-agent** (port 8003) - Research agent

Each service now has:
- Optional AWS credential environment variables
- Mounted `~/.aws` directory (read-only)
- AWS profile support

## Usage Comparison

### Shell Script (No Change)
```bash
# Just works with your AWS CLI configuration
aws configure
./start_services.sh
```

### Docker Compose (Before - Required .env)
```bash
# HAD TO: Create .env file
cat > .env << 'EOF'
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=us-east-1
EOF

docker-compose up -d
```

### Docker Compose (After - Automatic)
```bash
# NOW: Just works with your AWS CLI configuration!
aws configure
docker-compose up -d
```

## Credential Methods Supported

Both deployment methods now support the same credential sources:

### 1. AWS CLI Configuration (Recommended)
```bash
aws configure
# Credentials stored in ~/.aws/credentials
# Both shell script and Docker use these automatically
```

### 2. Environment Variables
```bash
export AWS_ACCESS_KEY_ID="key"
export AWS_SECRET_ACCESS_KEY="secret"
# Both shell script and Docker use these
```

### 3. .env File (Docker only)
```bash
# Create .env file
cat > .env << 'EOF'
AWS_ACCESS_KEY_ID=key
AWS_SECRET_ACCESS_KEY=secret
EOF
# Docker Compose reads from .env
```

### 4. IAM Roles (Production)
```bash
# On EC2/ECS with IAM role
# Both shell script and Docker use instance role automatically
```

## Implementation Details

### Volume Mount
```yaml
volumes:
  - ${HOME}/.aws:/root/.aws:ro
```
- Mounts user's AWS directory into container
- Read-only (`:ro`) for security
- Boto3 automatically finds credentials
- Works with profiles and config files

### Environment Variables
```yaml
- AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-}
- AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-}
- AWS_PROFILE=${AWS_PROFILE:-default}
```
- `${VAR:-}` provides empty default if not set
- Empty values allow boto3 to use mounted credentials
- AWS_PROFILE new addition for profile support

## Credential Precedence

AWS SDK checks in this order:
1. Environment variables (if set)
2. Mounted credentials file (~/.aws/credentials)
3. IAM instance role (if on EC2/ECS)

## Files Modified

- `docker-compose.yml` - Updated 5 services
  - Added volume mounts for `~/.aws`
  - Changed env vars to optional (empty defaults)
  - Added AWS_PROFILE support

## Documentation Created

- `AWS_CREDENTIALS_GUIDE.md` - Comprehensive credential guide
- Updated `DOCKER_DEPLOYMENT.md` - New credential methods
- Updated `QUICK_START.md` - Simplified Docker setup

## Testing

Verified both deployment methods work identically:

```bash
# Test 1: Shell script
aws configure
./start_services.sh
curl http://localhost:8100/api/workflow/execute ...
# ✅ Works

# Test 2: Docker Compose (no .env needed)
docker-compose down
docker-compose up -d
curl http://localhost:8100/api/workflow/execute ...
# ✅ Works identically
```

## Migration Guide

### If You Have Existing .env File
- ✅ Still works! No changes needed
- Environment variables take precedence over mounted credentials

### If You Use AWS CLI
- ✅ Remove .env file (optional)
- ✅ Just run `docker-compose up -d`
- ✅ Services automatically use your credentials

### If You Use IAM Roles (Production)
- ✅ Remove volume mounts from docker-compose.yml (optional)
- ✅ Services use instance role automatically

## Security Improvements

1. **Read-only mount**: Credentials cannot be modified by containers
2. **No credential duplication**: Single source of truth
3. **Automatic rotation**: Update credentials once, everywhere benefits
4. **No git exposure**: No .env files with credentials needed

## Verification Commands

```bash
# Check credentials are mounted
docker-compose exec orchestrator ls -la /root/.aws

# Test AWS access
docker-compose exec orchestrator python3 -c "
import boto3
client = boto3.client('bedrock-runtime', region_name='us-east-1')
print('✅ AWS working')
"

# View which credentials are being used
docker-compose logs orchestrator | grep -i bedrock
```

## Summary

**Before**: Docker and shell script deployments had different AWS setup  
**After**: Both deployments work identically with local AWS credentials

**Impact**: 
- Simplified setup process
- Better developer experience  
- Consistent behavior across deployment methods
- More secure credential management

**Status**: ✅ Implemented and tested  
**Breaking Changes**: None - backward compatible with .env files
