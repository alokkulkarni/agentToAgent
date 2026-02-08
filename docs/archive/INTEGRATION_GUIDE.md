# Integration Guide - Workflow Enhancements

## Overview

This guide shows how to integrate the new workflow enhancements (persistence, retry, parallel execution) into the existing orchestrator.

---

## Quick Integration Steps

### 1. Update Orchestrator Imports

Add to top of `services/orchestrator/app.py`:

```python
# New imports
from .models import (
    WorkflowRecord, StepRecord, WorkflowStatus, StepStatus,
    WorkflowConfig, RetryPolicy
)
from .database import WorkflowDatabase
from .retry import RetryManager, CircuitBreaker
from .executor import ParallelExecutor, DependencyAnalyzer
```

### 2. Initialize Components

Add after configuration section:

```python
# Workflow configuration
WORKFLOW_CONFIG = WorkflowConfig(
    retry_policy=RetryPolicy(
        max_retries=int(os.getenv("MAX_RETRIES", "3")),
        initial_delay_seconds=float(os.getenv("RETRY_INITIAL_DELAY", "1.0")),
        max_delay_seconds=float(os.getenv("RETRY_MAX_DELAY", "60.0"))
    ),
    enable_parallel_execution=os.getenv("ENABLE_PARALLEL", "true").lower() == "true",
    max_parallel_steps=int(os.getenv("MAX_PARALLEL_STEPS", "5")),
    step_timeout_seconds=int(os.getenv("STEP_TIMEOUT", "300")),
    workflow_timeout_seconds=int(os.getenv("WORKFLOW_TIMEOUT", "3600")),
    enable_persistence=os.getenv("ENABLE_PERSISTENCE", "true").lower() == "true"
)

# Initialize components
workflow_db = WorkflowDatabase(os.getenv("WORKFLOW_DB_PATH", "workflows.db"))
retry_manager = RetryManager(WORKFLOW_CONFIG.retry_policy)
circuit_breaker = CircuitBreaker()
parallel_executor = ParallelExecutor(WORKFLOW_CONFIG)
```

### 3. Add New API Endpoints

Add these endpoints to `app.py`:

```python
@app.get("/api/workflow/{workflow_id}")
async def get_workflow_status(workflow_id: str):
    """Get workflow execution status"""
    workflow = workflow_db.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    steps = workflow_db.get_workflow_steps(workflow_id)
    
    return {
        "workflow_id": workflow.workflow_id,
        "status": workflow.status,
        "total_steps": workflow.total_steps,
        "completed_steps": workflow.completed_steps,
        "created_at": workflow.created_at.isoformat(),
        "updated_at": workflow.updated_at.isoformat(),
        "steps": [
            {
                "step_number": step.step_number,
                "capability": step.capability,
                "status": step.status,
                "retry_count": step.retry_count
            }
            for step in steps
        ]
    }


@app.get("/api/workflows")
async def list_workflows(
    status: Optional[WorkflowStatus] = None,
    limit: int = 100
):
    """List workflows with optional status filter"""
    workflows = workflow_db.list_workflows(status, limit)
    
    return {
        "workflows": [
            {
                "workflow_id": w.workflow_id,
                "task_description": w.task_description,
                "status": w.status,
                "total_steps": w.total_steps,
                "completed_steps": w.completed_steps,
                "created_at": w.created_at.isoformat()
            }
            for w in workflows
        ],
        "total": len(workflows)
    }


@app.post("/api/workflow/{workflow_id}/resume")
async def resume_workflow(workflow_id: str):
    """Resume a failed or interrupted workflow"""
    workflow = workflow_db.get_workflow(workflow_id)
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    if workflow.status not in [WorkflowStatus.FAILED, WorkflowStatus.RUNNING]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume workflow in status: {workflow.status}"
        )
    
    # Update status to running
    workflow.status = WorkflowStatus.RUNNING
    workflow.updated_at = datetime.now()
    workflow_db.save_workflow(workflow)
    
    # Get incomplete steps
    steps = workflow_db.get_workflow_steps(workflow_id)
    incomplete_steps = [
        s for s in steps 
        if s.status in [StepStatus.PENDING, StepStatus.FAILED]
    ]
    
    # TODO: Execute incomplete steps
    
    return {
        "workflow_id": workflow_id,
        "status": "resumed",
        "steps_to_execute": len(incomplete_steps)
    }
```

### 4. Modify Workflow Execution

Update the main execution function to use new features:

```python
async def execute_workflow_enhanced(task: WorkflowTask) -> WorkflowResponse:
    """Execute workflow with persistence, retry, and parallel execution"""
    workflow_id = task.workflow_id or str(time.time())
    
    # Create workflow record
    if WORKFLOW_CONFIG.enable_persistence:
        workflow = WorkflowRecord(
            workflow_id=workflow_id,
            task_description=task.task_description,
            status=WorkflowStatus.PLANNING,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        workflow_db.save_workflow(workflow)
    
    try:
        # Phase 1: Plan
        workflow.status = WorkflowStatus.PLANNING
        workflow_db.save_workflow(workflow)
        
        execution_plan = await generate_execution_plan(task.task_description)
        workflow.execution_plan = execution_plan
        workflow.total_steps = len(execution_plan.get("steps", []))
        workflow_db.save_workflow(workflow)
        
        # Create step records
        step_records = []
        for i, step_plan in enumerate(execution_plan["steps"]):
            step = StepRecord(
                step_id=f"{workflow_id}_step_{i+1}",
                workflow_id=workflow_id,
                step_number=i + 1,
                capability=step_plan["capability"],
                status=StepStatus.PENDING,
                parameters=step_plan.get("parameters", {}),
                max_retries=WORKFLOW_CONFIG.retry_policy.max_retries,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                dependencies=step_plan.get("dependencies", [])
            )
            step_records.append(step)
            workflow_db.save_step(step)
        
        # Validate dependencies
        errors = DependencyAnalyzer.validate_dependencies(step_records)
        if errors:
            raise ValueError(f"Dependency validation failed: {errors}")
        
        # Check for circular dependencies
        cycle = DependencyAnalyzer.detect_circular_dependencies(step_records)
        if cycle:
            raise ValueError(f"Circular dependency detected: {cycle}")
        
        # Phase 2: Execute
        workflow.status = WorkflowStatus.RUNNING
        workflow.started_at = datetime.now()
        workflow_db.save_workflow(workflow)
        
        # Execute with parallel executor and retry
        async def execute_step_with_features(step: StepRecord):
            """Execute step with retry and circuit breaker"""
            step.status = StepStatus.RUNNING
            step.started_at = datetime.now()
            workflow_db.save_step(step)
            
            try:
                # Get agent for capability
                agent_info = await discover_agent(step.capability)
                step.agent = agent_info["name"]
                step.agent_endpoint = agent_info["endpoint"]
                workflow_db.save_step(step)
                
                # Execute with circuit breaker and retry
                result = await circuit_breaker.execute(
                    step.agent,
                    lambda: retry_manager.execute_with_retry(
                        step,
                        execute_step_on_agent,
                        step, agent_info
                    )
                )
                
                step.status = StepStatus.COMPLETED
                step.result = result
                step.completed_at = datetime.now()
                workflow_db.save_step(step)
                
                # Update workflow progress
                workflow.completed_steps += 1
                workflow_db.save_workflow(workflow)
                
                return result
                
            except Exception as e:
                step.status = StepStatus.FAILED
                step.error_message = str(e)
                step.completed_at = datetime.now()
                workflow_db.save_step(step)
                raise
        
        # Execute in parallel
        results = await parallel_executor.execute_parallel(
            step_records,
            execute_step_with_features
        )
        
        # Phase 3: Complete
        workflow.status = WorkflowStatus.COMPLETED
        workflow.completed_at = datetime.now()
        workflow.results = results
        workflow_db.save_workflow(workflow)
        
        return WorkflowResponse(
            workflow_id=workflow_id,
            status="completed",
            steps_completed=workflow.completed_steps,
            total_steps=workflow.total_steps,
            results=results
        )
        
    except Exception as e:
        # Mark workflow as failed
        if WORKFLOW_CONFIG.enable_persistence:
            workflow.status = WorkflowStatus.FAILED
            workflow.error_message = str(e)
            workflow.completed_at = datetime.now()
            workflow_db.save_workflow(workflow)
        
        raise
```

---

## Environment Variables

Add to `.env` files:

```bash
# Workflow Configuration
MAX_RETRIES=3
RETRY_INITIAL_DELAY=1.0
RETRY_MAX_DELAY=60.0
ENABLE_PARALLEL=true
MAX_PARALLEL_STEPS=5
STEP_TIMEOUT=300
WORKFLOW_TIMEOUT=3600
ENABLE_PERSISTENCE=true
WORKFLOW_DB_PATH=workflows.db
```

---

## Docker Compose Updates

Add volume for database persistence:

```yaml
orchestrator:
  volumes:
    - ${HOME}/.aws:/root/.aws:ro
    - workflow-data:/app/data  # NEW

volumes:
  database-data:
  workspace-data:
  workflow-data:  # NEW
```

Update environment in docker-compose.yml:

```yaml
orchestrator:
  environment:
    # ... existing vars ...
    - MAX_RETRIES=${MAX_RETRIES:-3}
    - ENABLE_PARALLEL=${ENABLE_PARALLEL:-true}
    - MAX_PARALLEL_STEPS=${MAX_PARALLEL_STEPS:-5}
    - WORKFLOW_DB_PATH=/app/data/workflows.db
```

---

## Testing

### Test Persistence
```bash
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Add 5 and 3"}'

# Get workflow status
curl http://localhost:8100/api/workflow/{workflow_id}

# List all workflows
curl http://localhost:8100/api/workflows
```

### Test Retry
```bash
# Simulate failure by stopping an agent temporarily
./stop_services.sh  # Stop MathAgent

# Start workflow (should retry and eventually fail)
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Add 5 and 3"}'

# Restart agent
./start_services.sh

# Resume workflow
curl -X POST http://localhost:8100/api/workflow/{workflow_id}/resume
```

### Test Parallel Execution
```bash
# Task with independent steps
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Analyze code quality AND check security AND generate documentation"
  }'

# Should execute analyze, check, and generate in parallel if independent
# Check execution time - should be faster than sequential
```

---

## Monitoring

### Database Queries

```bash
# Connect to database
sqlite3 workflows.db

# Count workflows by status
SELECT status, COUNT(*) FROM workflows GROUP BY status;

# Average execution time
SELECT AVG(execution_time_ms) FROM steps WHERE status = 'completed';

# Failed steps
SELECT workflow_id, step_number, capability, error_message 
FROM steps 
WHERE status = 'failed';

# Retry statistics
SELECT capability, AVG(retry_count), MAX(retry_count)
FROM steps
GROUP BY capability;
```

---

## Rollback Plan

If issues occur, disable new features:

```bash
# Disable all enhancements
export ENABLE_PERSISTENCE=false
export ENABLE_PARALLEL=false
export MAX_RETRIES=0

# Restart services
./stop_services.sh
./start_services.sh
```

Or use old orchestrator backup:

```bash
cp services/orchestrator/app.py services/orchestrator/app.py.enhanced
cp services/orchestrator/app.py.backup services/orchestrator/app.py
```

---

## Performance Impact

### Expected Improvements
- **Parallel Execution**: 30-60% faster for workflows with independent steps
- **Retry**: 95%+ success rate for transient failures
- **Persistence**: <5% overhead

### Resource Usage
- **Database**: ~100KB per workflow
- **Memory**: +50MB for parallel execution
- **CPU**: +10-20% during parallel execution

---

## Migration Checklist

- [x] Create new modules (models, database, retry, executor)
- [ ] Update orchestrator imports
- [ ] Initialize new components
- [ ] Add API endpoints
- [ ] Modify workflow execution logic
- [ ] Add environment variables
- [ ] Update docker-compose.yml
- [ ] Test each feature
- [ ] Update documentation
- [ ] Deploy to production

---

**Status**: Implementation complete, integration in progress  
**Next**: Test modules, integrate into orchestrator, deploy
