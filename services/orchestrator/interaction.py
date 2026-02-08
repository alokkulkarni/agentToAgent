"""
Interaction manager for handling user input during workflow execution
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging

from models import (
    InteractionRequest, InteractionResponse, InputType,
    WorkflowStatus, WorkflowContext, MessageRole, MessageType
)
from database import WorkflowDatabase

logger = logging.getLogger(__name__)


class InteractionManager:
    """Manages user interactions during workflow execution"""
    
    def __init__(self, db: WorkflowDatabase, default_timeout_seconds: int = 300):
        self.db = db
        self.default_timeout_seconds = default_timeout_seconds
        self._pending_interactions: Dict[str, InteractionRequest] = {}
    
    async def request_user_input(
        self,
        workflow_id: str,
        step_id: str,
        agent_name: str,
        question: str,
        input_type: InputType,
        options: Optional[list] = None,
        context: Optional[Dict] = None,
        reasoning: Optional[str] = None,
        timeout_seconds: Optional[int] = None
    ) -> InteractionRequest:
        """
        Request input from user, pausing workflow execution
        
        Args:
            workflow_id: ID of the workflow
            step_id: ID of the step requesting input
            agent_name: Name of the agent requesting input
            question: The question to ask the user
            input_type: Type of input expected
            options: List of options (for choice types)
            context: Additional context for the question
            reasoning: Agent's reasoning for asking
            timeout_seconds: Seconds to wait for response
        
        Returns:
            InteractionRequest object
        """
        timeout = timeout_seconds or self.default_timeout_seconds
        
        request = InteractionRequest(
            workflow_id=workflow_id,
            step_id=step_id,
            agent_name=agent_name,
            created_at=datetime.now(),
            timeout_at=datetime.now() + timedelta(seconds=timeout),
            question=question,
            input_type=input_type,
            options=options,
            context=context or {},
            reasoning=reasoning,
            status="pending"
        )
        
        # Save to database
        self.db.save_interaction_request(request)
        
        # Track in memory
        self._pending_interactions[request.request_id] = request
        
        # Add to conversation
        workflow_context = self.db.get_workflow_context(workflow_id)
        if workflow_context:
            workflow_context.add_message(
                role=MessageRole.AGENT,
                message_type=MessageType.QUESTION,
                content=question,
                agent=agent_name,
                requires_response=True,
                options=options
            )
            self.db.save_message(workflow_context.conversation[-1])
        
        # Add thought
        if reasoning:
            workflow_context.add_thought(
                thought_type="question",
                content=f"Requesting user input: {reasoning}",
                agent=agent_name
            )
            self.db.save_thought(workflow_id, workflow_context.thought_trail[-1])
        
        logger.info(f"Interaction request created: {request.request_id} for workflow {workflow_id}")
        
        return request
    
    async def wait_for_response(
        self,
        request_id: str,
        poll_interval: float = 1.0
    ) -> Optional[InteractionResponse]:
        """
        Wait for user response to interaction request
        
        Args:
            request_id: ID of the interaction request
            poll_interval: Seconds between polls
        
        Returns:
            InteractionResponse if received, None if timeout
        """
        request = self._pending_interactions.get(request_id) or \
                  self.db.get_interaction_request(request_id)
        
        if not request:
            logger.error(f"Interaction request not found: {request_id}")
            return None
        
        # Poll for response
        while datetime.now() < request.timeout_at:
            # Reload from database
            updated_request = self.db.get_interaction_request(request_id)
            
            if updated_request and updated_request.status == "answered":
                logger.info(f"Response received for {request_id}")
                
                response = InteractionResponse(
                    request_id=request_id,
                    workflow_id=updated_request.workflow_id,
                    response=updated_request.response,
                    additional_context=updated_request.response_metadata.get('additional_context'),
                    metadata=updated_request.response_metadata,
                    timestamp=updated_request.response_received_at or datetime.now()
                )
                
                # Remove from pending
                if request_id in self._pending_interactions:
                    del self._pending_interactions[request_id]
                
                return response
            
            await asyncio.sleep(poll_interval)
        
        # Timeout
        logger.warning(f"Interaction request timeout: {request_id}")
        request.status = "timeout"
        self.db.save_interaction_request(request)
        
        if request_id in self._pending_interactions:
            del self._pending_interactions[request_id]
        
        return None
    
    async def submit_response(
        self,
        request_id: str,
        response: Any,
        additional_context: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Submit user response to interaction request
        
        Args:
            request_id: ID of the interaction request
            response: User's response
            additional_context: Optional explanation
            metadata: Additional metadata
        
        Returns:
            True if successful, False otherwise
        """
        request = self.db.get_interaction_request(request_id)
        
        if not request:
            logger.error(f"Interaction request not found: {request_id}")
            return False
        
        if request.status != "pending":
            logger.warning(f"Interaction request not pending: {request_id} (status: {request.status})")
            return False
        
        # Validate response
        if not self._validate_response(request, response):
            logger.error(f"Invalid response for request {request_id}")
            return False
        
        # Update request
        request.response = response
        request.response_received_at = datetime.now()
        request.response_metadata = metadata or {}
        if additional_context:
            request.response_metadata['additional_context'] = additional_context
        request.status = "answered"
        
        # Save to database
        self.db.save_interaction_request(request)
        
        # Add to conversation
        workflow_context = self.db.get_workflow_context(request.workflow_id)
        if workflow_context:
            workflow_context.add_message(
                role=MessageRole.USER,
                message_type=MessageType.RESPONSE,
                content=str(response),
                additional_context=additional_context
            )
            self.db.save_message(workflow_context.conversation[-1])
        
        logger.info(f"Response submitted for {request_id}")
        
        return True
    
    def _validate_response(self, request: InteractionRequest, response: Any) -> bool:
        """Validate response matches expected input type"""
        if request.input_type == InputType.TEXT:
            return isinstance(response, str)
        
        elif request.input_type == InputType.SINGLE_CHOICE:
            return request.options and response in request.options
        
        elif request.input_type == InputType.MULTIPLE_CHOICE:
            return (request.options and isinstance(response, list) and
                    all(r in request.options for r in response))
        
        elif request.input_type == InputType.CONFIRMATION:
            return response in [True, False, "yes", "no", "cancel"]
        
        elif request.input_type == InputType.STRUCTURED_DATA:
            return isinstance(response, dict)
        
        return True
    
    async def cancel_interaction(self, request_id: str) -> bool:
        """Cancel pending interaction request"""
        request = self.db.get_interaction_request(request_id)
        
        if not request:
            return False
        
        if request.status != "pending":
            return False
        
        request.status = "cancelled"
        self.db.save_interaction_request(request)
        
        if request_id in self._pending_interactions:
            del self._pending_interactions[request_id]
        
        logger.info(f"Interaction request cancelled: {request_id}")
        return True
    
    def get_pending_interactions(self, workflow_id: Optional[str] = None) -> list:
        """Get all pending interaction requests"""
        if workflow_id:
            request = self.db.get_pending_interaction(workflow_id)
            return [request] if request else []
        
        return list(self._pending_interactions.values())
    
    def complete_interaction(self, request_id: str):
        """Mark an interaction as completed"""
        request = self._pending_interactions.get(request_id) or \
                  self.db.get_interaction_request(request_id)
        
        if request:
            request.status = "completed"
            self.db.save_interaction_request(request)
            
            if request_id in self._pending_interactions:
                del self._pending_interactions[request_id]
            
            logger.info(f"Interaction completed: {request_id}")
    
    def get_pending_requests(self, workflow_id: str) -> list:
        """Get all pending interaction requests for a workflow (alias for compatibility)"""
        return self.get_pending_interactions(workflow_id)
    
    def get_pending_request(self, workflow_id: str) -> Optional[InteractionRequest]:
        """Get single pending request for a workflow"""
        requests = self.get_pending_interactions(workflow_id)
        return requests[0] if requests else None
