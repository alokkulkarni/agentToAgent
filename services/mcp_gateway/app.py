"""
MCP Gateway Service
Routes tool execution requests to appropriate MCP servers with authentication support
"""
import os
import json
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
import uvicorn
import httpx
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

from shared.identity_provider import get_identity_provider, UserContext
from shared.auth_dependencies import get_current_user

# Load environment variables from .env file
load_dotenv()

# Initialize identity provider
identity_provider = get_identity_provider()

# Environment Configuration
GATEWAY_HOST = os.getenv("MCP_GATEWAY_HOST", "0.0.0.0")
GATEWAY_PORT = int(os.getenv("MCP_GATEWAY_PORT", "8220"))
MCP_REGISTRY_URL = os.getenv("MCP_REGISTRY_URL", "http://localhost:8200")
AWS_REGION = os.getenv("AWS_REGION", "eu-west-2")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").lower()


# Initialize Bedrock client
bedrock_client = None
try:
    # Try to use environment credentials first, fallback to local AWS config
    if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
        bedrock_client = boto3.client(
            "bedrock-runtime",
            region_name=AWS_REGION,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
        )
    else:
        bedrock_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    print("✓ Bedrock client initialized")
except Exception as e:
    print(f"⚠ Warning: Could not initialize Bedrock client: {e}")


# Models
class ToolCall(BaseModel):
    """Tool execution request"""
    tool_name: str
    parameters: Dict[str, Any]
    prefer_server: Optional[str] = None
    # Trace context — propagated from orchestrator for end-to-end observability
    workflow_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None


class GatewayRequest(BaseModel):
    """Gateway query request"""
    query: str
    context: Optional[Dict] = Field(default_factory=dict)
    auto_execute: bool = True


class ToolResult(BaseModel):
    """Tool execution result"""
    tool_name: str
    server_name: str
    server_id: str
    result: Any
    execution_time_ms: Optional[float] = None


# FastAPI App
app = FastAPI(title="MCP Gateway Service", version="1.0.0")

# HTTP client
http_client = httpx.AsyncClient(timeout=30.0)


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "MCP Gateway",
        "status": "running",
        "registry_url": MCP_REGISTRY_URL,
        "bedrock_available": bedrock_client is not None,
        "auth_enabled": identity_provider.enabled
    }


async def discover_tools():
    """Discover available tools from registry with auth metadata"""
    try:
        response = await http_client.get(f"{MCP_REGISTRY_URL}/api/mcp/tools")
        if response.status_code == 200:
            return response.json()
        return {"total_tools": 0, "tools": []}
    except Exception as e:
        print(f"Error discovering tools: {e}")
        return {"total_tools": 0, "tools": []}


async def get_tool_auth_requirements(tool_name: str) -> Optional[Dict]:
    """Get authentication requirements for a specific tool from registry"""
    try:
        response = await http_client.get(f"{MCP_REGISTRY_URL}/api/mcp/tools/{tool_name}/auth")
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        print(f"Error getting auth requirements for {tool_name}: {e}")
        return None


async def find_server_for_tool(tool_name: str, prefer_server: Optional[str] = None):
    """Find appropriate MCP server for a tool"""
    try:
        response = await http_client.get(f"{MCP_REGISTRY_URL}/api/mcp/tools/{tool_name}")
        if response.status_code == 200:
            data = response.json()
            servers = data.get("servers", [])
            
            if not servers:
                return None
            
            # Prefer specific server if requested
            if prefer_server:
                for server in servers:
                    if server["server_id"] == prefer_server or server["server_name"] == prefer_server:
                        return server
            
            # Return first active server
            return servers[0]
        
        return None
    except Exception as e:
        print(f"Error finding server for tool {tool_name}: {e}")
        return None


async def execute_tool_on_server(
    server_url: str, 
    tool_name: str, 
    parameters: Dict,
    auth_token: Optional[str] = None
):
    """Execute tool on specific MCP server with optional authentication"""
    try:
        headers = {}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        
        response = await http_client.post(
            f"{server_url}/api/tools/execute",
            json={"tool_name": tool_name, "parameters": parameters},
            headers=headers
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"Server returned status {response.status_code}", "detail": response.text}
    except Exception as e:
        return {"error": str(e)}


async def query_bedrock(query: str, context: Dict, available_tools: List[Dict]) -> Dict:
    """Use Bedrock to analyze query and determine tool usage"""
    if not bedrock_client:
        return {
            "analysis": "Bedrock not available - cannot analyze query",
            "suggested_tools": [],
            "reasoning": "Bedrock client not initialized"
        }
    
    # Build prompt with available tools
    tools_description = "\n".join([
        f"- {tool['tool_name']}: {tool['description']} (server: {tool['server_name']})"
        for tool in available_tools
    ])
    
    prompt = f"""Analyze the following user query and determine which tools should be used to fulfill it.

Available Tools:
{tools_description}

User Query: {query}

Context: {json.dumps(context, indent=2)}

Respond with a JSON object containing:
1. "analysis": Brief analysis of the query
2. "suggested_tools": List of tool names to use in order
3. "parameters": For each tool, suggest the parameters
4. "reasoning": Why these tools were chosen

Format your response as valid JSON only."""

    try:
        response = bedrock_client.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": prompt}]
                }
            ],
            inferenceConfig={
                "maxTokens": 2000,
                "temperature": 0.7
            }
        )
        
        content = response["output"]["message"]["content"][0]["text"]
        
        # Extract JSON from response
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        # Clean up common JSON issues
        content = content.strip()
        if not content.startswith("{"):
            # Find first { and last }
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                content = content[start:end]
        
        return json.loads(content)
        
    except ClientError as e:
        print(f"Bedrock API error: {e}")
        return {
            "analysis": f"Error calling Bedrock: {str(e)}",
            "suggested_tools": [],
            "reasoning": "API error"
        }
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        print(f"Content: {content}")
        return {
            "analysis": "Could not parse Bedrock response",
            "suggested_tools": [],
            "reasoning": "JSON parsing failed"
        }
    except Exception as e:
        print(f"Unexpected error: {e}")
        return {
            "analysis": f"Error: {str(e)}",
            "suggested_tools": [],
            "reasoning": "Unexpected error"
        }


@app.post("/api/gateway/query")
async def process_query(
    request: GatewayRequest,
    user: UserContext = Depends(get_current_user)
):
    """Process a natural language query and route to appropriate tools"""
    
    # Discover available tools
    tools_data = await discover_tools()
    available_tools = tools_data.get("tools", [])
    
    if not available_tools:
        raise HTTPException(status_code=503, detail="No MCP servers available")
    
    # Analyze query with Bedrock
    analysis = await query_bedrock(request.query, request.context, available_tools)
    
    results = {
        "query": request.query,
        "analysis": analysis,
        "tool_executions": []
    }
    
    # Execute tools if auto_execute is enabled
    if request.auto_execute and analysis.get("suggested_tools"):
        for tool_name in analysis["suggested_tools"]:
            # Get parameters for this tool
            tool_params = analysis.get("parameters", {}).get(tool_name, {})
            
            # Get auth requirements for tool
            auth_requirements = await get_tool_auth_requirements(tool_name)
            auth_token = None
            
            if auth_requirements and auth_requirements.get("auth_schema", {}).get("auth_type") != "none":
                required_scopes = auth_requirements.get("auth_schema", {}).get("required_scopes", [])
                if required_scopes:
                    # Get tool-specific token using OBO flow
                    try:
                        auth_token = await identity_provider.get_token_for_scope(
                            user, 
                            required_scopes,
                            resource=auth_requirements.get("auth_schema", {}).get("audience")
                        )
                        print(f"✓ Got auth token for tool {tool_name} with scopes: {required_scopes}")
                    except Exception as e:
                        print(f"⚠️  Failed to get auth token for {tool_name}: {e}")
                        results["tool_executions"].append({
                            "tool_name": tool_name,
                            "error": f"Authentication failed: {str(e)}"
                        })
                        continue
            
            # Find server for tool
            server_info = await find_server_for_tool(tool_name)
            
            if server_info:
                # Execute tool with auth
                result = await execute_tool_on_server(
                    server_info["server_url"],
                    tool_name,
                    tool_params,
                    auth_token=auth_token
                )
                
                results["tool_executions"].append({
                    "tool_name": tool_name,
                    "server_name": server_info["server_name"],
                    "server_id": server_info["server_id"],
                    "parameters": tool_params,
                    "result": result,
                    "authenticated": auth_token is not None
                })
            else:
                results["tool_executions"].append({
                    "tool_name": tool_name,
                    "error": "No server found for this tool"
                })
    
    return results


@app.post("/api/gateway/execute")
async def execute_tool(
    tool_call: ToolCall,
    user: UserContext = Depends(get_current_user)
):
    """Execute a specific tool directly with authentication"""
    
    # Get auth requirements for the tool
    auth_requirements = await get_tool_auth_requirements(tool_call.tool_name)
    auth_token = None
    
    if auth_requirements and auth_requirements.get("auth_schema", {}).get("auth_type") != "none":
        required_scopes = auth_requirements.get("auth_schema", {}).get("required_scopes", [])
        if required_scopes:
            # Get tool-specific token using OBO flow
            try:
                auth_token = await identity_provider.get_token_for_scope(
                    user,
                    required_scopes,
                    resource=auth_requirements.get("auth_schema", {}).get("audience")
                )
                print(f"✓ Got auth token for tool {tool_call.tool_name}")
            except Exception as e:
                raise HTTPException(
                    status_code=401,
                    detail=f"Failed to obtain required authentication: {str(e)}"
                )
    
    # Find server for tool
    server_info = await find_server_for_tool(tool_call.tool_name, tool_call.prefer_server)
    
    if not server_info:
        raise HTTPException(status_code=404, detail=f"No server found for tool: {tool_call.tool_name}")
    
    # Execute tool with auth
    result = await execute_tool_on_server(
        server_info["server_url"],
        tool_call.tool_name,
        tool_call.parameters,
        auth_token=auth_token
    )
    
    return ToolResult(
        tool_name=tool_call.tool_name,
        server_name=server_info["server_name"],
        server_id=server_info["server_id"],
        result=result
    )


@app.post("/api/gateway/execute")
async def execute_tool(tool_call: ToolCall):
    """Execute a specific tool directly"""
    
    if tool_call.workflow_id:
        print(
            f"[MCP] execute tool={tool_call.tool_name}"
            f" workflow={tool_call.workflow_id}"
            f" session={tool_call.session_id or '-'}"
            f" user={tool_call.user_id or '-'}"
        )

    # Find server for tool
    server_info = await find_server_for_tool(tool_call.tool_name, tool_call.prefer_server)
    
    if not server_info:
        raise HTTPException(status_code=404, detail=f"No server found for tool: {tool_call.tool_name}")
    
    # Execute tool
    result = await execute_tool_on_server(
        server_info["server_url"],
        tool_call.tool_name,
        tool_call.parameters
    )
    
    return ToolResult(
        tool_name=tool_call.tool_name,
        server_name=server_info["server_name"],
        server_id=server_info["server_id"],
        result=result
    )


@app.get("/api/gateway/discovery")
async def gateway_discovery():
    """Discover all available tools and servers"""
    try:
        response = await http_client.get(f"{MCP_REGISTRY_URL}/api/mcp/discovery")
        if response.status_code == 200:
            return response.json()
        raise HTTPException(status_code=503, detail="Registry unavailable")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Error connecting to registry: {str(e)}")


@app.get("/api/gateway/tools")
async def list_available_tools():
    """List all available tools"""
    return await discover_tools()


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown"""
    await http_client.aclose()


if __name__ == "__main__":
    print(f"🚀 Starting MCP Gateway Service on {GATEWAY_HOST}:{GATEWAY_PORT}")
    print(f"📡 Connected to MCP Registry: {MCP_REGISTRY_URL}")
    uvicorn.run(app, host=GATEWAY_HOST, port=GATEWAY_PORT, log_level=LOG_LEVEL)
