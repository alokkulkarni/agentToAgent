"""
Observer Agent - Standalone Service
Monitors system activity and provides metrics
"""
import os

from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio
from typing import Dict, Any, List
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv

from shared.a2a_protocol import (
    AgentMetadata, AgentRole, AgentCapability,
    TaskRequest, TaskResponse, TaskStatus,
    A2AClient
)

load_dotenv()

# Configuration
AGENT_NAME = os.getenv("AGENT_NAME", "Observer")
AGENT_PORT = int(os.getenv("AGENT_PORT", "8005"))
AGENT_HOST = os.getenv("AGENT_HOST", "localhost")
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://localhost:8000")

agent_id = None
agent_metadata = None
registry_client = None

# Metrics storage
event_counts: Dict[str, int] = defaultdict(int)
task_metrics: Dict[str, List[float]] = defaultdict(list)
agent_activity: Dict[str, int] = defaultdict(int)
events: List[Dict[str, Any]] = []
MAX_EVENTS = 1000


async def register_with_registry():
    """Register this agent with the registry"""
    global agent_id, agent_metadata, registry_client
    
    agent_metadata = AgentMetadata(
        name=AGENT_NAME,
        role=AgentRole.OBSERVER,
        capabilities=[
            AgentCapability(
                name="system_monitoring",
                description="Monitor system activity and metrics"
            ),
            AgentCapability(
                name="event_logging",
                description="Log and retrieve system events"
            ),
            AgentCapability(
                name="metrics_reporting",
                description="Generate system metrics and reports"
            ),
            AgentCapability(
                name="agent_statistics",
                description="Get statistics about agents"
            )
        ],
        has_llm=False,
        endpoint=f"http://{AGENT_HOST}:{AGENT_PORT}"
    )
    
    registry_client = A2AClient(REGISTRY_URL)
    
    try:
        response = await registry_client.register_agent(agent_metadata)
        agent_id = response.agent_id
        print(f"✓ Registered with registry: {agent_id}")
        asyncio.create_task(send_heartbeats())
        asyncio.create_task(monitor_system())
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


async def monitor_system():
    """Periodically collect system metrics"""
    while True:
        await asyncio.sleep(60)  # Every minute
        try:
            stats = await registry_client.get_registry_stats()
            event = {
                "timestamp": datetime.utcnow().isoformat(),
                "type": "system_snapshot",
                "data": stats
            }
            events.append(event)
            if len(events) > MAX_EVENTS:
                events.pop(0)
        except Exception as e:
            print(f"Monitoring error: {e}")


async def unregister_from_registry():
    """Unregister from registry"""
    if registry_client and agent_id:
        try:
            await registry_client.unregister_agent(agent_id)
            await registry_client.close()
            print("✓ Unregistered from registry")
        except Exception as e:
            print(f"✗ Failed to unregister: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management"""
    print(f"Starting {AGENT_NAME} Agent Service...")
    await register_with_registry()
    yield
    print(f"Shutting down {AGENT_NAME} Agent Service...")
    await unregister_from_registry()


app = FastAPI(
    title=f"{AGENT_NAME} Agent Service",
    description="Observer Agent for A2A System",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    return {
        "service": f"{AGENT_NAME} Agent",
        "agent_id": agent_id,
        "role": "observer",
        "status": "running"
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "agent_id": agent_id,
        "capabilities": [c.name for c in agent_metadata.capabilities],
        "events_tracked": len(events)
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
    
    start_time = datetime.utcnow()
    
    try:
        if task.capability == "system_monitoring":
            result = await get_system_status()
        elif task.capability == "event_logging":
            result = await get_recent_events(task.parameters)
        elif task.capability == "metrics_reporting":
            result = await generate_metrics_report()
        elif task.capability == "agent_statistics":
            result = await get_agent_statistics()
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


async def get_system_status() -> Dict[str, Any]:
    """Get current system status"""
    registry_stats = await registry_client.get_registry_stats()
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "registry": registry_stats,
        "observer_metrics": {
            "total_events_tracked": len(events),
            "events_by_type": dict(event_counts),
        }
    }


async def get_recent_events(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Get recent events"""
    limit = parameters.get("limit", 50)
    event_type = parameters.get("event_type")
    
    recent = events[-limit:]
    
    if event_type:
        recent = [e for e in recent if e.get("type") == event_type]
    
    return {
        "events": recent,
        "total": len(recent),
        "limit": limit
    }


async def generate_metrics_report() -> Dict[str, Any]:
    """Generate metrics report"""
    agents = await registry_client.get_all_agents()
    
    agent_summary = []
    for agent in agents:
        agent_summary.append({
            "agent_id": agent.agent_id,
            "name": agent.name,
            "role": agent.role.value,
            "capabilities": [c.name for c in agent.capabilities],
            "has_llm": agent.has_llm
        })
    
    return {
        "report_timestamp": datetime.utcnow().isoformat(),
        "summary": {
            "total_agents": len(agents),
            "total_events": len(events),
            "llm_enabled_agents": sum(1 for a in agents if a.has_llm)
        },
        "agents": agent_summary
    }


async def get_agent_statistics() -> Dict[str, Any]:
    """Get detailed agent statistics"""
    agents = await registry_client.get_all_agents()
    capabilities = await registry_client.get_all_capabilities()
    
    role_distribution = defaultdict(int)
    for agent in agents:
        role_distribution[agent.role.value] += 1
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "total_agents": len(agents),
        "total_capabilities": len(capabilities),
        "role_distribution": dict(role_distribution),
        "capability_coverage": {
            cap: len(agent_ids)
            for cap, agent_ids in capabilities.items()
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT, log_level="info")
