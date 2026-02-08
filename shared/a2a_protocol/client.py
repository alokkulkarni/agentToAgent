"""
A2A Protocol Client
HTTP client for communicating with Registry and other agents
"""
import httpx
from typing import Optional, List, Dict, Any
from .models import (
    AgentMetadata, RegistrationRequest, RegistrationResponse,
    DiscoveryRequest, DiscoveryResponse, TaskRequest, TaskResponse
)


class A2AClient:
    """Client for A2A protocol communication via HTTP"""
    
    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
    
    # Registry Operations
    
    async def register_agent(self, metadata: AgentMetadata) -> RegistrationResponse:
        """Register agent with registry"""
        url = f"{self.base_url}/api/registry/register"
        request = RegistrationRequest(metadata=metadata)
        
        response = await self.client.post(
            url,
            json=request.model_dump(mode='json')
        )
        response.raise_for_status()
        return RegistrationResponse(**response.json())
    
    async def unregister_agent(self, agent_id: str) -> Dict[str, Any]:
        """Unregister agent from registry"""
        url = f"{self.base_url}/api/registry/unregister/{agent_id}"
        
        response = await self.client.delete(url)
        response.raise_for_status()
        return response.json()
    
    async def heartbeat(self, agent_id: str) -> Dict[str, Any]:
        """Send heartbeat to registry"""
        url = f"{self.base_url}/api/registry/heartbeat/{agent_id}"
        
        response = await self.client.post(url)
        response.raise_for_status()
        return response.json()
    
    async def discover_agents(
        self,
        capability: Optional[str] = None,
        role: Optional[str] = None
    ) -> DiscoveryResponse:
        """Discover agents from registry"""
        url = f"{self.base_url}/api/registry/discover"
        
        params = {}
        if capability:
            params['capability'] = capability
        if role:
            params['role'] = role
        
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return DiscoveryResponse(**response.json())
    
    async def get_all_agents(self) -> List[AgentMetadata]:
        """Get all registered agents"""
        url = f"{self.base_url}/api/registry/agents"
        
        response = await self.client.get(url)
        response.raise_for_status()
        return [AgentMetadata(**agent) for agent in response.json()]
    
    async def get_registry_stats(self) -> Dict[str, Any]:
        """Get registry statistics"""
        url = f"{self.base_url}/api/registry/stats"
        
        response = await self.client.get(url)
        response.raise_for_status()
        return response.json()
    
    # Agent Communication
    
    async def send_task(
        self,
        agent_endpoint: str,
        task: TaskRequest
    ) -> TaskResponse:
        """Send task to an agent"""
        url = f"{agent_endpoint}/api/task"
        
        response = await self.client.post(
            url,
            json=task.model_dump(mode='json')
        )
        response.raise_for_status()
        return TaskResponse(**response.json())
    
    async def get_agent_health(self, agent_endpoint: str) -> Dict[str, Any]:
        """Check agent health"""
        url = f"{agent_endpoint}/health"
        
        response = await self.client.get(url)
        response.raise_for_status()
        return response.json()
