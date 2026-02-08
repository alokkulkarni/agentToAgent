"""
Code Analyzer Agent - Standalone Service
Analyzes and explains Python code using AWS Bedrock
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

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

load_dotenv()

# Configuration
AGENT_NAME = os.getenv("AGENT_NAME", "CodeAnalyzer")
AGENT_PORT = int(os.getenv("AGENT_PORT", "8001"))
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
                description="Analyze Python code structure with AST",
                requires_llm=False
            ),
            AgentCapability(
                name="explain_code",
                description="Explain code functionality using LLM",
                requires_llm=True
            ),
            AgentCapability(
                name="suggest_improvements",
                description="Suggest code improvements using LLM",
                requires_llm=True
            )
        ],
        has_llm=True,
        endpoint=f"http://localhost:{AGENT_PORT}"
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
    """Suggest code improvements using LLM"""
    code = parameters.get("code")
    if not code:
        raise ValueError("code parameter is required")
    
    prompt = f"""Review this code and suggest improvements for:
1. Code quality and readability
2. Performance optimization
3. Best practices
4. Potential bugs

Code:
{code}

Provide specific, actionable suggestions."""
    
    response = bedrock_client.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 2000, "temperature": 0.7}
    )
    
    suggestions = response['output']['message']['content'][0]['text']
    
    return {
        "code": code,
        "suggestions": suggestions,
        "llm_usage": {
            "input_tokens": response['usage'].get('inputTokens', 0),
            "output_tokens": response['usage'].get('outputTokens', 0)
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT, log_level="info")
