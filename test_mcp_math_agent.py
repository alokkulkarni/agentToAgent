"""
Test script for MCP System with Math Agent
Tests the integration of Agent Registry, MCP Registry, MCP Gateway, MCP Servers, and Math Agent
"""
import requests
import json
import time
from datetime import datetime, UTC

# Service URLs
AGENT_REGISTRY_URL = "http://localhost:8000"
MCP_REGISTRY_URL = "http://localhost:9001"
MCP_GATEWAY_URL = "http://localhost:9000"
MATH_AGENT_URL = "http://localhost:8006"

def print_section(title):
    """Print section header"""
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")

def print_test(test_name):
    """Print test header"""
    print(f"\n{'-'*60}")
    print(f"Test: {test_name}")
    print(f"{'-'*60}")

def test_services_health():
    """Test that all services are running"""
    print_section("Service Health Checks")
    
    services = {
        "Agent Registry": f"{AGENT_REGISTRY_URL}/health",
        "MCP Registry": f"{MCP_REGISTRY_URL}/health",
        "MCP Gateway": f"{MCP_GATEWAY_URL}/health",
        "Math Agent": f"{MATH_AGENT_URL}/health"
    }
    
    all_healthy = True
    for name, url in services.items():
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"✓ {name}: Healthy")
            else:
                print(f"✗ {name}: Unhealthy (Status: {response.status_code})")
                all_healthy = False
        except Exception as e:
            print(f"✗ {name}: Not reachable ({str(e)})")
            all_healthy = False
    
    return all_healthy

def test_agent_registry():
    """Test Agent Registry"""
    print_test("Agent Registry - List Agents")
    
    try:
        response = requests.get(f"{AGENT_REGISTRY_URL}/api/registry/agents")
        if response.status_code == 200:
            agents = response.json()
            print(f"✓ Found {len(agents)} registered agents")
            for agent in agents:
                print(f"  - {agent['name']} ({agent['role']})")
                print(f"    Capabilities: {', '.join([c['name'] for c in agent['capabilities']])}")
            return True
        else:
            print(f"✗ Failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        return False

def test_mcp_registry():
    """Test MCP Registry"""
    print_test("MCP Registry - List MCP Servers")
    
    try:
        response = requests.get(f"{MCP_REGISTRY_URL}/api/mcp/servers")
        if response.status_code == 200:
            servers = response.json()
            print(f"✓ Found {len(servers)} registered MCP servers")
            for server in servers:
                print(f"  - {server['name']}")
                print(f"    Description: {server['description']}")
                print(f"    Tools: {len(server['tools'])} available")
            return True
        else:
            print(f"✗ Failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        return False

def test_mcp_gateway_direct():
    """Test MCP Gateway direct tool execution"""
    print_test("MCP Gateway - Direct Tool Execution")
    
    tests = [
        {
            "name": "Addition",
            "server": "calculator",
            "tool": "add",
            "args": {"a": 10, "b": 5},
            "expected": 15
        },
        {
            "name": "Multiplication",
            "server": "calculator",
            "tool": "multiply",
            "args": {"a": 7, "b": 8},
            "expected": 56
        },
        {
            "name": "Square Root",
            "server": "calculator",
            "tool": "sqrt",
            "args": {"value": 16},
            "expected": 4
        }
    ]
    
    all_passed = True
    for test in tests:
        try:
            response = requests.post(
                f"{MCP_GATEWAY_URL}/api/mcp/execute",
                json={
                    "server_name": test["server"],
                    "tool_name": test["tool"],
                    "arguments": test["args"]
                },
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("result") == test["expected"]:
                    print(f"✓ {test['name']}: {test['args']} = {result['result']}")
                else:
                    print(f"✗ {test['name']}: Expected {test['expected']}, got {result.get('result')}")
                    all_passed = False
            else:
                print(f"✗ {test['name']}: Failed (Status: {response.status_code})")
                all_passed = False
        except Exception as e:
            print(f"✗ {test['name']}: Error - {str(e)}")
            all_passed = False
    
    return all_passed

def test_math_agent():
    """Test Math Agent capabilities"""
    print_test("Math Agent - Execute Tasks via A2A Protocol")
    
    tests = [
        {
            "name": "Basic Addition",
            "capability": "calculate",
            "parameters": {
                "operation": "add",
                "a": 25,
                "b": 17
            },
            "expected_result": 42
        },
        {
            "name": "Division",
            "capability": "calculate",
            "parameters": {
                "operation": "divide",
                "a": 100,
                "b": 4
            },
            "expected_result": 25
        },
        {
            "name": "Square Operation",
            "capability": "advanced_math",
            "parameters": {
                "operation": "square",
                "value": 9
            },
            "expected_result": 81
        },
        {
            "name": "Power Operation",
            "capability": "advanced_math",
            "parameters": {
                "operation": "power",
                "value": 2,
                "exponent": 10
            },
            "expected_result": 1024
        },
        {
            "name": "Statistics - Mean",
            "capability": "statistics",
            "parameters": {
                "operation": "mean",
                "numbers": [10, 20, 30, 40, 50]
            },
            "expected_result": 30
        }
    ]
    
    all_passed = True
    for test in tests:
        try:
            task_request = {
                "task_id": f"test-{datetime.now(UTC).timestamp()}",
                "capability": test["capability"],
                "parameters": test["parameters"]
            }
            
            response = requests.post(
                f"{MATH_AGENT_URL}/execute",
                json=task_request,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("status") == "completed":
                    actual_result = result.get("result", {}).get("result")
                    if actual_result == test["expected_result"]:
                        print(f"✓ {test['name']}: {actual_result}")
                    else:
                        print(f"✗ {test['name']}: Expected {test['expected_result']}, got {actual_result}")
                        all_passed = False
                else:
                    print(f"✗ {test['name']}: Task failed - {result.get('error')}")
                    all_passed = False
            else:
                print(f"✗ {test['name']}: Request failed (Status: {response.status_code})")
                print(f"  Response: {response.text}")
                all_passed = False
        except Exception as e:
            print(f"✗ {test['name']}: Error - {str(e)}")
            all_passed = False
    
    return all_passed

def test_end_to_end():
    """Test complete end-to-end workflow"""
    print_test("End-to-End Integration Test")
    
    print("\n1. Check Math Agent is registered in Agent Registry")
    try:
        response = requests.get(f"{AGENT_REGISTRY_URL}/api/registry/agents")
        agents = response.json()
        math_agent = next((a for a in agents if a['name'] == 'MathAgent'), None)
        
        if math_agent:
            print(f"✓ Math Agent found in registry")
            print(f"  Capabilities: {', '.join([c['name'] for c in math_agent['capabilities']])}")
        else:
            print(f"✗ Math Agent not found in registry")
            return False
    except Exception as e:
        print(f"✗ Error checking registry: {str(e)}")
        return False
    
    print("\n2. Check Calculator MCP Server is registered")
    try:
        response = requests.get(f"{MCP_REGISTRY_URL}/api/mcp/servers")
        servers = response.json()
        calc_server = next((s for s in servers if s['name'] == 'calculator'), None)
        
        if calc_server:
            print(f"✓ Calculator server found in MCP registry")
            print(f"  Tools: {len(calc_server['tools'])} available")
        else:
            print(f"✗ Calculator server not found in MCP registry")
            return False
    except Exception as e:
        print(f"✗ Error checking MCP registry: {str(e)}")
        return False
    
    print("\n3. Execute complex calculation through Math Agent")
    try:
        # Calculate: (10 + 5) * 2 = 30
        # Step 1: Add 10 + 5
        task1 = {
            "task_id": f"calc-step1-{datetime.now(UTC).timestamp()}",
            "capability": "calculate",
            "parameters": {"operation": "add", "a": 10, "b": 5}
        }
        
        response1 = requests.post(f"{MATH_AGENT_URL}/execute", json=task1, timeout=10)
        result1 = response1.json()
        
        if result1.get("status") == "completed":
            step1_result = result1.get("result", {}).get("result")
            print(f"✓ Step 1 (10 + 5): {step1_result}")
            
            # Step 2: Multiply result by 2
            task2 = {
                "task_id": f"calc-step2-{datetime.now(UTC).timestamp()}",
                "capability": "calculate",
                "parameters": {"operation": "multiply", "a": step1_result, "b": 2}
            }
            
            response2 = requests.post(f"{MATH_AGENT_URL}/execute", json=task2, timeout=10)
            result2 = response2.json()
            
            if result2.get("status") == "completed":
                final_result = result2.get("result", {}).get("result")
                if final_result == 30:
                    print(f"✓ Step 2 ({step1_result} * 2): {final_result}")
                    print(f"✓ Complete calculation: (10 + 5) * 2 = {final_result}")
                    return True
                else:
                    print(f"✗ Unexpected final result: {final_result}")
                    return False
            else:
                print(f"✗ Step 2 failed: {result2.get('error')}")
                return False
        else:
            print(f"✗ Step 1 failed: {result1.get('error')}")
            return False
    except Exception as e:
        print(f"✗ Error in calculation: {str(e)}")
        return False

def main():
    """Run all tests"""
    print_section("MCP System + Math Agent Test Suite")
    print(f"Started at: {datetime.now(UTC).isoformat()}")
    
    # Wait a bit for services to be fully ready
    print("\nWaiting for services to be ready...")
    time.sleep(2)
    
    results = {}
    
    # Test 1: Health checks
    results['health'] = test_services_health()
    
    if not results['health']:
        print("\n⚠ Some services are not healthy. Aborting remaining tests.")
        return
    
    # Test 2: Agent Registry
    results['agent_registry'] = test_agent_registry()
    
    # Test 3: MCP Registry
    results['mcp_registry'] = test_mcp_registry()
    
    # Test 4: MCP Gateway
    results['mcp_gateway'] = test_mcp_gateway_direct()
    
    # Test 5: Math Agent
    results['math_agent'] = test_math_agent()
    
    # Test 6: End-to-end
    results['end_to_end'] = test_end_to_end()
    
    # Summary
    print_section("Test Summary")
    total = len(results)
    passed = sum(1 for r in results.values() if r)
    
    for test_name, result in results.items():
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠ {total - passed} test(s) failed")

if __name__ == "__main__":
    main()
