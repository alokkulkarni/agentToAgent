"""
MCP Registry Service
Provides service discovery for MCP servers and their tools
"""
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn


# Environment Configuration
REGISTRY_HOST = os.getenv("MCP_REGISTRY_HOST", "0.0.0.0")
REGISTRY_PORT = int(os.getenv("MCP_REGISTRY_PORT", "8200"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")


# Models
class Tool(BaseModel):
    """MCP Tool definition"""
    name: str
    description: str
    input_schema: Dict
    
    
class MCPServer(BaseModel):
    """MCP Server registration"""
    server_id: Optional[str] = None
    name: str
    description: str
    base_url: str
    tools: List[Tool]
    metadata: Optional[Dict] = Field(default_factory=dict)
    

class MCPServerInfo(MCPServer):
    """MCP Server with registration info"""
    server_id: str
    registered_at: str
    last_heartbeat: str
    status: str = "active"


# In-memory registry
mcp_servers: Dict[str, MCPServerInfo] = {}
tools_index: Dict[str, List[str]] = {}  # tool_name -> [server_ids]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management"""
    # Startup
    print("🚀 MCP Registry Service starting...")
    yield
    # Shutdown
    print("⏹️  MCP Registry Service shutting down...")


# FastAPI App
app = FastAPI(
    title="MCP Registry Service",
    description="Service Discovery for MCP Servers and Tools",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "MCP Registry",
        "status": "running",
        "servers_registered": len(mcp_servers),
        "tools_available": len(tools_index)
    }


@app.post("/api/mcp/register", response_model=MCPServerInfo)
async def register_server(server: MCPServer):
    """Register an MCP server and its tools"""
    server_id = server.server_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    server_info = MCPServerInfo(
        server_id=server_id,
        name=server.name,
        description=server.description,
        base_url=server.base_url,
        tools=server.tools,
        metadata=server.metadata or {},
        registered_at=now,
        last_heartbeat=now,
        status="active"
    )
    
    mcp_servers[server_id] = server_info
    
    # Index tools
    for tool in server.tools:
        if tool.name not in tools_index:
            tools_index[tool.name] = []
        if server_id not in tools_index[tool.name]:
            tools_index[tool.name].append(server_id)
    
    print(f"✓ MCP Server registered: {server.name} ({server_id})")
    print(f"  Tools: {[t.name for t in server.tools]}")
    
    return server_info


@app.put("/api/mcp/heartbeat/{server_id}")
async def heartbeat(server_id: str):
    """Update server heartbeat"""
    if server_id not in mcp_servers:
        raise HTTPException(status_code=404, detail="Server not found")
    
    mcp_servers[server_id].last_heartbeat = datetime.now(timezone.utc).isoformat()
    mcp_servers[server_id].status = "active"
    
    return {"status": "ok", "server_id": server_id}


@app.delete("/api/mcp/unregister/{server_id}")
async def unregister_server(server_id: str):
    """Unregister an MCP server"""
    if server_id not in mcp_servers:
        raise HTTPException(status_code=404, detail="Server not found")
    
    server = mcp_servers[server_id]
    
    # Remove from tools index
    for tool in server.tools:
        if tool.name in tools_index:
            tools_index[tool.name] = [sid for sid in tools_index[tool.name] if sid != server_id]
            if not tools_index[tool.name]:
                del tools_index[tool.name]
    
    del mcp_servers[server_id]
    
    print(f"✓ MCP Server unregistered: {server.name} ({server_id})")
    
    return {"status": "unregistered", "server_id": server_id}


@app.get("/api/mcp/servers", response_model=List[MCPServerInfo])
async def list_servers(status: Optional[str] = None):
    """List all registered MCP servers"""
    servers = list(mcp_servers.values())
    
    if status:
        servers = [s for s in servers if s.status == status]
    
    return servers


@app.get("/api/mcp/servers/{server_id}", response_model=MCPServerInfo)
async def get_server(server_id: str):
    """Get specific MCP server details"""
    if server_id not in mcp_servers:
        raise HTTPException(status_code=404, detail="Server not found")
    
    return mcp_servers[server_id]


@app.get("/api/mcp/tools")
async def list_tools():
    """List all available tools across all servers"""
    tools_list = []
    
    for server in mcp_servers.values():
        for tool in server.tools:
            tools_list.append({
                "tool_name": tool.name,
                "description": tool.description,
                "server_id": server.server_id,
                "server_name": server.name,
                "server_url": server.base_url
            })
    
    return {"total_tools": len(tools_list), "tools": tools_list}


@app.get("/api/mcp/tools/{tool_name}")
async def find_tool(tool_name: str):
    """Find servers that provide a specific tool"""
    if tool_name not in tools_index:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    server_ids = tools_index[tool_name]
    servers = []
    
    for server_id in server_ids:
        server = mcp_servers.get(server_id)
        if server and server.status == "active":
            tool_info = next((t for t in server.tools if t.name == tool_name), None)
            servers.append({
                "server_id": server.server_id,
                "server_name": server.name,
                "server_url": server.base_url,
                "tool": tool_info
            })
    
    return {
        "tool_name": tool_name,
        "servers_available": len(servers),
        "servers": servers
    }


@app.get("/api/mcp/discovery")
async def discover_capabilities():
    """Discover all capabilities in the MCP ecosystem"""
    return {
        "total_servers": len(mcp_servers),
        "active_servers": len([s for s in mcp_servers.values() if s.status == "active"]),
        "total_tools": sum(len(s.tools) for s in mcp_servers.values()),
        "tool_categories": list(tools_index.keys()),
        "servers": [
            {
                "name": s.name,
                "server_id": s.server_id,
                "tools": [t.name for t in s.tools],
                "status": s.status
            }
            for s in mcp_servers.values()
        ]
    }


if __name__ == "__main__":
    uvicorn.run(app, host=REGISTRY_HOST, port=REGISTRY_PORT, log_level=LOG_LEVEL)
