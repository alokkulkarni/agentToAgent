"""
Retry mechanism with exponential backoff
"""
import asyncio
import random
from typing import Callable, Any, Optional
from datetime import datetime
import logging

from models import RetryPolicy, StepRecord, StepStatus

logger = logging.getLogger(__name__)


class RetryManager:
    """Manages retry logic with exponential backoff"""
    
    def __init__(self, policy: RetryPolicy):
        self.policy = policy
    
    def calculate_delay(self, retry_count: int) -> float:
        """Calculate delay for next retry with exponential backoff"""
        delay = min(
            self.policy.initial_delay_seconds * (self.policy.exponential_base ** retry_count),
            self.policy.max_delay_seconds
        )
        
        # Add jitter to prevent thundering herd
        if self.policy.jitter:
            delay = delay * (0.5 + random.random())
        
        return delay
    
    def is_retriable_error(self, error_message: str) -> bool:
        """Check if error is retriable based on policy"""
        if not error_message:
            return True
        
        error_lower = error_message.lower()
        return any(
            retriable in error_lower 
            for retriable in self.policy.retriable_errors
        )
    
    def should_retry(self, step: StepRecord, error_message: str) -> bool:
        """Determine if step should be retried"""
        # Check retry count
        if step.retry_count >= step.max_retries:
            logger.info(f"Step {step.step_id} exceeded max retries ({step.max_retries})")
            return False
        
        # Check if error is retriable
        if not self.is_retriable_error(error_message):
            logger.info(f"Step {step.step_id} error not retriable: {error_message}")
            return False
        
        return True
    
    async def execute_with_retry(
        self,
        step: StepRecord,
        execution_func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """Execute function with retry logic"""
        last_error = None
        
        for attempt in range(step.max_retries + 1):
            try:
                logger.info(f"Step {step.step_id} attempt {attempt + 1}/{step.max_retries + 1}")
                result = await execution_func(*args, **kwargs)
                
                if attempt > 0:
                    logger.info(f"Step {step.step_id} succeeded after {attempt} retries")
                
                return result
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Step {step.step_id} attempt {attempt + 1} failed: {last_error}")
                
                # Check if we should retry
                if attempt < step.max_retries and self.is_retriable_error(last_error):
                    delay = self.calculate_delay(attempt)
                    logger.info(f"Step {step.step_id} retrying in {delay:.2f}s...")
                    await asyncio.sleep(delay)
                else:
                    break
        
        # All retries exhausted
        raise Exception(f"Step failed after {step.max_retries + 1} attempts: {last_error}")


class CircuitBreaker:
    """Circuit breaker pattern for agent failures"""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_attempts: int = 1
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_attempts = half_open_attempts
        
        self.failure_count = {}
        self.last_failure_time = {}
        self.state = {}  # "closed", "open", "half_open"
        self.half_open_successes = {}
    
    def is_open(self, agent_id: str) -> bool:
        """Check if circuit is open for agent"""
        if agent_id not in self.state:
            self.state[agent_id] = "closed"
            return False
        
        state = self.state[agent_id]
        
        # If open, check if recovery timeout has passed
        if state == "open":
            time_since_failure = (
                datetime.now() - self.last_failure_time.get(agent_id, datetime.now())
            ).total_seconds()
            
            if time_since_failure >= self.recovery_timeout:
                logger.info(f"Circuit breaker for {agent_id} entering half-open state")
                self.state[agent_id] = "half_open"
                self.half_open_successes[agent_id] = 0
                return False
            
            return True
        
        return False
    
    def record_success(self, agent_id: str):
        """Record successful execution"""
        state = self.state.get(agent_id, "closed")
        
        if state == "half_open":
            self.half_open_successes[agent_id] = self.half_open_successes.get(agent_id, 0) + 1
            
            if self.half_open_successes[agent_id] >= self.half_open_attempts:
                logger.info(f"Circuit breaker for {agent_id} closing after successful recovery")
                self.state[agent_id] = "closed"
                self.failure_count[agent_id] = 0
        elif state == "closed":
            # Reset failure count on success
            self.failure_count[agent_id] = 0
    
    def record_failure(self, agent_id: str):
        """Record failed execution"""
        self.failure_count[agent_id] = self.failure_count.get(agent_id, 0) + 1
        self.last_failure_time[agent_id] = datetime.now()
        
        state = self.state.get(agent_id, "closed")
        
        if state == "half_open":
            logger.warning(f"Circuit breaker for {agent_id} reopening after half-open failure")
            self.state[agent_id] = "open"
        elif self.failure_count[agent_id] >= self.failure_threshold:
            logger.warning(
                f"Circuit breaker for {agent_id} opening after {self.failure_count[agent_id]} failures"
            )
            self.state[agent_id] = "open"
    
    async def execute(self, agent_id: str, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection"""
        if self.is_open(agent_id):
            raise Exception(f"Circuit breaker open for agent {agent_id}")
        
        try:
            result = await func(*args, **kwargs)
            self.record_success(agent_id)
            return result
        except Exception as e:
            self.record_failure(agent_id)
            raise e
