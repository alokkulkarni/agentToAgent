"""
Code Analyzer Agent - Standalone Service
Analyzes and explains Python code using AWS Bedrock
"""
import os

from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
import asyncio
import ast
from typing import Dict, Any
import boto3
from dotenv import load_dotenv

from shared.a2a_protocol import (
    AgentMetadata, AgentRole, AgentCapability,
    TaskRequest, TaskResponse, TaskStatus,
    A2AClient
)
from shared.agent_interaction import (
    AgentInteractionHelper,
    is_interaction_request
)

load_dotenv()

# Configuration
AGENT_NAME = os.getenv("AGENT_NAME", "CodeAnalyzer")
AGENT_PORT = int(os.getenv("AGENT_PORT", "8001"))
AGENT_HOST = os.getenv("AGENT_HOST", "localhost")
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://localhost:8000")
AWS_REGION = os.getenv("AWS_REGION", "eu-west-2")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")

# Agent metadata
agent_id = None
agent_metadata = None
registry_client = None
bedrock_client = None


async def register_with_registry():
    """Register this agent with the registry"""
    global agent_id, agent_metadata, registry_client
    
    agent_metadata = AgentMetadata(
        name=AGENT_NAME,
        role=AgentRole.SPECIALIZED,
        capabilities=[
            AgentCapability(
                name="analyze_python_code",
                description="Statically analyze Python code using AST: extract classes, functions, imports, complexity metrics.",
                requires_llm=False,
                input_schema={
                    "parameters": {
                        "code": {"type": "string", "required": True, "description": "Python source code to analyze"}
                    },
                    "example": {"code": "def hello():\n    print('hello')"}
                }
            ),
            AgentCapability(
                name="explain_code",
                description="Explain what a piece of code does in plain English using LLM.",
                requires_llm=True,
                input_schema={
                    "parameters": {
                        "code": {"type": "string", "required": True, "description": "Source code to explain"}
                    },
                    "example": {"code": "for i in range(10): print(i)"}
                }
            ),
            AgentCapability(
                name="suggest_improvements",
                description="Suggest refactoring and quality improvements for a piece of code using LLM.",
                requires_llm=True,
                input_schema={
                    "parameters": {
                        "code": {"type": "string", "required": True, "description": "Source code to improve"}
                    },
                    "example": {"code": "x = []; \nfor i in range(10): x.append(i*i)"}
                }
            )
        ],
        has_llm=True,
        endpoint=f"http://{AGENT_HOST}:{AGENT_PORT}"
    )
    
    registry_client = A2AClient(REGISTRY_URL)
    
    try:
        response = await registry_client.register_agent(agent_metadata)
        agent_id = response.agent_id
        print(f"✓ Registered with registry: {agent_id}")
        
        # Start heartbeat
        asyncio.create_task(send_heartbeats())
        
    except Exception as e:
        print(f"✗ Failed to register with registry: {e}")
        raise


async def send_heartbeats():
    """Send periodic heartbeats to registry"""
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
    # Startup
    print(f"Starting {AGENT_NAME} Agent Service...")
    init_bedrock()
    await register_with_registry()
    yield
    # Shutdown
    print(f"Shutting down {AGENT_NAME} Agent Service...")
    await unregister_from_registry()


app = FastAPI(
    title=f"{AGENT_NAME} Agent Service",
    description="Code Analysis Agent for A2A System",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": f"{AGENT_NAME} Agent",
        "agent_id": agent_id,
        "role": "specialized",
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "agent_id": agent_id,
        "capabilities": [c.name for c in agent_metadata.capabilities]
    }


@app.get("/api/capabilities")
async def get_capabilities():
    """Get agent capabilities"""
    return {
        "agent_id": agent_id,
        "capabilities": [c.model_dump() for c in agent_metadata.capabilities]
    }


@app.post("/api/task")
async def execute_task(task: TaskRequest) -> TaskResponse:
    """Execute a task"""
    print(f"Executing task: {task.task_id} - {task.capability}")
    
    # Inject context into parameters to ensure AgentInteractionHelper works correctly
    if task.context:
        task.parameters["context"] = task.context
    
    from datetime import datetime
    start_time = datetime.utcnow()
    
    try:
        if task.capability == "analyze_python_code":
            result = await analyze_python_code(task.parameters)
        elif task.capability == "explain_code":
            result = await explain_code(task.parameters)
        elif task.capability == "suggest_improvements":
            result = await suggest_improvements(task.parameters)
        else:
            raise ValueError(f"Unknown capability: {task.capability}")
        
        execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        return TaskResponse(
            task_id=task.task_id,
            status=TaskStatus.COMPLETED,
            result=result,
            execution_time_ms=execution_time,
            agent_id=agent_id
        )
        
    except Exception as e:
        return TaskResponse(
            task_id=task.task_id,
            status=TaskStatus.FAILED,
            error=str(e),
            agent_id=agent_id
        )


async def analyze_python_code(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze Python code structure"""
    code = parameters.get("code")
    if not code:
        raise ValueError("code parameter is required")
    
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {"error": f"Syntax error: {str(e)}"}
    
    classes = []
    functions = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
            classes.append({"name": node.name, "line": node.lineno, "methods": methods})
        elif isinstance(node, ast.FunctionDef) and node.col_offset == 0:
            functions.append({
                "name": node.name,
                "line": node.lineno,
                "args": [arg.arg for arg in node.args.args]
            })
    
    return {
        "total_lines": len(code.split('\n')),
        "classes": classes,
        "functions": functions,
        "class_count": len(classes),
        "function_count": len(functions)
    }


async def explain_code(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Explain code using LLM"""
    code = parameters.get("code")
    if not code:
        raise ValueError("code parameter is required")
    
    prompt = f"""Explain what this code does in clear, simple terms.

Code:
{code}

Provide:
1. Overall purpose
2. Key functions/classes
3. Main logic flow"""
    
    response = bedrock_client.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 2000, "temperature": 0.7}
    )
    
    explanation = response['output']['message']['content'][0]['text']
    
    return {
        "code": code,
        "explanation": explanation,
        "llm_usage": {
            "input_tokens": response['usage'].get('inputTokens', 0),
            "output_tokens": response['usage'].get('outputTokens', 0)
        }
    }


async def suggest_improvements(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Suggest code improvements using LLM
    
    ENHANCED: Now supports interactive workflow - can ask user for guidance
    when multiple issues are found
    """
    code = parameters.get("code")
    if not code:
        raise ValueError("code parameter is required")
    
    # Create interaction helper to check for user responses and request input if needed
    # Note: We need the full task_request for context, so we pass parameters as-is
    helper = AgentInteractionHelper(parameters)
    
    # First, analyze to find issues
    analysis_prompt = f"""Analyze this code and identify all issues. Categorize them as:
- CRITICAL: Security vulnerabilities, data loss risks, crashes
- HIGH: Performance issues, memory leaks, race conditions
- MEDIUM: Code quality, maintainability issues
- LOW: Style issues, minor improvements

Code:
{code}

For each issue, provide:
1. Severity level
2. Description
3. Suggested fix

Format as JSON array."""
    
    response = bedrock_client.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": analysis_prompt}]}],
        inferenceConfig={"maxTokens": 3000, "temperature": 0.3}
    )
    
    analysis = response['output']['message']['content'][0]['text']
    
    # Try to parse issues (simple count for now)
    # In production, you'd parse the JSON response
    issue_count = analysis.count("CRITICAL") + analysis.count("HIGH") + analysis.count("MEDIUM")
    critical_count = analysis.count("CRITICAL")
    high_count = analysis.count("HIGH")
    medium_count = analysis.count("MEDIUM")
    
    # INTERACTIVE WORKFLOW: If many issues found, ask user for guidance
    if issue_count > 5 and not helper.has_user_response():
        # Store partial analysis
        partial_results = {
            "analysis": analysis,
            "issue_count": issue_count,
            "critical": critical_count,
            "high": high_count,
            "medium": medium_count
        }
        
        # Ask user how to proceed
        return helper.ask_single_choice(
            question=f"Found {issue_count} issues ({critical_count} critical, {high_count} high, {medium_count} medium). How should I proceed?",
            options=[
                "Fix all issues automatically",
                "Fix only critical and high priority issues",
                "Show me detailed analysis first (no fixes)",
                "Let me review and decide on each issue"
            ],
            reasoning=f"Multiple issues detected. Automatic fixing of all {issue_count} issues could introduce unintended changes. User guidance recommended.",
            partial_results=partial_results
        )
    
    # Check if user provided guidance
    user_choice = helper.get_user_response()
    
    if user_choice:
        print(f"✓ User chose: {user_choice}")
        
        # Adjust our approach based on user's choice
        if "Show me detailed analysis" in user_choice:
            # Just return the analysis, don't fix
            return {
                "code": code,
                "analysis": analysis,
                "issue_summary": {
                    "total": issue_count,
                    "critical": critical_count,
                    "high": high_count,
                    "medium": medium_count
                },
                "action_taken": "analysis_only",
                "user_choice": user_choice,
                "llm_usage": {
                    "input_tokens": response['usage'].get('inputTokens', 0),
                    "output_tokens": response['usage'].get('outputTokens', 0)
                }
            }
        
        elif "critical and high" in user_choice:
            filter_instruction = "Focus ONLY on CRITICAL and HIGH priority issues. Ignore MEDIUM and LOW."
        
        elif "review and decide" in user_choice:
            # Return analysis with option for user to come back with specific issues to fix
            return {
                "code": code,
                "analysis": analysis,
                "issue_summary": {
                    "total": issue_count,
                    "critical": critical_count,
                    "high": high_count,
                    "medium": medium_count
                },
                "action_taken": "awaiting_specific_instructions",
                "user_choice": user_choice,
                "next_step": "Please specify which issues to fix, or submit a new task with specific instructions",
                "llm_usage": {
                    "input_tokens": response['usage'].get('inputTokens', 0),
                    "output_tokens": response['usage'].get('outputTokens', 0)
                }
            }
        
        else:  # "Fix all issues"
            filter_instruction = "Address all identified issues."
    else:
        # No user input needed/provided, proceed with all issues
        filter_instruction = "Address all identified issues."
    
    # Generate improvements based on user's choice or default
    improvement_prompt = f"""Based on this analysis, provide specific code improvements.

{filter_instruction}

Analysis:
{analysis}

Original Code:
{code}

Provide:
1. Improved code with fixes applied
2. Summary of changes made
3. Explanation of each fix"""
    
    improvement_response = bedrock_client.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": improvement_prompt}]}],
        inferenceConfig={"maxTokens": 3000, "temperature": 0.5}
    )
    
    suggestions = improvement_response['output']['message']['content'][0]['text']
    
    return {
        "code": code,
        "analysis": analysis,
        "suggestions": suggestions,
        "issue_summary": {
            "total": issue_count,
            "critical": critical_count,
            "high": high_count,
            "medium": medium_count
        },
        "user_choice": user_choice if user_choice else "default (all issues)",
        "llm_usage": {
            "input_tokens": response['usage'].get('inputTokens', 0) + improvement_response['usage'].get('inputTokens', 0),
            "output_tokens": response['usage'].get('outputTokens', 0) + improvement_response['usage'].get('outputTokens', 0)
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT, log_level="info")
