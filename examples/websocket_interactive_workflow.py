#!/usr/bin/env python3
"""
WebSocket Interactive Workflow Example
======================================

This example demonstrates how to use WebSocket for fully interactive workflows
where agents can ask multiple questions in sequence and receive responses.

Key Features:
- Bidirectional communication via WebSocket
- Real-time notifications of workflow progress
- Support for multiple sequential user interactions
- Automatic handling of new interaction requests

Prerequisites:
    pip install websockets asyncio

Usage:
    python3 examples/websocket_interactive_workflow.py
"""

import asyncio
import websockets
import json
import sys
from datetime import datetime


class WorkflowWebSocketClient:
    """Interactive workflow client using WebSocket"""
    
    def __init__(self, orchestrator_url: str = "ws://localhost:8100"):
        self.orchestrator_url = orchestrator_url
        self.websocket = None
        self.workflow_id = None
        self.pending_interactions = []
        
    async def connect(self, workflow_id: str):
        """Connect to workflow WebSocket"""
        self.workflow_id = workflow_id
        uri = f"{self.orchestrator_url}/ws/workflow/{workflow_id}"
        
        print(f"\n🔌 Connecting to WebSocket: {uri}")
        
        # Retry logic for connection
        max_retries = 5
        for i in range(max_retries):
            try:
                self.websocket = await websockets.connect(uri, open_timeout=20)
                print(f"✅ Connected to workflow: {workflow_id}\n")
                return
            except Exception as e:
                print(f"   ⚠️ Connection attempt {i+1}/{max_retries} failed: {e}")
                if i < max_retries - 1:
                    await asyncio.sleep(2)
        
        raise Exception(f"Failed to connect to WebSocket after {max_retries} attempts")
        
    async def send_message(self, message: dict):
        """Send message to orchestrator"""
        if not self.websocket:
            raise Exception("Not connected")
        
        await self.websocket.send(json.dumps(message))
        
    async def receive_message(self):
        """Receive message from orchestrator"""
        if not self.websocket:
            raise Exception("Not connected")
            
        message = await self.websocket.recv()
        return json.loads(message)
        
    async def send_user_response(self, request_id: str, response: str):
        """Send user response to interaction request"""
        print(f"\n📤 Sending response to request {request_id[:12]}...")
        print(f"   Response: {response}")
        
        await self.send_message({
            "type": "user_response",
            "request_id": request_id,
            "response": response
        })
        
    async def handle_messages(self):
        """Handle incoming messages from orchestrator"""
        try:
            while True:
                message = await self.receive_message()
                message_type = message.get("type", "unknown")
                
                print(f"\n📨 Received: {message_type}")
                
                if message_type == "connection_established":
                    print(f"   ✅ Connection established")
                    print(f"   Workflow: {message.get('workflow_id')}")
                    
                elif message_type == "workflow_status":
                    status = message.get("status")
                    print(f"   Status: {status}")
                    
                elif message_type == "step_started":
                    step = message.get("step", {})
                    print(f"   📌 Step {step.get('step_number')}: {step.get('description', 'N/A')[:60]}...")
                    
                elif message_type == "step_completed":
                    step = message.get("step", {})
                    print(f"   ✅ Step {step.get('step_number')} completed")
                    
                elif message_type == "user_input_required":
                    # This is the key message type for interactions!
                    interaction = message.get("interaction", {})
                    request_id = interaction.get("request_id")
                    question = interaction.get("question")
                    input_type = interaction.get("input_type", "text")
                    options = interaction.get("options", [])
                    
                    print(f"\n" + "="*80)
                    print(f"⏸️  USER INPUT REQUIRED")
                    print(f"="*80)
                    print(f"Request ID: {request_id}")
                    print(f"Question: {question}")
                    print(f"Input Type: {input_type}")
                    
                    if options:
                        print(f"\nOptions:")
                        for i, option in enumerate(options, 1):
                            print(f"  {i}. {option}")
                    
                    print(f"\n" + "="*80)
                    
                    # Store for user to respond to
                    self.pending_interactions.append({
                        "request_id": request_id,
                        "question": question,
                        "options": options,
                        "input_type": input_type
                    })
                    
                    # Auto-respond for demo purposes (in real app, wait for user input)
                    await asyncio.sleep(2)
                    
                    # Try to select from options if available
                    if options and len(options) > 0:
                        # Intelligently pick an option based on question context
                        if any(keyword in question.lower() for keyword in ["aspect", "focus", "which"]):
                            # Pick first meaningful option (usually most specific)
                            response = options[0] if len(options) > 0 else "All aspects"
                        elif "pricing" in question.lower():
                            # Look for pricing-related option
                            response = next((opt for opt in options if "pricing" in opt.lower()), options[0])
                        else:
                            # Default to first option or comprehensive option
                            response = next((opt for opt in options if "all" in opt.lower() or "comprehensive" in opt.lower()), options[0])
                    else:
                        # No options provided, give generic response
                        if "which aspect" in question.lower() or "focus" in question.lower():
                            response = "Focus on AWS, Azure, and Google Cloud Platform"
                        elif "pricing" in question.lower():
                            response = "Compare pricing models and cost structures"
                        elif "service" in question.lower():
                            response = "Analyze core IaaS and PaaS offerings"
                        else:
                            response = "Please provide a comprehensive analysis"
                    
                    await self.send_user_response(request_id, response)
                    
                elif message_type == "response_received":
                    print(f"   ✅ Response acknowledged")
                    
                elif message_type == "workflow_resuming":
                    print(f"   🔄 Workflow resuming execution...")
                    
                elif message_type == "workflow_completed":
                    print(f"\n🎉 WORKFLOW COMPLETED!")
                    result = message.get("result", {})
                    print(f"   Status: {result.get('status')}")
                    break
                    
                elif message_type == "error":
                    print(f"   ❌ Error: {message.get('message')}")
                    
                else:
                    print(f"   Unknown message type: {message_type}")
                    
        except websockets.exceptions.ConnectionClosed:
            print(f"\n🔌 WebSocket connection closed")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            
    async def close(self):
        """Close WebSocket connection"""
        if self.websocket:
            await self.websocket.close()
            print(f"\n👋 Connection closed")


async def main():
    """Main workflow execution"""
    import requests
    
    workflow_id = f"ws_test_{int(datetime.now().timestamp())}"
    orchestrator_rest = "http://localhost:8100"
    
    print(f"""
{'='*80}
WebSocket Interactive Workflow Example
{'='*80}

This example demonstrates:
1. Creating a workflow via REST API
2. Connecting to workflow via WebSocket
3. Receiving real-time updates
4. Responding to multiple interaction requests
5. Completing the workflow

Workflow ID: {workflow_id}
{'='*80}
""")
    
    # Step 1: Create workflow via REST API
    print(f"\n[1] Creating workflow via REST API...")
    try:
        response = requests.post(
            f"{orchestrator_rest}/api/workflow/execute",
            json={
                "workflow_id": workflow_id,
                "task_description": "Research and compare cloud computing competitors",
                "async": True  # Important: async mode returns immediately
            },
            timeout=30
        )
        
        if response.status_code in [200, 202]:
            result = response.json()
            print(f"   ✅ Workflow created")
            print(f"   Status: {result.get('status')}")
            
            # If it immediately needs input, note it
            if result.get('status') == 'waiting_for_input':
                interaction = result.get('interaction', {})
                print(f"   ⏸️  Already paused for input")
                print(f"   Question: {interaction.get('question', 'N/A')[:60]}...")
        else:
            print(f"   ❌ Failed: {response.status_code}")
            print(f"   {response.text}")
            return
            
    except Exception as e:
        print(f"   ❌ Error creating workflow: {e}")
        return
    
    # Step 2: Connect via WebSocket and handle messages
    print(f"\n[2] Connecting via WebSocket...")
    client = WorkflowWebSocketClient()
    
    try:
        await client.connect(workflow_id)
        
        # Start listening for messages
        await client.handle_messages()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await client.close()
    
    print(f"\n{'='*80}")
    print(f"Example completed")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n\n👋 Interrupted by user")
        sys.exit(0)
