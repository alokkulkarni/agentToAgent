"""
Conversation and context management for workflows
"""
from datetime import datetime
from typing import Dict, List, Any, Optional
import logging

from models import (
    WorkflowContext, ConversationMessage, ThoughtTrailEntry,
    MessageRole, MessageType
)
from database import WorkflowDatabase

logger = logging.getLogger(__name__)


class ConversationManager:
    """Manages conversation history and thought trails for workflows"""
    
    def __init__(self, db: WorkflowDatabase):
        self.db = db
    
    def get_or_create_context(self, workflow_id: str, task_description: str) -> WorkflowContext:
        """Get existing workflow context or create new one"""
        context = self.db.get_workflow_context(workflow_id)
        
        if not context:
            context = WorkflowContext(
                workflow_id=workflow_id,
                original_task=task_description
            )
            
            # Add initial message
            context.add_message(
                role=MessageRole.USER,
                message_type=MessageType.TASK,
                content=task_description
            )
            self.db.save_message(context.conversation[-1])
        
        return context
    
    def add_orchestrator_thought(
        self,
        workflow_id: str,
        thought: str,
        thought_type: str = "reasoning",
        **metadata
    ):
        """Add orchestrator's thought to trail"""
        context = self.db.get_workflow_context(workflow_id)
        if context:
            context.add_thought(
                thought_type=thought_type,
                content=thought,
                agent="orchestrator",
                **metadata
            )
            self.db.save_thought(workflow_id, context.thought_trail[-1])
            logger.debug(f"Orchestrator thought: {thought}")
    
    def add_agent_message(
        self,
        workflow_id: str,
        agent_name: str,
        message: str,
        message_type: MessageType = MessageType.MESSAGE,
        **metadata
    ):
        """Add agent message to conversation"""
        context = self.db.get_workflow_context(workflow_id)
        if context:
            context.add_message(
                role=MessageRole.AGENT,
                message_type=message_type,
                content=message,
                agent=agent_name,
                **metadata
            )
            self.db.save_message(context.conversation[-1])
            logger.debug(f"{agent_name}: {message}")
    
    def add_user_message(
        self,
        workflow_id: str,
        message: str,
        message_type: MessageType = MessageType.RESPONSE,
        **metadata
    ):
        """Add user message to conversation"""
        context = self.db.get_workflow_context(workflow_id)
        if context:
            context.add_message(
                role=MessageRole.USER,
                message_type=message_type,
                content=message,
                **metadata
            )
            self.db.save_message(context.conversation[-1])
            logger.debug(f"User: {message}")
    
    def reconstruct_context_for_agent(
        self,
        workflow_id: str,
        step_id: str,
        include_thoughts: bool = True
    ) -> Dict[str, Any]:
        """
        Reconstruct full context for agent resuming execution
        
        Returns dict with:
        - original_task
        - conversation_history
        - thought_trail
        - previous_step_results
        - current_step_info
        - user_responses (if any)
        """
        context = self.db.get_workflow_context(workflow_id)
        workflow = self.db.get_workflow(workflow_id)
        
        if not context or not workflow:
            return {}
        
        # Get all completed steps
        steps = self.db.get_workflow_steps(workflow_id)
        completed_steps = [s for s in steps if s.status.value == "completed"]
        
        reconstructed = {
            "workflow_id": workflow_id,
            "original_task": context.original_task,
            "conversation_history": context.get_conversation_history(),
            "previous_step_results": {
                f"step_{s.step_number}": s.result
                for s in completed_steps
            },
            "variables": context.variables
        }
        
        if include_thoughts:
            reconstructed["thought_trail"] = context.get_thought_summary()
        
        # Find user responses
        user_messages = [
            msg for msg in context.conversation
            if msg.role == MessageRole.USER and msg.message_type == MessageType.RESPONSE
        ]
        if user_messages:
            reconstructed["user_responses"] = [
                {
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                    "metadata": msg.metadata
                }
                for msg in user_messages
            ]
        
        # Current step info
        current_step = next((s for s in steps if s.step_id == step_id), None)
        if current_step:
            reconstructed["current_step"] = {
                "step_number": current_step.step_number,
                "capability": current_step.capability,
                "parameters": current_step.parameters,
                "retry_count": current_step.retry_count
            }
        
        return reconstructed
    
    def get_conversation_summary(self, workflow_id: str, max_messages: int = 10) -> str:
        """Get formatted conversation summary"""
        context = self.db.get_workflow_context(workflow_id)
        if not context:
            return ""
        
        messages = context.conversation[-max_messages:]
        
        summary_lines = []
        for msg in messages:
            role = msg.role.value.upper()
            timestamp = msg.timestamp.strftime("%H:%M:%S")
            
            if msg.role == MessageRole.AGENT:
                agent = msg.metadata.get('agent', 'Unknown')
                summary_lines.append(f"[{timestamp}] {agent}: {msg.content}")
            else:
                summary_lines.append(f"[{timestamp}] {role}: {msg.content}")
        
        return "\n".join(summary_lines)
    
    def get_thought_trail_summary(self, workflow_id: str, max_thoughts: int = 20) -> str:
        """Get formatted thought trail summary"""
        context = self.db.get_workflow_context(workflow_id)
        if not context:
            return ""
        
        thoughts = context.thought_trail[-max_thoughts:]
        
        summary_lines = []
        for thought in thoughts:
            timestamp = thought.timestamp.strftime("%H:%M:%S")
            agent = thought.agent or "orchestrator"
            thought_type = thought.thought_type.upper()
            
            summary_lines.append(f"[{timestamp}] [{agent}] [{thought_type}] {thought.content}")
        
        return "\n".join(summary_lines)
    
    def format_context_for_llm(
        self,
        workflow_id: str,
        include_full_conversation: bool = False
    ) -> str:
        """
        Format workflow context for LLM prompt
        
        Returns formatted string with:
        - Original task
        - Key conversation points
        - Thought process
        - Current state
        """
        context = self.db.get_workflow_context(workflow_id)
        workflow = self.db.get_workflow(workflow_id)
        
        if not context or not workflow:
            return ""
        
        output = []
        output.append(f"=== WORKFLOW CONTEXT ===")
        output.append(f"Original Task: {context.original_task}")
        output.append(f"Status: {workflow.status.value}")
        output.append(f"Progress: {workflow.completed_steps}/{workflow.total_steps} steps")
        output.append("")
        
        # Conversation
        if include_full_conversation:
            output.append("=== FULL CONVERSATION ===")
            output.append(self.get_conversation_summary(workflow_id, max_messages=100))
        else:
            output.append("=== RECENT CONVERSATION ===")
            output.append(self.get_conversation_summary(workflow_id, max_messages=5))
        output.append("")
        
        # Thought trail
        output.append("=== THOUGHT PROCESS ===")
        output.append(self.get_thought_trail_summary(workflow_id, max_thoughts=10))
        output.append("")
        
        # Pending interaction
        if context.pending_interaction:
            output.append("=== PENDING INTERACTION ===")
            output.append(f"Question: {context.pending_interaction.question}")
            if context.pending_interaction.reasoning:
                output.append(f"Reasoning: {context.pending_interaction.reasoning}")
            output.append("")
        
        return "\n".join(output)
    
    def save_variable(self, workflow_id: str, key: str, value: Any):
        """Save a variable to workflow context"""
        workflow = self.db.get_workflow(workflow_id)
        if workflow:
            if 'variables' not in workflow.workflow_context:
                workflow.workflow_context['variables'] = {}
            workflow.workflow_context['variables'][key] = value
            self.db.save_workflow(workflow)
    
    def get_variable(self, workflow_id: str, key: str, default: Any = None) -> Any:
        """Get a variable from workflow context"""
        workflow = self.db.get_workflow(workflow_id)
        if workflow and 'variables' in workflow.workflow_context:
            return workflow.workflow_context['variables'].get(key, default)
        return default
