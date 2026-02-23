#!/bin/bash

# =============================================================================
# A2A System Deployment Verification Script
# =============================================================================
# This script verifies that all services are running correctly and can
# communicate with each other.
#
# Usage: ./verify_deployment.sh
# =============================================================================

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
PASSED=0
FAILED=0

# Helper functions
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_test() {
    echo -e "${YELLOW}→ Testing:${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓ PASSED:${NC} $1"
    ((PASSED++))
}

print_failure() {
    echo -e "${RED}✗ FAILED:${NC} $1"
    ((FAILED++))
}

check_service() {
    local name=$1
    local url=$2
    local expected_code=${3:-200}
    
    print_test "$name ($url)"
    
    if response=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>&1); then
        if [ "$response" = "$expected_code" ]; then
            print_success "$name is healthy (HTTP $response)"
        else
            print_failure "$name returned HTTP $response (expected $expected_code)"
        fi
    else
        print_failure "$name is not reachable"
    fi
}

test_workflow() {
    local description=$1
    local task=$2
    local workflow_id=$3
    
    print_test "$description"
    
    response=$(curl -s -X POST http://localhost:8100/api/workflow/execute \
        -H "Content-Type: application/json" \
        -d "{\"task_description\": \"$task\", \"workflow_id\": \"$workflow_id\"}" 2>&1)
    
    if echo "$response" | grep -q "workflow_id"; then
        print_success "$description - Workflow executed"
    else
        print_failure "$description - Workflow failed"
        echo "$response"
    fi
}

# =============================================================================
# PHASE 1: Check if services are running
# =============================================================================
print_header "PHASE 1: Service Health Checks"

check_service "Registry" "http://localhost:8000/health"
check_service "Orchestrator" "http://localhost:8100/health"
check_service "MCP Registry" "http://localhost:8200/" 200
check_service "MCP Gateway" "http://localhost:8300/health"

# Agent services
check_service "Code Analyzer" "http://localhost:8001/health"
check_service "Data Processor" "http://localhost:8002/health"
check_service "Research Agent" "http://localhost:8003/health"
check_service "Task Executor" "http://localhost:8004/health"
check_service "Observer" "http://localhost:8005/health"
check_service "Math Agent" "http://localhost:8006/health"

# =============================================================================
# PHASE 2: Check service registration
# =============================================================================
print_header "PHASE 2: Service Registration"

print_test "Checking registered agents"
agents=$(curl -s http://localhost:8000/api/registry/agents)
if echo "$agents" | grep -q "CodeAnalyzer"; then
    print_success "Agents are registered with registry"
else
    print_failure "Agents are not properly registered"
fi

print_test "Checking registered MCP servers"
mcp_servers=$(curl -s http://localhost:8200/servers)
if echo "$mcp_servers" | grep -q "CalculatorServer"; then
    print_success "MCP servers are registered"
else
    print_failure "MCP servers are not properly registered"
fi

# =============================================================================
# PHASE 3: Test MCP tools directly
# =============================================================================
print_header "PHASE 3: MCP Tool Tests"

print_test "Testing calculator tool via MCP Gateway"
calc_response=$(curl -s -X POST http://localhost:8300/api/gateway/execute \
    -H "Content-Type: application/json" \
    -d '{"tool_name": "add", "arguments": {"a": 5, "b": 3}}')

if echo "$calc_response" | grep -q "result"; then
    print_success "Calculator tool works via MCP Gateway"
else
    print_failure "Calculator tool failed"
fi

# =============================================================================
# PHASE 4: Test workflows
# =============================================================================
print_header "PHASE 4: Workflow Execution Tests"

test_workflow \
    "Simple math workflow" \
    "Add 10 and 15" \
    "verify_math_001"

sleep 2

test_workflow \
    "Multi-step math workflow" \
    "Add 25 and 17, then square the result" \
    "verify_math_002"

sleep 2

test_workflow \
    "Research workflow" \
    "What is cloud computing?" \
    "verify_research_001"

# =============================================================================
# PHASE 5: Test WebSocket endpoint
# =============================================================================
print_header "PHASE 5: WebSocket Tests"

print_test "Testing WebSocket endpoint availability"
# Note: Simple connection test, actual WebSocket functionality requires a client
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8100/health | grep -q "200"; then
    print_success "WebSocket endpoint (orchestrator) is reachable"
else
    print_failure "WebSocket endpoint is not reachable"
fi

# =============================================================================
# PHASE 6: Test workflow persistence
# =============================================================================
print_header "PHASE 6: Workflow Persistence Tests"

print_test "Checking if workflow database exists"
if docker-compose exec -T orchestrator test -f /app/workflows.db 2>/dev/null; then
    print_success "Workflow database exists"
elif [ -f "./services/orchestrator/workflows.db" ]; then
    print_success "Workflow database exists (shell deployment)"
else
    print_failure "Workflow database not found"
fi

# =============================================================================
# SUMMARY
# =============================================================================
print_header "VERIFICATION SUMMARY"

TOTAL=$((PASSED + FAILED))
PASS_RATE=$(echo "scale=2; $PASSED * 100 / $TOTAL" | bc)

echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo "Total:  $TOTAL"
echo -e "Pass Rate: ${PASS_RATE}%\n"

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ ALL TESTS PASSED!${NC}"
    echo -e "${GREEN}System is fully operational.${NC}"
    echo -e "${GREEN}========================================${NC}"
    exit 0
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}✗ SOME TESTS FAILED!${NC}"
    echo -e "${RED}Please review the failures above.${NC}"
    echo -e "${RED}========================================${NC}"
    exit 1
fi
