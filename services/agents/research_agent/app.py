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
from typing import Dict, Any, List, Optional
import boto3
import httpx
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
from shared.llm_client import SafeLLMClient

load_dotenv()

# Configuration
AGENT_NAME = os.getenv("AGENT_NAME", "ResearchAgent")
AGENT_PORT = int(os.getenv("AGENT_PORT", "8003"))
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://localhost:8000")
MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", "http://localhost:8300")
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
    """Initialize Safe LLM client"""
    global bedrock_client
    
    # Initialize SafeLLMClient which handles authentication via boto3 internally
    # and enforces Enterprise Guardrails
    bedrock_client = SafeLLMClient(region_name=AWS_REGION)
    print(f"✓ SafeLLMClient initialized (region: {AWS_REGION}, model: {BEDROCK_MODEL_ID})")
    print(f"  - Guardrails: Enabled")
    print(f"  - PII Redaction: Enabled")
    print(f"  - Audit Logging: Enabled")


async def call_mcp_gateway(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Call MCP Gateway to execute tool"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            print(f"      calling MCP Gateway tool: {tool_name}")
            response = await client.post(
                f"{MCP_GATEWAY_URL}/api/gateway/execute",
                json={
                    "tool_name": tool_name,
                    "parameters": arguments
                }
            )
            response.raise_for_status()
            result = response.json()
            return result
        except httpx.HTTPError as e:
            print(f"      MCP Gateway error: {str(e)}")
            return {"error": str(e)}
        except Exception as e:
            print(f"      Error calling MCP Gateway: {str(e)}")
            return {"error": str(e)}


async def check_if_search_needed(query: str) -> bool:
    """Check if the query requires fresh web search data"""
    try:
        system_instruction = """Analyze user queries and determine if they require up-to-date information from the web (e.g., current events, recent tech, real-time data) that might be missing or stale in a fixed training set.
        
Respond with JSON: {"needs_search": true/false, "reason": "..."}"""

        user_query = f"Query: {query}"
        
        try:
            response = bedrock_client.converse(
                modelId=BEDROCK_MODEL_ID,
                system=[{
                    "text": system_instruction,
                    "cachePoint": {"type": "default"}
                }],
                messages=[{"role": "user", "content": [{"text": user_query}]}],
                inferenceConfig={"maxTokens": 200, "temperature": 0.1}
            )
        except Exception as e:
            # Fallback for prompt caching
            response = bedrock_client.converse(
                modelId=BEDROCK_MODEL_ID,
                system=[{"text": system_instruction}],
                messages=[{"role": "user", "content": [{"text": user_query}]}],
                inferenceConfig={"maxTokens": 200, "temperature": 0.1}
            )
        
        content = response['output']['message']['content'][0]['text']
        return "true" in content.lower() and "needs_search" in content.lower()
    except Exception as e:
        print(f"Error checking search need: {e}")
        return False


async def perform_web_research(query: str) -> str:
    """Perform web research using MCP"""
    print(f"      🔍 Performing web research for: {query}")
    
    # 1. Search Web
    search_result = await call_mcp_gateway("search_web", {"query": query, "max_results": 3})
    
    context = ""
    if "result" in search_result and "results" in search_result["result"]:
        results = search_result["result"]["results"]
        context += f"\n\n--- Web Search Results for '{query}' ---\n"
        
        for i, res in enumerate(results):
            context += f"Source {i+1}: {res.get('title')}\n"
            context += f"URL: {res.get('url')}\n"
            context += f"Snippet: {res.get('snippet')}\n\n"
            
    return context



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
    
    # Inject context into parameters to ensure AgentInteractionHelper works correctly
    if task.context:
        task.parameters["_workflow_context"] = task.context
    
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
    """Answer a question using LLM, potentially with web search"""
    question = parameters.get("question")
    if not question:
        raise ValueError("question parameter is required")
    
    context = parameters.get("context", "")
    # Ensure context is a string and not a dictionary/metadata
    if isinstance(context, dict):
        context = ""
    
    # Check if search is needed
    needs_search = await check_if_search_needed(question)
    search_context = ""
    
    if needs_search:
        print(f"      💡 Query requires fresh data. Initiating web search...")
        search_context = await perform_web_research(question)
    
    # Combine contexts
    full_context = f"{context}\n{search_context}" if context else search_context
    
    
    # Enable Prompt Caching for the context part
    # We construct the messages structure manually to inject cachePoint
    messages = []
    
    # 1. System/Context Message (Cached)
    if full_context:
        messages.append({
            "role": "user",  # Context provided as user message part of conversation history
            "content": [
                {
                    "text": f"Here is the context data to use for your answer:\n\n{full_context}",
                    "cachePoint": {"type": "default"}  # Cache this large context block
                }
            ]
        })
        
    # 2. Actual Question (Not Cached - unique per turn)
    messages.append({
        "role": "user",
        "content": [{"text": f"Question: {question}" + ("\n\n(Please incorporate the web search results above to answer this question with up-to-date information.)" if needs_search else "")}]
    })
    
    # If no context, just use simple message structure (no caching benefit for short prompts)
    if not full_context:
        simple_prompt = f"Question: {question}" + ("\n\n(Please incorporate the web search results above to answer this question with up-to-date information.)" if needs_search else "")
        messages = [{"role": "user", "content": [{"text": simple_prompt}]}]
    
    try:
        response = bedrock_client.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=messages,
            inferenceConfig={"maxTokens": 2000, "temperature": 0.7}
        )
    except Exception as e:
        # Fallback - strip cachePoint
        for msg in messages:
            for content_block in msg.get("content", []):
                if "cachePoint" in content_block:
                    del content_block["cachePoint"]
        
        response = bedrock_client.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=messages,
            inferenceConfig={"maxTokens": 2000, "temperature": 0.7}
        )
    
    answer = response['output']['message']['content'][0]['text']
    
    return {
        "question": question,
        "answer": answer,
        "search_performed": needs_search,
        "llm_usage": {
            "input_tokens": response['usage'].get('inputTokens', 0),
            "output_tokens": response['usage'].get('outputTokens', 0)
        }
    }


async def generate_report(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a detailed report
    
    ENHANCED: Now supports interactive workflow - can ask user to narrow scope
    when topic is too broad
    """
    topic = parameters.get("topic")
    if not topic:
        raise ValueError("topic parameter is required")
    
    # Create interaction helper
    helper = AgentInteractionHelper(parameters)
    
    aspects = parameters.get("aspects", [])
    aspects_str = ", ".join(aspects) if aspects else "all relevant aspects"
    
    # Check if user provided guidance (PRIORITY: Check this first to avoid re-analysis loop)
    user_choice = helper.get_user_response()
    
    if user_choice:
        print(f"✓ User chose to focus on: {user_choice}")
        
        if "Cover all aspects" in user_choice:
            focus_instruction = "Cover all major aspects comprehensively."
        else:
            focus_instruction = f"Focus specifically on: {user_choice}. Provide in-depth coverage of this aspect."
            
        # We can skip the scope check if user already decided
        scope_analysis = "User selected focus area directly."
        
    else:
        # User hasn't decided yet, assess scope
        # First, assess the scope of the topic
        scope_prompt = f"""Analyze this research topic and determine:
    1. Is it too broad for a single comprehensive report?
    2. What are the main sub-topics or aspects?
    3. How many sources/perspectives would be needed?
    
    Topic: {topic}
    
    Respond with JSON containing:
    - is_broad: boolean
    - sub_topics: list of main sub-topics
    - estimated_depth: "shallow", "medium", or "deep"
    - recommendation: suggested focus area if too broad"""
        
        scope_response = bedrock_client.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": scope_prompt}]}],
            inferenceConfig={"maxTokens": 1000, "temperature": 0.3}
        )
        
        scope_analysis = scope_response['output']['message']['content'][0]['text']
        
        # Check if topic is too broad
        is_broad = "is_broad\": true" in scope_analysis or "is_broad\":true" in scope_analysis
        
        # INTERACTIVE WORKFLOW: Ask user to narrow scope if topic is too broad
        if is_broad:
            # Try to extract sub-topics (simplified)
            import re
            subtopics_match = re.search(r'"sub_topics":\s*\[(.*?)\]', scope_analysis, re.DOTALL)
            subtopics = []
            if subtopics_match:
                # Extract quoted strings
                subtopics = re.findall(r'"([^"]+)"', subtopics_match.group(1))
            
            if subtopics and len(subtopics) > 1:
                # Offer specific sub-topics
                options = subtopics[:5] + ["Cover all aspects (comprehensive report)"]
            else:
                # Generic options
                options = [
                    "Focus on current trends and developments",
                    "Focus on historical context and evolution",
                    "Focus on practical applications and use cases",
                    "Focus on challenges and future outlook",
                    "Cover all aspects (comprehensive report)"
                ]
            
            return helper.ask_single_choice(
                question=f"The topic '{topic}' is quite broad. Which aspect should I focus on?",
                options=options,
                reasoning=f"Broad topic detected. Focusing on a specific aspect will produce a more detailed and useful report. Scope analysis: {scope_analysis[:200]}...",
                partial_results={"scope_analysis": scope_analysis}
            )
            
        focus_instruction = "Cover the topic comprehensively."
    
    # Check if search is needed for the topic
    needs_search = await check_if_search_needed(topic)
    search_context = ""
    
    if needs_search:
        print(f"      💡 Topic requires fresh data. Initiating web search...")
        # Search for main topic
        search_context = await perform_web_research(topic)
        
        # If user chose a specific aspect, search for that too
        if user_choice and "Cover all" not in user_choice:
             search_context += await perform_web_research(f"{topic} {user_choice}")

    # Generate the report with user's focus
    prompt = f"""Generate a comprehensive report on: {topic}

{focus_instruction}

Include {aspects_str}.

{search_context}

Structure the report with:
1. Executive Summary
2. Key Findings
3. Detailed Analysis
4. Conclusions and Recommendations

Make it detailed and well-researched. If web search results are provided, use them to ensure the information is current."""
    
    response = bedrock_client.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 4000, "temperature": 0.7}
    )
    
    report = response['output']['message']['content'][0]['text']
    
    # Calculate tokens (handle case where scope_response might be undefined)
    input_tokens = response['usage'].get('inputTokens', 0)
    output_tokens = response['usage'].get('outputTokens', 0)
    
    if 'scope_response' in locals():
        input_tokens += scope_response['usage'].get('inputTokens', 0)
        output_tokens += scope_response['usage'].get('outputTokens', 0)
    
    return {
        "topic": topic,
        "report": report,
        "focus_area": user_choice if user_choice else "comprehensive",
        "scope_analysis": scope_analysis,
        "search_performed": needs_search,
        "llm_usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens
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
