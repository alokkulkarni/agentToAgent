"""
Basic tests for A2A system
"""
import pytest
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_imports():
    """Test that all modules can be imported"""
    # These should import without errors (settings validation will fail without .env)
    from src.core import protocol
    from src.core import registry
    from src.core import communication
    
    assert protocol.MessageType.TASK_REQUEST == "task_request"
    assert protocol.AgentRole.ORCHESTRATOR == "orchestrator"


def test_protocol_models():
    """Test protocol models"""
    from src.core import AgentCapability, TaskRequest, TaskStatus
    
    capability = AgentCapability(
        name="test_cap",
        description="Test capability"
    )
    
    assert capability.name == "test_cap"
    assert capability.version == "1.0.0"
    
    task = TaskRequest(
        capability="test_cap",
        parameters={"key": "value"}
    )
    
    assert task.capability == "test_cap"
    assert task.priority == 5  # default


@pytest.mark.asyncio
async def test_registry():
    """Test agent registry"""
    from src.core import AgentRegistry, AgentMetadata, AgentRole, AgentCapability
    
    registry = AgentRegistry(heartbeat_timeout=30)
    
    metadata = AgentMetadata(
        name="TestAgent",
        role=AgentRole.WORKER,
        capabilities=[
            AgentCapability(name="test", description="Test")
        ]
    )
    
    # Register agent
    success = await registry.register(metadata)
    assert success
    
    # Get agent
    agent = await registry.get_agent(metadata.agent_id)
    assert agent is not None
    assert agent.name == "TestAgent"
    
    # Find by role
    agents = await registry.find_agents_by_role(AgentRole.WORKER)
    assert len(agents) == 1
    
    # Unregister
    success = await registry.unregister(metadata.agent_id)
    assert success


@pytest.mark.asyncio
async def test_message_bus():
    """Test message bus"""
    from src.core import MessageBus, A2AMessage, MessageType
    
    bus = MessageBus()
    
    received_messages = []
    
    async def handler(message):
        received_messages.append(message)
    
    # Subscribe
    await bus.subscribe("agent1", handler)
    
    # Publish message
    message = A2AMessage(
        message_type=MessageType.EVENT,
        sender_id="sender",
        receiver_id="agent1",
        payload={"test": "data"}
    )
    
    success = await bus.publish(message)
    assert success
    
    # Give async tasks time to process
    import asyncio
    await asyncio.sleep(0.1)
    
    # Check handler was called
    assert len(received_messages) == 1
    assert received_messages[0].payload["test"] == "data"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
