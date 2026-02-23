#!/usr/bin/env python3
"""
WebSocket Interactive Workflow Test
Tests the WebSocket real-time updates and user interaction
"""
import asyncio
import aiohttp
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:8100"
WS_URL = "ws://localhost:8100"
WORKFLOW_ID = f"ws_test_{int(time.time())}"

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(msg):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{msg}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")

def print_success(msg):
    print(f"{Colors.OKGREEN}✅ {msg}{Colors.ENDC}")

def print_error(msg):
    print(f"{Colors.FAIL}❌ {msg}{Colors.ENDC}")

def print_info(msg):
    print(f"{Colors.OKCYAN}ℹ️  {msg}{Colors.ENDC}")

def print_warning(msg):
    print(f"{Colors.WARNING}⚠️  {msg}{Colors.ENDC}")


async def websocket_listener(workflow_id, responses_to_provide):
    """Listen to WebSocket and provide responses when requested"""
    
    ws_url = f"{WS_URL}/ws/workflow/{workflow_id}"
    print_info(f"Connecting to WebSocket: {ws_url}")
    
    response_queue = list(responses_to_provide)
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.ws_connect(ws_url) as ws:
                print_success("WebSocket connected!")
                
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        msg_type = data.get("type")
                        
                        print_info(f"📨 Received: {msg_type}")
                        
                        if msg_type == "connection_established":
                            print_success("Connection established")
                            print(json.dumps(data, indent=2))
                        
                        elif msg_type == "workflow_status":
                            status = data.get("status")
                            print_info(f"Workflow status: {status}")
                        
                        elif msg_type == "step_started":
                            step = data.get("step", {})
                            print_info(f"Step {step.get('step_number')} started: {step.get('description')}")
                        
                        elif msg_type == "step_completed":
                            step = data.get("step", {})
                            print_success(f"Step {step.get('step_number')} completed!")
                        
                        elif msg_type == "user_input_required":
                            print_warning("🙋 User input required!")
                            interaction = data.get("interaction", {})
                            request_id = interaction.get("request_id")
                            question = interaction.get("question")
                            
                            print_info(f"Request ID: {request_id}")
                            print_info(f"Question: {question}")
                            
                            # Provide response if available
                            if response_queue:
                                response_text = response_queue.pop(0)
                                print_info(f"Providing response: {response_text}")
                                
                                # Send response via WebSocket
                                await ws.send_json({
                                    "type": "user_response",
                                    "request_id": request_id,
                                    "response": response_text
                                })
                                print_success("Response sent via WebSocket")
                            else:
                                print_warning("No more responses available")
                        
                        elif msg_type == "response_received":
                            print_success("Response acknowledged by server")
                        
                        elif msg_type == "workflow_resuming":
                            print_info("Workflow resuming...")
                        
                        elif msg_type == "workflow_completed":
                            print_success("🎉 Workflow completed!")
                            print(json.dumps(data, indent=2))
                            break
                        
                        elif msg_type == "error":
                            print_error(f"Error: {data.get('message')}")
                        
                        else:
                            print_info(f"Unknown message type: {msg_type}")
                            print(json.dumps(data, indent=2))
                    
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        print_error(f"WebSocket error: {ws.exception()}")
                        break
                
                print_info("WebSocket connection closed")
        
        except Exception as e:
            print_error(f"WebSocket error: {e}")
            import traceback
            traceback.print_exc()


async def start_workflow(workflow_id, task_description):
    """Start the workflow via REST API"""
    
    print_header("Starting Workflow via REST API")
    print_info(f"Workflow ID: {workflow_id}")
    print_info(f"Task: {task_description}")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{BASE_URL}/api/workflow/execute",
            json={
                "task_description": task_description,
                "workflow_id": workflow_id
            }
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                print_success("Workflow started")
                return result
            else:
                error = await resp.text()
                print_error(f"Failed to start workflow: {error}")
                return None


async def test_websocket_workflow():
    """Test complete workflow with WebSocket"""
    
    print_header("🔌 WebSocket Interactive Workflow Test")
    
    task_description = "Research and analyze potential competitors in the market and their strategies"
    
    # Prepare automated responses
    responses = [
        "Focus on cloud service providers: AWS, Azure, and Google Cloud Platform",
        "Compare pricing models, feature sets, and market share"
    ]
    
    # Start WebSocket listener in background
    ws_task = asyncio.create_task(websocket_listener(WORKFLOW_ID, responses))
    
    # Wait a bit for WebSocket to connect
    await asyncio.sleep(2)
    
    # Start workflow
    result = await start_workflow(WORKFLOW_ID, task_description)
    
    if not result:
        print_error("Failed to start workflow")
        ws_task.cancel()
        return
    
    # Wait for WebSocket task to complete (workflow finished)
    try:
        await asyncio.wait_for(ws_task, timeout=120)
        print_success("Test completed successfully!")
    except asyncio.TimeoutError:
        print_warning("Test timed out")
        ws_task.cancel()
    except Exception as e:
        print_error(f"Test failed: {e}")
        ws_task.cancel()


async def main():
    """Run WebSocket test"""
    print_header("🧪 WebSocket Interactive Workflow Test Suite")
    print_info(f"Base URL: {BASE_URL}")
    print_info(f"WebSocket URL: {WS_URL}")
    print_info(f"Timestamp: {datetime.now().isoformat()}\n")
    
    try:
        await test_websocket_workflow()
        print_header("✅ Test Suite Complete")
    except KeyboardInterrupt:
        print_warning("\n\nTest interrupted by user")
    except Exception as e:
        print_error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
