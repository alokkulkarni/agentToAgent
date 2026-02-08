"""
Shared interaction helper for agents to request user input during execution

This module provides a simple interface for agents to:
- Request user input (text, choices, confirmations)
- Return properly formatted interaction requests
- Check if workflow context includes user responses
"""
from typing import Optional, List, Dict, Any


class AgentInteractionHelper:
    """
    Helper class for agents to easily request user input during workflow execution
    
    Usage:
        helper = AgentInteractionHelper(task_request)
        
        # Request user choice
        if need_user_guidance:
            return helper.ask_single_choice(
                question="Which approach should I use?",
                options=["Approach A", "Approach B"],
                reasoning="Both approaches have trade-offs"
            )
        
        # Check if user already responded
        user_choice = helper.get_user_response()
        if user_choice:
            # Continue with user's choice
            proceed_with(user_choice)
    """
    
    def __init__(self, task_request: Dict[str, Any]):
        """
        Initialize helper with task request context
        
        Args:
            task_request: The task request dict from orchestrator
        """
        self.task_request = task_request
        
        # Extract context from task request
        self.context = task_request.get("context", {})
        
        # Try to get workflow_id, step_id, agent_name from direct params or context
        self.workflow_id = task_request.get("workflow_id") or self.context.get("workflow_id")
        self.step_id = task_request.get("step_id") or self.context.get("step_id") or f"step_{self.context.get('step_number', 0)}"
        self.agent_name = task_request.get("agent_name") or self.context.get("agent_name")
        
        self.conversation_history = self.context.get("conversation_history", [])
        self.thought_trail = self.context.get("thought_trail", [])
        self.previous_results = self.context.get("previous_step_results", {})
        self.user_responses = self.context.get("user_responses", [])
    
    def request_input(
        self,
        question: str,
        input_type: str,
        options: Optional[List[str]] = None,
        reasoning: Optional[str] = None,
        context: Optional[Dict] = None,
        default_value: Optional[Any] = None,
        partial_results: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Create an interaction request that orchestrator will recognize
        
        Args:
            question: Question to ask the user
            input_type: Type of input (text, single_choice, multiple_choice, confirmation, etc.)
            options: List of options for choice types
            reasoning: Explanation of why input is needed
            context: Additional context for the question
            default_value: Default value if user doesn't respond
            partial_results: Any partial work completed so far
        
        Returns:
            Dict formatted as interaction request
        """
        return {
            "status": "user_input_required",
            "interaction_request": {
                "workflow_id": self.workflow_id,
                "step_id": self.step_id,
                "agent_name": self.agent_name,
                "question": question,
                "input_type": input_type,
                "options": options,
                "reasoning": reasoning,
                "context": context or {},
                "default_value": default_value
            },
            "partial_results": partial_results,
            "message": f"Agent {self.agent_name} is requesting user input: {question}"
        }
    
    def ask_text(
        self,
        question: str,
        reasoning: Optional[str] = None,
        placeholder: Optional[str] = None,
        partial_results: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Request free-form text input from user"""
        context = {}
        if placeholder:
            context['placeholder'] = placeholder
        
        return self.request_input(
            question=question,
            input_type="text",
            reasoning=reasoning,
            context=context,
            partial_results=partial_results
        )
    
    def ask_single_choice(
        self,
        question: str,
        options: List[str],
        reasoning: Optional[str] = None,
        default: Optional[str] = None,
        partial_results: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Request user to select one option from a list"""
        return self.request_input(
            question=question,
            input_type="single_choice",
            options=options,
            reasoning=reasoning,
            default_value=default,
            partial_results=partial_results
        )
    
    def ask_multiple_choice(
        self,
        question: str,
        options: List[str],
        reasoning: Optional[str] = None,
        min_selections: int = 1,
        max_selections: Optional[int] = None,
        partial_results: Optional[Dict] = None
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
            context=context,
            partial_results=partial_results
        )
    
    def ask_confirmation(
        self,
        question: str,
        reasoning: Optional[str] = None,
        default: bool = False,
        partial_results: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Request yes/no/cancel confirmation from user"""
        return self.request_input(
            question=question,
            input_type="confirmation",
            options=["yes", "no", "cancel"],
            reasoning=reasoning,
            default_value="yes" if default else "no",
            partial_results=partial_results
        )
    
    def ask_structured_data(
        self,
        question: str,
        schema: Dict[str, Any],
        reasoning: Optional[str] = None,
        example: Optional[Dict] = None,
        partial_results: Optional[Dict] = None
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
            context=context,
            partial_results=partial_results
        )
    
    def has_user_response(self) -> bool:
        """Check if user has already responded to a previous interaction"""
        return len(self.user_responses) > 0
    
    def get_user_response(self, index: int = -1) -> Optional[Any]:
        """
        Get user's response from context
        
        Args:
            index: Which response to get (default: most recent)
        
        Returns:
            User's response value or None
        """
        if not self.user_responses:
            return None
        
        try:
            response = self.user_responses[index]
            return response.get('content') or response.get('value')
        except (IndexError, KeyError):
            return None
    
    def get_latest_user_message(self) -> Optional[str]:
        """Get the most recent user message from conversation"""
        for msg in reversed(self.conversation_history):
            if msg.get('role') == 'user' and msg.get('type') == 'response':
                return msg.get('content')
        return None
    
    def get_conversation_summary(self, max_messages: int = 5) -> str:
        """Get formatted conversation summary"""
        recent = self.conversation_history[-max_messages:]
        lines = []
        for msg in recent:
            role = msg.get('role', '').upper()
            content = msg.get('content', '')
            lines.append(f"{role}: {content}")
        return "\n".join(lines)
    
    def get_thought_summary(self) -> List[str]:
        """Get list of previous thoughts/reasoning"""
        return self.thought_trail
    
    def was_resumed(self) -> bool:
        """Check if this execution is a resume from user interaction"""
        return self.has_user_response() or 'resume_instruction' in self.context


def is_interaction_request(result: Any) -> bool:
    """
    Check if agent result is an interaction request
    
    Args:
        result: Result returned from agent
    
    Returns:
        True if result is an interaction request
    """
    return (
        isinstance(result, dict) and
        result.get("status") == "user_input_required" and
        "interaction_request" in result
    )


def extract_user_response_from_task(task_request: Dict[str, Any]) -> Optional[Any]:
    """
    Extract user's response from task request context
    
    Args:
        task_request: Task request from orchestrator
    
    Returns:
        User's response or None
    """
    context = task_request.get("context", {})
    user_responses = context.get("user_responses", [])
    
    if user_responses:
        # Return most recent response
        return user_responses[-1].get('content') or user_responses[-1].get('value')
    
    return None
