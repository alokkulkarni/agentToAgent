"""
Research Agent - Standalone Service
Performs research and information gathering using AWS Bedrock
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio
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
AGENT_NAME = os.getenv("AGENT_NAME", "ResearchAgent")
AGENT_PORT = int(os.getenv("AGENT_PORT", "8003"))
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://localhost:8000")
AWS_REGION = os.getenv("AWS_REGION", "eu-west-2")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")

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
                name="answer_question",
                description="Answer questions using LLM knowledge",
                requires_llm=True
            ),
            AgentCapability(
                name="generate_report",
                description="Generate detailed reports on topics",
                requires_llm=True
            ),
            AgentCapability(
                name="compare_concepts",
                description="Compare and contrast concepts",
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
    print(f"Starting {AGENT_NAME} Agent Service...")
    init_bedrock()
    await register_with_registry()
    yield
    print(f"Shutting down {AGENT_NAME} Agent Service...")
    await unregister_from_registry()


app = FastAPI(
    title=f"{AGENT_NAME} Agent Service",
    description="Research Agent for A2A System",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    return {
        "service": f"{AGENT_NAME} Agent",
        "agent_id": agent_id,
        "role": "specialized",
        "status": "running"
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "agent_id": agent_id,
        "capabilities": [c.name for c in agent_metadata.capabilities]
    }


@app.get("/api/capabilities")
async def get_capabilities():
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
        if task.capability == "answer_question":
            result = await answer_question(task.parameters)
        elif task.capability == "generate_report":
            result = await generate_report(task.parameters)
        elif task.capability == "compare_concepts":
            result = await compare_concepts(task.parameters)
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


async def answer_question(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Answer a question using LLM"""
    question = parameters.get("question")
    if not question:
        raise ValueError("question parameter is required")
    
    context = parameters.get("context", "")
    prompt = f"{context}\n\nQuestion: {question}" if context else question
    
    response = bedrock_client.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 2000, "temperature": 0.7}
    )
    
    answer = response['output']['message']['content'][0]['text']
    
    return {
        "question": question,
        "answer": answer,
        "llm_usage": {
            "input_tokens": response['usage'].get('inputTokens', 0),
            "output_tokens": response['usage'].get('outputTokens', 0)
        }
    }


async def generate_report(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a detailed report"""
    topic = parameters.get("topic")
    if not topic:
        raise ValueError("topic parameter is required")
    
    aspects = parameters.get("aspects", [])
    aspects_str = ", ".join(aspects) if aspects else "all relevant aspects"
    
    prompt = f"""Generate a comprehensive report on: {topic}

Include {aspects_str}.

Structure the report with:
1. Executive Summary
2. Key Findings
3. Detailed Analysis
4. Conclusions and Recommendations

Make it detailed and well-researched."""
    
    response = bedrock_client.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 4000, "temperature": 0.7}
    )
    
    report = response['output']['message']['content'][0]['text']
    
    return {
        "topic": topic,
        "report": report,
        "llm_usage": {
            "input_tokens": response['usage'].get('inputTokens', 0),
            "output_tokens": response['usage'].get('outputTokens', 0)
        }
    }


async def compare_concepts(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Compare and contrast concepts"""
    concept_a = parameters.get("concept_a")
    concept_b = parameters.get("concept_b")
    
    if not concept_a or not concept_b:
        raise ValueError("Both concept_a and concept_b are required")
    
    prompt = f"""Compare and contrast {concept_a} and {concept_b}.

Provide:
1. Similarities
2. Differences
3. Use cases for each
4. Pros and cons
5. Which to choose when

Be thorough and objective."""
    
    response = bedrock_client.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 2500, "temperature": 0.7}
    )
    
    comparison = response['output']['message']['content'][0]['text']
    
    return {
        "concept_a": concept_a,
        "concept_b": concept_b,
        "comparison": comparison,
        "llm_usage": {
            "input_tokens": response['usage'].get('inputTokens', 0),
            "output_tokens": response['usage'].get('outputTokens', 0)
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT, log_level="info")
