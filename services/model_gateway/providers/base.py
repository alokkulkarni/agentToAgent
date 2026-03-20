"""
Model Gateway - Base Provider Abstraction

Defines the abstract contract all LLM providers must implement.
Includes all shared data models for requests, responses, capabilities,
and health state used across the gateway.
"""

from __future__ import annotations

import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ProviderType(str, Enum):
    ANTHROPIC = "anthropic"
    BEDROCK = "bedrock"
    GEMINI = "gemini"
    OPENAI = "openai"


class ModelTier(str, Enum):
    """Cost / capability tier"""
    ECONOMY = "economy"       # cheapest, fast, good for simple tasks
    BALANCED = "balanced"     # mid-range, versatile
    PREMIUM = "premium"       # flagship, most capable
    REASONING = "reasoning"   # dedicated reasoning / o-series models


class TaskType(str, Enum):
    """Detected intent / workload category"""
    GENERAL = "general"
    CODING = "coding"
    REASONING = "reasoning"
    CREATIVE = "creative"
    SUMMARIZATION = "summarization"
    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"
    VISION = "vision"
    MATH = "math"
    LONG_CONTEXT = "long_context"
    FAST = "fast"            # latency-sensitive, cost-sensitive
    CHAT = "chat"


class ModelCapability(str, Enum):
    """Capabilities a model may expose"""
    VISION = "vision"
    TOOLS = "tools"
    STREAMING = "streaming"
    JSON_MODE = "json_mode"
    FUNCTION_CALLING = "function_calling"
    LONG_CONTEXT = "long_context"   # >= 100k tokens
    REASONING = "reasoning"         # specialised chain-of-thought
    MULTILINGUAL = "multilingual"
    CODE = "code"


class CircuitState(str, Enum):
    CLOSED = "closed"       # healthy, all requests go through
    HALF_OPEN = "half_open" # testing recovery after failures
    OPEN = "open"           # unhealthy, requests skipped


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TokenCost:
    """Cost in USD per 1 000 000 tokens"""
    input_per_million: float
    output_per_million: float
    cached_input_per_million: float = 0.0


@dataclass
class ModelInfo:
    """Full metadata for a single model"""
    model_id: str
    provider: ProviderType
    display_name: str
    tier: ModelTier
    context_window: int                         # maximum input tokens
    max_output_tokens: int
    capabilities: List[ModelCapability]
    task_suitability: Dict[TaskType, float]     # 0-1 score per task type
    cost: TokenCost
    supports_streaming: bool = True
    supports_system_prompt: bool = True
    is_deprecated: bool = False
    # Extra provider-specific info (e.g. bedrock model ARN, region constraints)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def supports_task(self, task: TaskType) -> float:
        return self.task_suitability.get(task, 0.0)

    def estimated_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            (input_tokens / 1_000_000) * self.cost.input_per_million
            + (output_tokens / 1_000_000) * self.cost.output_per_million
        )


@dataclass
class Message:
    """A single conversation turn"""
    role: str       # "system" | "user" | "assistant"
    content: Union[str, List[Dict[str, Any]]]   # str or multi-part content


@dataclass
class CompletionRequest:
    """Normalised completion request sent to any provider"""
    messages: List[Message]
    model_id: str
    provider: ProviderType
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 1.0
    stream: bool = False
    system_prompt: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[str] = None
    json_mode: bool = False
    # Pass-through of any extra provider-specific kwargs
    extra_params: Dict[str, Any] = field(default_factory=dict)
    # Traceability
    request_id: Optional[str] = None
    workflow_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None


@dataclass
class UsageMetrics:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cached_input_tokens: int = 0
    estimated_cost_usd: float = 0.0


@dataclass
class CompletionResponse:
    """Normalised completion response from any provider"""
    content: str
    model_id: str
    provider: ProviderType
    finish_reason: str                  # "stop" | "max_tokens" | "tool_calls" | …
    usage: UsageMetrics
    tool_calls: Optional[List[Dict[str, Any]]] = None
    raw_response: Optional[Dict[str, Any]] = None
    latency_ms: float = 0.0
    request_id: Optional[str] = None
    # Set when fallback occurred
    original_model_id: Optional[str] = None
    fallback_reason: Optional[str] = None


@dataclass
class StreamChunk:
    """Single token / delta from a streaming response"""
    content: str
    model_id: str
    provider: ProviderType
    finish_reason: Optional[str] = None
    usage: Optional[UsageMetrics] = None
    is_final: bool = False


@dataclass
class ProviderHealth:
    """Live health state for a provider"""
    provider: ProviderType
    is_healthy: bool
    circuit_state: CircuitState
    failure_count: int = 0
    success_count: int = 0
    last_failure_ts: Optional[float] = None
    last_success_ts: Optional[float] = None
    avg_latency_ms: float = 0.0
    error_rate: float = 0.0
    checked_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------

class BaseProvider(ABC):
    """
    Abstract base for all LLM provider implementations.

    Subclasses must implement:
    - complete()   — single-turn (non-streaming) completion
    - stream()     — streaming completion (async generator)
    - health_check() — probe provider liveness
    - list_models()  — return the static model catalogue for this provider
    """

    provider_type: ProviderType

    def __init__(self) -> None:
        self._health = ProviderHealth(
            provider=self.provider_type,
            is_healthy=True,
            circuit_state=CircuitState.CLOSED,
        )
        self._latency_samples: List[float] = []

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Execute a single, non-streaming completion."""
        ...

    @abstractmethod
    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        """Execute a streaming completion, yielding chunks."""
        ...

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Probe the provider and return its current health state."""
        ...

    @abstractmethod
    def list_models(self) -> List[ModelInfo]:
        """Return the static catalogue of models this provider supports."""
        ...

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def get_health(self) -> ProviderHealth:
        return self._health

    def _record_success(self, latency_ms: float) -> None:
        self._health.success_count += 1
        self._health.last_success_ts = time.time()
        self._health.is_healthy = True
        if self._health.circuit_state == CircuitState.HALF_OPEN:
            self._health.circuit_state = CircuitState.CLOSED
            logger.info("[%s] Circuit breaker closed (recovered).", self.provider_type.value)
        self._update_latency(latency_ms)
        self._update_error_rate()

    def _record_failure(self, error: Exception) -> None:
        self._health.failure_count += 1
        self._health.last_failure_ts = time.time()
        self._update_error_rate()
        logger.warning("[%s] Provider failure recorded: %s", self.provider_type.value, error)

    def _update_latency(self, latency_ms: float) -> None:
        self._latency_samples.append(latency_ms)
        if len(self._latency_samples) > 100:    # rolling window
            self._latency_samples = self._latency_samples[-100:]
        self._health.avg_latency_ms = sum(self._latency_samples) / len(self._latency_samples)

    def _update_error_rate(self) -> None:
        total = self._health.success_count + self._health.failure_count
        if total > 0:
            self._health.error_rate = self._health.failure_count / total
