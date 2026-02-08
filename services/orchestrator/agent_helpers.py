"""
Helper utilities for agents to request user input and maintain context
"""
from typing import Optional, List, Dict, Any
from datetime import datetime

from .models import InputType


class AgentInteractionHelper:
    """
    Helper class for agents to easily request user input
    
    Usage in agent:
        helper = AgentInteractionHelper(workflow_id, step_id, agent_name)
        
        response = await helper.ask_single_choice(
            question="Which priority?",
            options=["High", "Medium", "Low"],
            reasoning="Found multiple issues"
        )
    """
    
    def __init__(self, workflow_id: str, step_id: str, agent_name: str):
        self.workflow_id = workflow_id
        self.step_id = step_id
        self.agent_name = agent_name
    
    def request_input(
        self,
        question: str,
        input_type: str,
        options: Optional[List[str]] = None,
        reasoning: Optional[str] = None,
        context: Optional[Dict] = None,
        default_value: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Create an interaction request
        
        Returns a special response that orchestrator will recognize
        """
        return {
            "status": "user_input_required",
            "interaction_request": {
                "question": question,
                "input_type": input_type,
                "options": options,
                "reasoning": reasoning,
                "context": context or {},
                "default_value": default_value,
                "requested_by": self.agent_name,
                "step_id": self.step_id
            },
            "partial_results": None  # Agent can include partial work here
        }
    
    def ask_text(
        self,
        question: str,
        reasoning: Optional[str] = None,
        placeholder: Optional[str] = None
    ) -> Dict[str, Any]:
        """Request free-form text input from user"""
        context = {}
        if placeholder:
            context['placeholder'] = placeholder
        
        return self.request_input(
            question=question,
            input_type="text",
            reasoning=reasoning,
            context=context
        )
    
    def ask_single_choice(
        self,
        question: str,
        options: List[str],
        reasoning: Optional[str] = None,
        default: Optional[str] = None
    ) -> Dict[str, Any]:
        """Request user to select one option from a list"""
        return self.request_input(
            question=question,
            input_type="single_choice",
            options=options,
            reasoning=reasoning,
            default_value=default
        )
    
    def ask_multiple_choice(
        self,
        question: str,
        options: List[str],
        reasoning: Optional[str] = None,
        min_selections: int = 1,
        max_selections: Optional[int] = None
    ) -> Dict[str, Any]:
        """Request user to select multiple options from a list"""
        context = {
            "min_selections": min_selections
        }
        if max_selections:
            context["max_selections"] = max_selections
        
        return self.request_input(
            question=question,
            input_type="multiple_choice",
            options=options,
            reasoning=reasoning,
            context=context
        )
    
    def ask_confirmation(
        self,
        question: str,
        reasoning: Optional[str] = None,
        default: bool = False
    ) -> Dict[str, Any]:
        """Request yes/no/cancel confirmation from user"""
        return self.request_input(
            question=question,
            input_type="confirmation",
            options=["yes", "no", "cancel"],
            reasoning=reasoning,
            default_value="yes" if default else "no"
        )
    
    def ask_structured_data(
        self,
        question: str,
        schema: Dict[str, Any],
        reasoning: Optional[str] = None,
        example: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Request structured data (JSON) from user"""
        context = {
            "schema": schema
        }
        if example:
            context["example"] = example
        
        return self.request_input(
            question=question,
            input_type="structured_data",
            reasoning=reasoning,
            context=context
        )


def is_interaction_request(result: Any) -> bool:
    """Check if agent result is an interaction request"""
    return (
        isinstance(result, dict) and
        result.get("status") == "user_input_required" and
        "interaction_request" in result
    )


def extract_interaction_request(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract interaction request from agent result"""
    if is_interaction_request(result):
        return result["interaction_request"]
    return None


def create_context_for_resume(
    original_task: str,
    conversation_history: List[Dict],
    thought_trail: List[str],
    previous_results: Dict[str, Any],
    user_response: Any,
    user_context: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create enriched context for agent when resuming after user input
    
    This provides the agent with complete context to continue seamlessly
    """
    return {
        "original_task": original_task,
        "conversation_history": conversation_history,
        "thought_trail": thought_trail,
        "previous_results": previous_results,
        "user_response": {
            "value": user_response,
            "additional_context": user_context,
            "timestamp": datetime.now().isoformat()
        },
        "resume_instruction": (
            f"You previously asked for user input and received response: {user_response}. "
            f"Continue your work from where you paused, incorporating the user's feedback."
        )
    }


def format_conversation_for_agent(conversation: List[Dict]) -> str:
    """Format conversation history for agent LLM prompt"""
    lines = []
    lines.append("=== CONVERSATION HISTORY ===")
    
    for msg in conversation:
        role = msg.get('role', '').upper()
        msg_type = msg.get('type', '')
        content = msg.get('content', '')
        timestamp = msg.get('timestamp', '')
        
        if role == 'AGENT':
            agent = msg.get('agent', 'Unknown Agent')
            lines.append(f"[{timestamp}] {agent}: {content}")
        elif role == 'USER':
            lines.append(f"[{timestamp}] USER: {content}")
        elif role == 'ORCHESTRATOR':
            lines.append(f"[{timestamp}] SYSTEM: {content}")
    
    return "\n".join(lines)


def format_thought_trail_for_agent(thoughts: List[str]) -> str:
    """Format thought trail for agent LLM prompt"""
    lines = []
    lines.append("=== YOUR PREVIOUS THOUGHTS ===")
    
    for i, thought in enumerate(thoughts, 1):
        lines.append(f"{i}. {thought}")
    
    return "\n".join(lines)


def create_resume_prompt(
    agent_name: str,
    original_task: str,
    conversation: List[Dict],
    thoughts: List[str],
    user_response: Any,
    current_step_description: str
) -> str:
    """
    Create a comprehensive prompt for agent resuming after user input
    
    This helps maintain the agent's "thought line" and context
    """
    prompt_parts = []
    
    prompt_parts.append(f"You are {agent_name}. You were working on a task and needed user input.")
    prompt_parts.append("")
    prompt_parts.append(f"ORIGINAL TASK: {original_task}")
    prompt_parts.append("")
    
    if conversation:
        prompt_parts.append(format_conversation_for_agent(conversation))
        prompt_parts.append("")
    
    if thoughts:
        prompt_parts.append(format_thought_trail_for_agent(thoughts))
        prompt_parts.append("")
    
    prompt_parts.append("=== USER RESPONSE ===")
    prompt_parts.append(f"The user responded: {user_response}")
    prompt_parts.append("")
    
    prompt_parts.append("=== CONTINUE YOUR WORK ===")
    prompt_parts.append(f"Now continue with: {current_step_description}")
    prompt_parts.append("")
    prompt_parts.append("Remember:")
    prompt_parts.append("- You have full context of what you were doing")
    prompt_parts.append("- The user's response should guide your next steps")
    prompt_parts.append("- Maintain coherence with your previous reasoning")
    prompt_parts.append("- If you need more clarification, you can ask again")
    
    return "\n".join(prompt_parts)
