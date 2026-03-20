"""
Fallback Manager

Implements the circuit-breaker + transparent fallback strategy:

1. Maintains a circuit breaker per provider (CLOSED / HALF_OPEN / OPEN).
2. On every provider call, records success or failure.
3. When a provider transitions to OPEN, future requests automatically
   skip it and route to the next model in the fallback chain.
4. Periodically probes OPEN circuits to attempt recovery (HALF_OPEN).
5. All state transitions are logged for audit purposes.

Circuit breaker thresholds (configurable via environment):
    GATEWAY_CB_FAILURE_THRESHOLD    default 3  — consecutive failures to open
    GATEWAY_CB_HALF_OPEN_AFTER_SEC  default 60 — seconds before probing
    GATEWAY_CB_SUCCESS_THRESHOLD    default 2  — successes to close from HALF_OPEN
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Coroutine, Dict, List, Optional, Tuple, Any

from providers.base import (
    BaseProvider,
    CircuitState,
    CompletionRequest,
    CompletionResponse,
    ProviderHealth,
    ProviderType,
    StreamChunk,
)
from routing.model_selector import SelectionResult

logger = logging.getLogger(__name__)

_FM_INSTANCE: Optional[FallbackManager] = None

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
_CB_FAIL_THRESHOLD = int(os.getenv("GATEWAY_CB_FAILURE_THRESHOLD", "3"))
_CB_HALF_OPEN_AFTER = int(os.getenv("GATEWAY_CB_HALF_OPEN_AFTER_SEC", "60"))
_CB_SUCCESS_THRESHOLD = int(os.getenv("GATEWAY_CB_SUCCESS_THRESHOLD", "2"))
_MAX_RETRIES = int(os.getenv("GATEWAY_MAX_RETRIES", "2"))


@dataclass
class CircuitBreaker:
    """Per-provider circuit breaker state."""
    provider: ProviderType
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    opened_at: Optional[float] = None
    last_failure_reason: Optional[str] = None

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.consecutive_successes += 1
        if self.state == CircuitState.HALF_OPEN:
            if self.consecutive_successes >= _CB_SUCCESS_THRESHOLD:
                logger.info(
                    "[CircuitBreaker:%s] CLOSED after %d successes in HALF_OPEN.",
                    self.provider.value, self.consecutive_successes,
                )
                self.state = CircuitState.CLOSED
                self.opened_at = None

    def record_failure(self, reason: str) -> None:
        self.consecutive_successes = 0
        self.consecutive_failures += 1
        self.last_failure_reason = reason
        if self.state == CircuitState.CLOSED:
            if self.consecutive_failures >= _CB_FAIL_THRESHOLD:
                self.state = CircuitState.OPEN
                self.opened_at = time.time()
                logger.warning(
                    "[CircuitBreaker:%s] OPENED after %d consecutive failures. Last: %s",
                    self.provider.value, self.consecutive_failures, reason,
                )
        elif self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.opened_at = time.time()
            logger.warning(
                "[CircuitBreaker:%s] Returned to OPEN from HALF_OPEN. Reason: %s",
                self.provider.value, reason,
            )

    def should_allow_request(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.HALF_OPEN:
            return True  # allow probe
        # OPEN — check if enough time has elapsed to try recovery
        if self.opened_at and (time.time() - self.opened_at) >= _CB_HALF_OPEN_AFTER:
            self.state = CircuitState.HALF_OPEN
            self.consecutive_successes = 0
            logger.info(
                "[CircuitBreaker:%s] Transitioning to HALF_OPEN for probe.",
                self.provider.value,
            )
            return True
        return False

    def to_health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.provider,
            is_healthy=self.state == CircuitState.CLOSED,
            circuit_state=self.state,
            failure_count=self.consecutive_failures,
            last_failure_ts=self.opened_at,
            checked_at=time.time(),
        )


@dataclass
class FallbackEvent:
    """Recorded whenever a fallback occurs."""
    original_model_id: str
    original_provider: ProviderType
    fallback_model_id: str
    fallback_provider: ProviderType
    reason: str
    attempt: int
    timestamp: float = field(default_factory=time.time)


class FallbackManager:
    """
    Wraps provider calls with circuit-breaker logic and transparent fallback.

    Usage:
        result = await fallback_manager.execute(
            selection=selection_result,
            provider_map=provider_registry,
            request=completion_request,
        )
    """

    def __init__(self) -> None:
        self._breakers: Dict[ProviderType, CircuitBreaker] = {
            p: CircuitBreaker(provider=p) for p in ProviderType
        }
        self._fallback_history: List[FallbackEvent] = []

    # ------------------------------------------------------------------
    # Circuit breaker state
    # ------------------------------------------------------------------

    def get_open_providers(self) -> List[ProviderType]:
        """Return providers whose circuit is OPEN (requests will be skipped)."""
        return [
            p for p, cb in self._breakers.items()
            if not cb.should_allow_request()
        ]

    def get_breaker_health(self) -> Dict[str, dict]:
        return {
            p.value: {
                "state": cb.state.value,
                "consecutive_failures": cb.consecutive_failures,
                "consecutive_successes": cb.consecutive_successes,
                "opened_at": cb.opened_at,
                "last_failure_reason": cb.last_failure_reason,
            }
            for p, cb in self._breakers.items()
        }

    # ------------------------------------------------------------------
    # Main execution entry point
    # ------------------------------------------------------------------

    async def execute(
        self,
        selection: SelectionResult,
        provider_map: Dict[ProviderType, BaseProvider],
        request: CompletionRequest,
    ) -> CompletionResponse:
        """
        Try the primary model, then each fallback in order, until one succeeds.
        Updates circuit breakers and records fallback events.
        """
        chain = [selection.primary] + selection.fallbacks
        last_exc: Optional[Exception] = None
        fallback_reason: Optional[str] = None

        for attempt, model_info in enumerate(chain):
            provider_type = model_info.provider
            breaker = self._breakers[provider_type]

            if not breaker.should_allow_request():
                logger.info(
                    "Skipping %s/%s (circuit OPEN).",
                    provider_type.value, model_info.model_id,
                )
                continue

            provider = provider_map.get(provider_type)
            if not provider:
                logger.warning("No provider registered for %s", provider_type.value)
                continue

            # Clone request with the (possibly different) model id
            req = _clone_request_for_model(request, model_info.model_id)

            try:
                logger.info(
                    "Attempt %d — %s/%s", attempt + 1,
                    provider_type.value, model_info.model_id,
                )
                response = await provider.complete(req)
                breaker.record_success()

                if attempt > 0:
                    # Annotate response with fallback metadata
                    response.original_model_id = chain[0].model_id
                    response.fallback_reason = fallback_reason or "provider_error"

                return response

            except Exception as exc:
                err_str = str(exc)[:200]
                logger.warning(
                    "Provider %s failed (attempt %d): %s",
                    provider_type.value, attempt + 1, err_str,
                )
                breaker.record_failure(err_str)
                last_exc = exc
                fallback_reason = err_str

                # Record fallback event when moving to next in chain
                if attempt + 1 < len(chain):
                    next_model = chain[attempt + 1]
                    self._fallback_history.append(FallbackEvent(
                        original_model_id=model_info.model_id,
                        original_provider=provider_type,
                        fallback_model_id=next_model.model_id,
                        fallback_provider=next_model.provider,
                        reason=err_str,
                        attempt=attempt + 1,
                    ))

        raise RuntimeError(
            f"All models in fallback chain exhausted. Last error: {last_exc}"
        ) from last_exc

    # ------------------------------------------------------------------
    # Streaming execution
    # ------------------------------------------------------------------

    async def execute_stream(
        self,
        selection: SelectionResult,
        provider_map: Dict[ProviderType, BaseProvider],
        request: CompletionRequest,
    ):
        """
        Streaming variant — yields StreamChunk objects.
        Fallback on the first chunk failure (before any output is sent).
        """
        chain = [selection.primary] + selection.fallbacks

        for attempt, model_info in enumerate(chain):
            provider_type = model_info.provider
            breaker = self._breakers[provider_type]

            if not breaker.should_allow_request():
                continue

            provider = provider_map.get(provider_type)
            if not provider:
                continue

            req = _clone_request_for_model(request, model_info.model_id)
            try:
                async for chunk in provider.stream(req):
                    yield chunk
                breaker.record_success()
                return
            except Exception as exc:
                err_str = str(exc)[:200]
                logger.warning(
                    "Stream provider %s failed (attempt %d): %s",
                    provider_type.value, attempt + 1, err_str,
                )
                breaker.record_failure(err_str)
                if attempt + 1 < len(chain):
                    next_model = chain[attempt + 1]
                    self._fallback_history.append(FallbackEvent(
                        original_model_id=model_info.model_id,
                        original_provider=provider_type,
                        fallback_model_id=next_model.model_id,
                        fallback_provider=next_model.provider,
                        reason=err_str,
                        attempt=attempt + 1,
                    ))

        raise RuntimeError("All streaming providers exhausted.")

    def recent_fallback_events(self, limit: int = 50) -> List[dict]:
        events = self._fallback_history[-limit:]
        return [
            {
                "timestamp": e.timestamp,
                "original_model": e.original_model_id,
                "original_provider": e.original_provider.value,
                "fallback_model": e.fallback_model_id,
                "fallback_provider": e.fallback_provider.value,
                "reason": e.reason,
                "attempt": e.attempt,
            }
            for e in reversed(events)
        ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clone_request_for_model(
    request: CompletionRequest, model_id: str
) -> CompletionRequest:
    """Return a shallow copy of the request with an updated model_id."""
    from dataclasses import asdict, replace
    return CompletionRequest(
        messages=request.messages,
        model_id=model_id,
        provider=request.provider,        # will be overridden by provider anyway
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        top_p=request.top_p,
        stream=request.stream,
        system_prompt=request.system_prompt,
        tools=request.tools,
        tool_choice=request.tool_choice,
        json_mode=request.json_mode,
        extra_params=request.extra_params,
        request_id=request.request_id,
        workflow_id=request.workflow_id,
        session_id=request.session_id,
        user_id=request.user_id,
    )


def get_fallback_manager() -> FallbackManager:
    global _FM_INSTANCE
    if _FM_INSTANCE is None:
        _FM_INSTANCE = FallbackManager()
    return _FM_INSTANCE
