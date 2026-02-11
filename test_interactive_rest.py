#!/usr/bin/env python3
"""
REST-based Interactive Workflow Test

Tests interactive workflow using REST API instead of WebSocket
"""

import requests
import time
import json

ORCHESTRATOR_URL = "http://localhost:8100"

def test_interactive_workflow():
    """Test complete interactive workflow flow"""
    
    workflow_id = f"rest_test_{int(time.time())}"
    
    print(f"\n{'='*80}")
    print(f"  REST-Based Interactive Workflow Test")
    print(f"{'='*80}\n")
    
    # Step 1: Submit workflow
    print("📌 Step 1: Submitting workflow...")
    task = "Research and analyze potential competitors in the cloud computing market"
    
    response = requests.post(
        f"{ORCHESTRATOR_URL}/api/workflow/execute",
        json={
            "task_description": task,
            "workflow_id": workflow_id
        }
    )
    
    if response.status_code != 200:
        print(f"❌ Failed to submit workflow: {response.text}")
        return
    
    print(f"✅ Workflow submitted: {workflow_id}\n")
    
    # Step 2: Poll for workflow status and interaction requests
    print("📌 Step 2: Waiting for interaction request...")
    
    max_attempts = 30
    interaction_found = False
    
    for attempt in range(max_attempts):
        time.sleep(2)
        
        # Check workflow status
        status_response = requests.get(f"{ORCHESTRATOR_URL}/api/workflow/{workflow_id}/status")
        
        if status_response.status_code == 200:
            status_data = status_response.json()
            
            workflow_status = status_data.get("status")
            pending = status_data.get("pending_interactions", [])
            
            print(f"  Attempt {attempt + 1}: Status={workflow_status}, Pending={len(pending)}")
            
            if pending:
                interaction = pending[0]
                interaction_found = True
                
                print(f"\n✅ Interaction request received!")
                print(f"   Request ID: {interaction.get('request_id')}")
                print(f"   Question: {interaction.get('question')}")
                print(f"   Agent: {interaction.get('agent_name')}")
                
                # Step 3: Respond to interaction
                print(f"\n📌 Step 3: Responding to interaction...")
                
                response_payload = {
                    "request_id": interaction.get('request_id'),
                    "response": "Focus on AWS, Azure, and Google Cloud Platform in the enterprise market",
                    "additional_context": "Analyzing top 3 cloud providers"
                }
                
                respond_response = requests.post(
                    f"{ORCHESTRATOR_URL}/api/workflow/{workflow_id}/respond",
                    json=response_payload
                )
                
                if respond_response.status_code == 200:
                    print(f"✅ Response submitted successfully")
                    print(f"   Message: {respond_response.json().get('message')}")
                else:
                    print(f"❌ Failed to submit response: {respond_response.text}")
                    return
                
                break
            
            if workflow_status in ["completed", "failed"]:
                print(f"\n⚠️  Workflow {workflow_status} without requesting interaction")
                break
    
    if not interaction_found:
        print(f"\n❌ No interaction request received within timeout")
        return
    
    # Step 4: Wait for completion
    print(f"\n📌 Step 4: Waiting for workflow completion...")
    
    for attempt in range(max_attempts):
        time.sleep(2)
        
        status_response = requests.get(f"{ORCHESTRATOR_URL}/api/workflow/{workflow_id}/status")
        
        if status_response.status_code == 200:
            status_data = status_response.json()
            workflow_status = status_data.get("status")
            current_step = status_data.get("current_step", 0)
            total_steps = status_data.get("total_steps", 0)
            
            print(f"  Attempt {attempt + 1}: Status={workflow_status}, Steps={current_step}/{total_steps}")
            
            if workflow_status == "completed":
                print(f"\n✅ Workflow completed successfully!")
                
                # Print results
                results = status_data.get("results", [])
                print(f"\n📊 Results ({len(results)} steps):")
                for i, result in enumerate(results, 1):
                    print(f"\n  Step {i}: {result.get('capability')}")
                    print(f"    Agent: {result.get('agent')}")
                    print(f"    Status: {result.get('step_status', 'completed')}")
                
                return
            
            elif workflow_status == "failed":
                print(f"\n❌ Workflow failed")
                return
            
            # Check for more interactions
            pending = status_data.get("pending_interactions", [])
            if pending:
                print(f"\n⚠️  Another interaction needed!")
                # Could handle multiple interactions here
    
    print(f"\n❌ Workflow did not complete within timeout")

if __name__ == "__main__":
    try:
        test_interactive_workflow()
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
