"""
WebSocket Handler for Interactive Workflows
Enables real-time bidirectional communication between user and AI system
"""
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Any, Optional, Set
import asyncio
import json
from datetime import datetime
import logging

from models import WorkflowStatus

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for workflows"""
    
    def __init__(self):
        # workflow_id -> Set of WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # websocket -> workflow_id for reverse lookup
        self.connection_workflow: Dict[WebSocket, str] = {}
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, workflow_id: str):
        """Register a new WebSocket connection for a workflow"""
        await websocket.accept()
        
        async with self._lock:
            if workflow_id not in self.active_connections:
                self.active_connections[workflow_id] = set()
            
            self.active_connections[workflow_id].add(websocket)
            self.connection_workflow[websocket] = workflow_id
        
        logger.info(f"✓ WebSocket connected for workflow {workflow_id}")
        
        # Send welcome message
        await self.send_to_connection(websocket, {
            "type": "connection_established",
            "workflow_id": workflow_id,
            "timestamp": datetime.utcnow().isoformat(),
            "message": "Connected to workflow"
        })
    
    async def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection"""
        async with self._lock:
            workflow_id = self.connection_workflow.get(websocket)
            
            if workflow_id and workflow_id in self.active_connections:
                self.active_connections[workflow_id].discard(websocket)
                
                if not self.active_connections[workflow_id]:
                    del self.active_connections[workflow_id]
            
            if websocket in self.connection_workflow:
                del self.connection_workflow[websocket]
        
        logger.info(f"✓ WebSocket disconnected from workflow {workflow_id}")
    
    async def send_to_connection(self, websocket: WebSocket, message: Dict[str, Any]):
        """Send message to specific connection"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending to connection: {e}")
            await self.disconnect(websocket)
    
    async def broadcast_to_workflow(self, workflow_id: str, message: Dict[str, Any]):
        """Send message to all connections for a workflow"""
        if workflow_id not in self.active_connections:
            return
        
        disconnected = []
        
        for websocket in self.active_connections[workflow_id].copy():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to connection: {e}")
                disconnected.append(websocket)
        
        # Clean up disconnected sockets
        for websocket in disconnected:
            await self.disconnect(websocket)
    
    def get_workflow_connections(self, workflow_id: str) -> int:
        """Get number of active connections for a workflow"""
        return len(self.active_connections.get(workflow_id, set()))
    
    def has_connections(self, workflow_id: str) -> bool:
        """Check if workflow has any active connections"""
        return workflow_id in self.active_connections and len(self.active_connections[workflow_id]) > 0


class WebSocketMessageHandler:
    """Handles incoming WebSocket messages and routes them appropriately"""
    
    def __init__(self, db, interaction_manager, executor, resume_workflow_func=None):
        self.db = db
        self.interaction_manager = interaction_manager
        self.executor = executor
        self.resume_workflow_func = resume_workflow_func
        self.connection_manager = ConnectionManager()
    
    async def handle_connection(self, websocket: WebSocket, workflow_id: str):
        """Main handler for WebSocket connection lifecycle"""
        await self.connection_manager.connect(websocket, workflow_id)
        
        try:
            # Send current workflow status
            await self._send_workflow_status(websocket, workflow_id)
            
            # Listen for messages
            while True:
                try:
                    data = await websocket.receive_json()
                    await self.handle_message(websocket, workflow_id, data)
                except WebSocketDisconnect:
                    break
                except json.JSONDecodeError:
                    await self.connection_manager.send_to_connection(websocket, {
                        "type": "error",
                        "message": "Invalid JSON format"
                    })
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    await self.connection_manager.send_to_connection(websocket, {
                        "type": "error",
                        "message": str(e)
                    })
        
        finally:
            await self.connection_manager.disconnect(websocket)
    
    async def handle_message(self, websocket: WebSocket, workflow_id: str, data: Dict[str, Any]):
        """Route incoming messages based on type"""
        msg_type = data.get("type")
        
        if msg_type == "ping":
            await self.connection_manager.send_to_connection(websocket, {
                "type": "pong",
                "timestamp": datetime.utcnow().isoformat()
            })
        
        elif msg_type == "get_status":
            await self._send_workflow_status(websocket, workflow_id)
        
        elif msg_type == "user_response":
            await self._handle_user_response(websocket, workflow_id, data)
        
        elif msg_type == "cancel_workflow":
            await self._handle_cancel(websocket, workflow_id)
        
        elif msg_type == "get_conversation":
            await self._send_conversation_history(websocket, workflow_id)
        
        else:
            await self.connection_manager.send_to_connection(websocket, {
                "type": "error",
                "message": f"Unknown message type: {msg_type}"
            })
    
    async def _send_workflow_status(self, websocket: WebSocket, workflow_id: str):
        """Send current workflow status"""
        workflow = self.db.get_workflow(workflow_id)
        
        if not workflow:
            await self.connection_manager.send_to_connection(websocket, {
                "type": "error",
                "message": "Workflow not found"
            })
            return
        
        # Check for pending interaction
        pending_interaction = None
        if workflow.status.value == "waiting_for_input":
            pending_interaction = self.interaction_manager.get_pending_request(workflow_id)
        
        await self.connection_manager.send_to_connection(websocket, {
            "type": "workflow_status",
            "workflow_id": workflow_id,
            "status": workflow.status.value,
            "steps_completed": workflow.completed_steps,
            "total_steps": workflow.total_steps,
            "pending_interaction": pending_interaction,
            "current_step": getattr(workflow, "current_step", None),
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def _handle_user_response(self, websocket: WebSocket, workflow_id: str, data: Dict[str, Any]):
        """Handle user response to interaction request"""
        request_id = data.get("request_id")
        response = data.get("response")
        additional_context = data.get("additional_context")
        
        if not request_id or response is None:
            await self.connection_manager.send_to_connection(websocket, {
                "type": "error",
                "message": "Missing request_id or response"
            })
            return
        
        # Submit response
        success = await self.interaction_manager.submit_response(
            request_id=request_id,
            response=response,
            additional_context=additional_context
        )
        
        if not success:
            await self.connection_manager.send_to_connection(websocket, {
                "type": "error",
                "message": "Failed to submit response"
            })
            return
        
        # Acknowledge response
        await self.connection_manager.broadcast_to_workflow(workflow_id, {
            "type": "response_received",
            "request_id": request_id,
            "response": response,
            "timestamp": datetime.utcnow().isoformat(),
            "message": "Response received, resuming workflow..."
        })
        
        # Resume workflow execution in background
        asyncio.create_task(self._resume_workflow(workflow_id))
    
    async def _resume_workflow(self, workflow_id: str):
        """Resume workflow execution after user response"""
        try:
            # Broadcast status
            await self.connection_manager.broadcast_to_workflow(workflow_id, {
                "type": "workflow_resuming",
                "workflow_id": workflow_id,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Resume execution - use the passed function if available
            if self.resume_workflow_func:
                result = await self.resume_workflow_func(workflow_id)
            else:
                # Fallback to executor method (though it's not fully functional)
                result = await self.executor.resume_workflow(workflow_id)
            
            # Broadcast completion or next interaction
            workflow = self.db.get_workflow(workflow_id)
            
            if workflow and workflow.status == WorkflowStatus.WAITING_FOR_INPUT:
                # Another interaction needed
                pending_interaction = self.interaction_manager.get_pending_request(workflow_id)
                await self.connection_manager.broadcast_to_workflow(workflow_id, {
                    "type": "user_input_required",
                    "workflow_id": workflow_id,
                    "interaction": pending_interaction,
                    "timestamp": datetime.utcnow().isoformat()
                })
            else:
                # Workflow completed or failed
                await self.connection_manager.broadcast_to_workflow(workflow_id, {
                    "type": "workflow_completed",
                    "workflow_id": workflow_id,
                    "status": workflow.status.value if workflow else "unknown",
                    "result": result,
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        except Exception as e:
            logger.error(f"Error resuming workflow {workflow_id}: {e}")
            import traceback
            traceback.print_exc()
            await self.connection_manager.broadcast_to_workflow(workflow_id, {
                "type": "error",
                "message": f"Error resuming workflow: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            })
    
    async def _handle_cancel(self, websocket: WebSocket, workflow_id: str):
        """Handle workflow cancellation request"""
        success = await self.executor.cancel_workflow(workflow_id)
        
        if success:
            await self.connection_manager.broadcast_to_workflow(workflow_id, {
                "type": "workflow_cancelled",
                "workflow_id": workflow_id,
                "timestamp": datetime.utcnow().isoformat()
            })
        else:
            await self.connection_manager.send_to_connection(websocket, {
                "type": "error",
                "message": "Failed to cancel workflow"
            })
    
    async def _send_conversation_history(self, websocket: WebSocket, workflow_id: str):
        """Send conversation history"""
        from conversation import ConversationManager
        
        conversation_mgr = ConversationManager(self.db)
        history = conversation_mgr.get_conversation_history(workflow_id)
        
        await self.connection_manager.send_to_connection(websocket, {
            "type": "conversation_history",
            "workflow_id": workflow_id,
            "history": history,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    # Methods for agents/orchestrator to push updates to clients
    
    async def notify_step_started(self, workflow_id: str, step_info: Dict[str, Any]):
        """Notify clients that a step has started"""
        if self.connection_manager.has_connections(workflow_id):
            await self.connection_manager.broadcast_to_workflow(workflow_id, {
                "type": "step_started",
                "workflow_id": workflow_id,
                "step": step_info,
                "timestamp": datetime.utcnow().isoformat()
            })
    
    async def notify_step_completed(self, workflow_id: str, step_info: Dict[str, Any], result: Any):
        """Notify clients that a step has completed"""
        if self.connection_manager.has_connections(workflow_id):
            await self.connection_manager.broadcast_to_workflow(workflow_id, {
                "type": "step_completed",
                "workflow_id": workflow_id,
                "step": step_info,
                "result": result,
                "timestamp": datetime.utcnow().isoformat()
            })
    
    async def notify_interaction_required(self, workflow_id: str, interaction: Dict[str, Any]):
        """Notify clients that user input is required"""
        if self.connection_manager.has_connections(workflow_id):
            await self.connection_manager.broadcast_to_workflow(workflow_id, {
                "type": "user_input_required",
                "workflow_id": workflow_id,
                "interaction": interaction,
                "timestamp": datetime.utcnow().isoformat()
            })
    
    async def notify_workflow_completed(self, workflow_id: str, result: Dict[str, Any]):
        """Notify clients that workflow has completed"""
        if self.connection_manager.has_connections(workflow_id):
            await self.connection_manager.broadcast_to_workflow(workflow_id, {
                "type": "workflow_completed",
                "workflow_id": workflow_id,
                "result": result,
                "timestamp": datetime.utcnow().isoformat()
            })
    
    async def notify_error(self, workflow_id: str, error: str):
        """Notify clients of an error"""
        if self.connection_manager.has_connections(workflow_id):
            await self.connection_manager.broadcast_to_workflow(workflow_id, {
                "type": "error",
                "workflow_id": workflow_id,
                "error": error,
                "timestamp": datetime.utcnow().isoformat()
            })
