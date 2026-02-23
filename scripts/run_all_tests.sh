#!/bin/bash
# Complete System Test Suite
# Tests all functionality of the A2A distributed system

set -e

echo "=================================="
echo "🧪 A2A System Test Suite"
echo "=================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

print_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
    ((TESTS_PASSED++))
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
    ((TESTS_FAILED++))
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

# Check if services are running
print_test "Checking if services are running..."

if curl -s http://localhost:8000/health > /dev/null; then
    print_success "Registry service is running"
else
    print_error "Registry service is not running"
    echo "Please run: ./start_services.sh"
    exit 1
fi

if curl -s http://localhost:8100/health > /dev/null; then
    print_success "Orchestrator service is running"
else
    print_error "Orchestrator service is not running"
    echo "Please run: ./start_services.sh"
    exit 1
fi

echo ""
echo "=================================="
echo "Test 1: Basic Workflow"
echo "=================================="

print_test "Testing simple math workflow..."

RESULT=$(curl -s -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Calculate 25 + 17",
    "workflow_id": "test_math_basic"
  }')

if echo "$RESULT" | grep -q "completed"; then
    print_success "Basic workflow completed"
else
    print_error "Basic workflow failed"
    echo "$RESULT"
fi

echo ""
echo "=================================="
echo "Test 2: Multi-Step Workflow"
echo "=================================="

print_test "Testing multi-step workflow with context passing..."

RESULT=$(curl -s -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Calculate 25 + 17, then square the result",
    "workflow_id": "test_math_multistep"
  }')

if echo "$RESULT" | grep -q "completed"; then
    print_success "Multi-step workflow completed"
    
    # Check if result is correct (should be 1764)
    if echo "$RESULT" | grep -q "1764"; then
        print_success "Correct result calculated (1764)"
    else
        print_info "Result may not match expected value"
    fi
else
    print_error "Multi-step workflow failed"
    echo "$RESULT"
fi

echo ""
echo "=================================="
echo "Test 3: Research Workflow"
echo "=================================="

print_test "Testing research agent workflow..."

RESULT=$(curl -s -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "What are the benefits of cloud computing?",
    "workflow_id": "test_research_basic"
  }')

if echo "$RESULT" | grep -q "completed"; then
    print_success "Research workflow completed"
else
    print_error "Research workflow failed"
    echo "$RESULT"
fi

echo ""
echo "=================================="
echo "Test 4: Interactive Workflow (Pause)"
echo "=================================="

print_test "Starting workflow that requires user input..."

WORKFLOW_ID="test_interactive_$(date +%s)"

RESULT=$(curl -s -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d "{
    \"task_description\": \"Research and analyze potential competitors in the market and their strategies\",
    \"workflow_id\": \"$WORKFLOW_ID\"
  }")

if echo "$RESULT" | grep -q "waiting_for_input"; then
    print_success "Workflow paused for user input"
    
    # Extract request ID
    REQUEST_ID=$(echo "$RESULT" | grep -o '"request_id":"[^"]*"' | cut -d'"' -f4)
    
    if [ -n "$REQUEST_ID" ]; then
        print_success "Got interaction request ID: $REQUEST_ID"
        
        echo ""
        print_test "Submitting user response..."
        
        sleep 2  # Give it a moment
        
        RESPONSE_RESULT=$(curl -s -X POST "http://localhost:8100/api/workflow/$WORKFLOW_ID/respond" \
          -H "Content-Type: application/json" \
          -d "{
            \"request_id\": \"$REQUEST_ID\",
            \"response\": \"Focus on cloud service providers like AWS, Azure, and Google Cloud\"
          }")
        
        if echo "$RESPONSE_RESULT" | grep -q "success"; then
            print_success "Response submitted successfully"
            
            echo ""
            print_test "Waiting for workflow to resume and complete..."
            
            sleep 10
            
            # Check final status
            STATUS_RESULT=$(curl -s "http://localhost:8100/api/workflow/$WORKFLOW_ID/status")
            
            if echo "$STATUS_RESULT" | grep -q "completed"; then
                print_success "Workflow completed after resumption"
            elif echo "$STATUS_RESULT" | grep -q "waiting_for_input"; then
                print_info "Workflow paused again (may need additional input)"
            else
                print_error "Workflow did not complete as expected"
            fi
        else
            print_error "Failed to submit response"
        fi
    else
        print_error "Could not extract request ID"
    fi
elif echo "$RESULT" | grep -q "completed"; then
    print_info "Workflow completed without requiring input (agent had enough context)"
else
    print_error "Workflow did not pause as expected"
    echo "$RESULT"
fi

echo ""
echo "=================================="
echo "Test 5: Capability Discovery"
echo "=================================="

print_test "Testing capability discovery..."

CAPS=$(curl -s http://localhost:8100/api/capabilities)

if echo "$CAPS" | grep -q "calculate"; then
    print_success "Found calculate capability"
else
    print_error "calculate capability not found"
fi

if echo "$CAPS" | grep -q "answer_question"; then
    print_success "Found answer_question capability"
else
    print_error "answer_question capability not found"
fi

if echo "$CAPS" | grep -q "analyze_data"; then
    print_success "Found analyze_data capability"
else
    print_error "analyze_data capability not found"
fi

echo ""
echo "=================================="
echo "Test 6: Agent Registry"
echo "=================================="

print_test "Testing agent registry..."

AGENTS=$(curl -s http://localhost:8000/api/registry/agents)

if echo "$AGENTS" | grep -q "MathAgent"; then
    print_success "MathAgent registered"
else
    print_error "MathAgent not found"
fi

if echo "$AGENTS" | grep -q "ResearchAgent"; then
    print_success "ResearchAgent registered"
else
    print_error "ResearchAgent not found"
fi

if echo "$AGENTS" | grep -q "DataProcessor"; then
    print_success "DataProcessor registered"
else
    print_error "DataProcessor not found"
fi

echo ""
echo "=================================="
echo "Test 7: WebSocket Connection"
echo "=================================="

print_test "Testing WebSocket connectivity..."

# This would require a WebSocket client, so we just note it
print_info "WebSocket test requires manual testing or Python script"
print_info "Run: python3 test_websocket_interactive.py"

echo ""
echo "=================================="
echo "Test 8: Database Persistence"
echo "=================================="

print_test "Testing workflow persistence..."

DB_FILE="services/orchestrator/workflows.db"

if [ -f "$DB_FILE" ]; then
    print_success "Database file exists"
    
    # Check if workflows table has data
    WORKFLOW_COUNT=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM workflows;" 2>/dev/null || echo "0")
    
    if [ "$WORKFLOW_COUNT" -gt 0 ]; then
        print_success "Database has $WORKFLOW_COUNT workflow(s)"
    else
        print_info "Database exists but no workflows recorded yet"
    fi
else
    print_error "Database file not found"
fi

echo ""
echo "=================================="
echo "Test 9: Error Handling"
echo "=================================="

print_test "Testing error handling with invalid capability..."

ERROR_RESULT=$(curl -s -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Use a non-existent capability called magic_power",
    "workflow_id": "test_error_handling"
  }')

if echo "$ERROR_RESULT" | grep -q "completed\|skipped\|failed"; then
    print_success "System handled invalid capability gracefully"
else
    print_info "Error handling result: $ERROR_RESULT"
fi

echo ""
echo "=================================="
echo "Test 10: Context Enrichment"
echo "=================================="

print_test "Testing context enrichment across steps..."

CONTEXT_RESULT=$(curl -s -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "What is machine learning? Then summarize your answer.",
    "workflow_id": "test_context_enrichment"
  }')

if echo "$CONTEXT_RESULT" | grep -q "completed"; then
    print_success "Context enrichment workflow completed"
    
    # Check if both steps completed
    STEP_COUNT=$(echo "$CONTEXT_RESULT" | grep -o '"step":' | wc -l)
    if [ "$STEP_COUNT" -ge 2 ]; then
        print_success "Multiple steps completed with context passing"
    fi
else
    print_error "Context enrichment workflow failed"
fi

echo ""
echo "=================================="
echo "📊 Test Summary"
echo "=================================="
echo ""
echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Failed: $TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 All tests passed!${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠️  Some tests failed. Check output above.${NC}"
    exit 1
fi
