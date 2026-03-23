"""
Test Script for Distributed A2A System
Tests all services and A2A protocol communication
"""
import asyncio
import httpx
import json
from datetime import datetime, timezone


class DistributedSystemTester:
    """Test the distributed A2A system"""
    
    def __init__(self):
        self.registry_url = "http://localhost:8000"
        self.orchestrator_url = "http://localhost:8100"
        self.code_analyzer_url = "http://localhost:8001"
    
    async def test_services(self):
        """Run all tests"""
        print("=" * 60)
        print("Distributed A2A System Test Suite")
        print("=" * 60)
        print()
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Test 1: Registry Health
            await self.test_registry_health(client)
            
            # Test 2: Agent Registration (check registry)
            await self.test_agent_registration(client)
            
            # Test 3: Agent Direct Call
            await self.test_agent_direct(client)
            
            # Test 4: Orchestrator Discovery
            await self.test_orchestrator_discovery(client)
            
            # Test 5: Workflow Execution
            await self.test_workflow_execution(client)
        
        print()
        print("=" * 60)
        print("All Tests Completed!")
        print("=" * 60)
    
    async def test_registry_health(self, client: httpx.AsyncClient):
        """Test registry service health"""
        print("Test 1: Registry Service Health")
        print("-" * 60)
        
        try:
            response = await client.get(f"{self.registry_url}/health")
            if response.status_code == 200:
                data = response.json()
                print(f"✓ Registry is healthy")
                print(f"  Agents registered: {data.get('agents_registered', 0)}")
            else:
                print(f"✗ Registry health check failed: {response.status_code}")
        except Exception as e:
            print(f"✗ Cannot connect to registry: {e}")
        
        print()
    
    async def test_agent_registration(self, client: httpx.AsyncClient):
        """Check if agents are registered"""
        print("Test 2: Agent Registration Check")
        print("-" * 60)
        
        try:
            response = await client.get(f"{self.registry_url}/api/registry/agents")
            if response.status_code == 200:
                agents = response.json()
                print(f"✓ Found {len(agents)} registered agents:")
                for agent in agents:
                    print(f"  - {agent['name']} ({agent['role']}) - {len(agent['capabilities'])} capabilities")
            else:
                print(f"✗ Failed to get agents: {response.status_code}")
        except Exception as e:
            print(f"✗ Error: {e}")
        
        print()
    
    async def test_agent_direct(self, client: httpx.AsyncClient):
        """Test direct agent call"""
        print("Test 3: Direct Agent Call")
        print("-" * 60)
        
        try:
            # Test code analyzer
            task = {
                "task_id": f"test-{datetime.utcnow().timestamp()}",
                "capability": "analyze_python_code",
                "parameters": {
                    "code": "def fibonacci(n):\n    return n if n <= 1 else fibonacci(n-1) + fibonacci(n-2)"
                }
            }
            
            response = await client.post(
                f"{self.code_analyzer_url}/api/task",
                json=task
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✓ Code Analyzer responded")
                print(f"  Task ID: {result['task_id']}")
                print(f"  Status: {result['status']}")
                if result.get('result'):
                    print(f"  Functions found: {result['result'].get('function_count', 0)}")
                    print(f"  Lines: {result['result'].get('total_lines', 0)}")
            else:
                print(f"✗ Agent call failed: {response.status_code}")
        
        except Exception as e:
            print(f"✗ Error: {e}")
        
        print()
    
    async def test_orchestrator_discovery(self, client: httpx.AsyncClient):
        """Test orchestrator agent discovery"""
        print("Test 4: Orchestrator Agent Discovery")
        print("-" * 60)
        
        try:
            response = await client.get(f"{self.orchestrator_url}/api/agents")
            
            if response.status_code == 200:
                data = response.json()
                agents = data.get('agents', [])
                print(f"✓ Orchestrator can see {data['total']} agents:")
                for agent in agents:
                    caps = ', '.join(agent['capabilities'][:3])
                    print(f"  - {agent['name']}: {caps}...")
            else:
                print(f"✗ Discovery failed: {response.status_code}")
        
        except Exception as e:
            print(f"✗ Error: {e}")
        
        print()
    
    async def test_workflow_execution(self, client: httpx.AsyncClient):
        """Test workflow orchestration"""
        print("Test 5: Workflow Execution")
        print("-" * 60)
        
        try:
            workflow = {
                "task_description": "Analyze Python code for a simple function and explain what it does",
                "workflow_id": f"test-workflow-{datetime.now(timezone.utc).timestamp()}"
            }
            
            print("Executing workflow...")
            print(f"Task: {workflow['task_description']}")
            print()
            
            response = await client.post(
                f"{self.orchestrator_url}/api/workflow/execute",
                json=workflow,
                timeout=120.0  # Increase timeout for LLM calls
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✓ Workflow executed successfully")
                print(f"\n  Workflow ID: {result['workflow_id']}")
                print(f"  Status: {result['status']}")
                print(f"  Steps completed: {result['steps_completed']}/{result['total_steps']}")
                
                # Show execution plan
                if result.get('plan'):
                    print(f"\n  📋 Execution Plan:")
                    plan = result['plan']
                    print(f"     Reasoning: {plan.get('reasoning', 'N/A')}")
                    print(f"     Steps planned: {len(plan.get('steps', []))}")
                    for step in plan.get('steps', []):
                        print(f"       {step.get('step_number')}. {step.get('description')}")
                        print(f"          Capability: {step.get('capability')}")
                
                # Show execution results
                if result.get('results'):
                    print(f"\n  📊 Execution Results:")
                    for res in result['results']:
                        print(f"     Step {res.get('step')}: {res.get('capability')}")
                        print(f"       Agent: {res.get('agent', 'N/A')}")
                        print(f"       Result: {str(res.get('result', 'N/A'))[:150]}...")
                
                # Show execution log
                if result.get('execution_log'):
                    print(f"\n  📝 Execution Log:")
                    for log_entry in result['execution_log']:
                        if log_entry.get('step') == 'discovery':
                            print(f"     ✓ Discovery: Found {log_entry.get('agents_found')} agents")
                        elif log_entry.get('step') == 'planning':
                            print(f"     ✓ Planning: Generated {len(log_entry.get('plan', {}).get('steps', []))} steps")
                        elif log_entry.get('step_number'):
                            status = log_entry.get('status', 'unknown')
                            step_num = log_entry.get('step_number')
                            if status == 'completed':
                                print(f"     ✓ Step {step_num}: Completed by {log_entry.get('agent')}")
                            elif status == 'failed':
                                print(f"     ✗ Step {step_num}: Failed - {log_entry.get('error')}")
                            elif status == 'skipped':
                                print(f"     ⊘ Step {step_num}: Skipped - {log_entry.get('reason')}")
                
            else:
                print(f"✗ Workflow failed: {response.status_code}")
                print(f"  Response: {response.text}")
        
        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()
        
        print()


async def main():
    """Main test function"""
    tester = DistributedSystemTester()
    
    print()
    print("Prerequisites:")
    print("  - Registry service running on port 8000")
    print("  - Orchestrator service running on port 8100")
    print("  - At least one agent running (e.g., Code Analyzer on 8001)")
    print()
    print("Starting tests in 2 seconds...")
    await asyncio.sleep(2)
    print()
    
    await tester.test_services()


if __name__ == "__main__":
    asyncio.run(main())
