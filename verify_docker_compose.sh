#!/bin/bash

# Verification script for docker-compose.yml
# Checks that all services and dependencies are properly configured

echo "🔍 Verifying docker-compose.yml configuration..."
echo ""

# Check if docker-compose.yml exists
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ docker-compose.yml not found!"
    exit 1
fi
echo "✅ docker-compose.yml found"

# Validate YAML syntax
if command -v docker-compose &> /dev/null; then
    if docker-compose config > /dev/null 2>&1; then
        echo "✅ docker-compose.yml syntax is valid"
    else
        echo "❌ docker-compose.yml has syntax errors:"
        docker-compose config
        exit 1
    fi
else
    echo "⚠️  docker-compose not installed, skipping syntax validation"
fi

# Check for required services
REQUIRED_SERVICES=(
    "registry"
    "orchestrator"
    "mcp-registry"
    "calculator-server"
    "database-server"
    "file-ops-server"
    "web-search-server"
    "mcp-gateway"
    "code-analyzer"
    "data-processor"
    "research-agent"
    "task-executor"
    "observer"
    "math-agent"
)

echo ""
echo "📋 Checking required services..."
for service in "${REQUIRED_SERVICES[@]}"; do
    if grep -q "^  ${service}:" docker-compose.yml; then
        echo "  ✅ ${service}"
    else
        echo "  ❌ ${service} - MISSING"
    fi
done

# Check port mappings
echo ""
echo "🔌 Checking port mappings..."
PORTS=(
    "8000:registry"
    "8100:orchestrator"
    "8200:mcp-registry"
    "8210:file-ops-server"
    "8211:database-server"
    "8212:web-search-server"
    "8213:calculator-server"
    "8300:mcp-gateway"
    "8001:code-analyzer"
    "8002:data-processor"
    "8003:research-agent"
    "8004:task-executor"
    "8005:observer"
    "8006:math-agent"
)

for port_service in "${PORTS[@]}"; do
    port="${port_service%%:*}"
    service="${port_service##*:}"
    if grep -A 20 "^  ${service}:" docker-compose.yml | grep -q "\"${port}:"; then
        echo "  ✅ ${service} -> ${port}"
    else
        echo "  ❌ ${service} -> ${port} - NOT FOUND"
    fi
done

# Check Dockerfiles exist
echo ""
echo "📦 Checking Dockerfiles..."
DOCKERFILES=(
    "services/registry/Dockerfile"
    "services/orchestrator/Dockerfile"
    "services/mcp_registry/Dockerfile"
    "services/mcp_gateway/Dockerfile"
    "services/mcp_servers/calculator/Dockerfile"
    "services/mcp_servers/database/Dockerfile"
    "services/mcp_servers/file_ops/Dockerfile"
    "services/mcp_servers/web_search/Dockerfile"
    "services/agents/code_analyzer/Dockerfile"
    "services/agents/data_processor/Dockerfile"
    "services/agents/research_agent/Dockerfile"
    "services/agents/task_executor/Dockerfile"
    "services/agents/observer/Dockerfile"
    "services/agents/math_agent/Dockerfile"
)

for dockerfile in "${DOCKERFILES[@]}"; do
    if [ -f "${dockerfile}" ]; then
        echo "  ✅ ${dockerfile}"
    else
        echo "  ❌ ${dockerfile} - MISSING"
    fi
done

# Check dependencies
echo ""
echo "🔗 Checking service dependencies..."
echo "  Layer 1: registry (no dependencies)"
echo "  Layer 2: orchestrator, mcp-registry (depend on registry)"
echo "  Layer 3: MCP servers (depend on mcp-registry)"
echo "  Layer 4: mcp-gateway (depends on all MCP servers)"
echo "  Layer 5: agents (depend on registry, math-agent also on mcp-gateway)"

# Verify critical dependencies
if grep -A 10 "^  orchestrator:" docker-compose.yml | grep -q "registry:"; then
    echo "  ✅ orchestrator depends on registry"
else
    echo "  ❌ orchestrator missing registry dependency"
fi

if grep -A 10 "^  mcp-registry:" docker-compose.yml | grep -q "registry:"; then
    echo "  ✅ mcp-registry depends on registry"
else
    echo "  ❌ mcp-registry missing registry dependency"
fi

if grep -A 10 "^  calculator-server:" docker-compose.yml | grep -q "mcp-registry:"; then
    echo "  ✅ calculator-server depends on mcp-registry"
else
    echo "  ❌ calculator-server missing mcp-registry dependency"
fi

if grep -A 15 "^  mcp-gateway:" docker-compose.yml | grep -q "calculator-server"; then
    echo "  ✅ mcp-gateway depends on MCP servers"
else
    echo "  ❌ mcp-gateway missing MCP server dependencies"
fi

if grep -A 15 "^  math-agent:" docker-compose.yml | grep -q "mcp-gateway"; then
    echo "  ✅ math-agent depends on mcp-gateway"
else
    echo "  ❌ math-agent missing mcp-gateway dependency"
fi

echo ""
echo "✨ Verification complete!"
echo ""
echo "To start the system:"
echo "  docker-compose up -d"
echo ""
echo "To check status:"
echo "  docker-compose ps"
echo ""
echo "To view logs:"
echo "  docker-compose logs -f"
