"""
Registry Service - Standalone Agent Registry
FastAPI service for agent discovery and registration
"""
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import asyncio
from contextlib import asynccontextmanager

from shared.a2a_protocol import (
    AgentMetadata, AgentRole,
    RegistrationRequest, RegistrationResponse,
    DiscoveryResponse
)


# In-memory storage
agents: Dict[str, AgentMetadata] = {}
capabilities_index: Dict[str, List[str]] = {}
role_index: Dict[AgentRole, List[str]] = {role: [] for role in AgentRole}
last_heartbeat: Dict[str, datetime] = {}

HEARTBEAT_TIMEOUT = 60  # seconds


async def cleanup_stale_agents():
    """Periodically cleanup stale agents"""
    while True:
        await asyncio.sleep(30)
        current_time = datetime.utcnow()
        timeout = timedelta(seconds=HEARTBEAT_TIMEOUT)
        
        stale = [
            agent_id for agent_id, last_hb in last_heartbeat.items()
            if current_time - last_hb > timeout
        ]
        
        for agent_id in stale:
            if agent_id in agents:
                print(f"Removing stale agent: {agent_id}")
                await unregister_agent_internal(agent_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management"""
    # Startup
    print("Registry Service starting...")
    cleanup_task = asyncio.create_task(cleanup_stale_agents())
    yield
    # Shutdown
    print("Registry Service shutting down...")
    cleanup_task.cancel()


app = FastAPI(
    title="A2A Registry Service",
    description="Agent Registry for A2A Multi-Agent System",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "A2A Registry Service",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "agents_registered": len(agents),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/api/registry/register")
async def register_agent(request: RegistrationRequest) -> RegistrationResponse:
    """Register a new agent"""
    metadata = request.metadata
    agent_id = metadata.agent_id
    
    # Store agent
    agents[agent_id] = metadata
    last_heartbeat[agent_id] = datetime.utcnow()
    
    # Update role index
    if agent_id not in role_index[metadata.role]:
        role_index[metadata.role].append(agent_id)
    
    # Update capability index
    for capability in metadata.capabilities:
        cap_name = capability.name
        if cap_name not in capabilities_index:
            capabilities_index[cap_name] = []
        if agent_id not in capabilities_index[cap_name]:
            capabilities_index[cap_name].append(agent_id)
    
    print(f"Agent registered: {metadata.name} ({agent_id}) - Role: {metadata.role.value}")
    print(f"  Capabilities: {[c.name for c in metadata.capabilities]}")
    
    return RegistrationResponse(
        success=True,
        agent_id=agent_id,
        message=f"Agent {metadata.name} registered successfully"
    )


@app.delete("/api/registry/unregister/{agent_id}")
async def unregister_agent(agent_id: str):
    """Unregister an agent"""
    return await unregister_agent_internal(agent_id)


async def unregister_agent_internal(agent_id: str):
    """Internal unregister logic"""
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    metadata = agents[agent_id]
    
    # Remove from role index
    if agent_id in role_index[metadata.role]:
        role_index[metadata.role].remove(agent_id)
    
    # Remove from capability index
    for capability in metadata.capabilities:
        cap_name = capability.name
        if cap_name in capabilities_index and agent_id in capabilities_index[cap_name]:
            capabilities_index[cap_name].remove(agent_id)
            if not capabilities_index[cap_name]:
                del capabilities_index[cap_name]
    
    # Remove agent
    del agents[agent_id]
    if agent_id in last_heartbeat:
        del last_heartbeat[agent_id]
    
    print(f"Agent unregistered: {metadata.name} ({agent_id})")
    
    return {"success": True, "message": f"Agent {agent_id} unregistered"}


@app.post("/api/registry/heartbeat/{agent_id}")
async def heartbeat(agent_id: str):
    """Receive agent heartbeat"""
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    last_heartbeat[agent_id] = datetime.utcnow()
    return {"success": True, "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/registry/discover")
async def discover_agents(
    capability: Optional[str] = None,
    role: Optional[str] = None
) -> DiscoveryResponse:
    """Discover agents by capability or role"""
    result_agents = []
    
    if capability:
        # Find by capability
        agent_ids = capabilities_index.get(capability, [])
        result_agents = [agents[aid] for aid in agent_ids if aid in agents]
    elif role:
        # Find by role
        try:
            agent_role = AgentRole(role)
            agent_ids = role_index.get(agent_role, [])
            result_agents = [agents[aid] for aid in agent_ids if aid in agents]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid role: {role}")
    else:
        # Return all agents
        result_agents = list(agents.values())
    
    return DiscoveryResponse(agents=result_agents)


@app.get("/api/registry/agents")
async def get_all_agents() -> List[AgentMetadata]:
    """Get all registered agents"""
    return list(agents.values())


@app.get("/api/registry/agents/{agent_id}")
async def get_agent(agent_id: str) -> AgentMetadata:
    """Get specific agent"""
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents[agent_id]


@app.get("/api/registry/capabilities")
async def get_capabilities() -> Dict[str, List[str]]:
    """Get all capabilities and their agents"""
    return capabilities_index


@app.get("/api/registry/stats")
async def get_stats():
    """Get registry statistics"""
    return {
        "total_agents": len(agents),
        "total_capabilities": len(capabilities_index),
        "agents_by_role": {
            role.value: len(agent_ids)
            for role, agent_ids in role_index.items()
        },
        "capabilities": list(capabilities_index.keys()),
        "timestamp": datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
