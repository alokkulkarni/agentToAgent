"""
MCP Server - File Operations
Provides file system tools via MCP protocol
"""
import os
import json
import uuid
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import httpx
from datetime import datetime, timezone


# Environment Configuration
SERVER_HOST = os.getenv("MCP_FILE_OPS_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("MCP_FILE_OPS_PORT", "8210"))
MCP_REGISTRY_URL = os.getenv("MCP_REGISTRY_URL", "http://localhost:8200")
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", "/tmp/mcp_workspace")
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").lower()


# Models
class ToolExecutionRequest(BaseModel):
    """Tool execution request"""
    tool_name: str
    parameters: Dict[str, Any]


# FastAPI App
app = FastAPI(title="MCP File Operations Server", version="1.0.0")

# Server state
server_id = str(uuid.uuid4())
http_client = httpx.AsyncClient(timeout=10.0)


# Ensure workspace directory exists
Path(WORKSPACE_DIR).mkdir(parents=True, exist_ok=True)


# Tool implementations
def read_file(file_path: str) -> Dict[str, Any]:
    """Read contents of a file"""
    try:
        full_path = Path(WORKSPACE_DIR) / file_path
        
        if not full_path.exists():
            return {"error": f"File not found: {file_path}"}
        
        if not full_path.is_file():
            return {"error": f"Not a file: {file_path}"}
        
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        return {
            "file_path": file_path,
            "content": content,
            "size_bytes": len(content),
            "lines": len(content.splitlines())
        }
    except Exception as e:
        return {"error": str(e)}


def write_file(file_path: str, content: str) -> Dict[str, Any]:
    """Write content to a file"""
    try:
        full_path = Path(WORKSPACE_DIR) / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        return {
            "file_path": file_path,
            "size_bytes": len(content),
            "status": "written"
        }
    except Exception as e:
        return {"error": str(e)}


def list_files(directory: str = ".", pattern: str = "*") -> Dict[str, Any]:
    """List files in a directory"""
    try:
        full_path = Path(WORKSPACE_DIR) / directory
        
        if not full_path.exists():
            return {"error": f"Directory not found: {directory}"}
        
        if not full_path.is_dir():
            return {"error": f"Not a directory: {directory}"}
        
        files = []
        for item in full_path.glob(pattern):
            files.append({
                "name": item.name,
                "path": str(item.relative_to(WORKSPACE_DIR)),
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None
            })
        
        return {
            "directory": directory,
            "pattern": pattern,
            "files": files,
            "total": len(files)
        }
    except Exception as e:
        return {"error": str(e)}


def delete_file(file_path: str) -> Dict[str, Any]:
    """Delete a file"""
    try:
        full_path = Path(WORKSPACE_DIR) / file_path
        
        if not full_path.exists():
            return {"error": f"File not found: {file_path}"}
        
        if full_path.is_file():
            full_path.unlink()
        elif full_path.is_dir():
            full_path.rmdir()
        
        return {
            "file_path": file_path,
            "status": "deleted"
        }
    except Exception as e:
        return {"error": str(e)}


# Tool registry
TOOLS = {
    "read_file": {
        "function": read_file,
        "description": "Read the contents of a file",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to read"
                }
            },
            "required": ["file_path"]
        }
    },
    "write_file": {
        "function": write_file,
        "description": "Write content to a file",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to write"
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file"
                }
            },
            "required": ["file_path", "content"]
        }
    },
    "list_files": {
        "function": list_files,
        "description": "List files in a directory",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Directory to list (default: current)",
                    "default": "."
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to filter files (default: *)",
                    "default": "*"
                }
            }
        }
    },
    "delete_file": {
        "function": delete_file,
        "description": "Delete a file or empty directory",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to delete"
                }
            },
            "required": ["file_path"]
        }
    }
}


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "MCP File Operations Server",
        "status": "running",
        "server_id": server_id,
        "tools_available": len(TOOLS),
        "workspace": WORKSPACE_DIR
    }


@app.post("/api/tools/execute")
async def execute_tool(request: ToolExecutionRequest):
    """Execute a tool"""
    if request.tool_name not in TOOLS:
        raise HTTPException(status_code=404, detail=f"Tool not found: {request.tool_name}")
    
    tool = TOOLS[request.tool_name]
    
    try:
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
        "name": "FileOperationsServer",
        "description": "Provides file system operations (read, write, list, delete)",
        "base_url": f"http://{SERVER_HOST}:{SERVER_PORT}",
        "tools": tools,
        "metadata": {
            "workspace": WORKSPACE_DIR
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
    print(f"🚀 Starting MCP File Operations Server on {SERVER_HOST}:{SERVER_PORT}")
    print(f"📂 Workspace: {WORKSPACE_DIR}")
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level=LOG_LEVEL)
