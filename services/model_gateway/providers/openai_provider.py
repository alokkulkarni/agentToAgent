"""
OpenAI Provider — via the openai Python SDK

Covers GPT-4o, GPT-4o-mini, o1/o3 reasoning models, and legacy GPT models.
Uses the async client for non-blocking I/O.
"""

from __future__ import annotations

import logging
import os
import time
from typing import AsyncIterator, List, Optional

from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError

from .base import (
    BaseProvider,
    CircuitState,
    CompletionRequest,
    CompletionResponse,
    ModelCapability,
    ModelInfo,
    ModelTier,
    ProviderHealth,
    ProviderType,
    StreamChunk,
    TaskType,
    TokenCost,
    UsageMetrics,
)

logger = logging.getLogger(__name__)

# Reasoning models (o-series) do not support temperature / top_p / system prompt
_REASONING_MODELS = frozenset({"o1", "o1-mini", "o1-preview", "o3", "o3-mini", "o4-mini"})


class OpenAIProvider(BaseProvider):
    """
    OpenAI provider via the official openai SDK (v1.x).
    Requires OPENAI_API_KEY environment variable.
    """

    provider_type = ProviderType.OPENAI

    def __init__(self) -> None:
        super().__init__()
        api_key = os.getenv("OPENAI_API_KEY")
        org_id = os.getenv("OPENAI_ORG_ID")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set — OpenAI provider will be unavailable.")
            self._health.is_healthy = False
            self._client: Optional[AsyncOpenAI] = None
        else:
            self._client = AsyncOpenAI(
                api_key=api_key,
                organization=org_id or None,
            )
            logger.info("OpenAIProvider initialised.")

    # ------------------------------------------------------------------
    # Provider catalogue
    # ------------------------------------------------------------------

    def list_models(self) -> List[ModelInfo]:
        return [
            # ── Reasoning models (o-series) ──────────────────────────
            ModelInfo(
                model_id="o4-mini",
                provider=ProviderType.OPENAI,
                display_name="OpenAI o4-mini",
                tier=ModelTier.REASONING,
                context_window=200_000,
                max_output_tokens=100_000,
                capabilities=[
                    ModelCapability.REASONING, ModelCapability.TOOLS,
                    ModelCapability.CODE, ModelCapability.VISION,
                ],
                task_suitability={
                    TaskType.REASONING: 0.97, TaskType.MATH: 0.97,
                    TaskType.CODING: 0.95,    TaskType.GENERAL: 0.92,
                    TaskType.FAST: 0.88,
                },
                cost=TokenCost(input_per_million=1.1, output_per_million=4.4),
                metadata={"release_date": "2025-04"},
            ),
            ModelInfo(
                model_id="o3",
                provider=ProviderType.OPENAI,
                display_name="OpenAI o3",
                tier=ModelTier.REASONING,
                context_window=200_000,
                max_output_tokens=100_000,
                capabilities=[
                    ModelCapability.REASONING, ModelCapability.TOOLS,
                    ModelCapability.CODE, ModelCapability.MULTILINGUAL,
                ],
                task_suitability={
                    TaskType.REASONING: 1.0, TaskType.MATH: 1.0,
                    TaskType.CODING: 0.95,   TaskType.GENERAL: 0.90,
                    TaskType.LONG_CONTEXT: 0.88,
                },
                cost=TokenCost(input_per_million=10.0, output_per_million=40.0),
            ),
            ModelInfo(
                model_id="o3-mini",
                provider=ProviderType.OPENAI,
                display_name="OpenAI o3-mini",
                tier=ModelTier.REASONING,
                context_window=200_000,
                max_output_tokens=100_000,
                capabilities=[
                    ModelCapability.REASONING, ModelCapability.TOOLS,
                    ModelCapability.CODE,
                ],
                task_suitability={
                    TaskType.REASONING: 0.95, TaskType.MATH: 0.95,
                    TaskType.CODING: 0.90,    TaskType.GENERAL: 0.85,
                    TaskType.FAST: 0.80,
                },
                cost=TokenCost(input_per_million=1.1, output_per_million=4.4),
            ),
            ModelInfo(
                model_id="o1",
                provider=ProviderType.OPENAI,
                display_name="OpenAI o1",
                tier=ModelTier.REASONING,
                context_window=200_000,
                max_output_tokens=100_000,
                capabilities=[ModelCapability.REASONING, ModelCapability.CODE],
                task_suitability={
                    TaskType.REASONING: 0.98, TaskType.MATH: 0.98,
                    TaskType.CODING: 0.90,
                },
                cost=TokenCost(input_per_million=15.0, output_per_million=60.0),
            ),
            ModelInfo(
                model_id="o1-mini",
                provider=ProviderType.OPENAI,
                display_name="OpenAI o1-mini",
                tier=ModelTier.REASONING,
                context_window=128_000,
                max_output_tokens=65_536,
                capabilities=[ModelCapability.REASONING, ModelCapability.CODE],
                task_suitability={
                    TaskType.REASONING: 0.90, TaskType.MATH: 0.90,
                    TaskType.CODING: 0.85,    TaskType.FAST: 0.75,
                },
                cost=TokenCost(input_per_million=3.0, output_per_million=12.0),
            ),
            # ── GPT-4.5 ──────────────────────────────────────────────
            ModelInfo(
                model_id="gpt-4.5-preview",
                provider=ProviderType.OPENAI,
                display_name="GPT-4.5 Preview",
                tier=ModelTier.PREMIUM,
                context_window=128_000,
                max_output_tokens=16_384,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.JSON_MODE,
                    ModelCapability.FUNCTION_CALLING, ModelCapability.CODE,
                    ModelCapability.MULTILINGUAL,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.98,  TaskType.CODING: 0.97,
                    TaskType.REASONING: 0.95, TaskType.CREATIVE: 0.97,
                    TaskType.VISION: 0.97,   TaskType.CHAT: 0.98,
                    TaskType.SUMMARIZATION: 0.95, TaskType.EXTRACTION: 0.95,
                    TaskType.MATH: 0.93,
                },
                cost=TokenCost(input_per_million=75.0, output_per_million=150.0),
                metadata={"release_date": "2025-02"},
            ),
            # ── GPT-4o family ─────────────────────────────────────────
            ModelInfo(
                model_id="gpt-4o",
                provider=ProviderType.OPENAI,
                display_name="GPT-4o",
                tier=ModelTier.PREMIUM,
                context_window=128_000,
                max_output_tokens=16_384,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.JSON_MODE,
                    ModelCapability.FUNCTION_CALLING, ModelCapability.CODE,
                    ModelCapability.MULTILINGUAL,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.97,  TaskType.CODING: 0.95,
                    TaskType.REASONING: 0.90, TaskType.CREATIVE: 0.92,
                    TaskType.VISION: 1.0,    TaskType.CHAT: 0.97,
                    TaskType.SUMMARIZATION: 0.92, TaskType.EXTRACTION: 0.92,
                    TaskType.MATH: 0.90,
                },
                cost=TokenCost(input_per_million=2.5, output_per_million=10.0),
            ),
            ModelInfo(
                model_id="gpt-4o-mini",
                provider=ProviderType.OPENAI,
                display_name="GPT-4o mini",
                tier=ModelTier.ECONOMY,
                context_window=128_000,
                max_output_tokens=16_384,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.JSON_MODE,
                    ModelCapability.FUNCTION_CALLING, ModelCapability.CODE,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.85,  TaskType.FAST: 1.0,
                    TaskType.CODING: 0.82,   TaskType.VISION: 0.85,
                    TaskType.CHAT: 0.90,     TaskType.CLASSIFICATION: 0.90,
                    TaskType.EXTRACTION: 0.85, TaskType.SUMMARIZATION: 0.85,
                },
                cost=TokenCost(input_per_million=0.15, output_per_million=0.6),
            ),
            # ── GPT-4 Turbo ───────────────────────────────────────────
            ModelInfo(
                model_id="gpt-4-turbo",
                provider=ProviderType.OPENAI,
                display_name="GPT-4 Turbo",
                tier=ModelTier.PREMIUM,
                context_window=128_000,
                max_output_tokens=4_096,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.JSON_MODE,
                    ModelCapability.FUNCTION_CALLING, ModelCapability.CODE,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.92,  TaskType.CODING: 0.92,
                    TaskType.REASONING: 0.88, TaskType.CREATIVE: 0.88,
                    TaskType.VISION: 0.92,   TaskType.CHAT: 0.90,
                },
                cost=TokenCost(input_per_million=10.0, output_per_million=30.0),
            ),
            # ── GPT-3.5 (legacy, very cheap) ──────────────────────────
            ModelInfo(
                model_id="gpt-3.5-turbo",
                provider=ProviderType.OPENAI,
                display_name="GPT-3.5 Turbo",
                tier=ModelTier.ECONOMY,
                context_window=16_385,
                max_output_tokens=4_096,
                capabilities=[
                    ModelCapability.TOOLS, ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.65, TaskType.FAST: 0.92,
                    TaskType.CHAT: 0.75,    TaskType.CLASSIFICATION: 0.72,
                },
                cost=TokenCost(input_per_million=0.5, output_per_million=1.5),
            ),
        ]

    # ------------------------------------------------------------------
    # Completion
    # ------------------------------------------------------------------

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        if not self._client:
            raise RuntimeError("OpenAI provider not initialised (missing API key).")

        t0 = time.monotonic()
        is_reasoning = request.model_id in _REASONING_MODELS
        messages = self._build_messages(request, is_reasoning)

        kwargs: dict = {
            "model": request.model_id,
            "messages": messages,
            "max_completion_tokens": request.max_tokens,
        }
        # Reasoning models reject temperature / tools in certain configurations
        if not is_reasoning:
            kwargs["temperature"] = request.temperature
            kwargs["top_p"] = request.top_p
        if request.tools and not is_reasoning:
            kwargs["tools"] = request.tools
        if request.tool_choice and not is_reasoning:
            kwargs["tool_choice"] = request.tool_choice
        if request.json_mode and not is_reasoning:
            kwargs["response_format"] = {"type": "json_object"}
        kwargs.update(request.extra_params)

        try:
            response = await self._client.chat.completions.create(**kwargs)
            latency_ms = (time.monotonic() - t0) * 1000
            self._record_success(latency_ms)

            choice = response.choices[0]
            content = choice.message.content or ""
            finish_reason = choice.finish_reason or "stop"

            tool_calls = None
            if choice.message.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                    for tc in choice.message.tool_calls
                ]

            raw_usage = response.usage
            usage = UsageMetrics(
                input_tokens=raw_usage.prompt_tokens if raw_usage else 0,
                output_tokens=raw_usage.completion_tokens if raw_usage else 0,
                total_tokens=raw_usage.total_tokens if raw_usage else 0,
            )
            model_info = next(
                (m for m in self.list_models() if m.model_id == request.model_id), None
            )
            if model_info:
                usage.estimated_cost_usd = model_info.estimated_cost(
                    usage.input_tokens, usage.output_tokens
                )

            return CompletionResponse(
                content=content,
                model_id=request.model_id,
                provider=ProviderType.OPENAI,
                finish_reason=finish_reason,
                usage=usage,
                tool_calls=tool_calls,
                raw_response=response.model_dump(),
                latency_ms=latency_ms,
                request_id=request.request_id,
            )
        except (RateLimitError, APITimeoutError, APIError) as exc:
            self._record_failure(exc)
            raise

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        if not self._client:
            raise RuntimeError("OpenAI provider not initialised (missing API key).")

        is_reasoning = request.model_id in _REASONING_MODELS
        messages = self._build_messages(request, is_reasoning)

        kwargs: dict = {
            "model": request.model_id,
            "messages": messages,
            "max_completion_tokens": request.max_tokens,
            "stream": True,
        }
        if not is_reasoning:
            kwargs["temperature"] = request.temperature
            kwargs["top_p"] = request.top_p

        t0 = time.monotonic()
        try:
            async with await self._client.chat.completions.create(**kwargs) as stream_obj:
                async for chunk in stream_obj:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        yield StreamChunk(
                            content=delta.content,
                            model_id=request.model_id,
                            provider=ProviderType.OPENAI,
                        )
                    if chunk.choices and chunk.choices[0].finish_reason:
                        latency_ms = (time.monotonic() - t0) * 1000
                        self._record_success(latency_ms)
                        yield StreamChunk(
                            content="",
                            model_id=request.model_id,
                            provider=ProviderType.OPENAI,
                            finish_reason=chunk.choices[0].finish_reason,
                            is_final=True,
                        )
        except (RateLimitError, APITimeoutError, APIError) as exc:
            self._record_failure(exc)
            raise

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> ProviderHealth:
        if not self._client:
            self._health.is_healthy = False
            self._health.circuit_state = CircuitState.OPEN
            self._health.checked_at = time.time()
            return self._health
        try:
            t0 = time.monotonic()
            await self._client.models.list()
            latency_ms = (time.monotonic() - t0) * 1000
            self._record_success(latency_ms)
            self._health.is_healthy = True
            self._health.circuit_state = CircuitState.CLOSED
        except Exception as exc:
            self._record_failure(exc)
            self._health.is_healthy = False
            self._health.circuit_state = CircuitState.OPEN
        self._health.checked_at = time.time()
        return self._health

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_messages(request: CompletionRequest, is_reasoning: bool) -> list:
        messages = []
        for msg in request.messages:
            # Reasoning models use a "developer" system role rather than "system"
            if msg.role == "system":
                if is_reasoning:
                    messages.append({"role": "developer", "content": msg.content})
                else:
                    messages.append({"role": "system", "content": msg.content})
                continue
            messages.append({"role": msg.role, "content": msg.content})

        # Inject explicit system prompt if provided and not already present
        if request.system_prompt and not any(
            m["role"] in ("system", "developer") for m in messages
        ):
            role = "developer" if is_reasoning else "system"
            messages.insert(0, {"role": role, "content": request.system_prompt})

        return messages
