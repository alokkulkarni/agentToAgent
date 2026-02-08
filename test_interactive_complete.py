#!/usr/bin/env python3
"""
Complete Interactive Workflow Test
Tests the entire collaborative human-AI workflow:
1. Start workflow
2. Agent pauses and requests input
3. User provides response
4. Workflow resumes and continues
5. Workflow completes
"""
import asyncio
import aiohttp
import json
from datetime import datetime
import time

BASE_URL = "http://localhost:8100"
WORKFLOW_ID = f"interactive_test_{int(time.time())}"

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

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


async def wait_for_workflow_pause(workflow_id, timeout=60):
    """Poll workflow status until it pauses for input"""
    print_info(f"Waiting for workflow to pause (timeout: {timeout}s)...")
    
    async with aiohttp.ClientSession() as session:
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                async with session.get(f"{BASE_URL}/api/workflow/{workflow_id}/status") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        status = data.get("status")
                        
                        print_info(f"Current status: {status}")
                        
                        if status == "waiting_for_input":
                            print_success("Workflow paused for user input!")
                            return data
                        elif status in ["completed", "failed", "cancelled"]:
                            print_warning(f"Workflow ended with status: {status}")
                            return data
                
            except Exception as e:
                print_warning(f"Error checking status: {e}")
            
            await asyncio.sleep(2)
        
        print_error("Timeout waiting for workflow to pause")
        return None


async def test_interactive_workflow():
    """Test complete interactive workflow"""
    
    print_header("🚀 Interactive Workflow Test")
    
    # Test 1: Start workflow with task that requires input
    print_header("Step 1: Starting Workflow")
    
    task_description = "Research and analyze potential competitors in the market and their strategies"
    
    print_info(f"Workflow ID: {WORKFLOW_ID}")
    print_info(f"Task: {task_description}")
    
    async with aiohttp.ClientSession() as session:
        # Start workflow
        async with session.post(
            f"{BASE_URL}/api/workflow/execute",
            json={
                "task_description": task_description,
                "workflow_id": WORKFLOW_ID
            }
        ) as resp:
            if resp.status == 200:
                result = await resp.json()
                print_success("Workflow started successfully")
                print(json.dumps(result, indent=2))
                
                # Check if immediately paused
                if result.get("status") == "waiting_for_input":
                    print_success("Workflow paused immediately for input")
                    interaction = result.get("interaction", {})
                    request_id = interaction.get("request_id")
                    question = interaction.get("question")
                    
                    print_info(f"Request ID: {request_id}")
                    print_info(f"Question: {question}")
                    
                else:
                    # Wait for workflow to pause
                    print_info("Workflow running, waiting for pause...")
                    workflow_data = await wait_for_workflow_pause(WORKFLOW_ID, timeout=60)
                    
                    if not workflow_data:
                        print_error("Failed to detect workflow pause")
                        return
                    
                    interaction = workflow_data.get("interaction", {})
                    request_id = interaction.get("request_id")
                    question = interaction.get("question")
                    
                    if not request_id:
                        print_error("No interaction request found")
                        print(json.dumps(workflow_data, indent=2))
                        return
                    
                    print_info(f"Request ID: {request_id}")
                    print_info(f"Question: {question}")
                
                # Step 2: Provide user response
                print_header("Step 2: Providing User Response")
                
                user_response = "Focus on cloud service providers like AWS, Azure, and Google Cloud"
                print_info(f"User Response: {user_response}")
                
                async with session.post(
                    f"{BASE_URL}/api/workflow/{WORKFLOW_ID}/respond",
                    json={
                        "request_id": request_id,
                        "response": user_response,
                        "additional_context": {
                            "focus_area": "cloud services"
                        }
                    }
                ) as resp:
                    if resp.status == 200:
                        response_result = await resp.json()
                        print_success("Response submitted successfully")
                        print(json.dumps(response_result, indent=2))
                    else:
                        error = await resp.text()
                        print_error(f"Failed to submit response: {error}")
                        return
                
                # Step 3: Wait for workflow to resume and possibly complete
                print_header("Step 3: Waiting for Workflow Completion")
                
                await asyncio.sleep(5)  # Give it time to resume
                
                # Poll for completion
                for i in range(30):  # Poll for up to 60 seconds
                    async with session.get(f"{BASE_URL}/api/workflow/{WORKFLOW_ID}/status") as resp:
                        if resp.status == 200:
                            status_data = await resp.json()
                            status = status_data.get("status")
                            
                            print_info(f"Status check {i+1}: {status}")
                            
                            if status == "completed":
                                print_success("Workflow completed successfully!")
                                print(json.dumps(status_data, indent=2))
                                
                                # Show results
                                print_header("Final Results")
                                results = status_data.get("results", [])
                                for result in results:
                                    step = result.get("step")
                                    capability = result.get("capability")
                                    print_success(f"Step {step}: {capability}")
                                
                                return
                            
                            elif status == "waiting_for_input":
                                print_warning("Workflow paused again for more input")
                                interaction = status_data.get("interaction", {})
                                print_info(f"Question: {interaction.get('question')}")
                                
                                # For testing, provide another response
                                request_id = interaction.get("request_id")
                                if request_id:
                                    print_header("Providing Additional Response")
                                    async with session.post(
                                        f"{BASE_URL}/api/workflow/{WORKFLOW_ID}/respond",
                                        json={
                                            "request_id": request_id,
                                            "response": "Focus on pricing and feature comparison"
                                        }
                                    ) as resp2:
                                        if resp2.status == 200:
                                            print_success("Additional response submitted")
                            
                            elif status == "failed":
                                print_error("Workflow failed")
                                print(json.dumps(status_data, indent=2))
                                return
                    
                    await asyncio.sleep(2)
                
                print_warning("Workflow did not complete within timeout")
            
            else:
                error = await resp.text()
                print_error(f"Failed to start workflow: {error}")


async def test_rest_api():
    """Test REST API endpoints"""
    print_header("🔍 Testing REST API Endpoints")
    
    async with aiohttp.ClientSession() as session:
        # Test health endpoint
        async with session.get(f"{BASE_URL}/health") as resp:
            if resp.status == 200:
                print_success("Health endpoint OK")
            else:
                print_error("Health endpoint failed")
        
        # Test capabilities endpoint
        async with session.get(f"{BASE_URL}/api/capabilities") as resp:
            if resp.status == 200:
                caps = await resp.json()
                print_success(f"Capabilities endpoint OK ({len(caps)} capabilities)")
            else:
                print_error("Capabilities endpoint failed")


async def main():
    """Run all tests"""
    print_header("🧪 Complete Interactive Workflow Test Suite")
    print_info(f"Testing against: {BASE_URL}")
    print_info(f"Timestamp: {datetime.now().isoformat()}\n")
    
    try:
        # Test REST API
        await test_rest_api()
        
        # Test interactive workflow
        await test_interactive_workflow()
        
        print_header("✅ Test Suite Complete")
        
    except KeyboardInterrupt:
        print_warning("\n\nTest interrupted by user")
    except Exception as e:
        print_error(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
