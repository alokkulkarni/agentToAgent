"""
Google Gemini Provider — via the google-generativeai SDK

Supports all Gemini models including the 2M-context Gemini 1.5 Pro.
Handles streaming, tool calling, and vision (image input).
"""

from __future__ import annotations

import logging
import os
import time
from typing import AsyncIterator, List, Optional

import google.generativeai as genai
from google.api_core.exceptions import GoogleAPIError, ResourceExhausted

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


class GeminiProvider(BaseProvider):
    """
    Google Gemini provider via google-generativeai SDK.
    Requires GEMINI_API_KEY (or GOOGLE_API_KEY) environment variable.
    """

    provider_type = ProviderType.GEMINI

    def __init__(self) -> None:
        super().__init__()
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY not set — Gemini provider will be unavailable.")
            self._health.is_healthy = False
            self._available = False
        else:
            genai.configure(api_key=api_key)
            self._available = True
            logger.info("GeminiProvider initialised.")

    # ------------------------------------------------------------------
    # Provider catalogue
    # ------------------------------------------------------------------

    def list_models(self) -> List[ModelInfo]:
        return [
            # ── Gemini 3 series (2025–2026) ──────────────────────────
            # gemini-3.1-pro-preview — best reasoning+agentic (Feb 2026)
            ModelInfo(
                model_id="gemini-3.1-pro-preview",
                provider=ProviderType.GEMINI,
                display_name="Gemini 3.1 Pro Preview",
                tier=ModelTier.REASONING,
                context_window=1_048_576,
                max_output_tokens=65_536,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.JSON_MODE,
                    ModelCapability.FUNCTION_CALLING, ModelCapability.LONG_CONTEXT,
                    ModelCapability.CODE, ModelCapability.MULTILINGUAL,
                    ModelCapability.REASONING,
                ],
                task_suitability={
                    TaskType.GENERAL: 1.0,   TaskType.CODING: 1.0,
                    TaskType.REASONING: 1.0, TaskType.MATH: 1.0,
                    TaskType.CREATIVE: 0.95, TaskType.VISION: 0.97,
                    TaskType.LONG_CONTEXT: 1.0, TaskType.SUMMARIZATION: 0.97,
                    TaskType.EXTRACTION: 0.97, TaskType.CHAT: 0.95,
                },
                cost=TokenCost(input_per_million=1.25, output_per_million=10.0),
                metadata={
                    "supports_thinking": True,
                    "knowledge_cutoff": "2025-01",
                    "release_date": "2026-02",
                    "custom_tools_variant": "gemini-3.1-pro-preview-customtools",
                },
            ),
            # gemini-3-flash-preview — frontier multimodal + agentic (Dec 2025)
            ModelInfo(
                model_id="gemini-3-flash-preview",
                provider=ProviderType.GEMINI,
                display_name="Gemini 3 Flash Preview",
                tier=ModelTier.PREMIUM,
                context_window=1_048_576,
                max_output_tokens=65_536,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.JSON_MODE,
                    ModelCapability.FUNCTION_CALLING, ModelCapability.LONG_CONTEXT,
                    ModelCapability.CODE, ModelCapability.MULTILINGUAL,
                    ModelCapability.REASONING,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.97,  TaskType.CODING: 0.97,
                    TaskType.REASONING: 0.95, TaskType.MATH: 0.95,
                    TaskType.CREATIVE: 0.95, TaskType.VISION: 0.98,
                    TaskType.LONG_CONTEXT: 0.97, TaskType.SUMMARIZATION: 0.95,
                    TaskType.EXTRACTION: 0.95, TaskType.CHAT: 0.97,
                    TaskType.FAST: 0.92,
                },
                cost=TokenCost(input_per_million=0.15, output_per_million=0.60),
                metadata={
                    "supports_thinking": True,
                    "knowledge_cutoff": "2025-01",
                    "release_date": "2025-12",
                },
            ),
            # ── Gemini 2.5 series (stable GA, mid-2025) ──────────────
            # gemini-2.5-pro — state-of-the-art reasoning + coding
            ModelInfo(
                model_id="gemini-2.5-pro",
                provider=ProviderType.GEMINI,
                display_name="Gemini 2.5 Pro",
                tier=ModelTier.PREMIUM,
                context_window=1_048_576,
                max_output_tokens=65_536,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.JSON_MODE,
                    ModelCapability.FUNCTION_CALLING, ModelCapability.LONG_CONTEXT,
                    ModelCapability.CODE, ModelCapability.MULTILINGUAL,
                    ModelCapability.REASONING,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.96,  TaskType.CODING: 0.97,
                    TaskType.REASONING: 0.97, TaskType.MATH: 0.97,
                    TaskType.CREATIVE: 0.92, TaskType.VISION: 0.95,
                    TaskType.LONG_CONTEXT: 0.97, TaskType.SUMMARIZATION: 0.95,
                    TaskType.EXTRACTION: 0.95, TaskType.CHAT: 0.93,
                },
                cost=TokenCost(input_per_million=1.25, output_per_million=10.0),
                metadata={"supports_thinking": True, "release_date": "2025-06"},
            ),
            # gemini-2.5-flash — best price/performance, reasoning, high-volume
            ModelInfo(
                model_id="gemini-2.5-flash",
                provider=ProviderType.GEMINI,
                display_name="Gemini 2.5 Flash",
                tier=ModelTier.BALANCED,
                context_window=1_048_576,
                max_output_tokens=65_536,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.JSON_MODE,
                    ModelCapability.FUNCTION_CALLING, ModelCapability.LONG_CONTEXT,
                    ModelCapability.CODE, ModelCapability.MULTILINGUAL,
                    ModelCapability.REASONING,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.92,  TaskType.CODING: 0.90,
                    TaskType.REASONING: 0.88, TaskType.FAST: 0.95,
                    TaskType.VISION: 0.90,   TaskType.LONG_CONTEXT: 0.95,
                    TaskType.SUMMARIZATION: 0.92, TaskType.CHAT: 0.93,
                    TaskType.EXTRACTION: 0.90, TaskType.CLASSIFICATION: 0.90,
                },
                cost=TokenCost(input_per_million=0.075, output_per_million=0.30),
                metadata={"supports_thinking": True, "release_date": "2025-06"},
            ),
            # gemini-2.5-flash-lite — fastest + most budget-friendly
            ModelInfo(
                model_id="gemini-2.5-flash-lite",
                provider=ProviderType.GEMINI,
                display_name="Gemini 2.5 Flash-Lite",
                tier=ModelTier.ECONOMY,
                context_window=1_048_576,
                max_output_tokens=65_536,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.LONG_CONTEXT,
                    ModelCapability.CODE, ModelCapability.FUNCTION_CALLING,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.82,  TaskType.FAST: 1.0,
                    TaskType.CLASSIFICATION: 0.88, TaskType.EXTRACTION: 0.85,
                    TaskType.SUMMARIZATION: 0.82, TaskType.CHAT: 0.85,
                    TaskType.LONG_CONTEXT: 0.88,
                },
                cost=TokenCost(input_per_million=0.015, output_per_million=0.06),
                metadata={"supports_thinking": True, "release_date": "2025-07"},
            ),
            # ── Gemini 1.5 series (2024, still available) ────────────
            ModelInfo(
                model_id="gemini-1.5-pro-002",
                provider=ProviderType.GEMINI,
                display_name="Gemini 1.5 Pro 002",
                tier=ModelTier.BALANCED,
                context_window=2_000_000,
                max_output_tokens=8_192,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.FUNCTION_CALLING,
                    ModelCapability.LONG_CONTEXT, ModelCapability.CODE,
                    ModelCapability.MULTILINGUAL,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.90,  TaskType.CODING: 0.88,
                    TaskType.REASONING: 0.85, TaskType.CREATIVE: 0.82,
                    TaskType.VISION: 0.90,   TaskType.LONG_CONTEXT: 1.0,
                    TaskType.SUMMARIZATION: 0.90, TaskType.CHAT: 0.88,
                },
                cost=TokenCost(input_per_million=1.25, output_per_million=5.0),
            ),
            ModelInfo(
                model_id="gemini-1.5-flash-002",
                provider=ProviderType.GEMINI,
                display_name="Gemini 1.5 Flash 002",
                tier=ModelTier.ECONOMY,
                context_window=1_000_000,
                max_output_tokens=8_192,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.FUNCTION_CALLING,
                    ModelCapability.LONG_CONTEXT, ModelCapability.CODE,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.82,  TaskType.FAST: 0.90,
                    TaskType.CODING: 0.80,   TaskType.VISION: 0.82,
                    TaskType.LONG_CONTEXT: 0.90, TaskType.CHAT: 0.85,
                    TaskType.SUMMARIZATION: 0.82,
                },
                cost=TokenCost(input_per_million=0.075, output_per_million=0.30),
            ),
            ModelInfo(
                model_id="gemini-1.5-flash-8b",
                provider=ProviderType.GEMINI,
                display_name="Gemini 1.5 Flash 8B",
                tier=ModelTier.ECONOMY,
                context_window=1_000_000,
                max_output_tokens=8_192,
                capabilities=[
                    ModelCapability.STREAMING, ModelCapability.LONG_CONTEXT,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.70, TaskType.FAST: 1.0,
                    TaskType.CHAT: 0.76,    TaskType.CLASSIFICATION: 0.78,
                },
                cost=TokenCost(input_per_million=0.0375, output_per_million=0.15),
            ),
            # ── Deprecated ───────────────────────────────────────────
            ModelInfo(
                model_id="gemini-2.0-flash",
                provider=ProviderType.GEMINI,
                display_name="Gemini 2.0 Flash (Deprecated)",
                tier=ModelTier.ECONOMY,
                context_window=1_000_000,
                max_output_tokens=8_192,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.FUNCTION_CALLING,
                    ModelCapability.LONG_CONTEXT, ModelCapability.CODE,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.85, TaskType.FAST: 0.92,
                    TaskType.CHAT: 0.88,    TaskType.LONG_CONTEXT: 0.90,
                },
                cost=TokenCost(input_per_million=0.075, output_per_million=0.30),
                is_deprecated=True,
            ),
            ModelInfo(
                model_id="gemini-1.0-pro",
                provider=ProviderType.GEMINI,
                display_name="Gemini 1.0 Pro (Deprecated)",
                tier=ModelTier.ECONOMY,
                context_window=30_720,
                max_output_tokens=2_048,
                capabilities=[ModelCapability.STREAMING, ModelCapability.CODE],
                task_suitability={
                    TaskType.GENERAL: 0.65, TaskType.CHAT: 0.70,
                    TaskType.FAST: 0.78,
                },
                cost=TokenCost(input_per_million=0.5, output_per_million=1.5),
                is_deprecated=True,
            ),
        ]

    # ------------------------------------------------------------------
    # Completion
    # ------------------------------------------------------------------

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        if not self._available:
            raise RuntimeError("Gemini provider not initialised (missing API key).")

        t0 = time.monotonic()
        model_obj = genai.GenerativeModel(
            model_name=request.model_id,
            system_instruction=request.system_prompt or "",
            tools=request.tools or None,
        )
        generation_config = genai.types.GenerationConfig(
            max_output_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
        )
        contents = self._build_contents(request)

        try:
            response = await model_obj.generate_content_async(
                contents, generation_config=generation_config
            )
            latency_ms = (time.monotonic() - t0) * 1000
            self._record_success(latency_ms)

            content = response.text if hasattr(response, "text") else ""
            usage = UsageMetrics()
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                um = response.usage_metadata
                usage.input_tokens = getattr(um, "prompt_token_count", 0)
                usage.output_tokens = getattr(um, "candidates_token_count", 0)
                usage.total_tokens = getattr(um, "total_token_count", 0)
            model_info = next(
                (m for m in self.list_models() if m.model_id == request.model_id), None
            )
            if model_info:
                usage.estimated_cost_usd = model_info.estimated_cost(
                    usage.input_tokens, usage.output_tokens
                )

            finish_reason = "stop"
            if response.candidates:
                fr = response.candidates[0].finish_reason
                finish_reason = str(fr).lower() if fr else "stop"

            return CompletionResponse(
                content=content,
                model_id=request.model_id,
                provider=ProviderType.GEMINI,
                finish_reason=finish_reason,
                usage=usage,
                raw_response={"text": content},
                latency_ms=latency_ms,
                request_id=request.request_id,
            )
        except (GoogleAPIError, ResourceExhausted) as exc:
            self._record_failure(exc)
            raise

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        if not self._available:
            raise RuntimeError("Gemini provider not initialised (missing API key).")

        model_obj = genai.GenerativeModel(
            model_name=request.model_id,
            system_instruction=request.system_prompt or "",
        )
        generation_config = genai.types.GenerationConfig(
            max_output_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
        )
        contents = self._build_contents(request)
        t0 = time.monotonic()

        try:
            async for chunk in await model_obj.generate_content_async(
                contents, generation_config=generation_config, stream=True
            ):
                text = chunk.text if hasattr(chunk, "text") else ""
                if text:
                    yield StreamChunk(
                        content=text,
                        model_id=request.model_id,
                        provider=ProviderType.GEMINI,
                    )
            latency_ms = (time.monotonic() - t0) * 1000
            self._record_success(latency_ms)
            yield StreamChunk(
                content="",
                model_id=request.model_id,
                provider=ProviderType.GEMINI,
                finish_reason="stop",
                is_final=True,
            )
        except (GoogleAPIError, ResourceExhausted) as exc:
            self._record_failure(exc)
            raise

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> ProviderHealth:
        if not self._available:
            self._health.is_healthy = False
            self._health.circuit_state = CircuitState.OPEN
            self._health.checked_at = time.time()
            return self._health
        try:
            t0 = time.monotonic()
            model_obj = genai.GenerativeModel("gemini-1.5-flash-8b")
            await model_obj.generate_content_async(
                "ping",
                generation_config=genai.types.GenerationConfig(max_output_tokens=5),
            )
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
    def _build_contents(request: CompletionRequest) -> list:
        """Convert normalised messages to Gemini contents format."""
        contents = []
        for msg in request.messages:
            if msg.role == "system":
                continue  # handled via system_instruction
            role = "user" if msg.role == "user" else "model"
            if isinstance(msg.content, str):
                contents.append({"role": role, "parts": [{"text": msg.content}]})
            else:
                contents.append({"role": role, "parts": msg.content})
        return contents
