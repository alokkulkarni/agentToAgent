"""
Demo Workflow
Demonstrates the A2A agent system capabilities
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.utils import setup_logging
setup_logging()

from src.config import settings
from src.core import AgentRegistry, MessageBus, MessageType, TaskRequest
from src.orchestrator.orchestrator import OrchestratorAgent
from src.agents import (
    ObserverAgent,
    CodeAnalyzerAgent,
    DataProcessorAgent,
    ResearchAgent,
    TaskExecutorAgent
)
import structlog

logger = structlog.get_logger()


async def demo_workflow():
    """Run a demonstration workflow"""
    
    logger.info("=" * 60)
    logger.info("Starting A2A Demo Workflow")
    logger.info("=" * 60)
    
    # Validate settings
    if not settings.validate():
        logger.error("Configuration validation failed - check your .env file")
        return
    
    # Initialize system
    registry = AgentRegistry()
    message_bus = MessageBus()
    
    # Create agents
    logger.info("Initializing agents...")
    
    orchestrator = OrchestratorAgent("DemoOrchestrator", registry, message_bus)
    observer = ObserverAgent("DemoObserver", registry, message_bus)
    code_analyzer = CodeAnalyzerAgent("DemoCodeAnalyzer", registry, message_bus)
    data_processor = DataProcessorAgent("DemoDataProcessor", registry, message_bus)
    research_agent = ResearchAgent("DemoResearch", registry, message_bus)
    task_executor = TaskExecutorAgent("DemoExecutor", registry, message_bus)
    
    agents = [orchestrator, observer, code_analyzer, data_processor, research_agent, task_executor]
    
    # Start all agents
    logger.info("Starting agents...")
    for agent in agents:
        await agent.start()
    
    await asyncio.sleep(2)  # Let agents register
    
    try:
        # Demo 1: Simple Code Analysis (No LLM)
        logger.info("\n" + "=" * 60)
        logger.info("Demo 1: Python Code Analysis")
        logger.info("=" * 60)
        
        sample_code = """
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

class Calculator:
    def add(self, a, b):
        return a + b
    
    def multiply(self, a, b):
        return a * b
"""
        
        task = TaskRequest(
            capability="analyze_python_code",
            parameters={"code": sample_code}
        )
        
        # Send task to code analyzer
        await orchestrator.send_to(
            receiver_id=code_analyzer.agent_id,
            message_type=MessageType.TASK_REQUEST,
            payload={"task": task.model_dump()}
        )
        
        await asyncio.sleep(3)
        
        # Demo 2: Code Explanation (Uses LLM)
        logger.info("\n" + "=" * 60)
        logger.info("Demo 2: Code Explanation with LLM")
        logger.info("=" * 60)
        
        task = TaskRequest(
            capability="explain_code",
            parameters={"code": sample_code}
        )
        
        await orchestrator.send_to(
            receiver_id=code_analyzer.agent_id,
            message_type=MessageType.TASK_REQUEST,
            payload={"task": task.model_dump()}
        )
        
        await asyncio.sleep(5)
        
        # Demo 3: Research Question (Uses LLM)
        logger.info("\n" + "=" * 60)
        logger.info("Demo 3: Research Question with LLM")
        logger.info("=" * 60)
        
        task = TaskRequest(
            capability="answer_question",
            parameters={
                "question": "What is the Agent-to-Agent (A2A) protocol and why is it useful?",
                "context": "We're building a multi-agent system"
            }
        )
        
        await orchestrator.send_to(
            receiver_id=research_agent.agent_id,
            message_type=MessageType.TASK_REQUEST,
            payload={"task": task.model_dump()}
        )
        
        await asyncio.sleep(5)
        
        # Demo 4: Data Analysis (Uses LLM)
        logger.info("\n" + "=" * 60)
        logger.info("Demo 4: Data Analysis with LLM")
        logger.info("=" * 60)
        
        sample_data = {
            "sales": [100, 150, 200, 180, 220, 250],
            "months": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
            "region": "North America"
        }
        
        task = TaskRequest(
            capability="analyze_data",
            parameters={"data": sample_data}
        )
        
        await orchestrator.send_to(
            receiver_id=data_processor.agent_id,
            message_type=MessageType.TASK_REQUEST,
            payload={"task": task.model_dump()}
        )
        
        await asyncio.sleep(5)
        
        # Demo 5: Orchestrated Workflow (Complex)
        logger.info("\n" + "=" * 60)
        logger.info("Demo 5: Orchestrated Workflow")
        logger.info("=" * 60)
        
        workflow_task = TaskRequest(
            capability="orchestrate_workflow",
            parameters={
                "task_description": "Analyze Python code, explain it, and suggest improvements"
            },
            context={"code": sample_code}
        )
        
        await orchestrator.execute_task(workflow_task)
        
        # Demo 6: System Metrics
        logger.info("\n" + "=" * 60)
        logger.info("Demo 6: System Metrics from Observer")
        logger.info("=" * 60)
        
        metrics = await observer.get_live_metrics()
        logger.info("System Metrics", metrics=metrics)
        
        logger.info("\n" + "=" * 60)
        logger.info("Demo Completed Successfully!")
        logger.info("=" * 60)
        
    finally:
        # Cleanup
        logger.info("\nShutting down agents...")
        for agent in agents:
            await agent.stop()
        
        logger.info("Demo workflow completed")


if __name__ == "__main__":
    try:
        asyncio.run(demo_workflow())
    except KeyboardInterrupt:
        logger.info("Demo interrupted by user")
    except Exception as e:
        logger.error("Demo failed", error=str(e), exc_info=True)
