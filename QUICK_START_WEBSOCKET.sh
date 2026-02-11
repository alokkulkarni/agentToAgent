#!/bin/bash
# Quick Reference: Interactive Workflow with curl + websocat

cat << 'EOF'
================================================================================
QUICK REFERENCE: Interactive Workflow (WebSocket)
================================================================================

PREREQUISITES:
  brew install websocat      # macOS
  cargo install websocat     # Linux/Windows

STEP 1: Start Workflow (curl)
─────────────────────────────────────────────────────────────────────────────
WORKFLOW_ID="demo_$(date +%s)"

curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d "{
    \"workflow_id\": \"$WORKFLOW_ID\",
    \"task_description\": \"Research cloud computing competitors\",
    \"async_mode\": true
  }" | jq

# Save the workflow_id for next step
echo "Workflow ID: $WORKFLOW_ID"

STEP 2: Connect WebSocket (websocat)
─────────────────────────────────────────────────────────────────────────────
websocat "ws://localhost:8100/ws/workflow/$WORKFLOW_ID"

STEP 3: Interact with Workflow
─────────────────────────────────────────────────────────────────────────────

You'll receive messages from the orchestrator:

┌──────────────────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR SENDS:                                                      │
├──────────────────────────────────────────────────────────────────────────┤
│ {"type": "connection_established", "workflow_id": "demo_123"}           │
│ {"type": "step_started", "step": {"step_number": 1, ...}}              │
│ {"type": "step_completed", "step": {"step_number": 1}}                 │
│                                                                          │
│ {"type": "user_input_required",                                         │
│  "interaction": {                                                       │
│    "request_id": "req_001",                                            │
│    "question": "Which aspect should I focus on?",                      │
│    "options": ["Pricing", "Services", "All"]                           │
│  }}                                                                     │
└──────────────────────────────────────────────────────────────────────────┘

When you see "user_input_required", TYPE THIS and press ENTER:

┌──────────────────────────────────────────────────────────────────────────┐
│ YOU SEND:                                                                │
├──────────────────────────────────────────────────────────────────────────┤
│ {"type":"user_response","request_id":"req_001","response":"AWS, Azure"}│
└──────────────────────────────────────────────────────────────────────────┘

The workflow will resume and may ask ANOTHER question:

┌──────────────────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR SENDS:                                                      │
├──────────────────────────────────────────────────────────────────────────┤
│ {"type": "workflow_resuming"}                                           │
│                                                                          │
│ {"type": "user_input_required",                                         │
│  "interaction": {                                                       │
│    "request_id": "req_002",  ◄── NEW request_id!                       │
│    "question": "Should I include pricing?",                            │
│    "input_type": "text"                                                │
│  }}                                                                     │
└──────────────────────────────────────────────────────────────────────────┘

Respond again with the NEW request_id:

┌──────────────────────────────────────────────────────────────────────────┐
│ YOU SEND:                                                                │
├──────────────────────────────────────────────────────────────────────────┤
│ {"type":"user_response","request_id":"req_002","response":"Yes"}       │
└──────────────────────────────────────────────────────────────────────────┘

Continue until you see:

┌──────────────────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR SENDS:                                                      │
├──────────────────────────────────────────────────────────────────────────┤
│ {"type": "workflow_completed", "result": {...}}                        │
└──────────────────────────────────────────────────────────────────────────┘

TIPS:
─────────────────────────────────────────────────────────────────────────────
• Keep the websocat window open during entire workflow
• Each question gets a NEW request_id - use the latest one
• You can send multiple responses in sequence
• Press Ctrl+C to disconnect

COMPLETE EXAMPLE SESSION:
─────────────────────────────────────────────────────────────────────────────
# Terminal 1: Start workflow
WORKFLOW_ID="test_$(date +%s)"
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d "{\"workflow_id\":\"$WORKFLOW_ID\",\"task_description\":\"Research cloud competitors\",\"async_mode\":true}"

# Terminal 2: Connect and interact
websocat "ws://localhost:8100/ws/workflow/$WORKFLOW_ID"

# Wait for: {"type":"user_input_required","interaction":{"request_id":"req_001",...}}
# Type: {"type":"user_response","request_id":"req_001","response":"AWS, Azure, GCP"}

# Wait for: {"type":"user_input_required","interaction":{"request_id":"req_002",...}}
# Type: {"type":"user_response","request_id":"req_002","response":"Compare pricing"}

# Wait for: {"type":"user_input_required","interaction":{"request_id":"req_003",...}}
# Type: {"type":"user_response","request_id":"req_003","response":"Include market share"}

# Wait for: {"type":"workflow_completed",...}
# Done!

ALTERNATIVE: Using REST API (polling)
─────────────────────────────────────────────────────────────────────────────
If you don't have websocat, use the polling script:

    ./examples/rest_interactive_workflow.sh

This simulates WebSocket by checking status every 3 seconds.

MORE INFORMATION:
─────────────────────────────────────────────────────────────────────────────
• Full Guide: WEBSOCKET_GUIDE.md
• Architecture: MULTI_STEP_INTERACTIONS.md
• Python Example: examples/websocket_interactive_workflow.py

================================================================================
EOF
