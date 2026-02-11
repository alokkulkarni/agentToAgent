#!/bin/bash
# WebSocket Interactive Workflow - Shell Script Example
# This demonstrates the complete flow using REST + polling (simulating WebSocket)

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "================================================================================"
echo "WebSocket-Style Interactive Workflow (REST + Polling Simulation)"
echo "================================================================================"
echo ""

ORCHESTRATOR_URL="http://localhost:8100"
WORKFLOW_ID="shell_test_$(date +%s)"

echo -e "${BLUE}Step 1: Create Workflow${NC}"
echo "Workflow ID: $WORKFLOW_ID"
echo ""

# Create workflow
RESPONSE=$(curl -s -X POST "$ORCHESTRATOR_URL/api/workflow/execute" \
  -H "Content-Type: application/json" \
  -d "{
    \"workflow_id\": \"$WORKFLOW_ID\",
    \"task_description\": \"Research cloud computing competitors\",
    \"async\": true
  }")

echo "$RESPONSE" | python3 -m json.tool
echo ""

# Extract first interaction request if present
FIRST_REQUEST_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('interaction', {}).get('request_id', ''))" 2>/dev/null || echo "")

if [ -z "$FIRST_REQUEST_ID" ]; then
    echo -e "${RED}No interaction request found. Workflow may be running in background.${NC}"
    echo "Checking status..."
    echo ""
fi

echo -e "${BLUE}Step 2: Monitor Workflow Status${NC}"
echo "Checking for interaction requests every 3 seconds..."
echo ""

INTERACTION_COUNT=0
MAX_ITERATIONS=30

for i in $(seq 1 $MAX_ITERATIONS); do
    echo -e "${YELLOW}[Check $i/$MAX_ITERATIONS]${NC}"
    
    # Get workflow status
    STATUS_RESPONSE=$(curl -s "$ORCHESTRATOR_URL/api/workflow/$WORKFLOW_ID/status")
    
    # Extract status and pending interactions
    STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))" 2>/dev/null || echo "error")
    PENDING_COUNT=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('pending_interactions', [])))" 2>/dev/null || echo "0")
    
    echo "  Workflow Status: $STATUS"
    echo "  Pending Interactions: $PENDING_COUNT"
    
    # Check if workflow completed
    if [ "$STATUS" = "completed" ]; then
        echo ""
        echo -e "${GREEN}✅ Workflow Completed!${NC}"
        break
    fi
    
    # Check if workflow failed
    if [ "$STATUS" = "failed" ]; then
        echo ""
        echo -e "${RED}❌ Workflow Failed!${NC}"
        break
    fi
    
    # Check for pending interactions
    if [ "$STATUS" = "waiting_for_input" ] && [ "$PENDING_COUNT" -gt "0" ]; then
        echo ""
        echo -e "${GREEN}⏸️  User Input Required!${NC}"
        echo ""
        
        # Get interaction details
        REQUEST_ID=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; reqs=json.load(sys.stdin).get('pending_interactions', []); print(reqs[0]['request_id'] if reqs else '')" 2>/dev/null)
        QUESTION=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; reqs=json.load(sys.stdin).get('pending_interactions', []); print(reqs[0]['question'] if reqs else '')" 2>/dev/null)
        OPTIONS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; reqs=json.load(sys.stdin).get('pending_interactions', []); opts=reqs[0].get('options', []) if reqs else []; print('\n'.join(opts) if opts else '')" 2>/dev/null)
        
        if [ -z "$REQUEST_ID" ]; then
            # Try workflow_context for request info
            REQUEST_ID=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('workflow_context', {}).get('pending_interaction', {}).get('request_id', ''))" 2>/dev/null)
            QUESTION=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('workflow_context', {}).get('pending_interaction', {}).get('question', ''))" 2>/dev/null)
            OPTIONS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); opts=d.get('workflow_context', {}).get('pending_interaction', {}).get('options', []); print('\n'.join(opts) if opts else '')" 2>/dev/null)
        fi
        
        if [ -n "$REQUEST_ID" ]; then
            echo "Request ID: $REQUEST_ID"
            echo ""
            echo -e "${YELLOW}Question:${NC}"
            echo "$QUESTION"
            echo ""
            
            # Show options if available
            if [ -n "$OPTIONS" ]; then
                echo -e "${YELLOW}Available Options:${NC}"
                echo "$OPTIONS" | nl -w2 -s'. '
                echo ""
                echo -e "${BLUE}You can choose from above or provide your own response.${NC}"
                echo ""
            fi
            
            # Increment interaction counter
            INTERACTION_COUNT=$((INTERACTION_COUNT + 1))
            
            # Prompt user for input
            echo -e "${GREEN}Your Response #$INTERACTION_COUNT:${NC}"
            read -p "> " USER_RESPONSE
            
            # If user didn't provide response, skip
            if [ -z "$USER_RESPONSE" ]; then
                echo -e "${YELLOW}⚠️  No response provided. Skipping...${NC}"
                echo ""
                continue
            fi
            
            echo ""
            echo -e "${BLUE}Submitting:${NC} $USER_RESPONSE"
            echo ""
            
            # Submit response
            RESPONSE_RESULT=$(curl -s -X POST "$ORCHESTRATOR_URL/api/workflow/$WORKFLOW_ID/respond" \
              -H "Content-Type: application/json" \
              -d "{
                \"request_id\": \"$REQUEST_ID\",
                \"response\": \"$USER_RESPONSE\"
              }")
            
            echo "$RESPONSE_RESULT" | python3 -m json.tool
            echo ""
            echo -e "${GREEN}✅ Response submitted. Waiting for workflow to resume...${NC}"
            echo ""
            
            # Give workflow time to process
            sleep 3
        else
            echo -e "${YELLOW}⚠️  No request ID found in response${NC}"
        fi
    fi
    
    sleep 3
    echo ""
done

if [ $i -eq $MAX_ITERATIONS ]; then
    echo -e "${YELLOW}⚠️  Maximum iterations reached. Workflow may still be running.${NC}"
fi

echo ""
echo "================================================================================"
echo "Summary:"
echo "  Total Interactions: $INTERACTION_COUNT"
echo "  Final Status: $STATUS"
echo "================================================================================"
echo ""
echo "To use WebSocket instead of polling, use:"
echo "  python3 examples/websocket_interactive_workflow.py"
echo ""
