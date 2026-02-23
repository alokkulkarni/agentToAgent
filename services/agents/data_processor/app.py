"""
Data Processor Agent - Standalone Service
Processes and analyzes data using AWS Bedrock
"""
import os

from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio
import json
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
AGENT_NAME = os.getenv("AGENT_NAME", "DataProcessor")
AGENT_PORT = int(os.getenv("AGENT_PORT", "8002"))
AGENT_HOST = os.getenv("AGENT_HOST", "localhost")
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
                name="transform_data",
                description="Transform data between formats"
            ),
            AgentCapability(
                name="analyze_data",
                description="Analyze data and extract insights using LLM",
                requires_llm=True
            ),
            AgentCapability(
                name="summarize_data",
                description="Summarize large datasets using LLM",
                requires_llm=True
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
    description="Data Processing Agent for A2A System",
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
    
    # Inject context into parameters to ensure AgentInteractionHelper works correctly
    if task.context:
        task.parameters["context"] = task.context
    
    from datetime import datetime
    start_time = datetime.utcnow()
    
    try:
        if task.capability == "transform_data":
            result = await transform_data(task.parameters)
        elif task.capability == "analyze_data":
            result = await analyze_data(task.parameters)
        elif task.capability == "summarize_data":
            result = await summarize_data(task.parameters)
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


async def transform_data(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Transform data between formats"""
    data = parameters.get("data")
    from_format = parameters.get("from_format", "json")
    to_format = parameters.get("to_format", "json")
    
    if from_format == "json" and to_format == "dict":
        if isinstance(data, str):
            result = json.loads(data)
        else:
            result = data
    elif from_format == "dict" and to_format == "json":
        result = json.dumps(data, indent=2)
    else:
        result = data
    
    return {"transformed_data": result, "from": from_format, "to": to_format}


async def analyze_data(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze data using LLM
    
    ENHANCED: Now supports interactive workflow - can ask user for clarification
    when data issues or ambiguities are detected
    """
    data = parameters.get("data")
    if not data:
        raise ValueError("data parameter is required")
    
    # Create interaction helper
    helper = AgentInteractionHelper(parameters)
    
    data_str = json.dumps(data, indent=2) if isinstance(data, dict) else str(data)
    
    # First, do preliminary analysis to detect issues
    preliminary_prompt = f"""Examine this data and identify:
1. Data quality issues (missing values, outliers, inconsistencies)
2. Potential ambiguities in interpretation
3. Whether additional context is needed for proper analysis

Data:
{data_str}

Respond with JSON containing:
- has_issues: boolean
- issues: list of issues found
- needs_clarification: boolean
- clarification_questions: list of questions if clarification needed"""
    
    prelim_response = bedrock_client.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": preliminary_prompt}]}],
        inferenceConfig={"maxTokens": 1000, "temperature": 0.3}
    )
    
    prelim_analysis = prelim_response['output']['message']['content'][0]['text']
    
    # Check if data has significant issues or ambiguities
    has_issues = "has_issues\": true" in prelim_analysis or "has_issues\":true" in prelim_analysis
    needs_clarification = "needs_clarification\": true" in prelim_analysis or "needs_clarification\":true" in prelim_analysis
    
    # INTERACTIVE WORKFLOW: Ask user for clarification if needed
    if (has_issues or needs_clarification) and not helper.has_user_response():
        # Extract specific questions (simplified - in production parse JSON properly)
        return helper.ask_single_choice(
            question="I've detected some issues with the data. How would you like me to proceed?",
            options=[
                "Proceed with analysis despite issues",
                "Exclude problematic data points and analyze the rest",
                "Show me the issues first before proceeding",
                "Provide additional context to help with interpretation"
            ],
            reasoning=f"Data quality issues or ambiguities detected: {prelim_analysis[:200]}...",
            partial_results={"preliminary_analysis": prelim_analysis}
        )
    
    # Check if user provided guidance
    user_choice = helper.get_user_response()
    
    if user_choice:
        print(f"✓ User chose: {user_choice}")
        
        if "Show me the issues" in user_choice:
            # Return preliminary analysis
            return {
                "data": data,
                "preliminary_analysis": prelim_analysis,
                "action_taken": "showing_issues",
                "user_choice": user_choice,
                "next_step": "Please review and provide further instructions",
                "llm_usage": {
                    "input_tokens": prelim_response['usage'].get('inputTokens', 0),
                    "output_tokens": prelim_response['usage'].get('outputTokens', 0)
                }
            }
        
        elif "additional context" in user_choice:
            # Ask for context
            return helper.ask_text(
                question="Please provide additional context to help with data interpretation:",
                reasoning="Additional context will improve analysis accuracy",
                placeholder="E.g., data source, time period, units of measurement, etc.",
                partial_results={"preliminary_analysis": prelim_analysis}
            )
        
        elif "Exclude problematic" in user_choice:
            analysis_instruction = "Exclude any problematic or ambiguous data points and analyze only the clean, reliable data."
        else:
            analysis_instruction = "Proceed with analysis, noting any limitations due to data quality issues."
    else:
        analysis_instruction = "Analyze the data as-is, noting any data quality concerns."
    
    # Additional context from user (if they provided it in a text response)
    user_context = ""
    if user_choice and isinstance(user_choice, str) and len(user_choice) > 50:
        user_context = f"\n\nUser provided context: {user_choice}"
    
    # Perform full analysis
    prompt = f"""Analyze this data and provide:
1. Key patterns and trends
2. Statistical insights
3. Anomalies or interesting observations
4. Actionable recommendations

{analysis_instruction}
{user_context}

Data:
{data_str}"""
    
    response = bedrock_client.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 2000, "temperature": 0.7}
    )
    
    analysis = response['output']['message']['content'][0]['text']
    
    return {
        "data": data,
        "analysis": analysis,
        "preliminary_check": prelim_analysis,
        "user_guidance": user_choice if user_choice else "none",
        "llm_usage": {
            "input_tokens": prelim_response['usage'].get('inputTokens', 0) + response['usage'].get('inputTokens', 0),
            "output_tokens": prelim_response['usage'].get('outputTokens', 0) + response['usage'].get('outputTokens', 0)
        }
    }


async def summarize_data(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize data using LLM"""
    data = parameters.get("data")
    if not data:
        raise ValueError("data parameter is required")
    
    data_str = json.dumps(data, indent=2) if isinstance(data, dict) else str(data)
    
    prompt = f"""Provide a concise summary of this data:
1. Main findings (3-5 bullet points)
2. Key metrics
3. Overall assessment

Data:
{data_str}"""
    
    response = bedrock_client.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 1500, "temperature": 0.7}
    )
    
    summary = response['output']['message']['content'][0]['text']
    
    return {
        "data": data,
        "summary": summary,
        "llm_usage": {
            "input_tokens": response['usage'].get('inputTokens', 0),
            "output_tokens": response['usage'].get('outputTokens', 0)
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT, log_level="info")
