#!/usr/bin/env python3
"""
Test script for interactive workflow with user input requests
"""
import asyncio
import websockets
import json
import sys
import aiohttp
from datetime import datetime

ORCHESTRATOR_REST = "http://localhost:8100"
ORCHESTRATOR_WS = "ws://localhost:8100/ws/workflow"

async def test_interactive_workflow():
    workflow_id = f"test_interactive_{int(datetime.now().timestamp())}"
    task_description = "Research and analyze potential competitors in the market and their strategies"
    
    print("=" * 80)
    print("🧪 TESTING INTERACTIVE WORKFLOW")
    print("=" * 80)
    print(f"Workflow ID: {workflow_id}")
    print(f"Task: {task_description}")
    print()
    
    try:
        # First, submit workflow via REST API in async mode
        print("📤 Submitting workflow via REST API (async mode)...")
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{ORCHESTRATOR_REST}/api/workflow/execute",
                json={
                    "workflow_id": workflow_id,
                    "task_description": task_description,
                    "async": True  # Run in background
                }
            ) as resp:
                if resp.status != 200:
                    print(f"❌ Failed to submit workflow: {resp.status}")
                    return False
                result = await resp.json()
                print(f"✅ Workflow submitted: {result.get('status')}")
                print(f"   WebSocket URL: {result.get('websocket_url')}")
                print()
        
        # Wait a moment for workflow to initialize
        await asyncio.sleep(0.5)
        
        # Now connect to WebSocket to monitor progress
        uri = f"{ORCHESTRATOR_WS}/{workflow_id}"
        print(f"🔌 Connecting to WebSocket: {uri}")
        
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to orchestrator WebSocket")
            print()
            
            # Listen for messages
            interaction_count = 0
            
            while True:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=120.0)
                    data = json.loads(message)
                    
                    msg_type = data.get("type")
                    print(f"📨 Received: {msg_type}")
                    
                    if msg_type == "workflow_started":
                        print(f"🚀 Workflow started: {data.get('workflow_id')}")
                        print()
                    
                    elif msg_type == "step_started":
                        step_info = data.get("step", {})
                        print(f"📌 Step {step_info.get('step_number')}: {step_info.get('description')}")
                        print(f"   Capability: {step_info.get('capability')}")
                        print(f"   Agent: {step_info.get('agent')}")
                        print()
                    
                    elif msg_type == "step_completed":
                        step_info = data.get("step", {})
                        print(f"✅ Step {step_info.get('step_number')} completed")
                        print()
                    
                    elif msg_type == "user_input_required":
                        interaction_count += 1
                        request_id = data.get("request_id")
                        question = data.get("question")
                        context = data.get("context", {})
                        
                        print("=" * 80)
                        print(f"❓ USER INPUT REQUIRED (#{interaction_count})")
                        print("=" * 80)
                        print(f"Request ID: {request_id}")
                        print(f"Agent: {context.get('agent_name')}")
                        print(f"Step: {context.get('step_id')}")
                        print()
                        print(f"Question: {question}")
                        print()
                        
                        # Simulate user response based on the question
                        user_response = ""
                        if "market" in question.lower() or "industry" in question.lower():
                            user_response = "Focus on the cloud computing and SaaS market, specifically companies like AWS, Azure, Google Cloud, and Salesforce."
                        elif "aspect" in question.lower() or "focus" in question.lower():
                            user_response = "Focus on their market positioning, pricing strategies, and key product features."
                        elif "proceed" in question.lower() or "issues" in question.lower():
                            user_response = "Please proceed with the available data and note any limitations in your analysis."
                        else:
                            user_response = "Please proceed with your best judgment based on the available information."
                        
                        print(f"💬 User response: {user_response}")
                        print()
                        
                        # Send response
                        response_msg = {
                            "type": "user_response",
                            "request_id": request_id,
                            "response": user_response
                        }
                        
                        await websocket.send(json.dumps(response_msg))
                        print("✅ Response sent")
                        print("=" * 80)
                        print()
                    
                    elif msg_type == "step_error":
                        step_info = data.get("step", {})
                        error = data.get("error")
                        print(f"❌ Step {step_info.get('step_number')} error: {error}")
                        print()
                    
                    elif msg_type == "workflow_completed":
                        print("=" * 80)
                        print("✅ WORKFLOW COMPLETED")
                        print("=" * 80)
                        status = data.get("status")
                        steps_completed = data.get("steps_completed")
                        total_steps = data.get("total_steps")
                        
                        print(f"Status: {status}")
                        print(f"Steps completed: {steps_completed}/{total_steps}")
                        print(f"User interactions: {interaction_count}")
                        print()
                        
                        results = data.get("results", [])
                        print(f"Results ({len(results)} steps):")
                        for i, result in enumerate(results, 1):
                            print(f"\n  Step {i}:")
                            print(f"    Capability: {result.get('capability')}")
                            print(f"    Agent: {result.get('agent')}")
                            print(f"    Status: {result.get('status', 'N/A')}")
                            
                            if 'result' in result:
                                result_data = result['result']
                                if isinstance(result_data, dict):
                                    for key, value in result_data.items():
                                        if key in ['answer', 'analysis', 'report']:
                                            preview = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                                            print(f"    {key}: {preview}")
                        
                        print()
                        break
                    
                    elif msg_type == "workflow_error":
                        print("=" * 80)
                        print("❌ WORKFLOW ERROR")
                        print("=" * 80)
                        print(f"Error: {data.get('error')}")
                        print()
                        break
                    
                    elif msg_type == "error":
                        print(f"❌ Error: {data.get('message')}")
                        print()
                    
                    else:
                        print(f"📋 Message data: {json.dumps(data, indent=2)[:200]}...")
                        print()
                
                except asyncio.TimeoutError:
                    print("⏱️  Timeout waiting for message (120s)")
                    break
                except websockets.exceptions.ConnectionClosed:
                    print("🔌 Connection closed")
                    break
            
            print("=" * 80)
            print(f"🏁 Test completed with {interaction_count} user interactions")
            print("=" * 80)
    
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    print("Starting interactive workflow test...")
    print()
    
    result = asyncio.run(test_interactive_workflow())
    
    sys.exit(0 if result else 1)
