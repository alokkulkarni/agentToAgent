"""
Task Executor Agent - Standalone Service
General-purpose worker for executing various tasks
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio
from typing import Dict, Any
from dotenv import load_dotenv

from shared.a2a_protocol import (
    AgentMetadata, AgentRole, AgentCapability,
    TaskRequest, TaskResponse, TaskStatus,
    A2AClient
)

load_dotenv()

# Configuration
AGENT_NAME = os.getenv("AGENT_NAME", "TaskExecutor")
AGENT_PORT = int(os.getenv("AGENT_PORT", "8004"))
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://localhost:8000")

agent_id = None
agent_metadata = None
registry_client = None


async def register_with_registry():
    """Register this agent with the registry"""
    global agent_id, agent_metadata, registry_client
    
    agent_metadata = AgentMetadata(
        name=AGENT_NAME,
        role=AgentRole.WORKER,
        capabilities=[
            AgentCapability(
                name="execute_command",
                description="Execute system commands (simulated for safety)"
            ),
            AgentCapability(
                name="file_operations",
                description="Perform file operations (read/write)"
            ),
            AgentCapability(
                name="wait_task",
                description="Wait for specified duration (testing)"
            )
        ],
        has_llm=False,
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
    description="Task Executor Agent for A2A System",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    return {
        "service": f"{AGENT_NAME} Agent",
        "agent_id": agent_id,
        "role": "worker",
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
        if task.capability == "execute_command":
            result = await execute_command(task.parameters)
        elif task.capability == "file_operations":
            result = await file_operations(task.parameters)
        elif task.capability == "wait_task":
            result = await wait_task(task.parameters)
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


async def execute_command(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a system command (simulated for safety)"""
    command = parameters.get("command")
    if not command:
        raise ValueError("command parameter is required")
    
    # For safety, this is simulated - not actually executing
    return {
        "command": command,
        "status": "simulated",
        "message": "Command execution is simulated for safety",
        "output": f"Would execute: {command}"
    }


async def file_operations(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Perform file operations"""
    operation = parameters.get("operation")
    file_path = parameters.get("file_path")
    
    if not operation or not file_path:
        raise ValueError("operation and file_path are required")
    
    if operation == "read":
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            return {
                "operation": "read",
                "file_path": file_path,
                "content": content,
                "size_bytes": len(content)
            }
        except Exception as e:
            return {"operation": "read", "error": str(e)}
    
    elif operation == "write":
        content = parameters.get("content", "")
        try:
            with open(file_path, 'w') as f:
                f.write(content)
            return {
                "operation": "write",
                "file_path": file_path,
                "status": "success",
                "bytes_written": len(content)
            }
        except Exception as e:
            return {"operation": "write", "error": str(e)}
    
    else:
        raise ValueError(f"Unknown operation: {operation}")


async def wait_task(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Wait for specified duration"""
    duration = parameters.get("duration", 1)
    await asyncio.sleep(duration)
    return {
        "waited_seconds": duration,
        "status": "completed",
        "message": f"Successfully waited {duration} seconds"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT, log_level="info")
