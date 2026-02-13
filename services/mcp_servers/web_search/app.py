"""
MCP Server - Web Search
Provides web search and content retrieval tools via MCP protocol
"""
import os
import json
import uuid
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import httpx
from datetime import datetime, timezone


# Environment Configuration
SERVER_HOST = os.getenv("MCP_WEB_SEARCH_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("MCP_WEB_SEARCH_PORT", "8212"))
MCP_REGISTRY_URL = os.getenv("MCP_REGISTRY_URL", "http://localhost:8200")
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")


# Models
class ToolExecutionRequest(BaseModel):
    """Tool execution request"""
    tool_name: str
    parameters: Dict[str, Any]


# FastAPI App
app = FastAPI(title="MCP Web Search Server", version="1.0.0")

# Server state
server_id = str(uuid.uuid4())
http_client = httpx.AsyncClient(timeout=30.0)


# Tool implementations
async def search_web(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Simulate web search (placeholder - would integrate with real search API)"""
    try:
        # This is a mock implementation
        # In production, integrate with Google Custom Search, Bing API, or similar
        
        results = [
            {
                "title": f"Result {i+1} for '{query}'",
                "url": f"https://example.com/result-{i+1}",
                "snippet": f"This is a sample search result {i+1} related to {query}. In production, this would contain actual search results from a search API.",
                "relevance_score": 1.0 - (i * 0.1)
            }
            for i in range(min(max_results, 5))
        ]
        
        return {
            "query": query,
            "results": results,
            "total_results": len(results),
            "note": "This is a mock implementation. Integrate with a real search API in production."
        }
    except Exception as e:
        return {"error": str(e)}


async def fetch_url(url: str) -> Dict[str, Any]:
    """Fetch content from a URL"""
    try:
        response = await http_client.get(url, follow_redirects=True)
        
        return {
            "url": url,
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", "unknown"),
            "content_length": len(response.content),
            "content": response.text[:5000],  # Limit to first 5000 chars
            "headers": dict(response.headers)
        }
    except Exception as e:
        return {"error": str(e), "url": url}


async def extract_links(url: str) -> Dict[str, Any]:
    """Extract links from a webpage (simplified)"""
    try:
        response = await http_client.get(url, follow_redirects=True)
        content = response.text
        
        # Simple link extraction (in production, use proper HTML parser)
        import re
        links = re.findall(r'href=["\'](https?://[^\s"\']+)["\']', content)
        
        # Deduplicate
        links = list(set(links))[:50]  # Limit to 50 links
        
        return {
            "url": url,
            "links_found": len(links),
            "links": links
        }
    except Exception as e:
        return {"error": str(e), "url": url}


def summarize_text(text: str, max_length: int = 200) -> Dict[str, Any]:
    """Simple text summarization"""
    try:
        # Simple summarization - just take first N words
        # In production, use proper NLP summarization
        
        words = text.split()
        
        if len(words) <= max_length:
            summary = text
        else:
            summary = " ".join(words[:max_length]) + "..."
        
        return {
            "original_length": len(text),
            "summary_length": len(summary),
            "summary": summary,
            "compression_ratio": len(summary) / len(text) if text else 0
        }
    except Exception as e:
        return {"error": str(e)}


# Tool registry
TOOLS = {
    "search_web": {
        "function": search_web,
        "description": "Search the web for information",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5)",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    "fetch_url": {
        "function": fetch_url,
        "description": "Fetch content from a URL",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch"
                }
            },
            "required": ["url"]
        }
    },
    "extract_links": {
        "function": extract_links,
        "description": "Extract all links from a webpage",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL of the webpage"
                }
            },
            "required": ["url"]
        }
    },
    "summarize_text": {
        "function": summarize_text,
        "description": "Summarize a text to a shorter version",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to summarize"
                },
                "max_length": {
                    "type": "integer",
                    "description": "Maximum length of summary in words (default: 200)",
                    "default": 200
                }
            },
            "required": ["text"]
        }
    }
}


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "MCP Web Search Server",
        "status": "running",
        "server_id": server_id,
        "tools_available": len(TOOLS)
    }


@app.post("/api/tools/execute")
async def execute_tool(request: ToolExecutionRequest):
    """Execute a tool"""
    if request.tool_name not in TOOLS:
        raise HTTPException(status_code=404, detail=f"Tool not found: {request.tool_name}")
    
    tool = TOOLS[request.tool_name]
    
    try:
        # Handle async functions
        if request.tool_name in ["search_web", "fetch_url", "extract_links"]:
            result = await tool["function"](**request.parameters)
        else:
            result = tool["function"](**request.parameters)
        
        return {
            "tool_name": request.tool_name,
            "result": result,
            "executed_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {
            "tool_name": request.tool_name,
            "error": str(e)
        }


@app.get("/api/tools")
async def list_tools():
    """List available tools"""
    return {
        "tools": [
            {
                "name": name,
                "description": tool["description"],
                "input_schema": tool["input_schema"]
            }
            for name, tool in TOOLS.items()
        ]
    }


async def register_with_registry():
    """Register this server with the MCP registry"""
    tools = [
        {
            "name": name,
            "description": tool["description"],
            "input_schema": tool["input_schema"]
        }
        for name, tool in TOOLS.items()
    ]
    
    registration = {
        "server_id": server_id,
        "name": "WebSearchServer",
        "description": "Provides web search and content retrieval operations",
        "base_url": f"http://{SERVER_HOST}:{SERVER_PORT}",
        "tools": tools,
        "metadata": {
            "capabilities": ["search", "fetch", "extract", "summarize"]
        }
    }
    
    try:
        response = await http_client.post(
            f"{MCP_REGISTRY_URL}/api/mcp/register",
            json=registration
        )
        
        if response.status_code == 200:
            print(f"✓ Registered with MCP Registry: {server_id}")
            print(f"  Tools: {list(TOOLS.keys())}")
        else:
            print(f"✗ Failed to register: {response.status_code}")
    except Exception as e:
        print(f"✗ Error registering with registry: {e}")


async def unregister_from_registry():
    """Unregister this server from the MCP registry"""
    try:
        await http_client.delete(f"{MCP_REGISTRY_URL}/api/mcp/unregister/{server_id}")
        print(f"✓ Unregistered from MCP Registry")
    except Exception as e:
        print(f"Error unregistering: {e}")


@app.on_event("startup")
async def startup_event():
    """Register with registry on startup"""
    await register_with_registry()


@app.on_event("shutdown")
async def shutdown_event():
    """Unregister from registry on shutdown"""
    await unregister_from_registry()
    await http_client.aclose()


if __name__ == "__main__":
    print(f"🚀 Starting MCP Web Search Server on {SERVER_HOST}:{SERVER_PORT}")
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level=LOG_LEVEL)
