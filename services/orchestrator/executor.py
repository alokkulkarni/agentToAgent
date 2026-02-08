"""
Parallel workflow execution engine
"""
import asyncio
from typing import List, Dict, Set, Any, Optional
from datetime import datetime
import logging

from models import StepRecord, StepStatus, WorkflowConfig

logger = logging.getLogger(__name__)


class ParallelExecutor:
    """Executes workflow steps in parallel when possible"""
    
    def __init__(self, config: WorkflowConfig):
        self.config = config
        self.semaphore = asyncio.Semaphore(config.max_parallel_steps)
    
    def build_dependency_graph(self, steps: List[StepRecord]) -> Dict[str, Set[str]]:
        """Build dependency graph from steps"""
        graph = {}
        
        for step in steps:
            step_id = step.step_id
            graph[step_id] = set(step.dependencies)
        
        return graph
    
    def get_ready_steps(
        self,
        steps: List[StepRecord],
        completed_steps: Set[str],
        running_steps: Set[str]
    ) -> List[StepRecord]:
        """Get steps that are ready to execute (dependencies met)"""
        ready = []
        
        for step in steps:
            # Skip if already completed or running
            if step.step_id in completed_steps or step.step_id in running_steps:
                continue
            
            # Skip if not pending
            if step.status != StepStatus.PENDING:
                continue
            
            # Check if all dependencies are completed
            dependencies_met = all(
                dep_id in completed_steps 
                for dep_id in step.dependencies
            )
            
            if dependencies_met:
                ready.append(step)
        
        return ready
    
    async def execute_step(
        self,
        step: StepRecord,
        execution_func: callable,
        *args,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute a single step with semaphore control"""
        async with self.semaphore:
            logger.info(f"Executing step {step.step_number}: {step.capability}")
            start_time = datetime.now()
            
            try:
                # Add timeout
                result = await asyncio.wait_for(
                    execution_func(step, *args, **kwargs),
                    timeout=self.config.step_timeout_seconds
                )
                
                execution_time = (datetime.now() - start_time).total_seconds() * 1000
                
                return {
                    "step_id": step.step_id,
                    "success": True,
                    "result": result,
                    "execution_time_ms": execution_time
                }
                
            except asyncio.TimeoutError:
                logger.error(f"Step {step.step_id} timed out after {self.config.step_timeout_seconds}s")
                return {
                    "step_id": step.step_id,
                    "success": False,
                    "error": f"Step timed out after {self.config.step_timeout_seconds}s"
                }
            except Exception as e:
                logger.error(f"Step {step.step_id} failed: {str(e)}")
                return {
                    "step_id": step.step_id,
                    "success": False,
                    "error": str(e)
                }
    
    async def execute_parallel(
        self,
        steps: List[StepRecord],
        execution_func: callable,
        *args,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute steps in parallel respecting dependencies"""
        
        if not self.config.enable_parallel_execution:
            # Fall back to sequential execution
            logger.info("Parallel execution disabled, executing sequentially")
            return await self.execute_sequential(steps, execution_func, *args, **kwargs)
        
        logger.info(f"Starting parallel execution of {len(steps)} steps")
        
        completed_steps: Set[str] = set()
        running_steps: Set[str] = set()
        step_results: Dict[str, Any] = {}
        step_map = {step.step_id: step for step in steps}
        
        # Track pending tasks
        pending_tasks: Dict[str, asyncio.Task] = {}
        
        while len(completed_steps) < len(steps):
            # Get steps ready to execute
            ready_steps = self.get_ready_steps(steps, completed_steps, running_steps)
            
            if not ready_steps and not pending_tasks:
                # No steps ready and no tasks running - check for circular dependencies
                remaining = [s for s in steps if s.step_id not in completed_steps]
                if remaining:
                    logger.error("Workflow stuck - possible circular dependencies")
                    for step in remaining:
                        step_results[step.step_id] = {
                            "step_id": step.step_id,
                            "success": False,
                            "error": "Workflow stuck - dependencies not met"
                        }
                break
            
            # Start new tasks for ready steps
            for step in ready_steps:
                running_steps.add(step.step_id)
                task = asyncio.create_task(
                    self.execute_step(step, execution_func, *args, **kwargs)
                )
                pending_tasks[step.step_id] = task
                logger.info(f"Started step {step.step_number}: {step.capability}")
            
            # Wait for at least one task to complete
            if pending_tasks:
                done, pending = await asyncio.wait(
                    pending_tasks.values(),
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Process completed tasks
                for task in done:
                    result = await task
                    step_id = result["step_id"]
                    
                    # Update tracking sets
                    running_steps.remove(step_id)
                    
                    if result["success"]:
                        completed_steps.add(step_id)
                        logger.info(f"Step {step_map[step_id].step_number} completed successfully")
                    else:
                        logger.error(f"Step {step_map[step_id].step_number} failed: {result.get('error')}")
                        # Mark as completed anyway to unblock dependent steps
                        # They will handle the missing data
                        completed_steps.add(step_id)
                    
                    # Store result
                    step_results[step_id] = result
                    
                    # Remove from pending
                    del pending_tasks[step_id]
        
        # Calculate summary
        successful_steps = sum(1 for r in step_results.values() if r["success"])
        failed_steps = len(step_results) - successful_steps
        
        logger.info(
            f"Parallel execution complete: {successful_steps} successful, "
            f"{failed_steps} failed out of {len(steps)} total"
        )
        
        return {
            "total_steps": len(steps),
            "successful_steps": successful_steps,
            "failed_steps": failed_steps,
            "step_results": step_results
        }
    
    async def execute_sequential(
        self,
        steps: List[StepRecord],
        execution_func: callable,
        *args,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute steps sequentially (fallback mode)"""
        logger.info(f"Starting sequential execution of {len(steps)} steps")
        
        step_results = {}
        successful = 0
        failed = 0
        
        for step in sorted(steps, key=lambda s: s.step_number):
            result = await self.execute_step(step, execution_func, *args, **kwargs)
            step_results[step.step_id] = result
            
            if result["success"]:
                successful += 1
            else:
                failed += 1
                # Optionally stop on first failure
                # break
        
        return {
            "total_steps": len(steps),
            "successful_steps": successful,
            "failed_steps": failed,
            "step_results": step_results
        }


class DependencyAnalyzer:
    """Analyzes and validates step dependencies"""
    
    @staticmethod
    def detect_circular_dependencies(steps: List[StepRecord]) -> Optional[List[str]]:
        """Detect circular dependencies in workflow steps"""
        graph = {step.step_id: set(step.dependencies) for step in steps}
        visited = set()
        rec_stack = set()
        
        def has_cycle(node: str, path: List[str]) -> Optional[List[str]]:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in graph.get(node, set()):
                if neighbor not in visited:
                    cycle = has_cycle(neighbor, path[:])
                    if cycle:
                        return cycle
                elif neighbor in rec_stack:
                    # Found cycle
                    cycle_start = path.index(neighbor)
                    return path[cycle_start:] + [neighbor]
            
            rec_stack.remove(node)
            return None
        
        for step_id in graph:
            if step_id not in visited:
                cycle = has_cycle(step_id, [])
                if cycle:
                    return cycle
        
        return None
    
    @staticmethod
    def validate_dependencies(steps: List[StepRecord]) -> List[str]:
        """Validate that all dependencies exist"""
        step_ids = {step.step_id for step in steps}
        errors = []
        
        for step in steps:
            for dep_id in step.dependencies:
                if dep_id not in step_ids:
                    errors.append(
                        f"Step {step.step_id} depends on non-existent step {dep_id}"
                    )
        
        return errors


class WorkflowExecutor:
    """Simple workflow executor for managing workflow lifecycle"""
    
    def __init__(self, db, interaction_mgr):
        """Initialize executor with database and interaction manager"""
        self.db = db
        self.interaction_mgr = interaction_mgr
        logger.info("WorkflowExecutor initialized")
    
    async def resume_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """Resume a paused workflow"""
        try:
            workflow = self.db.get_workflow(workflow_id)
            if not workflow:
                return {"success": False, "error": "Workflow not found"}
            
            logger.info(f"Resuming workflow {workflow_id}")
            
            # Update workflow status
            self.db.update_workflow_status(workflow_id, "running")
            
            return {
                "success": True,
                "workflow_id": workflow_id,
                "message": "Workflow resumed successfully"
            }
        except Exception as e:
            logger.error(f"Failed to resume workflow {workflow_id}: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancel a running workflow"""
        try:
            workflow = self.db.get_workflow(workflow_id)
            if not workflow:
                return False
            
            logger.info(f"Cancelling workflow {workflow_id}")
            
            # Update workflow status
            self.db.update_workflow_status(workflow_id, "cancelled")
            
            return True
        except Exception as e:
            logger.error(f"Failed to cancel workflow {workflow_id}: {str(e)}")
            return False
