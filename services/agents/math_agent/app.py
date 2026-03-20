"""
Math Agent - Standalone Service
Performs mathematical operations using MCP Gateway
"""
import os

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
from shared.config import ConfigManager

load_dotenv()

# Get configuration from centralized config manager
config = ConfigManager.get_instance()

# Configuration with fallbacks to environment variables
AGENT_KEY = "math_agent"
agent_config = config.get_agent_config(AGENT_KEY)

AGENT_NAME = os.getenv("AGENT_NAME", agent_config.get("name", "MathAgent"))
AGENT_PORT = int(os.getenv("AGENT_PORT", agent_config.get("port", 8006)))
AGENT_HOST = os.getenv("AGENT_HOST", config.network.bind_host)
PUBLIC_HOST = os.getenv("PUBLIC_HOST", config.network.public_host)

# Service URLs from config
REGISTRY_URL = os.getenv("REGISTRY_URL", config.get_service_url("registry"))
MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", config.get_service_url("mcp_gateway"))

agent_id = None
agent_metadata = None
registry_client = None
audit_logger = AuditLogger()


async def register_with_registry():
    """Register this agent with the registry"""
    global agent_id, agent_metadata, registry_client
    
    # Use public host for endpoint registration
    endpoint_url = f"http://{PUBLIC_HOST}:{AGENT_PORT}"
    
    agent_metadata = AgentMetadata(
        name=AGENT_NAME,
        role=AgentRole.SPECIALIZED,
        capabilities=[
            AgentCapability(
                name="calculate",
                description="Perform basic arithmetic (add, subtract, multiply, divide) on two numbers. USE THIS for any task involving +, -, *, / with explicit numbers. Do NOT use answer_question for arithmetic.",
                requires_llm=False,
                input_schema={
                    "parameters": {
                        "operation": {"type": "string", "required": True, "enum": ["add", "subtract", "multiply", "divide"], "description": "The arithmetic operation"},
                        "a": {"type": "number", "required": True, "description": "First operand"},
                        "b": {"type": "number", "required": True, "description": "Second operand"}
                    },
                    "example": {"operation": "add", "a": 85, "b": 85},
                    "step_reference": "Results from earlier steps can be referenced as '<result_from_step_N>'"
                }
            ),
            AgentCapability(
                name="advanced_math",
                description="Perform advanced math: power/exponent, square root, trigonometry. USE THIS for squaring, cubing, sqrt. Value can reference a previous step result.",
                requires_llm=False,
                input_schema={
                    "parameters": {
                        "operation": {"type": "string", "required": True, "enum": ["power", "sqrt", "square", "sin", "cos", "tan"], "description": "The operation to perform"},
                        "value": {"type": "number_or_step_ref", "required": True, "description": "The number to operate on, or <result_from_step_N> for chained steps"},
                        "exponent": {"type": "number", "required": False, "description": "Required when operation is 'power'. E.g. 2 for square, 3 for cube"}
                    },
                    "example": {"operation": "power", "value": "<result_from_step_1>", "exponent": 2}
                }
            ),
            AgentCapability(
                name="solve_equation",
                description="Solve a mathematical equation expressed as a string (e.g. 'x^2 + 3x - 4 = 0').",
                requires_llm=False,
                input_schema={
                    "parameters": {
                        "equation": {"type": "string", "required": True, "description": "The equation to solve as a string"}
                    },
                    "example": {"equation": "x^2 - 4 = 0"}
                }
            ),
            AgentCapability(
                name="statistics",
                description="Calculate statistical measures (mean, median, standard deviation, sum) over a list of numbers.",
                requires_llm=False,
                input_schema={
                    "parameters": {
                        "operation": {"type": "string", "required": True, "enum": ["mean", "median", "std_dev", "sum"], "description": "Statistical measure to compute"},
                        "numbers": {"type": "list[number]", "required": True, "description": "List of numbers to compute over"}
                    },
                    "example": {"operation": "mean", "numbers": [10, 20, 30, 40]}
                }
            )
        ],
        has_llm=False,
        endpoint=endpoint_url
    )
    
    registry_client = A2AClient(REGISTRY_URL)
    
    try:
        response = await registry_client.register_agent(agent_metadata)
        agent_id = response.agent_id
        print(f"✓ Registered with registry: {agent_id}")
        print(f"  Endpoint: {endpoint_url}")
        print(f"  Registry: {REGISTRY_URL}")
        print(f"  MCP Gateway: {MCP_GATEWAY_URL}")
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


async def call_mcp_gateway(server_name: str, tool_name: str, arguments: Dict[str, Any], workflow_id: str = None, session_id: str = None, user_id: str = None) -> Dict[str, Any]:
    """Call MCP Gateway to execute tool"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            body: Dict[str, Any] = {
                "tool_name": tool_name,
                "parameters": arguments,
            }
            if workflow_id:
                body["workflow_id"] = workflow_id
            if session_id:
                body["session_id"] = session_id
            if user_id:
                body["user_id"] = user_id
            response = await client.post(
                f"{MCP_GATEWAY_URL}/api/gateway/execute",
                json=body,
            )
            response.raise_for_status()
            data = response.json()
            # Detect embedded errors returned inside an HTTP 200 response
            # (e.g. {"result": {"error": "All connection attempts failed"}})
            inner_result = data.get("result")
            if isinstance(inner_result, dict) and "error" in inner_result:
                raise HTTPException(
                    status_code=500,
                    detail=f"MCP tool '{tool_name}' failed: {inner_result['error']}"
                )
            return data
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
        user_id = user_identity.get("user_id") or context.get("user_id")

        # Trace IDs for end-to-end traceability
        workflow_id = context.get("workflow_id")
        session_id = context.get("session_id")
        
        audit_logger.log_event(
            workflow_id=workflow_id or "direct_call",
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
            result = await handle_calculate(parameters, workflow_id=workflow_id, session_id=session_id, user_id=user_id)
        elif capability == "advanced_math":
            result = await handle_advanced_math(parameters, workflow_id=workflow_id, session_id=session_id, user_id=user_id)
        elif capability == "solve_equation":
            result = await handle_solve_equation(parameters, workflow_id=workflow_id, session_id=session_id, user_id=user_id)
        elif capability == "statistics":
            result = await handle_statistics(parameters, workflow_id=workflow_id, session_id=session_id, user_id=user_id)
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


async def handle_calculate(params: Dict[str, Any], workflow_id: str = None, session_id: str = None, user_id: str = None) -> Dict[str, Any]:
    """Handle basic calculations using MCP Gateway"""
    # Create interaction helper
    helper = AgentInteractionHelper(params)
    
    operation = params.get("operation")
    a = params.get("a")
    b = params.get("b")
    
    # Check for user response if we asked for missing input previously.
    # user_responses now contains the FULL ordered history of Q&A for this step
    # (oldest first). Scan all of them to resolve 'a', 'b', and 'operation'.
    if helper.has_user_response():
        for resp in helper.user_responses:
            q = (resp.get("question") or "").lower()
            v = resp.get("content") or resp.get("value")
            if v is None:
                continue
            try:
                # Map the answer to the param based on the question text
                if "first number" in q or "(a)" in q or "parameter 'a'" in q or "number (a)" in q:
                    if a is None:
                        a = float(v)
                elif ("second number" in q or "(b)" in q or "parameter 'b'" in q
                      or "number (b)" in q or "to add with" in q or "to subtract" in q
                      or "to multiply" in q or "to divide" in q):
                    if b is None:
                        b = float(v)
                elif "operation" in q or "which operation" in q or "what operation" in q:
                    if not operation:
                        operation = v.lower()
                else:
                    # Fallback heuristic: fill missing params in order
                    if a is None:
                        a = float(v)
                    elif b is None:
                        b = float(v)
                    elif not operation:
                        operation = v.lower()
            except (ValueError, TypeError):
                pass  # Non-numeric answer — will ask again below
            
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
        arguments={"a": float(a), "b": float(b)},
        workflow_id=workflow_id, session_id=session_id, user_id=user_id,
    )
    
    ret = {"operation": operation, "a": a, "b": b, "result": result.get("result"), "mcp_response": result}
    if workflow_id:
        ret["_trace"] = {"workflow_id": workflow_id, "session_id": session_id, "user_id": user_id}
    return ret


async def handle_advanced_math(params: Dict[str, Any], workflow_id: str = None, session_id: str = None, user_id: str = None) -> Dict[str, Any]:
    """Handle advanced math operations using MCP Gateway"""
    operation = params.get("operation")
    value = params.get("value")
    
    if not operation or value is None:
        raise ValueError("operation and value are required")

    # Reject non-numeric values early — if a prior step failed and injected an error
    # dict as the value, surface a clear message instead of a cryptic float() TypeError.
    if isinstance(value, dict):
        error_msg = value.get("error") or str(value)
        raise ValueError(
            f"Invalid value for advanced_math '{operation}': received an error from a previous step: {error_msg}"
        )

    # Reject unresolved step-reference placeholders (e.g. "<result_from_step_1>"),
    # which means the dependency step failed or its result was never stored.
    if isinstance(value, str) and "<" in value and ">" in value:
        raise ValueError(
            f"Invalid value for advanced_math '{operation}': unresolved step reference '{value}'. "
            f"The previous step that should provide this value likely failed."
        )

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
        arguments=arguments,
        workflow_id=workflow_id, session_id=session_id, user_id=user_id,
    )
    
    ret = {"operation": operation, "input": params, "result": result.get("result"), "mcp_response": result}
    if workflow_id:
        ret["_trace"] = {"workflow_id": workflow_id, "session_id": session_id, "user_id": user_id}
    return ret


async def handle_solve_equation(params: Dict[str, Any], workflow_id: str = None, session_id: str = None, user_id: str = None) -> Dict[str, Any]:
    """Handle equation solving using MCP Gateway"""
    equation = params.get("equation")
    
    if not equation:
        raise ValueError("equation is required")
    
    result = await call_mcp_gateway(
        server_name="calculator",
        tool_name="solve_equation",
        arguments={"equation": equation},
        workflow_id=workflow_id, session_id=session_id, user_id=user_id,
    )
    
    ret = {"equation": equation, "solution": result.get("result"), "mcp_response": result}
    if workflow_id:
        ret["_trace"] = {"workflow_id": workflow_id, "session_id": session_id, "user_id": user_id}
    return ret


async def handle_statistics(params: Dict[str, Any], workflow_id: str = None, session_id: str = None, user_id: str = None) -> Dict[str, Any]:
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
        arguments={"numbers": [float(n) for n in numbers]},
        workflow_id=workflow_id, session_id=session_id, user_id=user_id,
    )
    
    ret = {"operation": operation, "numbers": numbers, "result": result.get("result"), "mcp_response": result}
    if workflow_id:
        ret["_trace"] = {"workflow_id": workflow_id, "session_id": session_id, "user_id": user_id}
    return ret


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=AGENT_HOST, port=AGENT_PORT)
