#!/usr/bin/env python3
"""
Test script to debug workflow response submission
"""
import requests
import json

ORCHESTRATOR_URL = "http://localhost:8100"

def test_workflow_response():
    """Test workflow response submission with debugging"""
    
    # Test 1: Check workflow status
    print("=" * 80)
    print("TEST 1: Check workflow status")
    print("=" * 80)
    
    try:
        response = requests.get(f"{ORCHESTRATOR_URL}/api/workflow/test_001/status")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except Exception as e:
        print(f"Error: {e}")
    
    print("\n")
    
    # Test 2: Submit response
    print("=" * 80)
    print("TEST 2: Submit response to interaction request")
    print("=" * 80)
    
    request_id = input("Enter the request_id from the workflow output: ").strip()
    
    if not request_id:
        print("No request_id provided, using example: req_1770556458340")
        request_id = "req_1770556458340"
    
    payload = {
        "request_id": request_id,
        "response": "Focus on AWS, Azure, and Google Cloud Platform"
    }
    
    print(f"\nPayload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(
            f"{ORCHESTRATOR_URL}/api/workflow/test_001/respond",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        print(f"\nStatus Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except Exception as e:
        print(f"Error: {e}")
        if hasattr(e, 'response'):
            print(f"Response text: {e.response.text}")

if __name__ == "__main__":
    test_workflow_response()
