#!/bin/bash

# Test WebSocket Real-time Updates
# This script submits a workflow and shows you should see real-time updates in WebSocket client

echo "=================================="
echo "WebSocket Real-time Update Test"
echo "=================================="
echo ""
echo "Prerequisites:"
echo "1. Services should be running (./start_services.sh)"
echo "2. WebSocket client should be open in browser"
echo "3. WebSocket client should be connected to a workflow ID"
echo ""
echo "This test will:"
echo "- Submit a simple math workflow"
echo "- You should see real-time updates in the WebSocket client"
echo ""

read -p "Enter workflow ID from WebSocket client (e.g., test_workflow_123): " WORKFLOW_ID

if [ -z "$WORKFLOW_ID" ]; then
    echo "Error: Workflow ID required"
    exit 1
fi

echo ""
echo "Submitting workflow..."
echo ""

curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d "{
    \"task_description\": \"Add 25 and 17, then square the result\",
    \"workflow_id\": \"$WORKFLOW_ID\"
  }" | jq .

echo ""
echo "=================================="
echo "Check your WebSocket client!"
echo "You should see:"
echo "  ▶️ Step started messages"
echo "  ✅ Step completed messages"
echo "  🎉 Workflow completed message"
echo "=================================="
