"""
Calculator MCP Server
Provides basic and advanced mathematical operations as MCP tools
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
import httpx
import math
import asyncio
from dotenv import load_dotenv

load_dotenv()

# Configuration
SERVER_NAME = os.getenv("MCP_SERVER_NAME", "calculator")
SERVER_PORT = int(os.getenv("MCP_SERVER_PORT", "9001"))
MCP_REGISTRY_URL = os.getenv("MCP_REGISTRY_URL", "http://localhost:8500")

server_id = None


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]


class ToolRequest(BaseModel):
    tool_name: str
    parameters: Dict[str, Any]


# Define available tools
TOOLS = {
    "add": {
        "name": "add",
        "description": "Add two numbers",
        "input_schema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "First number"},
                "b": {"type": "number", "description": "Second number"}
            },
            "required": ["a", "b"]
        }
    },
    "subtract": {
        "name": "subtract",
        "description": "Subtract b from a",
        "input_schema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "First number"},
                "b": {"type": "number", "description": "Second number"}
            },
            "required": ["a", "b"]
        }
    },
    "multiply": {
        "name": "multiply",
        "description": "Multiply two numbers",
        "input_schema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "First number"},
                "b": {"type": "number", "description": "Second number"}
            },
            "required": ["a", "b"]
        }
    },
    "divide": {
        "name": "divide",
        "description": "Divide a by b",
        "input_schema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "Numerator"},
                "b": {"type": "number", "description": "Denominator (cannot be zero)"}
            },
            "required": ["a", "b"]
        }
    },
    "power": {
        "name": "power",
        "description": "Raise a number to a power",
        "input_schema": {
            "type": "object",
            "properties": {
                "base": {"type": "number", "description": "Base number"},
                "exponent": {"type": "number", "description": "Exponent"}
            },
            "required": ["base", "exponent"]
        }
    },
    "square": {
        "name": "square",
        "description": "Square a number (multiply by itself)",
        "input_schema": {
            "type": "object",
            "properties": {
                "value": {"type": "number", "description": "Number to square"}
            },
            "required": ["value"]
        }
    },
    "sqrt": {
        "name": "sqrt",
        "description": "Calculate square root of a number",
        "input_schema": {
            "type": "object",
            "properties": {
                "value": {"type": "number", "description": "Number (must be non-negative)"}
            },
            "required": ["value"]
        }
    },
    "abs": {
        "name": "abs",
        "description": "Calculate absolute value",
        "input_schema": {
            "type": "object",
            "properties": {
                "value": {"type": "number", "description": "Number"}
            },
            "required": ["value"]
        }
    }
}


async def register_with_mcp_registry():
    """Register this MCP server with the MCP registry"""
    global server_id
    
    # Retry with exponential backoff
    max_retries = 10
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{MCP_REGISTRY_URL}/api/mcp/register",
                    json={
                        "name": SERVER_NAME,
                        "description": "Provides basic and advanced mathematical operations",
                        "base_url": f"http://localhost:{SERVER_PORT}",
                        "tools": list(TOOLS.values())
                    }
                )
                response.raise_for_status()
                data = response.json()
                server_id = data["server_id"]
                print(f"✓ Registered with MCP Registry: {server_id}")
                print(f"  Tools: {list(TOOLS.keys())}")
                return
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                await asyncio.sleep(wait_time)
            else:
                print(f"✗ Failed to register with MCP Registry after {max_retries} attempts: {e}")


async def unregister_from_mcp_registry():
    """Unregister from MCP registry"""
    if server_id:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.delete(
                    f"{MCP_REGISTRY_URL}/api/mcp/unregister/{server_id}"
                )
                print("✓ Unregistered from MCP Registry")
        except Exception as e:
            print(f"✗ Failed to unregister: {e}")


app = FastAPI(title="Calculator MCP Server")


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy", "server": SERVER_NAME}


@app.get("/api/mcp/tools")
async def list_tools():
    """List available tools"""
    return {"tools": list(TOOLS.values())}


@app.post("/api/mcp/execute")
@app.post("/api/tools/execute")
async def execute_tool(request: ToolRequest):
    """Execute a tool"""
    tool_name = request.tool_name
    parameters = request.parameters
    
    if tool_name not in TOOLS:
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")
    
    try:
        # Execute the appropriate operation
        if tool_name == "add":
            result = parameters["a"] + parameters["b"]
        elif tool_name == "subtract":
            result = parameters["a"] - parameters["b"]
        elif tool_name == "multiply":
            result = parameters["a"] * parameters["b"]
        elif tool_name == "divide":
            if parameters["b"] == 0:
                raise ValueError("Cannot divide by zero")
            result = parameters["a"] / parameters["b"]
        elif tool_name == "power":
            result = parameters["base"] ** parameters["exponent"]
        elif tool_name == "square":
            result = parameters["value"] ** 2
        elif tool_name == "sqrt":
            if parameters["value"] < 0:
                raise ValueError("Cannot take square root of negative number")
            result = math.sqrt(parameters["value"])
        elif tool_name == "abs":
            result = abs(parameters["value"])
        else:
            raise HTTPException(status_code=400, detail=f"Unknown tool: {tool_name}")
        
        return {
            "success": True,
            "result": result,
            "tool": tool_name,
            "parameters": parameters
        }
    
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing required argument: {e}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution error: {str(e)}")


@app.on_event("startup")
async def startup_event():
    """Register with registry on startup"""
    print(f"Starting Calculator MCP Server on port {SERVER_PORT}...")
    await register_with_mcp_registry()


@app.on_event("shutdown")
async def shutdown_event():
    """Unregister from registry on shutdown"""
    print("Shutting down Calculator MCP Server...")
    await unregister_from_mcp_registry()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT)
