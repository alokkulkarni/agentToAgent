"""
Anthropic Provider — Direct Anthropic API (non-Bedrock)

Uses the `anthropic` Python SDK to call Claude models.
Handles streaming, tool calling, vision, and caching headers.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import AsyncIterator, List, Optional

import anthropic
from anthropic import AsyncAnthropic, APIError, APITimeoutError, RateLimitError

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


class AnthropicProvider(BaseProvider):
    """
    Anthropic (Claude) provider via the direct REST API (not Bedrock).
    Requires ANTHROPIC_API_KEY environment variable.
    """

    provider_type = ProviderType.ANTHROPIC

    def __init__(self) -> None:
        super().__init__()
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set — Anthropic provider will be unavailable.")
            self._health.is_healthy = False
            self._client: Optional[AsyncAnthropic] = None
        else:
            self._client = AsyncAnthropic(api_key=api_key)
            logger.info("AnthropicProvider initialised.")

    # ------------------------------------------------------------------
    # Provider catalogue
    # ------------------------------------------------------------------

    def list_models(self) -> List[ModelInfo]:
        return [
            # ── Claude 4.6-series (latest, Feb 2026) ─────────────────
            ModelInfo(
                model_id="claude-opus-4-6",
                provider=ProviderType.ANTHROPIC,
                display_name="Claude Opus 4.6",
                tier=ModelTier.PREMIUM,
                context_window=1_000_000,   # 1M beta; standard 200K
                max_output_tokens=128_000,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.JSON_MODE,
                    ModelCapability.FUNCTION_CALLING, ModelCapability.LONG_CONTEXT,
                    ModelCapability.CODE, ModelCapability.MULTILINGUAL,
                    ModelCapability.REASONING,
                ],
                task_suitability={
                    TaskType.GENERAL: 1.0,   TaskType.CODING: 1.0,
                    TaskType.REASONING: 1.0, TaskType.CREATIVE: 1.0,
                    TaskType.SUMMARIZATION: 0.98, TaskType.EXTRACTION: 0.98,
                    TaskType.VISION: 0.97,   TaskType.MATH: 1.0,
                    TaskType.LONG_CONTEXT: 1.0, TaskType.CHAT: 1.0,
                },
                cost=TokenCost(
                    input_per_million=5.0,
                    output_per_million=25.0,
                    cached_input_per_million=0.5,
                ),
                metadata={
                    "supports_extended_thinking": True,
                    "adaptive_thinking": True,
                    "effort_control": True,
                    "context_compaction": True,
                    "release_date": "2026-02-05",
                    "knowledge_cutoff": "2025-03",
                },
            ),
            ModelInfo(
                model_id="claude-sonnet-4-6",
                provider=ProviderType.ANTHROPIC,
                display_name="Claude Sonnet 4.6",
                tier=ModelTier.BALANCED,
                context_window=1_000_000,   # 1M beta; standard 200K
                max_output_tokens=64_000,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.JSON_MODE,
                    ModelCapability.FUNCTION_CALLING, ModelCapability.LONG_CONTEXT,
                    ModelCapability.CODE, ModelCapability.MULTILINGUAL,
                    ModelCapability.REASONING,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.98,  TaskType.CODING: 0.98,
                    TaskType.REASONING: 0.96, TaskType.CREATIVE: 0.95,
                    TaskType.SUMMARIZATION: 0.97, TaskType.EXTRACTION: 0.97,
                    TaskType.VISION: 0.95,   TaskType.MATH: 0.95,
                    TaskType.LONG_CONTEXT: 0.98, TaskType.CHAT: 0.98,
                },
                cost=TokenCost(
                    input_per_million=3.0,
                    output_per_million=15.0,
                    cached_input_per_million=0.3,
                ),
                metadata={
                    "supports_extended_thinking": True,
                    "adaptive_thinking": True,
                    "context_compaction": True,
                    "release_date": "2026-02-17",
                    "knowledge_cutoff": "2025-03",
                },
            ),
            # ── Claude 4.5-series (Nov 2025) ─────────────────────────
            ModelInfo(
                model_id="claude-opus-4-5",
                provider=ProviderType.ANTHROPIC,
                display_name="Claude Opus 4.5",
                tier=ModelTier.PREMIUM,
                context_window=200_000,
                max_output_tokens=32_768,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.JSON_MODE,
                    ModelCapability.FUNCTION_CALLING, ModelCapability.LONG_CONTEXT,
                    ModelCapability.CODE, ModelCapability.MULTILINGUAL,
                    ModelCapability.REASONING,
                ],
                task_suitability={
                    TaskType.GENERAL: 1.0,   TaskType.CODING: 1.0,
                    TaskType.REASONING: 1.0, TaskType.CREATIVE: 1.0,
                    TaskType.SUMMARIZATION: 0.95, TaskType.EXTRACTION: 0.95,
                    TaskType.VISION: 0.95,   TaskType.MATH: 1.0,
                    TaskType.LONG_CONTEXT: 1.0, TaskType.CHAT: 1.0,
                },
                cost=TokenCost(
                    input_per_million=15.0,
                    output_per_million=75.0,
                    cached_input_per_million=1.5,
                ),
            ),
            ModelInfo(
                model_id="claude-sonnet-4-5",
                provider=ProviderType.ANTHROPIC,
                display_name="Claude Sonnet 4.5",
                tier=ModelTier.BALANCED,
                context_window=200_000,
                max_output_tokens=16_384,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.JSON_MODE,
                    ModelCapability.FUNCTION_CALLING, ModelCapability.LONG_CONTEXT,
                    ModelCapability.CODE, ModelCapability.MULTILINGUAL,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.95,  TaskType.CODING: 0.95,
                    TaskType.REASONING: 0.90, TaskType.CREATIVE: 0.90,
                    TaskType.SUMMARIZATION: 0.95, TaskType.EXTRACTION: 0.95,
                    TaskType.VISION: 0.90,   TaskType.MATH: 0.90,
                    TaskType.LONG_CONTEXT: 0.95, TaskType.CHAT: 0.95,
                },
                cost=TokenCost(
                    input_per_million=3.0,
                    output_per_million=15.0,
                    cached_input_per_million=0.3,
                ),
            ),
            # ── Claude 3.7 (Feb 2025) — extended thinking ────────────
            ModelInfo(
                model_id="claude-3-7-sonnet-20250219",
                provider=ProviderType.ANTHROPIC,
                display_name="Claude 3.7 Sonnet (Extended Thinking)",
                tier=ModelTier.REASONING,
                context_window=200_000,
                max_output_tokens=128_000,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.JSON_MODE,
                    ModelCapability.FUNCTION_CALLING, ModelCapability.LONG_CONTEXT,
                    ModelCapability.REASONING, ModelCapability.CODE,
                    ModelCapability.MULTILINGUAL,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.97,  TaskType.CODING: 1.0,
                    TaskType.REASONING: 1.0, TaskType.MATH: 1.0,
                    TaskType.CREATIVE: 0.92, TaskType.SUMMARIZATION: 0.95,
                    TaskType.EXTRACTION: 0.95, TaskType.VISION: 0.92,
                    TaskType.LONG_CONTEXT: 0.97, TaskType.CHAT: 0.95,
                },
                cost=TokenCost(
                    input_per_million=3.0,
                    output_per_million=15.0,
                    cached_input_per_million=0.3,
                ),
                metadata={"supports_extended_thinking": True, "thinking_budget_tokens": 16000},
            ),
            # ── Claude 3.5-series (late 2024) ────────────────────────
            ModelInfo(
                model_id="claude-3-5-sonnet-20241022",
                provider=ProviderType.ANTHROPIC,
                display_name="Claude 3.5 Sonnet v2 (Oct 2024)",
                tier=ModelTier.BALANCED,
                context_window=200_000,
                max_output_tokens=8_096,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.JSON_MODE,
                    ModelCapability.FUNCTION_CALLING, ModelCapability.LONG_CONTEXT,
                    ModelCapability.CODE, ModelCapability.MULTILINGUAL,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.92,  TaskType.CODING: 0.95,
                    TaskType.REASONING: 0.88, TaskType.CREATIVE: 0.88,
                    TaskType.SUMMARIZATION: 0.92, TaskType.EXTRACTION: 0.92,
                    TaskType.VISION: 0.88,   TaskType.MATH: 0.88,
                    TaskType.LONG_CONTEXT: 0.92, TaskType.CHAT: 0.92,
                },
                cost=TokenCost(input_per_million=3.0, output_per_million=15.0),
            ),
            ModelInfo(
                model_id="claude-3-5-haiku-20241022",
                provider=ProviderType.ANTHROPIC,
                display_name="Claude 3.5 Haiku",
                tier=ModelTier.ECONOMY,
                context_window=200_000,
                max_output_tokens=8_096,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.JSON_MODE,
                    ModelCapability.FUNCTION_CALLING, ModelCapability.LONG_CONTEXT,
                    ModelCapability.CODE, ModelCapability.MULTILINGUAL,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.80,  TaskType.CODING: 0.82,
                    TaskType.FAST: 1.0,      TaskType.CHAT: 0.88,
                    TaskType.SUMMARIZATION: 0.85, TaskType.EXTRACTION: 0.85,
                    TaskType.CLASSIFICATION: 0.88, TaskType.LONG_CONTEXT: 0.80,
                },
                cost=TokenCost(input_per_million=0.8, output_per_million=4.0),
            ),
            # ── Claude 3-series (legacy, still available) ────────────
            ModelInfo(
                model_id="claude-3-opus-20240229",
                provider=ProviderType.ANTHROPIC,
                display_name="Claude 3 Opus (Legacy)",
                tier=ModelTier.PREMIUM,
                context_window=200_000,
                max_output_tokens=4_096,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.FUNCTION_CALLING,
                    ModelCapability.LONG_CONTEXT, ModelCapability.CODE,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.88,  TaskType.CODING: 0.86,
                    TaskType.REASONING: 0.90, TaskType.CREATIVE: 0.90,
                    TaskType.LONG_CONTEXT: 0.88, TaskType.CHAT: 0.88,
                },
                cost=TokenCost(input_per_million=15.0, output_per_million=75.0),
                is_deprecated=True,
            ),
            ModelInfo(
                model_id="claude-3-haiku-20240307",
                provider=ProviderType.ANTHROPIC,
                display_name="Claude 3 Haiku (Legacy)",
                tier=ModelTier.ECONOMY,
                context_window=200_000,
                max_output_tokens=4_096,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.FUNCTION_CALLING,
                    ModelCapability.CODE,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.70, TaskType.FAST: 0.92,
                    TaskType.CHAT: 0.80,    TaskType.CLASSIFICATION: 0.80,
                    TaskType.EXTRACTION: 0.76,
                },
                cost=TokenCost(input_per_million=0.25, output_per_million=1.25),
                is_deprecated=True,
            ),
        ]

    # ------------------------------------------------------------------
    # Completion
    # ------------------------------------------------------------------

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        if not self._client:
            raise RuntimeError("Anthropic provider not initialised (missing API key).")

        t0 = time.monotonic()
        messages = self._build_messages(request)
        kwargs = dict(
            model=request.model_id,
            max_tokens=request.max_tokens,
            messages=messages,
            temperature=request.temperature,
            top_p=request.top_p,
        )
        if request.system_prompt:
            kwargs["system"] = request.system_prompt
        if request.tools:
            kwargs["tools"] = request.tools
        if request.tool_choice:
            kwargs["tool_choice"] = {"type": request.tool_choice}
        kwargs.update(request.extra_params)

        try:
            response = await self._client.messages.create(**kwargs)
            latency_ms = (time.monotonic() - t0) * 1000
            self._record_success(latency_ms)

            content = self._extract_content(response)
            tool_calls = self._extract_tool_calls(response)
            usage = UsageMetrics(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens,
                cached_input_tokens=getattr(response.usage, "cache_read_input_tokens", 0),
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
                provider=ProviderType.ANTHROPIC,
                finish_reason=response.stop_reason or "stop",
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
            raise RuntimeError("Anthropic provider not initialised (missing API key).")

        messages = self._build_messages(request)
        kwargs = dict(
            model=request.model_id,
            max_tokens=request.max_tokens,
            messages=messages,
            temperature=request.temperature,
            top_p=request.top_p,
        )
        if request.system_prompt:
            kwargs["system"] = request.system_prompt
        kwargs.update(request.extra_params)

        t0 = time.monotonic()
        try:
            async with self._client.messages.stream(**kwargs) as stream_obj:
                async for text in stream_obj.text_stream:
                    yield StreamChunk(
                        content=text,
                        model_id=request.model_id,
                        provider=ProviderType.ANTHROPIC,
                    )
                final_msg = await stream_obj.get_final_message()
                latency_ms = (time.monotonic() - t0) * 1000
                self._record_success(latency_ms)
                usage = UsageMetrics(
                    input_tokens=final_msg.usage.input_tokens,
                    output_tokens=final_msg.usage.output_tokens,
                    total_tokens=final_msg.usage.input_tokens + final_msg.usage.output_tokens,
                )
                yield StreamChunk(
                    content="",
                    model_id=request.model_id,
                    provider=ProviderType.ANTHROPIC,
                    finish_reason=final_msg.stop_reason or "stop",
                    usage=usage,
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
            return self._health
        try:
            t0 = time.monotonic()
            # minimal probe: list models endpoint is lightweight
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
    def _build_messages(request: CompletionRequest) -> List[dict]:
        messages = []
        for msg in request.messages:
            if msg.role == "system":
                continue  # system goes in top-level param
            messages.append({"role": msg.role, "content": msg.content})
        return messages

    @staticmethod
    def _extract_content(response) -> str:
        parts = []
        for block in response.content:
            if hasattr(block, "text"):
                parts.append(block.text)
        return "".join(parts)

    @staticmethod
    def _extract_tool_calls(response) -> List[dict] | None:
        calls = []
        for block in response.content:
            if block.type == "tool_use":
                calls.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
        return calls if calls else None
