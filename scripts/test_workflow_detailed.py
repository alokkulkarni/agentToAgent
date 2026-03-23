#!/usr/bin/env python3
"""
Detailed Workflow Test - Shows complete A2A protocol execution
Tests the THINK-PLAN-EXECUTE-VERIFY-REFLECT pattern with full visibility
"""
import requests
import json
import time
from datetime import datetime
from typing import Dict, Any


class Color:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(title: str):
    """Print a formatted header"""
    print(f"\n{Color.BOLD}{Color.HEADER}{'='*80}{Color.ENDC}")
    print(f"{Color.BOLD}{Color.HEADER}{title.center(80)}{Color.ENDC}")
    print(f"{Color.BOLD}{Color.HEADER}{'='*80}{Color.ENDC}\n")


def print_section(title: str):
    """Print a section title"""
    print(f"\n{Color.BOLD}{Color.CYAN}{'─'*80}{Color.ENDC}")
    print(f"{Color.BOLD}{Color.CYAN}{title}{Color.ENDC}")
    print(f"{Color.BOLD}{Color.CYAN}{'─'*80}{Color.ENDC}")


def print_success(message: str):
    """Print success message"""
    print(f"{Color.GREEN}✓ {message}{Color.ENDC}")


def print_error(message: str):
    """Print error message"""
    print(f"{Color.RED}✗ {message}{Color.ENDC}")


def print_info(message: str, indent: int = 0):
    """Print info message"""
    prefix = "  " * indent
    print(f"{prefix}{Color.BLUE}• {message}{Color.ENDC}")


def print_data(label: str, data: Any, indent: int = 0):
    """Print labeled data"""
    prefix = "  " * indent
    if isinstance(data, (dict, list)):
        print(f"{prefix}{Color.YELLOW}{label}:{Color.ENDC}")
        print(f"{prefix}  {json.dumps(data, indent=2)}")
    else:
        print(f"{prefix}{Color.YELLOW}{label}:{Color.ENDC} {data}")


def check_service(name: str, url: str) -> bool:
    """Check if a service is running"""
    try:
        response = requests.get(f"{url}/health", timeout=5)
        if response.status_code == 200:
            print_success(f"{name} is healthy")
            return True
        else:
            print_error(f"{name} returned status {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print_error(f"{name} is not reachable: {e}")
        return False


def test_workflow_execution(task_description: str, workflow_id: str):
    """Execute and monitor a complete workflow"""
    
    print_header("A2A MULTI-AGENT WORKFLOW EXECUTION")
    
    print_info(f"Task: {task_description}")
    print_info(f"Workflow ID: {workflow_id}")
    print_info(f"Timestamp: {datetime.now().isoformat()}")
    
    # Step 1: Check all services
    print_section("STEP 1: Service Health Check")
    
    services = {
        "Registry": "http://localhost:8000",
        "Orchestrator": "http://localhost:8100",
        "ResearchAgent": "http://localhost:8001",
        "CodeAnalyzer": "http://localhost:8002",
        "DataProcessor": "http://localhost:8003"
    }
    
    all_healthy = True
    for name, url in services.items():
        if not check_service(name, url):
            all_healthy = False
    
    if not all_healthy:
        print_error("Not all services are healthy. Please start all services first.")
        return
    
    # Step 2: Check registered agents
    print_section("STEP 2: Discover Registered Agents")
    
    try:
        response = requests.get("http://localhost:8000/api/registry/agents")
        agents = response.json()
        
        print_info(f"Total agents registered: {len(agents)}")
        
        for agent in agents:
            print_info(f"Agent: {agent['name']} ({agent['role']})", indent=1)
            print_info(f"ID: {agent['agent_id']}", indent=2)
            print_info(f"Capabilities:", indent=2)
            for cap in agent['capabilities']:
                print_info(f"- {cap['name']}: {cap['description']}", indent=3)
    
    except Exception as e:
        print_error(f"Failed to get agents: {e}")
        return
    
    # Step 3: Execute workflow
    print_section("STEP 3: Execute Workflow via Orchestrator")
    
    workflow_request = {
        "task_description": task_description,
        "workflow_id": workflow_id
    }
    
    print_data("Request Payload", workflow_request)
    
    try:
        print_info("Sending request to orchestrator...")
        start_time = time.time()
        
        response = requests.post(
            "http://localhost:8100/api/workflow/execute",
            json=workflow_request,
            timeout=300  # 5 minutes
        )
        
        execution_time = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            
            print_success(f"Workflow completed in {execution_time:.2f} seconds")
            
            # Step 4: Display execution plan
            print_section("STEP 4: Execution Plan (THINK → PLAN)")
            
            plan = result.get("plan", {})
            print_data("Plan Reasoning", plan.get("reasoning", "N/A"))
            
            print_info(f"Total Steps Planned: {len(plan.get('steps', []))}")
            
            for step in plan.get("steps", []):
                print_info(f"Step {step.get('step_number')}: {step.get('description')}", indent=1)
                print_info(f"Capability: {step.get('capability')}", indent=2)
                print_info(f"Parameters: {json.dumps(step.get('parameters', {}), indent=2)}", indent=2)
                print_info(f"Expected Output: {step.get('expected_output', 'N/A')}", indent=2)
            
            # Step 5: Display execution details
            print_section("STEP 5: Execution Details (EXECUTE → VERIFY)")
            
            print_info(f"Steps Completed: {result.get('steps_completed')}/{result.get('total_steps')}")
            
            execution_log = result.get("execution_log", [])
            
            for log_entry in execution_log:
                phase = log_entry.get("phase", log_entry.get("step", "UNKNOWN"))
                
                if phase == "THINK":
                    print_info(f"[THINK] Discovered {log_entry.get('agents_found', 0)} agents")
                    print_info(f"Capabilities: {', '.join(log_entry.get('capabilities_available', []))}", indent=1)
                
                elif phase == "PLAN":
                    print_info(f"[PLAN] Generated plan with {log_entry.get('total_steps', 0)} steps")
                
                elif phase == "EXECUTE-VERIFY":
                    step_num = log_entry.get("step_number")
                    status = log_entry.get("status")
                    agent = log_entry.get("agent")
                    capability = log_entry.get("capability")
                    
                    if status == "completed":
                        print_success(f"[STEP {step_num}] {agent} executed '{capability}'")
                        result_preview = log_entry.get("result_preview", "")
                        if result_preview:
                            print_info(f"Result: {result_preview}...", indent=1)
                    else:
                        error = log_entry.get("error", "Unknown error")
                        print_error(f"[STEP {step_num}] {agent} failed: {error}")
            
            # Step 6: Display results
            print_section("STEP 6: Step Results")
            
            for result_item in result.get("results", []):
                step = result_item.get("step")
                agent = result_item.get("agent")
                capability = result_item.get("capability")
                step_result = result_item.get("result")
                description = result_item.get("description", "")
                
                print_info(f"Step {step}: {description}", indent=0)
                print_info(f"Agent: {agent}", indent=1)
                print_info(f"Capability: {capability}", indent=1)
                print_info(f"Result ({len(str(step_result))} chars):", indent=1)
                
                # Show result preview
                result_str = str(step_result)
                if len(result_str) > 500:
                    print(f"    {result_str[:500]}...")
                    print(f"    {Color.YELLOW}[{len(result_str) - 500} more characters]{Color.ENDC}")
                else:
                    print(f"    {result_str}")
            
            # Step 7: Display workflow context
            print_section("STEP 7: Workflow Context Flow")
            
            workflow_context = result.get("workflow_context", {})
            step_results = workflow_context.get("step_results", {})
            
            print_info(f"Context entries: {len(step_results)}")
            
            for step_key, step_data in step_results.items():
                print_info(f"{step_key}: {step_data.get('description')}", indent=1)
                print_info(f"Capability: {step_data.get('capability')}", indent=2)
                result_size = len(str(step_data.get('result', '')))
                print_info(f"Result size: {result_size} characters", indent=2)
            
            # Step 8: Display reflection
            print_section("STEP 8: Reflection (REFLECT)")
            
            reflection = result.get("reflection", {})
            
            print_data("Summary", reflection.get("summary", "N/A"))
            print_data("Success Rate", reflection.get("success_rate", "N/A"))
            print_data("Success Percentage", f"{reflection.get('success_percentage', 0):.1f}%")
            print_data("Overall Assessment", reflection.get("overall_assessment", "N/A"))
            
            print_info("Strengths:")
            for strength in reflection.get("strengths", []):
                print_info(f"+ {strength}", indent=1)
            
            if reflection.get("weaknesses"):
                print_info("Weaknesses:")
                for weakness in reflection.get("weaknesses", []):
                    print_info(f"- {weakness}", indent=1)
            
            if reflection.get("suggestions"):
                print_info("Suggestions:")
                for suggestion in reflection.get("suggestions", []):
                    print_info(f"→ {suggestion}", indent=1)
            
            # Final summary
            print_header("WORKFLOW EXECUTION COMPLETE")
            print_success(f"Workflow ID: {result.get('workflow_id')}")
            print_success(f"Status: {result.get('status')}")
            print_success(f"Steps: {result.get('steps_completed')}/{result.get('total_steps')}")
            print_success(f"Execution time: {execution_time:.2f}s")
            
        else:
            print_error(f"Workflow failed with status {response.status_code}")
            print_data("Error Response", response.json())
    
    except requests.exceptions.Timeout:
        print_error("Request timed out after 5 minutes")
    except Exception as e:
        print_error(f"Execution failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print_header("A2A PROTOCOL - DISTRIBUTED AGENT SYSTEM TEST")
    
    # Test Case 1: Research and comparison
    test_workflow_execution(
        task_description="Research the benefits of microservices architecture, then research monolithic architecture, and finally create a detailed comparison report of both",
        workflow_id=f"research-comparison-{int(time.time())}"
    )
    
    print("\n" + "="*80)
    input(f"\n{Color.BOLD}Press Enter to test another workflow...{Color.ENDC}\n")
    
    # Test Case 2: Data processing
    test_workflow_execution(
        task_description="Analyze the data trends in cloud computing adoption and generate insights",
        workflow_id=f"data-analysis-{int(time.time())}"
    )
