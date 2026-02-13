"""
Math Agent - Standalone Service
Performs mathematical operations using MCP Gateway
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
import asyncio
from typing import Dict, Any, List
import httpx
from dotenv import load_dotenv

from shared.a2a_protocol import (
    AgentMetadata, AgentRole, AgentCapability,
    TaskRequest, TaskResponse, TaskStatus,
    A2AClient
)
from shared.agent_interaction import AgentInteractionHelper
from shared.audit import AuditLogger

load_dotenv()

# Configuration
AGENT_NAME = os.getenv("AGENT_NAME", "MathAgent")
AGENT_PORT = int(os.getenv("AGENT_PORT", "8006"))
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://localhost:8000")
MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", "http://localhost:9000")

agent_id = None
agent_metadata = None
registry_client = None
audit_logger = AuditLogger()


async def register_with_registry():
    """Register this agent with the registry"""
    global agent_id, agent_metadata, registry_client
    
    agent_metadata = AgentMetadata(
        name=AGENT_NAME,
        role=AgentRole.SPECIALIZED,
        capabilities=[
            AgentCapability(
                name="calculate",
                description="Perform mathematical calculations (add, subtract, multiply, divide)",
                requires_llm=False
            ),
            AgentCapability(
                name="advanced_math",
                description="Perform advanced mathematical operations (power, sqrt, trigonometry)",
                requires_llm=False
            ),
            AgentCapability(
                name="solve_equation",
                description="Solve mathematical equations",
                requires_llm=False
            ),
            AgentCapability(
                name="statistics",
                description="Calculate statistical measures (mean, median, std dev)",
                requires_llm=False
            )
        ],
        has_llm=False,
        endpoint=f"http://localhost:{AGENT_PORT}"
    )
    
    registry_client = A2AClient(REGISTRY_URL)
    
    try:
        response = await registry_client.register_agent(agent_metadata)
        agent_id = response.agent_id
        print(f"✓ Registered with registry: {agent_id}")
        asyncio.create_task(send_heartbeats())
    except Exception as e:
        print(f"✗ Failed to register: {e}")
        raise


async def send_heartbeats():
    """Send periodic heartbeats"""
    while True:
        await asyncio.sleep(30)
        try:
            await registry_client.heartbeat(agent_id)
        except Exception as e:
            print(f"Heartbeat failed: {e}")


async def unregister_from_registry():
    """Unregister from registry"""
    if registry_client and agent_id:
        try:
            await registry_client.unregister_agent(agent_id)
            await registry_client.close()
            print("✓ Unregistered from registry")
        except Exception as e:
            print(f"✗ Failed to unregister: {e}")


async def call_mcp_gateway(server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Call MCP Gateway to execute tool"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{MCP_GATEWAY_URL}/api/gateway/execute",
                json={
                    "tool_name": tool_name,
                    "parameters": arguments
                }
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=500, detail=f"MCP Gateway error: {str(e)}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management"""
    print(f"Starting {AGENT_NAME}...")
    await register_with_registry()
    yield
    print(f"Shutting down {AGENT_NAME}...")
    await unregister_from_registry()


app = FastAPI(title=AGENT_NAME, lifespan=lifespan)


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "agent": AGENT_NAME}


@app.post("/api/task")
async def execute_task(task: TaskRequest) -> TaskResponse:
    """Execute a task using A2A protocol"""
    try:
        capability = task.capability
        parameters = task.parameters
        
        # AUDIT: Log task execution with propagated identity
        context = task.context or {}
        user_identity = context.get("user_identity", {"user_id": "unknown", "role": "unknown"})
        user_id = user_identity.get("user_id")
        
        audit_logger.log_event(
            workflow_id=context.get("workflow_id", "direct_call"),
            user_id=user_id,
            event_type="AGENT_EXECUTION",
            details={
                "agent": AGENT_NAME,
                "capability": capability,
                "parameters": parameters
            }
        )
        
        # Inject context into parameters to ensure AgentInteractionHelper works correctly
        if task.context:
            task.parameters["context"] = task.context
            parameters = task.parameters
        
        if capability == "calculate":
            result = await handle_calculate(parameters)
        elif capability == "advanced_math":
            result = await handle_advanced_math(parameters)
        elif capability == "solve_equation":
            result = await handle_solve_equation(parameters)
        elif capability == "statistics":
            result = await handle_statistics(parameters)
        else:
            return TaskResponse(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                error=f"Unknown capability: {capability}"
            )
        
        return TaskResponse(
            task_id=task.task_id,
            agent_id=agent_id,
            status=TaskStatus.COMPLETED,
            result=result
        )
    
    except Exception as e:
        return TaskResponse(
            task_id=task.task_id,
            agent_id=agent_id,
            status=TaskStatus.FAILED,
            error=str(e)
        )


async def handle_calculate(params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle basic calculations using MCP Gateway"""
    # Create interaction helper
    helper = AgentInteractionHelper(params)
    
    operation = params.get("operation")
    a = params.get("a")
    b = params.get("b")
    
    # Check for user response if we asked for missing input previously
    if helper.has_user_response():
        user_response = helper.get_user_response()
        # Try to parse the missing value from user response
        # This is a simple implementation - in production use LLM or robust parsing
        try:
            # If we were missing 'b', try to parse 'b'
            if b is None and a is not None and user_response:
                b = float(user_response)
            # If we were missing 'a', try to parse 'a'
            elif a is None and user_response:
                a = float(user_response)
            # If we were missing 'operation', use response
            elif not operation and user_response:
                operation = user_response.lower()
        except ValueError:
            pass # Could not parse, will ask again or fail
            
    # INTERACTIVE: Ask for missing parameters
    if a is None:
        return helper.ask_text(
            question="Please provide the first number (a) for the calculation:",
            reasoning="Missing parameter 'a' for calculation."
        )
        
    if b is None:
        return helper.ask_text(
            question=f"Please provide the second number (b) to {operation or 'calculate'} with {a}:",
            reasoning="Missing parameter 'b' for calculation."
        )
        
    if not operation:
        return helper.ask_single_choice(
            question=f"What operation would you like to perform on {a} and {b}?",
            options=["add", "subtract", "multiply", "divide"],
            reasoning="Missing parameter 'operation'."
        )
    
    # Map operations to MCP calculator tools
    tool_map = {
        "add": "add",
        "subtract": "subtract",
        "multiply": "multiply",
        "divide": "divide"
    }
    
    if operation not in tool_map:
        raise ValueError(f"Unknown operation: {operation}")
    
    result = await call_mcp_gateway(
        server_name="calculator",
        tool_name=tool_map[operation],
        arguments={"a": float(a), "b": float(b)}
    )
    
    return {
        "operation": operation,
        "a": a,
        "b": b,
        "result": result.get("result"),
        "mcp_response": result
    }


async def handle_advanced_math(params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle advanced math operations using MCP Gateway"""
    operation = params.get("operation")
    value = params.get("value")
    
    if not operation or value is None:
        raise ValueError("operation and value are required")
    
    # Map operations to MCP calculator tools and prepare arguments
    if operation == "square":
        tool_name = "square"
        arguments = {"value": float(value)}
    elif operation == "sqrt":
        tool_name = "sqrt"
        arguments = {"value": float(value)}
    elif operation == "power":
        exponent = params.get("exponent")
        if exponent is None:
            raise ValueError("exponent is required for power operation")
        tool_name = "power"
        arguments = {"base": float(value), "exponent": float(exponent)}
    else:
        raise ValueError(f"Unknown operation: {operation}")
    
    result = await call_mcp_gateway(
        server_name="calculator",
        tool_name=tool_name,
        arguments=arguments
    )
    
    return {
        "operation": operation,
        "input": params,
        "result": result.get("result"),
        "mcp_response": result
    }


async def handle_solve_equation(params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle equation solving using MCP Gateway"""
    equation = params.get("equation")
    
    if not equation:
        raise ValueError("equation is required")
    
    result = await call_mcp_gateway(
        server_name="calculator",
        tool_name="solve_equation",
        arguments={"equation": equation}
    )
    
    return {
        "equation": equation,
        "solution": result.get("result"),
        "mcp_response": result
    }


async def handle_statistics(params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle statistical calculations using MCP Gateway"""
    operation = params.get("operation")
    numbers = params.get("numbers")
    
    if not operation or not numbers:
        raise ValueError("operation and numbers are required")
    
    if not isinstance(numbers, list):
        raise ValueError("numbers must be a list")
    
    # Map operations to MCP calculator tools
    tool_map = {
        "mean": "mean",
        "median": "median",
        "sum": "sum"
    }
    
    if operation not in tool_map:
        raise ValueError(f"Unknown operation: {operation}")
    
    result = await call_mcp_gateway(
        server_name="calculator",
        tool_name=tool_map[operation],
        arguments={"numbers": [float(n) for n in numbers]}
    )
    
    return {
        "operation": operation,
        "numbers": numbers,
        "result": result.get("result"),
        "mcp_response": result
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
