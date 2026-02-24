"""
Orchestrator Service - Standalone Orchestration Service
Coordinates multi-agent workflows using A2A protocol
"""
import os

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional
import asyncio
import json
from datetime import datetime
import boto3
from dotenv import load_dotenv
import uuid
from collections import defaultdict

from shared.a2a_protocol import (
    AgentMetadata, AgentRole, AgentCapability,
    TaskRequest, TaskResponse, TaskStatus,
    A2AClient
)
from shared.config import EnterpriseConfig
from shared.guardrails import GuardrailService
from shared.audit import AuditLogger
from shared.security import SecurityManager
from shared.identity_provider import get_identity_provider, UserContext
from shared.auth_dependencies import get_current_user, get_user_headers
from shared.vector_memory import get_vector_memory, VectorMemoryStore
from shared.distributed_state import get_distributed_state, DistributedState
try:
    from models import WorkflowRecord, WorkflowStatus, StepRecord, StepStatus
except ImportError:
    from .models import WorkflowRecord, WorkflowStatus, StepRecord, StepStatus  # type: ignore

load_dotenv()

# Initialize Enterprise Services
guardrails = GuardrailService()
audit_logger = AuditLogger()
security_manager = SecurityManager()
identity_provider = get_identity_provider()
vector_memory = get_vector_memory()
# Distributed state (replaces per-process active_workflows dict and session_store).
# Backed by Redis in HA mode (HA_BACKEND=redis) or in-memory for single-node dev.
dist_state: DistributedState = get_distributed_state()


async def enrich_with_workflow_context(
    capability: str,
    parameters: Dict[str, Any],
    workflow_context: Dict[str, Any],
    step_description: str,
    session_history: List[Dict] = None
) -> Dict[str, Any]:
    """
    Dynamically enrich parameters using accumulated workflow context.
    Uses LLM-based understanding to inject relevant previous results.
    """
    enriched = parameters.copy()
    step_results = workflow_context.get("step_results", {})
    capability_outputs = workflow_context.get("capability_outputs", {})
    
    # Pre-append session history to 'context' or 'question' if available
    # Specifically for ResearchAgent capabilities
    if session_history and (capability in ['answer_question', 'generate_report', 'research', 'explain_code']):
        history_context = "\n\n--- PREVIOUS SESSION HISTORY ---\n"
        for i, entry in enumerate(session_history[-5:]): # Increased to last 5 turns
             history_context += f"Turn {i+1} Task: {entry['task']}\nTurn {i+1} Result: {str(entry['result'])[:800]}\n\n"
        
        # Inject into 'context' parameter if it exists or create it
        if 'context' in enriched:
            # Check if it's already a string
            if isinstance(enriched['context'], str):
                enriched['context'] = history_context + enriched['context']
            else:
                enriched['context'] = history_context
        else:
            enriched['context'] = history_context
            
        print(f"         ✓ Injected {len(session_history)} session history items into context")
            
    print(f"      🔗 Context enrichment for '{capability}'...")

    # Strategy -1: Resolve {{step_id.result}} / {{step_id.anything}} mustache templates
    # The LLM often uses this syntax to reference prior steps by their plan-assigned id.
    import re as _re
    _mustache = _re.compile(r'\{\{([\w]+)\.([\w]+)\}\}')

    def _resolve_mustache(value):
        """Replace all {{id.field}} occurrences in a string with the actual result."""
        if not isinstance(value, str):
            return value
        def _sub(m):
            ref_id, ref_field = m.group(1), m.group(2)
            # 1. Look up by plan step id or step_N key in step_results
            entry = step_results.get(ref_id)
            if entry is None:
                # 2. Try capability_outputs keyed by capability name
                cap_val = capability_outputs.get(ref_id)
                if cap_val is not None:
                    result = cap_val
                    if isinstance(result, dict):
                        return str(result.get(ref_field, result.get('result', result.get('answer', str(result)))))
                    return str(result)
                return m.group(0)  # leave unresolved template as-is
            result = entry.get('result', '')
            if isinstance(result, dict):
                return str(result.get(ref_field, result.get('result', result.get('answer', str(result)))))
            return str(result)
        return _mustache.sub(_sub, value)

    for key, value in list(enriched.items()):
        if isinstance(value, str) and '{{' in value:
            resolved = _resolve_mustache(value)
            if resolved != value:
                enriched[key] = resolved
                print(f"         ✓ Resolved mustache template in '{key}'")

    # Strategy 0: Generic template replacement for <result_from_step_N> and <output from step N>
    import re
    
    for key, value in list(enriched.items()):
        if isinstance(value, str):
            # Match <result_from_step_1>, <output from step 2>, <output_from_step_2>, etc.
            pattern = r'<(?:result_from_step_|output_from_step_|output from step\s*)(\d+)>'
            match = re.search(pattern, value, re.IGNORECASE)
            
            if match:
                step_num = match.group(1)
                step_key = f"step_{step_num}"
                
                if step_key in step_results:
                    result = step_results[step_key]["result"]
                    
                    # Helper to extract scalar from dict (redefined here for scope)
                    def extract_scalar_recursive(data):
                        if not isinstance(data, dict):
                            return data
                        # If this dict is itself an error payload, return None so callers
                        # know not to inject this value into downstream parameters.
                        if "error" in data and len(data) == 1:
                            return None
                        for key in ["result", "answer", "output", "value", "content"]:
                            if key in data:
                                val = data[key]
                                if isinstance(val, dict):
                                    inner = extract_scalar_recursive(val)
                                    # Propagate None (error) upward
                                    return inner
                                return val
                        return data

                    # If result is a dict with common output keys, extract the value
                    if isinstance(result, dict):
                        extracted = extract_scalar_recursive(result)
                        if extracted is None:
                            # Step result is an error — skip injection so downstream steps
                            # keep the placeholder and fail with a clear message.
                            print(f"         ⚠️  Step {step_num} result is an error — skipping injection")
                        else:
                            enriched[key] = extracted
                            print(f"         ✓ Injected extracted value from step {step_num}")
                    else:
                        enriched[key] = result
                        print(f"         ✓ Injected result from step {step_num}")
    
    # Strategy 1: Generic Input Chaining
    # This replaces specific capability checks (math, transform, etc.) with a generic heuristic.
    # If parameters are missing but required, try to fill them from the previous step result.
    
    # Identify potential "chainable" input parameters
    # These are common names for primary inputs in agent capabilities
    primary_input_keys = ["data", "input", "value", "text", "context", "a", "base", "equation", "numbers", "code", "content"]
    
    # Identify which keys are present in current parameters but empty/None
    missing_keys = [k for k in primary_input_keys if k in enriched and (enriched[k] is None or enriched[k] == "")]
    
    # Also check if any critical primary keys are completely missing from parameters
    # (In a real system, we would check the agent's schema definition here)
    # For now, we assume if specific common keys are standard for a capability, we check them
    
    # If we have missing inputs and previous results exist
    if step_results:
        # Get the most recent result (Step N-1)
        # Sort by step number to ensure we get the last one
        try:
            last_key = sorted(step_results.keys(), key=lambda x: int(x.split('_')[1]))[-1]
            last_result = step_results[last_key]["result"]
        except Exception as e:
             print(f"      ⚠️  Error extracting last result: {e}")
             return enriched
        
        # Extract the actual value from the result structure
        chain_value = last_result
        
        # Helper to extract scalar from dict
        def extract_scalar(data):
            if not isinstance(data, dict):
                return data
            
            # Prioritize specific keys
            for key in ["result", "answer", "output", "value", "content"]:
                if key in data:
                    val = data[key]
                    # If extraction yielded another dict, recurse one level
                    if isinstance(val, dict):
                        return extract_scalar(val)
                    return val
            return data

        chain_value = extract_scalar(last_result)
        
        # Apply Generic Chaining Rules
        
        # Rule 1: Fill missing primary inputs
        for key in missing_keys:
            if enriched[key] is None or enriched[key] == "":
                enriched[key] = chain_value
                print(f"         ✓ Generic Chain: Injected previous result into '{key}'")
        
        # Rule 2: If 'transform_data' or 'analyze_data' or 'generate_report', ensure 'data' is filled
        if capability in ["transform_data", "analyze_data", "generate_report"] and "data" not in enriched:
             enriched["data"] = chain_value
             print(f"         ✓ Generic Chain: Injected previous result into 'data'")
             
        # Rule 3: Math specific chaining (generic fallback for numeric inputs)
        if capability in ["calculate", "advanced_math", "solve_equation", "statistics"]:
            # If 'value', 'a', or 'base' are missing, inject numeric values
            target_keys = ["value", "a", "base", "numbers"]
            for target in target_keys:
                if target not in enriched or enriched[target] is None:
                    # Only inject if we have a numeric-like value
                    is_numeric = isinstance(chain_value, (int, float)) or (isinstance(chain_value, str) and chain_value.replace('.','',1).isdigit())
                    if is_numeric:
                        if target == "numbers" and not isinstance(chain_value, list):
                            enriched[target] = [chain_value] # Wrap single number for statistics
                        else:
                            enriched[target] = chain_value
                        print(f"         ✓ Generic Chain: Injected numeric result into '{target}'")
                        break # Only fill one primary input per step to avoid 'a' and 'b' being same
                        
    # Strategy 2: Specific overrides if needed (kept minimal)
    if capability == "compare_concepts":
        # Need two concepts to compare
        if "concept_a" not in enriched or not enriched["concept_a"]:
            # Look for research/question answering results
            research_results = [
                res["result"] for res in step_results.values()
                if res.get("capability") in ["answer_question", "generate_report"]
            ]
            
            if len(research_results) >= 2:
                enriched["concept_a"] = research_results[-2]
                enriched["concept_b"] = research_results[-1]
                print(f"         ✓ Injected two research results for comparison")
            elif len(research_results) == 1:
                enriched["concept_a"] = research_results[0]
                # Try to extract second concept from description
                if "and" in step_description.lower():
                    parts = step_description.lower().split("and")
                    enriched["concept_b"] = parts[-1].strip()
                    print(f"         ✓ Injected one result + parsed concept from description")
    
    elif capability == "explain_code":
        if "code" not in enriched or not enriched["code"]:
            if "analyze_python_code" in capability_outputs:
                enriched["code"] = capability_outputs["analyze_python_code"]
                print(f"         ✓ Injected analyzed code")
    
    elif capability == "summarize_data":
        if "data" not in enriched:
            # Summarize all previous outputs
            enriched["data"] = {
                k: v["result"] for k, v in step_results.items()
            }
            print(f"         ✓ Injected all previous step results")
    
    elif capability == "analyze_data":
        # Check if data parameter is a placeholder or missing
        if "data" not in enriched or not enriched["data"] or \
           (isinstance(enriched["data"], str) and ("<" in enriched["data"] or "output from step" in enriched["data"].lower())):
            # Use last result from previous step
            if step_results:
                last_result = list(step_results.values())[-1]["result"]
                # If the last result is from answer_question or research, use the answer
                last_capability = list(step_results.values())[-1].get("capability")
                if last_capability in ["answer_question", "research"]:
                    if isinstance(last_result, dict) and "answer" in last_result:
                        enriched["data"] = last_result["answer"]
                        print(f"         ✓ Injected research answer for analysis")
                    else:
                        enriched["data"] = last_result
                        print(f"         ✓ Injected research result for analysis")
                else:
                    enriched["data"] = last_result
                    print(f"         ✓ Injected last step result for analysis")
            elif "answer_question" in capability_outputs:
                result = capability_outputs["answer_question"]
                if isinstance(result, dict) and "answer" in result:
                    enriched["data"] = result["answer"]
                else:
                    enriched["data"] = result
                print(f"         ✓ Injected answer_question output for analysis")
    
    elif capability == "calculate":
        # Extract mathematical operation from description
        if not enriched or "operation" not in enriched:
            import re
            desc_lower = step_description.lower()
            
            # Try to extract numbers and operation
            numbers = re.findall(r'\d+(?:\.\d+)?', desc_lower)
            
            if "sum" in desc_lower or "add" in desc_lower or "plus" in desc_lower or "+" in desc_lower:
                enriched["operation"] = "add"
            elif "subtract" in desc_lower or "minus" in desc_lower or "difference" in desc_lower:
                enriched["operation"] = "subtract"
            elif "multiply" in desc_lower or "times" in desc_lower or "product" in desc_lower:
                enriched["operation"] = "multiply"
            elif "divide" in desc_lower or "quotient" in desc_lower:
                enriched["operation"] = "divide"
            
            if len(numbers) >= 2:
                enriched["a"] = float(numbers[0])
                enriched["b"] = float(numbers[1])
                print(f"         ✓ Extracted math operation: {enriched.get('operation')} {enriched.get('a')} and {enriched.get('b')}")
    
    elif capability == "advanced_math":
        # Handle advanced math operations
        import re
        desc_lower = step_description.lower()
        
        # Get value from previous step if available
        value = None
        if step_results:
            last_result = list(step_results.values())[-1].get("result", {})
            # Navigate through nested result structure
            if isinstance(last_result, dict):
                # Try to extract the numeric result value
                if "result" in last_result:
                    nested = last_result["result"]
                    if isinstance(nested, dict) and "result" in nested:
                        value = nested["result"]
                    elif isinstance(nested, (int, float)):
                        value = nested
                    else:
                        value = nested
                elif "value" in last_result:
                    value = last_result["value"]
            elif isinstance(last_result, (int, float)):
                value = last_result
        
        # Check if value parameter is a placeholder
        if "value" in enriched and isinstance(enriched["value"], str):
            if "result_from_step" in enriched["value"] or enriched["value"].startswith("<"):
                if value is not None:
                    enriched["value"] = value
                    print(f"         ✓ Replaced placeholder with actual value: {value}")
        
        # If operation is missing, try to determine it
        if "operation" not in enriched:
            # Determine operation
            if "square" in desc_lower:
                enriched["operation"] = "square"
                if value is not None and "value" not in enriched:
                    enriched["value"] = value
                    print(f"         ✓ Extracted square operation on value: {value}")
            elif "sqrt" in desc_lower or "square root" in desc_lower:
                enriched["operation"] = "sqrt"
                if value is not None and "value" not in enriched:
                    enriched["value"] = value
                    print(f"         ✓ Extracted sqrt operation on value: {value}")
            elif "power" in desc_lower or "^" in desc_lower:
                enriched["operation"] = "power"
                if value is not None and "value" not in enriched:
                    enriched["value"] = value
                # Try to extract exponent
                numbers = re.findall(r'\d+', desc_lower)
                if numbers and "exponent" not in enriched:
                    enriched["exponent"] = float(numbers[0])
                print(f"         ✓ Extracted power operation")
    
    # Strategy 2: If still missing critical params, use last result
    if not enriched or all(v == "" or v is None for v in enriched.values()):
        if step_results:
            last_step = list(step_results.values())[-1]
            # Try to map to first expected parameter
            if "question" in str(parameters):
                enriched["question"] = workflow_context.get("original_task", "")
            elif "data" in str(parameters):
                enriched["data"] = last_step["result"]
            else:
                # Generic fallback
                enriched["input"] = last_step["result"]
            print(f"         ⚠️  Applied generic context injection")
    
    return enriched

# Configuration
ORCHESTRATOR_NAME = os.getenv("ORCHESTRATOR_NAME", "MainOrchestrator")
ORCHESTRATOR_PORT = int(os.getenv("ORCHESTRATOR_PORT", "8100"))
ORCHESTRATOR_HOST = os.getenv("ORCHESTRATOR_HOST", "localhost")
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://localhost:8000")
AWS_REGION = os.getenv("AWS_REGION", "eu-west-2")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")

# Global state
orchestrator_id = None
registry_client = None
bedrock_client = None
# NOTE: active_workflows was a per-process dict and has been replaced by
# dist_state.workflows — a shared, Redis-backed store for HA deployments.
# All former `active_workflows[...]` usages now go through dist_state.


async def register_with_registry():
    """Register orchestrator with registry"""
    global orchestrator_id, registry_client
    
    metadata = AgentMetadata(
        name=ORCHESTRATOR_NAME,
        role=AgentRole.ORCHESTRATOR,
        capabilities=[
            AgentCapability(
                name="orchestrate_workflow",
                description="Orchestrate complex multi-agent workflows",
                requires_llm=True
            ),
            AgentCapability(
                name="plan_execution",
                description="Plan task execution using LLM reasoning",
                requires_llm=True
            )
        ],
        has_llm=True,
        endpoint=f"http://{ORCHESTRATOR_HOST}:{ORCHESTRATOR_PORT}"
    )
    
    registry_client = A2AClient(REGISTRY_URL, timeout=int(os.getenv("AGENT_TASK_TIMEOUT", "300")))
    
    try:
        response = await registry_client.register_agent(metadata)
        orchestrator_id = response.agent_id
        print(f"✓ Orchestrator registered: {orchestrator_id}")
        asyncio.create_task(send_heartbeats())
    except Exception as e:
        print(f"✗ Failed to register: {e}")
        raise


async def send_heartbeats():
    """Send periodic heartbeats"""
    while True:
        await asyncio.sleep(30)
        try:
            await registry_client.heartbeat(orchestrator_id)
        except Exception as e:
            print(f"Heartbeat failed: {e}")


def init_bedrock():
    """Initialize Bedrock client"""
    global bedrock_client
    
    # Build client configuration - always use region
    client_config = {
        'service_name': 'bedrock-runtime',
        'region_name': AWS_REGION
    }
    
    # Only add credentials if explicitly provided in .env and not placeholder values
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
    
    if aws_access_key and aws_secret_key and aws_access_key not in ["your_key", ""]:
        client_config['aws_access_key_id'] = aws_access_key
        client_config['aws_secret_access_key'] = aws_secret_key
        
        # Add session token if present (for temporary credentials)
        aws_session_token = os.getenv("AWS_SESSION_TOKEN", "").strip()
        if aws_session_token:
            client_config['aws_session_token'] = aws_session_token
        
        print("✓ Using AWS credentials from .env file")
    else:
        print("✓ Using AWS credentials from local AWS configuration (~/.aws/credentials)")
    
    bedrock_client = boto3.client(**client_config)
    print(f"✓ Bedrock client initialized (region: {AWS_REGION}, model: {BEDROCK_MODEL_ID})")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management"""
    global db, interaction_mgr, executor
    
    print("Starting Orchestrator Service...")
    
    # Initialize database and managers
    from ha_database import get_workflow_database
    from interaction import InteractionManager
    from executor import WorkflowExecutor
    
    global db, interaction_mgr, executor
    db = get_workflow_database()
    interaction_mgr = InteractionManager(db)
    executor = WorkflowExecutor(db, interaction_mgr)
    print("✓ Database and managers initialized")
    
    # Start distributed state (registers instance, begins heartbeat)
    await dist_state.startup()
    print(f"✓ Distributed state started — backend={dist_state.backend.value} instance={dist_state.instance_id}")
    
    # Initialize Bedrock
    init_bedrock()
    
    # Register with registry
    await register_with_registry()
    
    # Initialize WebSocket handler
    init_websocket_handler()
    
    yield
    
    print("Shutting down Orchestrator Service...")
    if registry_client and orchestrator_id:
        await registry_client.unregister_agent(orchestrator_id)
        await registry_client.close()
    # Graceful distributed state shutdown (deregisters instance, closes connections)
    await dist_state.shutdown()


app = FastAPI(
    title="A2A Orchestrator Service",
    description="Orchestrator for A2A Multi-Agent System",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware for WebSocket connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize WebSocket handler (will be set up after managers are available)
# Global state
registry_client: A2AClient = None
orchestrator_id: str = None
bedrock_runtime = None

# Global managers (initialized in lifespan)
db = None
interaction_mgr = None
executor = None
ws_handler = None


def init_websocket_handler():
    """Initialize WebSocket handler with database and managers"""
    global ws_handler, db, interaction_mgr, executor
    from websocket_handler import WebSocketMessageHandler
    
    # Use the global instances created during lifespan startup
    if not db:
        print("⚠️  Warning: Database not initialized yet")
        return
    if not interaction_mgr:
        print("⚠️  Warning: Interaction manager not initialized yet")
        return
    if not executor:
        print("⚠️  Warning: Executor not initialized yet")
        return
    
    # Pass the resume_workflow function to the handler
    ws_handler = WebSocketMessageHandler(db, interaction_mgr, executor, resume_workflow_func=resume_workflow)

    # HA: wrap broadcast_to_workflow so every local broadcast ALSO publishes to
    # Redis pub/sub — other replicas subscribe and forward to their WS clients.
    _original_broadcast = ws_handler.connection_manager.broadcast_to_workflow

    async def _ha_broadcast(workflow_id: str, event: dict) -> None:
        # Deliver to WebSocket clients connected to THIS instance directly.
        await _original_broadcast(workflow_id, event)
        # Fan-out to OTHER replicas via pub/sub backend.
        # In single-instance (InMemory) mode we must NOT also publish here because
        # subscribe_local_websocket() registered each WS client as a pub/sub
        # subscriber that calls _local_broadcast — publishing would re-deliver
        # every event a second time to the same connections.
        from shared.distributed_state import InMemoryPubSubBroker
        if not isinstance(dist_state.pubsub, InMemoryPubSubBroker):
            await dist_state.pubsub.publish(workflow_id, event)

    ws_handler.connection_manager.broadcast_to_workflow = _ha_broadcast
    # Store the original local-only broadcast so pub/sub subscribers can forward
    # to local WS clients WITHOUT re-publishing to pub/sub (prevents feedback loop)
    ws_handler.connection_manager._local_broadcast = _original_broadcast
    print("✓ WebSocket handler initialized (HA pub/sub fan-out enabled)")


# NOTE: session_store was a per-process defaultdict. It is now backed by
# dist_state.sessions which is Redis-backed in HA mode for cross-instance persistence.


@app.get("/")
async def root():
    return {
        "service": "A2A Orchestrator",
        "orchestrator_id": orchestrator_id,
        "status": "running"
    }


@app.get("/health")
async def health():
    active_ids = await dist_state.workflows.list_ids()
    return {
        "status": "healthy",
        "orchestrator_id": orchestrator_id,
        "instance_id": dist_state.instance_id,
        "ha_backend": dist_state.backend.value,
        "active_workflows": len(active_ids)
    }


@app.post("/api/workflow/execute")
async def execute_workflow(
    request: Dict[str, Any],
    user: UserContext = Depends(get_current_user),
    user_headers: Dict[str, str] = Depends(get_user_headers)
):
    """Execute a workflow using THINK-PLAN-EXECUTE-VERIFY-REFLECT pattern"""
    task_description = request.get("task_description")
    if not task_description:
        raise HTTPException(status_code=400, detail="task_description required")
    
    workflow_id = request.get("workflow_id", str(datetime.utcnow().timestamp()))
    session_id = request.get("session_id")
    async_mode = request.get("async", False)  # Support async execution
    
    # Register workflow immediately in both memory and DB
    workflow_state = {
        "workflow_id": workflow_id,
        "session_id": session_id,  # Store session ID
        "status": "initializing",
        "task_description": task_description,
        "start_time": datetime.utcnow().isoformat(),
        "results": [],
        "completed_steps": []
    }
    
    if not await dist_state.workflow_exists(workflow_id):
        await dist_state.set_workflow_state(workflow_id, workflow_state)
        # Also save to DB for WebSocket handler
        workflow_record = WorkflowRecord(
            workflow_id=workflow_id,
            task_description=task_description,
            status=WorkflowStatus.PLANNING,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.save_workflow(workflow_record)  # Not async
    
    if async_mode:
        # Run workflow in background task
        async def run_workflow_with_error_handling():
            try:
                # Use real authenticated user context
                await _execute_workflow_internal(workflow_id, task_description, headers=user_headers)
            except Exception as e:
                print(f"❌ Background workflow execution failed: {e}")
                import traceback
                traceback.print_exc()
                # Update workflow status in distributed store
                await dist_state.update_workflow_state(workflow_id, {"status": "failed", "error": str(e)})
        
        asyncio.create_task(run_workflow_with_error_handling())
        return {
            "workflow_id": workflow_id,
            "status": "started",
            "message": "Workflow started in background. Connect to WebSocket for updates.",
            "websocket_url": f"/ws/workflow/{workflow_id}"
        }
    else:
        # Run workflow synchronously (original behavior)
        return await _execute_workflow_internal(workflow_id, task_description, headers=user_headers)


async def _execute_workflow_internal(workflow_id: str, task_description: str, headers: Dict[str, str] = None):
    """Internal workflow execution logic"""
    headers = headers or {}
    user_context = security_manager.get_user_context(headers)
    user_id = user_context.user_id
    
    print(f"\n{'='*80}")
    print(f"🚀 WORKFLOW EXECUTION STARTED (User: {user_id})")
    print(f"{'='*80}")
    
    # AUDIT: Log workflow start
    audit_logger.log_event(workflow_id, user_id, "WORKFLOW_START", {"task": task_description})
    
    # GUARDRAIL: Input Validation
    is_valid, reason = guardrails.validate_input(task_description)
    if not is_valid:
        error_msg = f"Guardrail Blocked Input: {reason}"
        print(f"❌ {error_msg}")
        audit_logger.log_event(workflow_id, user_id, "GUARDRAIL_VIOLATION", {"reason": reason})
        raise HTTPException(status_code=400, detail=error_msg)
        
    print(f"Workflow ID: {workflow_id}")
    print(f"Task: {task_description}")
    print()
    
    execution_log = []
    
    # Retrieve session history from distributed store
    workflow_state = await dist_state.get_workflow_state(workflow_id) or {}
    session_id = workflow_state.get("session_id")
    session_history = None
    if session_id:
        # Retrieve from DB instead of memory
        session_history = db.get_session_history(session_id)
        if session_history:
            print(f"   📜 Found {len(session_history)} previous session interactions")

        # Augment with semantically relevant long-term memories
        if vector_memory.is_enabled:
            semantic_memories = await vector_memory.recall(
                query=task_description,
                session_id=None,  # Search globally across sessions
                top_k=5
            )
            if semantic_memories:
                print(f"   🧠 Recalled {len(semantic_memories)} long-term memories via vector search")
                # Prepend semantic memories to session history so the planner sees them
                memory_items = [
                    {
                        "task": m.metadata.get("task", m.text[:120]),
                        "result": m.metadata.get("result", ""),
                        "timestamp": m.metadata.get("timestamp", ""),
                        "workflow_id": m.metadata.get("workflow_id", ""),
                        "_memory_score": round(m.score, 3),
                        "_source": "vector_recall"
                    }
                    for m in semantic_memories
                ]
                session_history = memory_items + (session_history or [])
    
    try:
        # PHASE 1: THINK - Understand the task and available resources
        print(f"💭 PHASE 1: THINK - Understanding task and resources...")
        print(f"   Task Analysis: {task_description}")
        
        agents = await registry_client.get_all_agents()
        print(f"   Found {len(agents)} registered agents")
        
        capabilities = {}
        capability_descriptions = {}
        capability_schemas: Dict[str, Any] = {}   # input_schema per capability
        for agent in agents:
            print(f"   - {agent.name} ({agent.role.value})")
            for cap in agent.capabilities:
                if cap.name not in capabilities:
                    capabilities[cap.name] = []
                    capability_descriptions[cap.name] = cap.description
                    if cap.input_schema:
                        capability_schemas[cap.name] = cap.input_schema
                capabilities[cap.name].append({
                    "agent_id": agent.agent_id,
                    "agent_name": agent.name,
                    "endpoint": agent.endpoint,
                    "description": cap.description
                })
                print(f"     ✓ {cap.name}: {cap.description}")
        
        execution_log.append({
            "phase": "THINK",
            "agents_found": len(agents),
            "capabilities_available": list(capabilities.keys())
        })
        
        # PHASE 2: PLAN - Generate dynamic execution plan
        print(f"\n📋 PHASE 2: PLAN - Generating dynamic execution plan...")
        print(f"   Model: {BEDROCK_MODEL_ID}")
        
        plan = await generate_dynamic_plan(
            task_description, capabilities, capability_descriptions,
            session_history, capability_schemas
        )
        
        print(f"   Generated plan with {len(plan.get('steps', []))} steps")
        print(f"   Reasoning: {plan.get('reasoning', 'N/A')[:200]}...")
        
        for i, step in enumerate(plan.get('steps', []), 1):
            print(f"   Step {i}: {step.get('description')}")
            print(f"      └─ Capability: {step.get('capability')}")
        
        execution_log.append({
            "phase": "PLAN",
            "plan": plan,
            "total_steps": len(plan.get('steps', []))
        })
        
        # PHASE 3: EXECUTE - Execute plan with context propagation
        print(f"\n⚙️  PHASE 3: EXECUTE - Running planned steps...")
        
        workflow_state = {
            "workflow_id": workflow_id,
            "task_description": task_description,
            "plan": plan,
            "start_time": datetime.utcnow().isoformat(),
            "completed_steps": [],
            "results": [],
            "context": {},  # Shared context across steps
            "execution_log": execution_log
        }
        
        await dist_state.set_workflow_state(workflow_id, workflow_state)
        # Claim ownership so other replicas know this instance is handling it
        await dist_state.ownership.claim(workflow_id, dist_state.instance_id)
        
        # Context accumulator for cross-step data sharing
        workflow_context = {
            "original_task": task_description,
            "step_results": {},
            "capability_outputs": {}
        }
        
        for step in plan.get("steps", []):
            step_num = step.get("step_number", 0)
            
            # Check if workflow is paused (e.g., waiting for user input)
            if workflow_state.get("paused", False):
                print(f"⏸️  Workflow paused, stopping execution at step {step_num}")
                break
            
            capability = step.get("capability")
            parameters = step.get("parameters", {})
            description = step.get("description", "")
            
            print(f"\n   📌 Step {step_num}/{len(plan.get('steps', []))}: {description}")
            print(f"      Capability: {capability}")
            print(f"      Initial Parameters: {json.dumps(parameters, indent=10)}")
            
            # Find agent for capability
            if capability not in capabilities:
                print(f"      ❌ No agent found for capability: {capability}")
                execution_log.append({
                    "step_number": step_num,
                    "status": "skipped",
                    "reason": f"No agent for capability: {capability}"
                })
                continue
            
            agent_info = capabilities[capability][0]
            agent_endpoint = agent_info["endpoint"]
            agent_name = agent_info["agent_name"]
            
            print(f"      Agent: {agent_name}")
            print(f"      Endpoint: {agent_endpoint}")

            # Notify WebSocket clients: step started
            if ws_handler and ws_handler.connection_manager.has_connections(workflow_id):
                await ws_handler.connection_manager.broadcast_to_workflow(workflow_id, {
                    "type": "step_started",
                    "workflow_id": workflow_id,
                    "step": {
                        "step_number": step_num,
                        "total_steps": len(plan.get('steps', [])),
                        "capability": capability,
                        "description": description,
                        "agent": agent_name
                    },
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            # Dynamically enrich parameters with workflow context
            enriched_parameters = await enrich_with_workflow_context(
                capability=capability,
                parameters=parameters,
                workflow_context=workflow_context,
                step_description=description,
                session_history=session_history
            )
            
            print(f"      Enriched Parameters: {json.dumps(enriched_parameters, indent=10)}")
            
            # Create task with full context
            task = TaskRequest(
                capability=capability,
                parameters=enriched_parameters,
                context={
                    "workflow_id": workflow_id,
                    "step_number": step_num,
                    "step_id": f"step_{step_num}",
                    "agent_name": agent_name,
                    "total_steps": len(plan.get('steps', [])),
                    "workflow_context": workflow_context,
                    "user_identity": user_context # Propagate Identity
                }
            )
            
            # SECURITY: Tool Authorization (Deterministic Check)
            if not security_manager.validate_tool_authorization(user_context.role, capability, enriched_parameters):
                error_msg = f"Security Policy Blocked: Authorization failed for '{capability}' with params {enriched_parameters}"
                print(f"      ❌ {error_msg}")
                audit_logger.log_event(workflow_id, user_id, "SECURITY_VIOLATION", {"capability": capability, "params": enriched_parameters})
                execution_log.append({
                    "step_number": step_num,
                    "status": "failed",
                    "error": error_msg
                })
                continue

            # AUDIT: Log CoT (Thought/Plan)
            audit_logger.log_cot(
                workflow_id, step_num, 
                thought=f"Need to execute {capability}", 
                plan=f"Call agent {agent_name}", 
                observation="Pending", 
                action=f"Invoke {capability} with {enriched_parameters}"
            )
            
            # Execute task
            try:
                print(f"      🔄 Sending task to {agent_name}...")
                response = await registry_client.send_task(agent_endpoint, task)
                
                # Check if agent is requesting user input
                if (response.status == TaskStatus.COMPLETED and 
                    isinstance(response.result, dict) and 
                    response.result.get("status") == "user_input_required"):
                    
                    interaction_req = response.result.get("interaction_request", {})
                    
                    print(f"      ⏸️  Step {step_num} PAUSED - Awaiting user input")
                    print(f"      Question: {interaction_req.get('question', 'N/A')}")
                    
                    # Determine input type
                    from models import InputType
                    input_type_str = interaction_req.get("input_type", "text")
                    if input_type_str == "single_choice":
                        input_type = InputType.SINGLE_CHOICE
                    elif input_type_str == "multiple_choice":
                        input_type = InputType.MULTIPLE_CHOICE
                    elif input_type_str == "confirmation":
                        input_type = InputType.CONFIRMATION
                    else:
                        input_type = InputType.TEXT
                    
                    # Create interaction request via interaction manager
                    # Merge agent context with orchestrator context
                    merged_context = {"capability": capability, "step": step_num}
                    agent_context = interaction_req.get("context", {})
                    if isinstance(agent_context, dict):
                        merged_context.update(agent_context)
                    
                    # Extract and validate reasoning field
                    reasoning = interaction_req.get("reasoning", "")
                    if not isinstance(reasoning, str):
                        reasoning = str(reasoning) if reasoning else ""
                    
                    interaction_request = await interaction_mgr.request_user_input(
                        workflow_id=workflow_id,
                        step_id=f"step_{step_num}",
                        agent_name=agent_name,
                        question=interaction_req.get("question", "Additional input needed"),
                        input_type=input_type,
                        options=interaction_req.get("options"),
                        context=merged_context,
                        reasoning=reasoning
                    )
                    
                    # Create interaction object matching HTML client expectations
                    interaction = {
                        "request_id": interaction_request.request_id,
                        "workflow_id": workflow_id,
                        "step_number": step_num,
                        "agent": agent_name,
                        "capability": capability,
                        "question": interaction_request.question,
                        "reasoning": interaction_request.reasoning or "",
                        "input_type": input_type_str,
                        "options": interaction_request.options,
                        "placeholder": interaction_req.get("placeholder", "Enter your response...")
                    }
                    
                    # Save workflow state to database
                    db.update_workflow_state(workflow_id, {
                        "status": "waiting_for_input",
                        "current_step": step_num,
                        "plan": plan,
                        "workflow_context": workflow_context,
                        "workflow_state": workflow_state,
                        "pending_interaction": interaction,
                        "agent_endpoint": agent_endpoint,
                        "agent_name": agent_name,
                        "original_task": task.dict() if hasattr(task, 'dict') else task
                    })
                    
                    # Notify WebSocket clients: user input needed
                    if ws_handler and ws_handler.connection_manager.has_connections(workflow_id):
                        await ws_handler.connection_manager.broadcast_to_workflow(workflow_id, {
                            "type": "user_input_required",
                            "workflow_id": workflow_id,
                            "interaction": interaction,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                    
                    # Mark workflow as paused and break from loop
                    workflow_state["paused"] = True
                    workflow_state["pending_interaction"] = interaction
                    workflow_state["pause_step"] = step_num
                    workflow_state["agent_endpoint"] = agent_endpoint
                    workflow_state["agent_name"] = agent_name
                    
                    print(f"      ⏸️  Workflow paused at step {step_num}")
                    break  # Exit the loop
                
                # PHASE 4: VERIFY - Verify step execution
                elif response.status == TaskStatus.COMPLETED:
                    # Guard: some agents return HTTP 200 / COMPLETED but embed an MCP
                    # failure inside the result payload, e.g.:
                    #   {"result": {"error": "All connection attempts failed"}, ...}
                    # Detect this and treat the step as genuinely failed so the error is
                    # surfaced cleanly instead of propagating a corrupt value downstream.
                    _r = response.result if isinstance(response.result, dict) else {}
                    _inner_r = _r.get("result", _r)
                    _embedded_err = _inner_r.get("error") if isinstance(_inner_r, dict) else None
                    if _embedded_err:
                        _err_msg = f"MCP tool error: {_embedded_err}"
                        print(f"      ❌ Step {step_num} VERIFICATION FAILED: {_err_msg}")
                        execution_log.append({
                            "phase": "EXECUTE-VERIFY",
                            "step_number": step_num,
                            "status": "failed",
                            "error": _err_msg
                        })
                        if ws_handler and ws_handler.connection_manager.has_connections(workflow_id):
                            await ws_handler.connection_manager.broadcast_to_workflow(workflow_id, {
                                "type": "step_failed",
                                "workflow_id": workflow_id,
                                "step": {
                                    "step_number": step_num,
                                    "capability": capability,
                                    "description": description
                                },
                                "error": _err_msg,
                                "timestamp": datetime.utcnow().isoformat()
                            })
                        continue  # Do NOT add to completed_steps / step_results

                    workflow_state["completed_steps"].append(step_num)
                    
                    result_data = {
                        "step": step_num,
                        "capability": capability,
                        "agent": agent_name,
                        "result": response.result,
                        "description": description
                    }
                    workflow_state["results"].append(result_data)
                    
                    # Update workflow context with result
                    
                    # GUARDRAIL: Output Validation (PII Redaction / Topic Filtering)
                    if isinstance(response.result, str):
                        is_valid_out, sanitized_result = guardrails.validate_output(response.result)
                        if not is_valid_out:
                            print(f"      ⚠️  Guardrail Modified Output: {sanitized_result}")
                        response.result = sanitized_result
                    
                    workflow_context["step_results"][f"step_{step_num}"] = {
                        "description": description,
                        "capability": capability,
                        "result": response.result
                    }
                    workflow_context["capability_outputs"][capability] = response.result
                    
                    print(f"      ✅ Step {step_num} VERIFIED - Success")
                    print(f"      Result: {str(response.result)[:200]}...")
                    
                    # AUDIT: Log Observation
                    audit_logger.log_cot(
                        workflow_id, step_num, 
                        thought="Execution completed", 
                        plan="Verify result", 
                        observation=str(response.result)[:500], 
                        action="Proceed to next step"
                    )
                    
                    execution_log.append({
                        "phase": "EXECUTE-VERIFY",
                        "step_number": step_num,
                        "status": "completed",
                        "agent": agent_name,
                        "capability": capability,
                        "result_preview": str(response.result)[:100]
                    })
                    
                    # Notify WebSocket clients: step completed
                    if ws_handler and ws_handler.connection_manager.has_connections(workflow_id):
                        await ws_handler.connection_manager.broadcast_to_workflow(workflow_id, {
                            "type": "step_completed",
                            "workflow_id": workflow_id,
                            "step": {
                                "step_number": step_num,
                                "capability": capability,
                                "description": description,
                                "agent": agent_name,
                                "status": "completed"
                            },
                            "result": response.result,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                else:
                    print(f"      ❌ Step {step_num} VERIFICATION FAILED: {response.error}")
                    execution_log.append({
                        "phase": "EXECUTE-VERIFY",
                        "step_number": step_num,
                        "status": "failed",
                        "error": response.error
                    })
                    
                    # Notify WebSocket clients: step failed
                    if ws_handler and ws_handler.connection_manager.has_connections(workflow_id):
                        await ws_handler.connection_manager.broadcast_to_workflow(workflow_id, {
                            "type": "step_failed",
                            "workflow_id": workflow_id,
                            "step": {
                                "step_number": step_num,
                                "capability": capability,
                                "description": description
                            },
                            "error": response.error,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                    # Continue with remaining steps instead of breaking
                    
            except Exception as e:
                print(f"      ❌ Step {step_num} ERROR: {str(e)}")
                execution_log.append({
                    "phase": "EXECUTE",
                    "step_number": step_num,
                    "status": "error",
                    "error": str(e)
                })
                
                # Notify WebSocket clients: step error
                if ws_handler and ws_handler.connection_manager.has_connections(workflow_id):
                    await ws_handler.connection_manager.broadcast_to_workflow(workflow_id, {
                        "type": "step_error",
                        "workflow_id": workflow_id,
                        "step": {
                            "step_number": step_num,
                            "capability": capability,
                            "description": description
                        },
                        "error": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    })
                # Continue with remaining steps
        
        # Check if workflow was paused for user input
        if workflow_state.get("paused", False):
            return {
                "workflow_id": workflow_id,
                "status": "waiting_for_input",
                "request_id": workflow_state["pending_interaction"]["request_id"],
                "message": "Workflow paused - awaiting user input",
                "interaction": workflow_state["pending_interaction"],
                "steps_completed": len(workflow_state["completed_steps"]),
                "current_step": workflow_state["pause_step"],
                "total_steps": len(plan.get('steps', []))
            }
        
        # PHASE 5: REFLECT - Analyze execution and results
        print(f"\n🤔 PHASE 5: REFLECT - Analyzing execution...")
        
        reflection = await generate_reflection(
            task_description=task_description,
            plan=plan,
            workflow_context=workflow_context,
            completed_steps=len(workflow_state["completed_steps"]),
            total_steps=len(plan.get('steps', []))
        )
        
        print(f"   Reflection: {reflection.get('summary', 'N/A')}")
        print(f"   Success Rate: {reflection.get('success_rate', 'N/A')}")
        
        workflow_state["end_time"] = datetime.utcnow().isoformat()
        workflow_state["status"] = "completed"
        workflow_state["context"] = workflow_context
        workflow_state["reflection"] = reflection
        workflow_state["execution_log"] = execution_log
        
        print(f"\n{'='*80}")
        print(f"✅ WORKFLOW COMPLETED")
        print(f"{'='*80}")
        print(f"Steps completed: {len(workflow_state['completed_steps'])}/{len(plan.get('steps', []))}")
        print(f"Success rate: {reflection.get('success_rate', 'N/A')}")
        print()
        
        result = {
            "workflow_id": workflow_id,
            "status": "completed",
            "steps_completed": len(workflow_state["completed_steps"]),
            "total_steps": len(plan.get("steps", [])),
            "results": workflow_state["results"],
            "workflow_context": workflow_context,
            "reflection": reflection,
            "execution_log": execution_log,
            "plan": plan
        }
        
        # Notify WebSocket clients: workflow completed
        if ws_handler and ws_handler.connection_manager.has_connections(workflow_id):
            await ws_handler.connection_manager.broadcast_to_workflow(workflow_id, {
                "type": "workflow_completed",
                "workflow_id": workflow_id,
                "status": "completed",
                "steps_completed": len(workflow_state["completed_steps"]),
                "total_steps": len(plan.get("steps", [])),
                "result": result,
                "timestamp": datetime.utcnow().isoformat()
            })
        
        return result
        
    except Exception as e:
        print(f"\n❌ WORKFLOW EXECUTION FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


async def resume_workflow(workflow_id: str) -> Dict[str, Any]:
    """
    Resume a paused workflow after receiving user input.
    Continues execution from the paused step with user response injected into context.
    """
    global db, interaction_mgr, registry_client, ws_handler
    
    try:
        print(f"\n🔄 RESUMING WORKFLOW: {workflow_id}")
        
        # 1. Load workflow state from database
        workflow_record = db.get_workflow(workflow_id)
        if not workflow_record:
            raise HTTPException(404, "Workflow not found")
        
        if workflow_record.status != WorkflowStatus.WAITING_FOR_INPUT:
            raise HTTPException(400, f"Workflow not paused (status: {workflow_record.status.value})")
        
        # 2. Get answered interaction request (user has already responded)
        interaction_request = interaction_mgr.get_answered_request(workflow_id)
        if not interaction_request:
            raise HTTPException(400, "No answered interaction request found for this workflow")
        
        print(f"   User response: {interaction_request.response}")
        
        # 3. Mark interaction as completed
        interaction_mgr.complete_interaction(interaction_request.request_id)
        
        # 4. Load saved workflow state
        # The plan is stored in workflow_context, not execution_plan
        if workflow_record.execution_plan and 'steps' in workflow_record.execution_plan:
            plan = workflow_record.execution_plan
        elif workflow_record.workflow_context and 'plan' in workflow_record.workflow_context:
            plan = workflow_record.workflow_context['plan']
        else:
            raise HTTPException(500, "No execution plan found in workflow record")
        
        # workflow_record.workflow_context contains the FULL state_data that was saved
        # We need to extract the ACTUAL workflow_context from inside it
        saved_state = workflow_record.workflow_context
        workflow_context = saved_state.get("workflow_context", {})
        workflow_state = saved_state.get("workflow_state", {})
        
        # If workflow_context is still empty, try workflow_record.workflow_state
        if not workflow_context:
            workflow_context = {}
        if not workflow_state and workflow_record.workflow_state:
            workflow_state = workflow_record.workflow_state
        
        # Ensure required context structures exist
        if "step_results" not in workflow_context:
            workflow_context["step_results"] = {}
        if "capability_outputs" not in workflow_context:
            workflow_context["capability_outputs"] = {}
        
        print(f"   📊 Loaded context: {len(workflow_context.get('step_results', {}))} step results, {len(workflow_context.get('capability_outputs', {}))} outputs")
        
        # Get the actual pause step from workflow_state
        pause_step = (workflow_state.get("pause_step") or 
                     saved_state.get("current_step") or 
                     workflow_record.current_step)
        
        if not pause_step or pause_step == 0:
            raise HTTPException(500, f"Could not determine paused step (pause_step={pause_step})")
        
        # Try to get agent info from multiple locations
        agent_endpoint = (workflow_state.get("agent_endpoint") or 
                         saved_state.get("agent_endpoint"))
        agent_name = (workflow_state.get("agent_name") or 
                     saved_state.get("agent_name"))
        
        if not agent_endpoint or not agent_name:
            raise HTTPException(500, f"Agent information not found in workflow state (endpoint={agent_endpoint}, name={agent_name})")
        
        original_task = workflow_record.task_description
        
        # 5. Inject user response into workflow context
        user_response_key = f"user_response_step_{pause_step}"
        workflow_context[user_response_key] = interaction_request.response
        
        # Ensure required context structures exist
        if "capability_outputs" not in workflow_context:
            workflow_context["capability_outputs"] = {}
        if "step_results" not in workflow_context:
            workflow_context["step_results"] = {}
            
        workflow_context["capability_outputs"][f"user_input_{pause_step}"] = interaction_request.response
        
        print(f"   ✓ Injected user response into context as '{user_response_key}'")
        
        # 6. Re-execute the paused step with user input
        step = plan['steps'][pause_step - 1]  # Steps are 1-indexed
        capability = step.get("capability")
        parameters = step.get("parameters", {})
        description = step.get("description", "")
        
        print(f"\n   📌 Re-executing Step {pause_step}/{len(plan['steps'])}: {description}")
        print(f"      Capability: {capability}")
        
        # Enrich parameters with user response
        enriched_parameters = await enrich_with_workflow_context(
            capability=capability,
            parameters=parameters,
            workflow_context=workflow_context,
            step_description=description
        )
        
        # Add user response explicitly if not already enriched
        if "user_input" not in enriched_parameters and interaction_request.response:
            enriched_parameters["user_input"] = interaction_request.response
        
        print(f"      Enriched Parameters: {json.dumps(enriched_parameters, indent=10)}")
        
        # Create task with user response in context
        # Build user_responses list for agent's InteractionHelper.
        # Include ALL previous answered Q&A turns for this step so multi-turn
        # agents (e.g. asking for 'a', then 'b') can see the full history.
        previous_turns = interaction_mgr.get_all_answered_for_step(
            workflow_id, f"step_{pause_step}"
        )
        user_responses_list = [
            {
                "content": r.response,
                "value": r.response,
                "request_id": r.request_id,
                "question": r.question,
                "step": pause_step
            }
            for r in previous_turns
        ]
        # The current interaction may already be in previous_turns if it was
        # marked 'completed' by complete_interaction() above; add it only if not.
        current_ids = {r.request_id for r in previous_turns}
        if interaction_request.request_id not in current_ids:
            user_responses_list.append({
                "content": interaction_request.response,
                "value": interaction_request.response,
                "request_id": interaction_request.request_id,
                "question": interaction_request.question,
                "step": pause_step
            })
        
        task = TaskRequest(
            capability=capability,
            parameters=enriched_parameters,
            context={
                "workflow_id": workflow_id,
                "step_number": pause_step,
                "step_id": f"step_{pause_step}",
                "agent_name": agent_name,
                "total_steps": len(plan['steps']),
                "workflow_context": workflow_context,
                "user_response": interaction_request.response,  # Keep for backwards compatibility
                "user_responses": user_responses_list,  # New format for AgentInteractionHelper
                "resuming_from_pause": True,
                "original_task": original_task,
                "previous_interactions": [
                    {
                        "question": interaction_request.question,
                        "response": interaction_request.response,
                        "step": pause_step
                    }
                ],
                "previous_step_results": workflow_context.get("step_results", {}),
                "step_results": workflow_context.get("step_results", {}),
                "capability_outputs": workflow_context.get("capability_outputs", {})
            }
        )
        
        # 7. Execute the step with user input
        print(f"      🔄 Re-sending task to {agent_name} with user input...")
        print(f"      📦 Context includes:")
        print(f"         - Original task: {original_task[:50]}...")
        print(f"         - User response: {interaction_request.response}")
        print(f"         - Step results: {list(workflow_context.get('step_results', {}).keys())}")
        print(f"         - Previous outputs: {list(workflow_context.get('capability_outputs', {}).keys())}")
        response = await registry_client.send_task(agent_endpoint, task)
        
        # 8. Check if it completed or needs more input
        if response.status == TaskStatus.COMPLETED and \
           isinstance(response.result, dict) and \
           response.result.get("status") == "user_input_required":
            # Agent needs MORE input - pause again
            print(f"      ⏸️  Agent needs additional input, pausing again...")
            return await _handle_additional_input_request(
                workflow_id, pause_step, response.result, 
                agent_name, agent_endpoint, plan, workflow_context, workflow_state
            )
        
        elif response.status == TaskStatus.COMPLETED:
            # Step completed successfully!
            print(f"      ✅ Step {pause_step} completed with user input")
            
            # Update workflow context
            workflow_context["step_results"][f"step_{pause_step}"] = {
                "description": description,
                "capability": capability,
                "result": response.result
            }
            workflow_context["capability_outputs"][capability] = response.result
            
            workflow_state["completed_steps"].append(pause_step)
            workflow_state["results"].append({
                "step": pause_step,
                "capability": capability,
                "agent": agent_name,
                "result": response.result,
                "description": description
            })
            
            # Unpause workflow
            workflow_state["paused"] = False
            workflow_state.pop("pending_interaction", None)
            workflow_state.pop("pause_step", None)
            
            # Notify WebSocket clients
            if ws_handler and ws_handler.connection_manager.has_connections(workflow_id):
                await ws_handler.connection_manager.broadcast_to_workflow(workflow_id, {
                    "type": "step_completed",
                    "workflow_id": workflow_id,
                    "step": {
                        "step_number": pause_step,
                        "capability": capability,
                        "description": description
                    },
                    "result": response.result,
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            # 9. Continue with remaining steps
            print(f"\n   ▶️  Continuing with remaining steps...")
            
            # Get agent capabilities once for all remaining steps
            # TODO: Consider storing agent assignments in workflow_state to avoid registry queries
            print(f"      🔍 Discovering available agents...")
            agents = await registry_client.get_all_agents()
            capabilities = {}
            for agent in agents:
                for cap in agent.capabilities:
                    if cap.name not in capabilities:
                        capabilities[cap.name] = []
                    capabilities[cap.name].append({
                        "agent_id": agent.agent_id,
                        "agent_name": agent.name,
                        "endpoint": agent.endpoint,
                        "description": cap.description
                    })
            print(f"      ✓ Found {len(capabilities)} capabilities from {len(agents)} agents")
            
            remaining_steps = plan['steps'][pause_step:]  # Continue from next step
            
            for step in remaining_steps:
                step_num = step.get("step_number", 0)
                
                # Check pause flag
                if workflow_state.get("paused", False):
                    print(f"⏸️  Workflow paused again at step {step_num}")
                    break
                
                capability = step.get("capability")
                parameters = step.get("parameters", {})
                description = step.get("description", "")
                
                print(f"\n   📌 Step {step_num}/{len(plan['steps'])}: {description}")
                print(f"      Capability: {capability}")
                
                # Find agent for this capability (using cached capabilities)
                if capability not in capabilities:
                    print(f"      ❌ No agent found for capability: {capability}")
                    continue
                
                agent_info = capabilities[capability][0]
                agent_endpoint = agent_info["endpoint"]
                agent_name = agent_info["agent_name"]
                
                # Enrich parameters
                enriched_parameters = await enrich_with_workflow_context(
                    capability=capability,
                    parameters=parameters,
                    workflow_context=workflow_context,
                    step_description=description
                )
                
                # Create and execute task
                task = TaskRequest(
                    capability=capability,
                    parameters=enriched_parameters,
                    context={
                        "workflow_id": workflow_id,
                        "step_number": step_num,
                        "step_id": f"step_{step_num}",
                        "agent_name": agent_name,
                        "total_steps": len(plan['steps']),
                        "workflow_context": workflow_context
                    }
                )
                
                print(f"      🔄 Sending task to {agent_name}...")
                response = await registry_client.send_task(agent_endpoint, task)
                
                # Check for user input request
                if response.status == TaskStatus.COMPLETED and \
                   isinstance(response.result, dict) and \
                   response.result.get("status") == "user_input_required":
                    return await _handle_additional_input_request(
                        workflow_id, step_num, response.result,
                        agent_name, agent_endpoint, plan, workflow_context, workflow_state
                    )
                
                elif response.status == TaskStatus.COMPLETED:
                    # Update context
                    workflow_context["step_results"][f"step_{step_num}"] = {
                        "description": description,
                        "capability": capability,
                        "result": response.result
                    }
                    workflow_context["capability_outputs"][capability] = response.result
                    
                    workflow_state["completed_steps"].append(step_num)
                    workflow_state["results"].append({
                        "step": step_num,
                        "capability": capability,
                        "agent": agent_name,
                        "result": response.result,
                        "description": description
                    })
                    
                    print(f"      ✅ Step {step_num} completed")
                    
                    # Notify WebSocket
                    if ws_handler and ws_handler.connection_manager.has_connections(workflow_id):
                        await ws_handler.connection_manager.broadcast_to_workflow(workflow_id, {
                            "type": "step_completed",
                            "workflow_id": workflow_id,
                            "step": {
                                "step_number": step_num,
                                "capability": capability,
                                "description": description
                            },
                            "result": response.result,
                            "timestamp": datetime.utcnow().isoformat()
                        })
            
            # Check if workflow paused again or completed
            if workflow_state.get("paused", False):
                # Save state and return pause status
                db.update_workflow_state(workflow_id, {
                    "status": "waiting_for_input",
                    "plan": plan,
                    "workflow_context": workflow_context,
                    "workflow_state": workflow_state,
                    "current_step": workflow_state["pause_step"]
                })
                
                return {
                    "workflow_id": workflow_id,
                    "status": "waiting_for_input",
                    "message": "Workflow paused again - awaiting additional input",
                    "interaction": workflow_state["pending_interaction"],
                    "steps_completed": len(workflow_state["completed_steps"]),
                    "total_steps": len(plan['steps'])
                }
            
            # Workflow completed!
            print(f"\n✅ WORKFLOW COMPLETED")
            workflow_state["status"] = "completed"
            workflow_state["end_time"] = datetime.utcnow().isoformat()
            
            # Update database
            db.update_workflow_state(workflow_id, {
                "status": "completed",
                "plan": plan,
                "workflow_context": workflow_context,
                "workflow_state": workflow_state
            })
            
            # Generate reflection
            reflection = await generate_reflection(
                task_description=workflow_context["original_task"],
                plan=plan,
                workflow_context=workflow_context,
                completed_steps=len(workflow_state["completed_steps"]),
                total_steps=len(plan['steps'])
            )
            
            result = {
                "workflow_id": workflow_id,
                "status": "completed",
                "steps_completed": len(workflow_state["completed_steps"]),
                "total_steps": len(plan['steps']),
                "results": workflow_state["results"],
                "workflow_context": workflow_context,
                "reflection": reflection,
                "success_rate": f"{len(workflow_state['completed_steps'])}/{len(plan['steps'])}"
            }
            
            # Save to session history if session_id exists
            if session_id:
                # Extract main result/summary
                final_output = ""
                # Try to get the result of the last step or report
                if workflow_state["results"]:
                    last_result = workflow_state["results"][-1]["result"]
                    if isinstance(last_result, dict) and "answer" in last_result:
                        final_output = last_result["answer"]
                    elif isinstance(last_result, dict) and "report" in last_result:
                         final_output = last_result["report"]
                    else:
                        final_output = str(last_result)
                
                history_item = {
                    "task": task_description,
                    "result": final_output,
                    "timestamp": datetime.utcnow().isoformat(),
                    "workflow_id": workflow_id
                }
                db.save_session_history(session_id, history_item)

                # Store in vector memory for long-term semantic recall
                if vector_memory.is_enabled:
                    await vector_memory.remember(
                        session_id=session_id,
                        text=f"Task: {task_description}\nResult: {final_output[:500]}",
                        metadata={
                            "task": task_description,
                            "result": final_output[:1000],
                            "result_summary": final_output[:400],
                            "workflow_id": workflow_id,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    )
                    print(f"   🧠 Stored workflow result in vector memory")
                
                # Get count for logging
                hist = db.get_session_history(session_id)
                print(f"   💾 Saved workflow result to session history ({len(hist)} items)")

            # Notify WebSocket
            if ws_handler and ws_handler.connection_manager.has_connections(workflow_id):
                await ws_handler.connection_manager.broadcast_to_workflow(workflow_id, {
                    "type": "workflow_completed",
                    "workflow_id": workflow_id,
                    "status": "completed",
                    "steps_completed": len(workflow_state["completed_steps"]),
                    "total_steps": len(plan['steps']),
                    "result": result,
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            return result
        
        else:
            # Step failed
            print(f"      ❌ Step {pause_step} failed: {response.error}")
            raise HTTPException(500, f"Step failed after user input: {response.error}")
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error resuming workflow: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to resume workflow: {str(e)}")


async def _handle_additional_input_request(
    workflow_id: str, step_num: int, interaction_data: dict,
    agent_name: str, agent_endpoint: str, plan: dict,
    workflow_context: dict, workflow_state: dict
) -> Dict[str, Any]:
    """Helper function to handle when agent requests additional input"""
    global interaction_mgr, db, ws_handler
    
    interaction_req = interaction_data.get("interaction_request", {})
    
    print(f"      ⏸️  Agent requesting additional input")
    print(f"      Question: {interaction_req.get('question', 'N/A')}")
    
    # Determine input type
    from models import InputType
    input_type_str = interaction_req.get("input_type", "text")
    if input_type_str == "single_choice":
        input_type = InputType.SINGLE_CHOICE
    elif input_type_str == "multiple_choice":
        input_type = InputType.MULTIPLE_CHOICE
    elif input_type_str == "confirmation":
        input_type = InputType.CONFIRMATION
    else:
        input_type = InputType.TEXT
    
    # Create interaction request
    merged_context = {"capability": plan['steps'][step_num-1].get("capability"), "step": step_num}
    agent_context = interaction_req.get("context", {})
    if isinstance(agent_context, dict):
        merged_context.update(agent_context)
    
    reasoning = interaction_req.get("reasoning", "")
    if not isinstance(reasoning, str):
        reasoning = str(reasoning) if reasoning else ""
    
    interaction_request = await interaction_mgr.request_user_input(
        workflow_id=workflow_id,
        step_id=f"step_{step_num}",
        agent_name=agent_name,
        question=interaction_req.get("question", "Additional input needed"),
        input_type=input_type,
        options=interaction_req.get("options"),
        context=merged_context,
        reasoning=reasoning
    )
    
    # Create interaction object
    interaction = {
        "request_id": interaction_request.request_id,
        "workflow_id": workflow_id,
        "step_number": step_num,
        "agent": agent_name,
        "capability": plan['steps'][step_num-1].get("capability"),
        "question": interaction_request.question,
        "reasoning": interaction_request.reasoning or "",
        "input_type": input_type_str,
        "options": interaction_request.options,
        "placeholder": interaction_req.get("placeholder", "Enter your response...")
    }
    
    # Save workflow state
    db.update_workflow_state(workflow_id, {
        "status": "waiting_for_input",
        "current_step": step_num,
        "plan": plan,
        "workflow_context": workflow_context,
        "workflow_state": workflow_state,
        "pending_interaction": interaction,
        "agent_endpoint": agent_endpoint,
        "agent_name": agent_name
    })
    
    # Notify WebSocket clients
    if ws_handler and ws_handler.connection_manager.has_connections(workflow_id):
        await ws_handler.connection_manager.broadcast_to_workflow(workflow_id, {
            "type": "user_input_required",
            "workflow_id": workflow_id,
            "interaction": interaction,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    # Mark workflow as paused
    workflow_state["paused"] = True
    workflow_state["pending_interaction"] = interaction
    workflow_state["pause_step"] = step_num
    workflow_state["agent_endpoint"] = agent_endpoint
    workflow_state["agent_name"] = agent_name
    
    return {
        "workflow_id": workflow_id,
        "status": "waiting_for_input",
        "request_id": interaction["request_id"],
        "message": "Workflow paused - awaiting user input",
        "interaction": interaction,
        "steps_completed": len(workflow_state["completed_steps"]),
        "current_step": step_num,
        "total_steps": len(plan['steps'])
    }


async def generate_dynamic_plan(
    task_description: str,
    capabilities: Dict[str, List[Dict]],
    capability_descriptions: Dict[str, str],
    session_history: List[Dict] = None,
    capability_schemas: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Generate a dynamic execution plan using the LLM.
    All routing decisions are driven by the live registry data (capability
    descriptions + input_schema) — no hardcoded routing logic here.
    """
    capability_schemas = capability_schemas or {}
    capabilities_list = list(capabilities.keys())

    # ── Session history ─────────────────────────────────────────────────
    history_str = ""
    if session_history:
        history_str = "\nPREVIOUS CONVERSATION HISTORY (use as context if relevant):\n"
        for i, entry in enumerate(session_history[-5:]):
            history_str += f"Turn {i+1} Task: {entry['task']}\n"
            result_preview = str(entry['result'])
            if len(result_preview) > 800:
                result_preview = result_preview[:800] + "...(truncated)"
            history_str += f"Turn {i+1} Result: {result_preview}\n\n"

    # ── Build capability documentation dynamically from registry data ────
    # Each capability self-describes its parameters and usage via input_schema
    # registered by the agent at startup — nothing is hardcoded here.
    def _build_cap_doc(cap_name: str) -> str:
        agents_for_cap = capabilities.get(cap_name, [])
        agent_name = agents_for_cap[0]["agent_name"] if agents_for_cap else "Unknown"
        description = capability_descriptions.get(cap_name, "")
        schema = capability_schemas.get(cap_name, {})
        lines = [f"- {cap_name} (handled by: {agent_name})"]
        lines.append(f"  Description: {description}")
        params = schema.get("parameters", {})
        if params:
            param_parts = []
            for pname, pmeta in params.items():
                req = "REQUIRED" if pmeta.get("required") else "optional"
                ptype = pmeta.get("type", "any")
                pdesc = pmeta.get("description", "")
                enum_vals = pmeta.get("enum")
                enum_str = f" — one of {enum_vals}" if enum_vals else ""
                param_parts.append(f"    {pname} ({req}, {ptype}{enum_str}): {pdesc}")
            lines.append("  Parameters:")
            lines.extend(param_parts)
        example = schema.get("example")
        if example:
            lines.append(f"  Usage example: {json.dumps(example)}")
        step_ref = schema.get("step_reference")
        if step_ref:
            lines.append(f"  Note: {step_ref}")
        return "\n".join(lines)

    capability_docs = "\n\n".join(_build_cap_doc(c) for c in capabilities_list)

    # ── Assemble planning prompt ─────────────────────────────────────────
    system_instruction = """\
You are an intelligent task orchestrator. Your job is to produce an optimal step-by-step \
execution plan for the user's task using ONLY the capabilities listed below.

RULES:
1. Use ONLY capabilities from the list. Never invent capability names.
2. Choose the capability whose description BEST matches what that step needs to accomplish. \
   Read each capability description carefully — they explicitly state what they should and \
   should not be used for.
3. Each step uses exactly ONE capability. Steps should chain logically.
4. Decompose compound tasks (joined by "then", "and then", "after") into separate steps.
5. When a step's input depends on an earlier step's output, reference it as \
   <result_from_step_N> in the parameter value (e.g. <result_from_step_1>).
6. For comparison workflows: research each concept first (separate steps), then compare.
7. For report workflows: gather all data first, then generate the report.
8. Set parameters to empty string / empty list when the orchestrator will inject prior \
   step results (this is noted in each capability's description).
9. Return ONLY valid JSON — no markdown, no code fences, no extra text.

RESPONSE FORMAT:
{
  "steps": [
    {
      "step_number": 1,
      "capability": "capability_name",
      "description": "Clear description of what this step does",
      "parameters": {"key": "value"},
      "expected_output": "What this step produces",
      "depends_on": []
    }
  ],
  "reasoning": "Brief explanation of why this plan structure was chosen"
}"""

    user_message = f"USER TASK:\n{task_description}\n"
    if history_str:
        user_message += history_str
    user_message += f"\nAVAILABLE CAPABILITIES (registered by live agents):\n\n{capability_docs}\n\nGenerate the execution plan JSON."

    print(f"   Calling Bedrock with model: {BEDROCK_MODEL_ID}")
    print(f"   Temperature: 0.1 (low for structured output)")
    if session_history:
        print(f"   Generating plan with {len(session_history)} history items")

    try:
        response = bedrock_client.converse(
            modelId=BEDROCK_MODEL_ID,
            system=[{"text": system_instruction}],
            messages=[{"role": "user", "content": [{"text": user_message}]}],
            inferenceConfig={"maxTokens": 4000, "temperature": 0.1}
        )
        
        content = response['output']['message']['content'][0]['text']
        print(f"   ✓ LLM Response received ({len(content)} characters)")
        
        # Clean up response - remove markdown code blocks and extra text
        content = content.strip()
        
        # Remove markdown code fences
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        # Try to extract JSON if there's extra text
        if not content.startswith("{"):
            # Find first { and last }
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                content = content[start:end+1]
        
        print(f"   Parsing JSON response...")
        
        try:
            plan = json.loads(content)

            # Normalise nested {"plan": {"steps": [...]}} structure that some
            # LLM responses return instead of the expected top-level {"steps": [...]}
            if "plan" in plan and isinstance(plan["plan"], dict):
                inner = plan["plan"]
                plan = {
                    "steps": inner.get("steps", []),
                    "reasoning": inner.get("description") or inner.get("name") or inner.get("purpose") or ""
                }

            # Normalise step fields: "action" → "capability", "id" → step_number placeholder
            for step in plan.get("steps", []):
                if "capability" not in step and "action" in step:
                    step["capability"] = step.pop("action")

            # Validate plan structure
            if "steps" not in plan or not isinstance(plan["steps"], list) or len(plan["steps"]) == 0:
                print(f"   ⚠️  Invalid plan structure - missing or empty steps")
                print(f"   Plan content: {plan}")
                plan = create_intelligent_default_plan(task_description, capabilities_list)
            else:
                # Validate each step has required fields
                valid_steps = []
                for i, step in enumerate(plan["steps"], 1):
                    if "capability" in step and "description" in step:
                        if "step_number" not in step:
                            step["step_number"] = i
                        if "parameters" not in step:
                            step["parameters"] = {}
                        if "expected_output" not in step:
                            step["expected_output"] = "Result"
                        if "depends_on" not in step:
                            step["depends_on"] = []
                        valid_steps.append(step)
                
                if len(valid_steps) == 0:
                    print(f"   ⚠️  No valid steps found in plan")
                    plan = create_intelligent_default_plan(task_description, capabilities_list)
                else:
                    plan["steps"] = valid_steps
                    print(f"   ✓ Valid plan with {len(valid_steps)} steps")
                    
                    # Log the plan details
                    for step in valid_steps:
                        print(f"      - Step {step['step_number']}: {step['capability']} - {step['description']}")
            
            return plan
            
        except json.JSONDecodeError as e:
            print(f"   ⚠️  Failed to parse LLM response as JSON: {e}")
            print(f"   Response preview: {content[:300]}...")
            print(f"   Creating intelligent default plan instead")
            return create_intelligent_default_plan(task_description, capabilities_list)
    
    except Exception as e:
        print(f"   ❌ Bedrock API error: {e}")
        import traceback
        traceback.print_exc()
        print(f"   Creating intelligent default plan instead")
        return create_intelligent_default_plan(task_description, capabilities_list)


def create_intelligent_default_plan(task_description: str, capabilities: List[str]) -> Dict[str, Any]:
    """Minimal fallback plan used only when the LLM planner fails entirely.

    Creates a single best-effort step.  Do NOT add keyword-based routing logic
    here — all routing decisions are the LLM's responsibility, driven by the
    capability descriptions that each agent registers in the service registry.
    """
    print("   ⚠️  LLM planner failed; creating minimal fallback plan")
    fallback_cap = next(
        (c for c in ["answer_question", "analyze_data"] if c in capabilities),
        capabilities[0] if capabilities else "answer_question",
    )
    params: Dict[str, Any] = (
        {"question": task_description}
        if fallback_cap == "answer_question"
        else {"data": task_description}
    )
    return {
        "steps": [
            {
                "step_number": 1,
                "capability": fallback_cap,
                "description": f"Execute: {task_description}",
                "parameters": params,
                "expected_output": "Result",
                "depends_on": [],
            }
        ],
        "reasoning": "Minimal fallback plan — LLM planner unavailable",
    }


def create_default_plan(task_description: str, capabilities: List[str]) -> Dict[str, Any]:
    """Thin compatibility shim — delegates to create_intelligent_default_plan."""
    return create_intelligent_default_plan(task_description, capabilities)


# NOTE: _fix_math_routing and the old keyword-matching create_intelligent_default_plan
# have been removed.  Routing is entirely driven by the LLM using capability
# descriptions + input_schema from the agent registry.


async def generate_reflection(
    task_description: str,
    plan: Dict[str, Any],
    workflow_context: Dict[str, Any],
    completed_steps: int,
    total_steps: int
) -> Dict[str, Any]:
    """
    Generate reflection on workflow execution using LLM.
    Analyzes what worked, what didn't, and suggests improvements.
    """
    
    success_rate = f"{completed_steps}/{total_steps}" if total_steps > 0 else "0/0"
    success_percentage = (completed_steps / total_steps * 100) if total_steps > 0 else 0
    
    step_results_summary = []
    for step_key, step_data in workflow_context.get("step_results", {}).items():
        step_results_summary.append({
            "step": step_key,
            "capability": step_data.get("capability"),
            "description": step_data.get("description"),
            "result_length": len(str(step_data.get("result", "")))
        })
    
    
    system_instruction = f"""You are reflecting on a multi-agent workflow execution. Analyze the execution and provide a structured reflection.

Return JSON format:
{{
  "summary": "2-3 sentence summary of execution",
  "success_rate": "{success_rate}",
  "success_percentage": {success_percentage:.1f},
  "strengths": ["what worked well"],
  "weaknesses": ["what didn't work"],
  "suggestions": ["how to improve"],
  "overall_assessment": "excellent|good|fair|poor"
}}"""

    user_context = f"""ORIGINAL TASK:
{task_description}

EXECUTION PLAN:
{json.dumps(plan, indent=2)}

EXECUTION RESULTS:
- Steps Completed: {completed_steps} / {total_steps}
- Success Rate: {success_percentage:.1f}%

STEP OUTCOMES:
{json.dumps(step_results_summary, indent=2)}

ANALYZE:
1. Was the plan appropriate for the task?
2. Did steps execute in the right order?
3. Was context properly shared between steps?
4. Were any steps unnecessary or missing?
5. What could be improved?"""
    
    try:
        response = bedrock_client.converse(
            modelId=BEDROCK_MODEL_ID,
            system=[{"text": system_instruction}],
            messages=[{"role": "user", "content": [{"text": user_context}]}],
            inferenceConfig={"maxTokens": 2000, "temperature": 0.5}
        )
        
        content = response['output']['message']['content'][0]['text']
        content = content.strip()
        
        # Clean markdown
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        reflection = json.loads(content)
        return reflection
        
    except Exception as e:
        print(f"   ⚠️  Reflection generation failed: {e}")
        return {
            "summary": f"Completed {completed_steps} of {total_steps} steps",
            "success_rate": success_rate,
            "success_percentage": success_percentage,
            "strengths": ["Execution attempted"],
            "weaknesses": ["Could not generate detailed reflection"],
            "suggestions": ["Review logs for details"],
            "overall_assessment": "good" if success_percentage > 50 else "fair"
        }


@app.get("/api/workflow/{workflow_id}")
async def get_workflow(workflow_id: str):
    """Get workflow status"""
    state = await dist_state.get_workflow_state(workflow_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return state


@app.get("/api/agents")
async def list_agents():
    """List all registered agents"""
    agents = await registry_client.get_all_agents()
    return {
        "total": len(agents),
        "agents": [
            {
                "agent_id": agent.agent_id,
                "name": agent.name,
                "role": agent.role.value,
                "capabilities": [c.name for c in agent.capabilities],
                "endpoint": agent.endpoint
            }
            for agent in agents
        ]
    }


@app.websocket("/ws/workflow/{workflow_id}")
async def websocket_endpoint(websocket: WebSocket, workflow_id: str):
    """
    WebSocket endpoint for real-time workflow interaction
    
    Enables bidirectional communication:
    - Client receives real-time updates (step progress, interaction requests, etc.)
    - Client can send responses to interaction requests
    - Client can query status and conversation history
    
    Message types from server:
    - connection_established: Welcome message
    - workflow_status: Current workflow state
    - step_started: A step has started
    - step_completed: A step has completed
    - user_input_required: Agent needs user input
    - response_received: User response acknowledged
    - workflow_resuming: Workflow is resuming after user input
    - workflow_completed: Workflow finished
    - error: Error occurred
    - pong: Response to ping
    
    Message types from client:
    - ping: Keep-alive
    - get_status: Request current workflow status
    - get_conversation: Request conversation history
    - user_response: Submit response to interaction request
      {
        "type": "user_response",
        "request_id": "req_123",
        "response": "user's answer",
        "additional_context": {} (optional)
      }
    - cancel_workflow: Cancel workflow execution
    """
    if not ws_handler:
        await websocket.close(code=1011, reason="WebSocket handler not initialized")
        return

    # HA: subscribe to pub/sub so this replica receives events published by
    # whichever replica is currently executing the workflow.
    await dist_state.subscribe_local_websocket(workflow_id, ws_handler.connection_manager)
    try:
        await ws_handler.handle_connection(websocket, workflow_id)
    finally:
        await dist_state.pubsub.unsubscribe(workflow_id)


@app.post("/api/workflow/{workflow_id}/respond")
async def respond_to_interaction(workflow_id: str, response: Dict[str, Any]):
    """
    REST endpoint for responding to interaction requests (alternative to WebSocket)
    
    Request body:
    {
        "request_id": "req_123",
        "response": "user's answer",
        "additional_context": {} (optional)
    }
    """
    if not ws_handler:
        raise HTTPException(status_code=503, detail="WebSocket handler not initialized")
    
    request_id = response.get("request_id")
    user_response = response.get("response")
    additional_context = response.get("additional_context")
    
    print(f"\n📨 RECEIVED RESPONSE:")
    print(f"   Workflow ID: {workflow_id}")
    print(f"   Request ID: {request_id}")
    print(f"   Response: {user_response}")
    
    if not request_id or user_response is None:
        raise HTTPException(status_code=400, detail="request_id and response required")
    
    # Submit response
    print(f"   Submitting response to interaction manager...")
    success = await ws_handler.interaction_manager.submit_response(
        request_id=request_id,
        response=user_response,
        additional_context=additional_context
    )
    
    print(f"   Submit result: {success}")
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to submit response")
    
    # Notify via WebSocket if connected
    if ws_handler.connection_manager.has_connections(workflow_id):
        await ws_handler.connection_manager.broadcast_to_workflow(workflow_id, {
            "type": "response_received",
            "request_id": request_id,
            "response": user_response,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    # Resume workflow
    asyncio.create_task(ws_handler._resume_workflow(workflow_id))
    
    return {
        "success": True,
        "message": "Response submitted, workflow resuming"
    }


@app.get("/api/workflow/{workflow_id}/status")
async def get_workflow_status(workflow_id: str):
    """
    Get the current status of a workflow
    
    Returns:
    {
        "workflow_id": "...",
        "status": "running|paused|completed|failed",
        "current_step": 2,
        "total_steps": 5,
        "pending_interactions": [...],
        "results": [...]
    }
    """
    from database import WorkflowDatabase
    
    if not ws_handler:
        raise HTTPException(status_code=503, detail="WebSocket handler not initialized")
    
    # Try to get workflow from database first
    db = WorkflowDatabase()
    workflow = db.get_workflow(workflow_id)
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # Get pending interaction requests
    pending = ws_handler.interaction_manager.get_pending_requests(workflow_id)
    
    return {
        "workflow_id": workflow_id,
        "status": workflow.status.value if isinstance(workflow.status, WorkflowStatus) else workflow.status,
        "current_step": workflow.current_step,
        "total_steps": workflow.total_steps,
        "pending_interactions": pending,
        "results": workflow.results,
        "start_time": workflow.started_at.isoformat() if workflow.started_at else None,
        "last_update": workflow.updated_at.isoformat() if workflow.updated_at else None,
        "workflow_context": workflow.workflow_context
    }


@app.get("/api/workflow/{workflow_id}/conversation")
async def get_conversation(workflow_id: str):
    """Get conversation history for a workflow"""
    from conversation import ConversationManager
    from database import WorkflowDatabase
    
    db = WorkflowDatabase()
    conversation_mgr = ConversationManager(db)
    history = conversation_mgr.get_conversation_history(workflow_id)
    
    return {
        "workflow_id": workflow_id,
        "conversation": history
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=ORCHESTRATOR_PORT, log_level="info")
