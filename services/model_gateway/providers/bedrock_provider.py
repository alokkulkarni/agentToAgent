"""
AWS Bedrock Provider — via the Converse / ConverseStream API

Supports all Bedrock-hosted models uniformly through the unified Converse
interface, which abstracts over each model's native request/response format.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from typing import AsyncIterator, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError, EndpointResolutionError

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


class BedrockProvider(BaseProvider):
    """
    AWS Bedrock provider using the Converse / ConverseStream API.
    Works with cross-region inference profiles and on-demand throughput.

    Credential resolution order (first match wins):
      1. Role assumption  — set BEDROCK_ROLE_ARN.  The STS call that assumes
         the role uses static keys (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY)
         when present, otherwise the default boto3 credential chain.
         Credentials are automatically refreshed before they expire.
      2. Static keys      — AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY
         (optionally with AWS_SESSION_TOKEN).
      3. Default chain    — IAM instance profile, ECS task role, ~/.aws/,
         environment variables, etc. (boto3 standard precedence).

    Region configuration (first match wins):
        BEDROCK_REGION  →  AWS_REGION  →  "us-east-1"

    Optional env vars:
        BEDROCK_ROLE_ARN              — IAM role ARN to assume
        BEDROCK_ROLE_EXTERNAL_ID      — STS ExternalId condition (if required)
        BEDROCK_ROLE_SESSION_NAME     — STS session name  (default: model-gateway)
        BEDROCK_ROLE_DURATION_SECONDS — credential lifetime in seconds (default: 3600)
        BEDROCK_ENDPOINT_URL          — custom VPC endpoint URL (optional)
        BEDROCK_REGION / AWS_REGION   — AWS region
    """

    provider_type = ProviderType.BEDROCK
    # Refresh assumed-role credentials when fewer than this many seconds remain
    _REFRESH_BUFFER_SECONDS = 300

    def __init__(self) -> None:
        super().__init__()
        self._region: str = (
            os.getenv("BEDROCK_REGION")
            or os.getenv("AWS_REGION", "us-east-1")
        )
        self._role_arn: Optional[str] = os.getenv("BEDROCK_ROLE_ARN", "").strip() or None
        self._role_external_id: Optional[str] = (
            os.getenv("BEDROCK_ROLE_EXTERNAL_ID", "").strip() or None
        )
        self._role_session_name: str = os.getenv(
            "BEDROCK_ROLE_SESSION_NAME", "model-gateway"
        )
        self._role_duration_seconds: int = int(
            os.getenv("BEDROCK_ROLE_DURATION_SECONDS", "3600")
        )
        self._cred_expiry: Optional[float] = None  # POSIX timestamp
        self._client_lock = threading.Lock()
        try:
            self._client = self._build_client()
            logger.info(
                "BedrockProvider initialised in region %s (role: %s).",
                self._region,
                self._role_arn or "none — using credential chain",
            )
        except Exception as exc:
            logger.warning("Could not initialise Bedrock client: %s", exc)
            self._client = None
            self._health.is_healthy = False

    # ------------------------------------------------------------------
    # Provider catalogue — all Bedrock-hosted models
    # ------------------------------------------------------------------

    def list_models(self) -> List[ModelInfo]:
        return [
            # ── Anthropic Claude on Bedrock ──────────────────────────
            # Claude 4.6-series (latest, Feb 2026)
            ModelInfo(
                model_id="anthropic.claude-opus-4-6-20260205-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Claude Opus 4.6 (Bedrock)",
                tier=ModelTier.PREMIUM,
                context_window=200_000,
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
                cost=TokenCost(input_per_million=5.0, output_per_million=25.0),
                metadata={
                    "bedrock_region": "us-east-1",
                    "supports_extended_thinking": True,
                    "adaptive_thinking": True,
                },
            ),
            ModelInfo(
                model_id="anthropic.claude-sonnet-4-6-20260217-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Claude Sonnet 4.6 (Bedrock)",
                tier=ModelTier.BALANCED,
                context_window=200_000,
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
                cost=TokenCost(input_per_million=3.0, output_per_million=15.0),
                metadata={
                    "bedrock_region": "us-east-1",
                    "supports_extended_thinking": True,
                    "adaptive_thinking": True,
                },
            ),
            # Claude 4.5-series (Nov 2025)
            ModelInfo(
                model_id="anthropic.claude-opus-4-5-20251101-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Claude Opus 4.5 (Bedrock)",
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
                    TaskType.GENERAL: 1.0,    TaskType.CODING: 1.0,
                    TaskType.REASONING: 1.0,  TaskType.CREATIVE: 1.0,
                    TaskType.SUMMARIZATION: 0.95, TaskType.MATH: 1.0,
                    TaskType.LONG_CONTEXT: 1.0, TaskType.CHAT: 1.0,
                },
                cost=TokenCost(input_per_million=15.0, output_per_million=75.0),
                metadata={"bedrock_region": "us-east-1"},
            ),
            ModelInfo(
                model_id="anthropic.claude-sonnet-4-5-20250514-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Claude Sonnet 4.5 (Bedrock)",
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
                cost=TokenCost(input_per_million=3.0, output_per_million=15.0),
                metadata={"bedrock_region": "us-east-1"},
            ),
            # Claude 3.7 Sonnet with extended thinking (Feb 2025)
            ModelInfo(
                model_id="anthropic.claude-3-7-sonnet-20250219-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Claude 3.7 Sonnet (Bedrock, Extended Thinking)",
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
                cost=TokenCost(input_per_million=3.0, output_per_million=15.0),
                metadata={
                    "bedrock_region": "us-east-1",
                    "supports_extended_thinking": True,
                    "thinking_budget_tokens": 16000,
                },
            ),
            ModelInfo(
                model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
                provider=ProviderType.BEDROCK,
                display_name="Claude 3.5 Sonnet v2 (Bedrock)",
                tier=ModelTier.BALANCED,
                context_window=200_000,
                max_output_tokens=8_096,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.JSON_MODE,
                    ModelCapability.FUNCTION_CALLING, ModelCapability.LONG_CONTEXT,
                    ModelCapability.CODE,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.92,  TaskType.CODING: 0.95,
                    TaskType.REASONING: 0.88, TaskType.SUMMARIZATION: 0.92,
                    TaskType.VISION: 0.88,   TaskType.LONG_CONTEXT: 0.92,
                    TaskType.CHAT: 0.92,
                },
                cost=TokenCost(input_per_million=3.0, output_per_million=15.0),
            ),
            ModelInfo(
                model_id="anthropic.claude-3-5-haiku-20241022-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Claude 3.5 Haiku (Bedrock)",
                tier=ModelTier.ECONOMY,
                context_window=200_000,
                max_output_tokens=8_096,
                capabilities=[
                    ModelCapability.TOOLS, ModelCapability.STREAMING,
                    ModelCapability.JSON_MODE, ModelCapability.CODE,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.80, TaskType.FAST: 1.0,
                    TaskType.CHAT: 0.88,    TaskType.CLASSIFICATION: 0.88,
                    TaskType.EXTRACTION: 0.85,
                },
                cost=TokenCost(input_per_million=0.8, output_per_million=4.0),
            ),
            ModelInfo(
                model_id="anthropic.claude-3-opus-20240229-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Claude 3 Opus (Bedrock, Legacy)",
                tier=ModelTier.PREMIUM,
                context_window=200_000,
                max_output_tokens=4_096,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.CODE,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.88,  TaskType.REASONING: 0.90,
                    TaskType.CREATIVE: 0.90, TaskType.LONG_CONTEXT: 0.88,
                },
                cost=TokenCost(input_per_million=15.0, output_per_million=75.0),
                is_deprecated=True,
            ),
            # ── Amazon Nova ──────────────────────────────────────────
            # Nova Premier — flagship multimodal (Jan 2025)
            ModelInfo(
                model_id="amazon.nova-premier-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Amazon Nova Premier",
                tier=ModelTier.PREMIUM,
                context_window=1_000_000,
                max_output_tokens=10_000,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.LONG_CONTEXT,
                    ModelCapability.FUNCTION_CALLING, ModelCapability.CODE,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.92,  TaskType.CODING: 0.88,
                    TaskType.REASONING: 0.88, TaskType.VISION: 0.92,
                    TaskType.LONG_CONTEXT: 1.0, TaskType.SUMMARIZATION: 0.92,
                    TaskType.EXTRACTION: 0.90, TaskType.CHAT: 0.90,
                },
                cost=TokenCost(input_per_million=2.5, output_per_million=12.5),
            ),
            ModelInfo(
                model_id="amazon.nova-pro-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Amazon Nova Pro",
                tier=ModelTier.BALANCED,
                context_window=300_000,
                max_output_tokens=5_120,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.LONG_CONTEXT,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.85,  TaskType.SUMMARIZATION: 0.88,
                    TaskType.EXTRACTION: 0.88, TaskType.VISION: 0.85,
                    TaskType.LONG_CONTEXT: 0.88, TaskType.CHAT: 0.85,
                },
                cost=TokenCost(input_per_million=0.8, output_per_million=3.2),
            ),
            ModelInfo(
                model_id="amazon.nova-lite-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Amazon Nova Lite",
                tier=ModelTier.ECONOMY,
                context_window=300_000,
                max_output_tokens=5_120,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.LONG_CONTEXT,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.75, TaskType.FAST: 0.90,
                    TaskType.CLASSIFICATION: 0.82, TaskType.EXTRACTION: 0.80,
                    TaskType.CHAT: 0.80,
                },
                cost=TokenCost(input_per_million=0.06, output_per_million=0.24),
            ),
            ModelInfo(
                model_id="amazon.nova-micro-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Amazon Nova Micro",
                tier=ModelTier.ECONOMY,
                context_window=128_000,
                max_output_tokens=5_120,
                capabilities=[ModelCapability.STREAMING],
                task_suitability={
                    TaskType.GENERAL: 0.65, TaskType.FAST: 1.0,
                    TaskType.CLASSIFICATION: 0.75,
                },
                cost=TokenCost(input_per_million=0.035, output_per_million=0.14),
            ),
            # ── Meta Llama 4 (Apr 2025) ───────────────────────────────
            ModelInfo(
                model_id="meta.llama4-maverick-17b-128e-instruct-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Llama 4 Maverick 17B 128E (Bedrock)",
                tier=ModelTier.BALANCED,
                context_window=1_000_000,
                max_output_tokens=8_192,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.TOOLS,
                    ModelCapability.STREAMING, ModelCapability.LONG_CONTEXT,
                    ModelCapability.CODE, ModelCapability.MULTILINGUAL,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.90,  TaskType.CODING: 0.88,
                    TaskType.REASONING: 0.88, TaskType.VISION: 0.88,
                    TaskType.LONG_CONTEXT: 0.92, TaskType.CHAT: 0.90,
                    TaskType.SUMMARIZATION: 0.88,
                },
                cost=TokenCost(input_per_million=0.24, output_per_million=0.77),
            ),
            ModelInfo(
                model_id="meta.llama4-scout-17b-instruct-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Llama 4 Scout 17B (Bedrock)",
                tier=ModelTier.ECONOMY,
                context_window=10_000_000,
                max_output_tokens=8_192,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.STREAMING,
                    ModelCapability.LONG_CONTEXT, ModelCapability.CODE,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.85,  TaskType.FAST: 0.90,
                    TaskType.LONG_CONTEXT: 1.0, TaskType.CHAT: 0.85,
                    TaskType.VISION: 0.82,   TaskType.SUMMARIZATION: 0.85,
                },
                cost=TokenCost(input_per_million=0.17, output_per_million=0.66),
            ),
            # ── Meta Llama 3.3 (Nov 2024) ─────────────────────────────
            ModelInfo(
                model_id="meta.llama3-3-70b-instruct-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Llama 3.3 70B Instruct (Bedrock)",
                tier=ModelTier.BALANCED,
                context_window=128_000,
                max_output_tokens=8_192,
                capabilities=[
                    ModelCapability.STREAMING, ModelCapability.CODE,
                    ModelCapability.TOOLS,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.85,  TaskType.CODING: 0.85,
                    TaskType.REASONING: 0.82, TaskType.CHAT: 0.85,
                    TaskType.SUMMARIZATION: 0.82,
                },
                cost=TokenCost(input_per_million=0.72, output_per_million=0.72),
            ),
            # ── Meta Llama 3.2 (Sep 2024) ────────────────────────────
            ModelInfo(
                model_id="meta.llama3-2-90b-instruct-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Llama 3.2 90B Instruct (Bedrock)",
                tier=ModelTier.BALANCED,
                context_window=128_000,
                max_output_tokens=2_048,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.STREAMING, ModelCapability.CODE,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.82,  TaskType.CODING: 0.82,
                    TaskType.VISION: 0.80,   TaskType.CHAT: 0.82,
                },
                cost=TokenCost(input_per_million=2.0, output_per_million=2.0),
            ),
            ModelInfo(
                model_id="meta.llama3-2-11b-instruct-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Llama 3.2 11B Instruct (Bedrock)",
                tier=ModelTier.ECONOMY,
                context_window=128_000,
                max_output_tokens=2_048,
                capabilities=[
                    ModelCapability.VISION, ModelCapability.STREAMING,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.72, TaskType.FAST: 0.88,
                    TaskType.VISION: 0.72,  TaskType.CHAT: 0.75,
                },
                cost=TokenCost(input_per_million=0.16, output_per_million=0.16),
            ),
            # ── Meta Llama 3 (Apr 2024) ───────────────────────────────
            ModelInfo(
                model_id="meta.llama3-70b-instruct-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Llama 3 70B Instruct (Bedrock)",
                tier=ModelTier.BALANCED,
                context_window=8_192,
                max_output_tokens=2_048,
                capabilities=[ModelCapability.STREAMING, ModelCapability.CODE],
                task_suitability={
                    TaskType.GENERAL: 0.78,  TaskType.CODING: 0.76,
                    TaskType.CHAT: 0.78,     TaskType.SUMMARIZATION: 0.76,
                },
                cost=TokenCost(input_per_million=2.65, output_per_million=3.5),
            ),
            ModelInfo(
                model_id="meta.llama3-8b-instruct-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Llama 3 8B Instruct (Bedrock)",
                tier=ModelTier.ECONOMY,
                context_window=8_192,
                max_output_tokens=2_048,
                capabilities=[ModelCapability.STREAMING],
                task_suitability={
                    TaskType.GENERAL: 0.62, TaskType.FAST: 0.88,
                    TaskType.CHAT: 0.68,
                },
                cost=TokenCost(input_per_million=0.3, output_per_million=0.6),
            ),
            # ── DeepSeek R1 (Jan 2025) ────────────────────────────────
            ModelInfo(
                model_id="deepseek.r1-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="DeepSeek R1 (Bedrock)",
                tier=ModelTier.REASONING,
                context_window=64_000,
                max_output_tokens=8_000,
                capabilities=[
                    ModelCapability.STREAMING, ModelCapability.REASONING,
                    ModelCapability.CODE,
                ],
                task_suitability={
                    TaskType.REASONING: 1.0, TaskType.MATH: 1.0,
                    TaskType.CODING: 0.92,   TaskType.GENERAL: 0.82,
                },
                cost=TokenCost(input_per_million=1.35, output_per_million=5.4),
            ),
            # ── Mistral ───────────────────────────────────────────────
            ModelInfo(
                model_id="mistral.mistral-large-2407-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Mistral Large 2 (Bedrock)",
                tier=ModelTier.BALANCED,
                context_window=128_000,
                max_output_tokens=8_192,
                capabilities=[
                    ModelCapability.TOOLS, ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING, ModelCapability.CODE,
                    ModelCapability.MULTILINGUAL,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.85,  TaskType.CODING: 0.88,
                    TaskType.REASONING: 0.85, TaskType.CHAT: 0.85,
                    TaskType.SUMMARIZATION: 0.82,
                },
                cost=TokenCost(input_per_million=3.0, output_per_million=9.0),
            ),
            ModelInfo(
                model_id="mistral.mistral-large-2402-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Mistral Large (Bedrock, Legacy)",
                tier=ModelTier.BALANCED,
                context_window=32_768,
                max_output_tokens=8_192,
                capabilities=[
                    ModelCapability.TOOLS, ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING, ModelCapability.CODE,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.80,  TaskType.CODING: 0.80,
                    TaskType.REASONING: 0.80, TaskType.CHAT: 0.80,
                },
                cost=TokenCost(input_per_million=3.0, output_per_million=9.0),
                is_deprecated=True,
            ),
            ModelInfo(
                model_id="mistral.mixtral-8x7b-instruct-v0:1",
                provider=ProviderType.BEDROCK,
                display_name="Mixtral 8x7B Instruct (Bedrock)",
                tier=ModelTier.ECONOMY,
                context_window=32_768,
                max_output_tokens=4_096,
                capabilities=[ModelCapability.STREAMING, ModelCapability.CODE],
                task_suitability={
                    TaskType.GENERAL: 0.70, TaskType.FAST: 0.82,
                    TaskType.CODING: 0.70,  TaskType.CHAT: 0.72,
                },
                cost=TokenCost(input_per_million=0.45, output_per_million=0.7),
            ),
            # ── Cohere ────────────────────────────────────────────────
            ModelInfo(
                model_id="cohere.command-r-plus-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Cohere Command R+ (Bedrock)",
                tier=ModelTier.BALANCED,
                context_window=128_000,
                max_output_tokens=4_096,
                capabilities=[
                    ModelCapability.TOOLS, ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING, ModelCapability.CODE,
                    ModelCapability.MULTILINGUAL,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.82,  TaskType.CODING: 0.80,
                    TaskType.EXTRACTION: 0.88, TaskType.CLASSIFICATION: 0.88,
                    TaskType.SUMMARIZATION: 0.85, TaskType.CHAT: 0.82,
                },
                cost=TokenCost(input_per_million=3.0, output_per_million=15.0),
            ),
            ModelInfo(
                model_id="cohere.command-r-v1:0",
                provider=ProviderType.BEDROCK,
                display_name="Cohere Command R (Bedrock)",
                tier=ModelTier.ECONOMY,
                context_window=128_000,
                max_output_tokens=4_096,
                capabilities=[
                    ModelCapability.TOOLS, ModelCapability.STREAMING,
                    ModelCapability.FUNCTION_CALLING,
                ],
                task_suitability={
                    TaskType.GENERAL: 0.75, TaskType.FAST: 0.85,
                    TaskType.EXTRACTION: 0.82, TaskType.CLASSIFICATION: 0.82,
                    TaskType.CHAT: 0.78,
                },
                cost=TokenCost(input_per_million=0.5, output_per_million=1.5),
            ),
        ]

    # ------------------------------------------------------------------
    # Completion
    # ------------------------------------------------------------------

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        if not self._client:
            raise RuntimeError("Bedrock client not initialised.")
        self._refresh_client_if_needed()

        t0 = time.monotonic()
        converse_kwargs = self._build_converse_request(request)

        try:
            # Bedrock is synchronous; run in executor to avoid blocking the event loop
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._client.converse(**converse_kwargs)
            )
            latency_ms = (time.monotonic() - t0) * 1000
            self._record_success(latency_ms)

            output = response.get("output", {})
            message = output.get("message", {})
            content_blocks = message.get("content", [])

            text_parts = [
                b.get("text", "") for b in content_blocks if "text" in b
            ]
            content = "".join(text_parts)

            tool_calls = None
            tool_use_blocks = [b for b in content_blocks if "toolUse" in b]
            if tool_use_blocks:
                tool_calls = [
                    {
                        "id": b["toolUse"]["toolUseId"],
                        "name": b["toolUse"]["name"],
                        "input": b["toolUse"]["input"],
                    }
                    for b in tool_use_blocks
                ]

            raw_usage = response.get("usage", {})
            usage = UsageMetrics(
                input_tokens=raw_usage.get("inputTokens", 0),
                output_tokens=raw_usage.get("outputTokens", 0),
                total_tokens=raw_usage.get("totalTokens", 0),
            )
            model_info = next(
                (m for m in self.list_models() if m.model_id == request.model_id), None
            )
            if model_info:
                usage.estimated_cost_usd = model_info.estimated_cost(
                    usage.input_tokens, usage.output_tokens
                )

            finish_reason = response.get("stopReason", "end_turn")
            return CompletionResponse(
                content=content,
                model_id=request.model_id,
                provider=ProviderType.BEDROCK,
                finish_reason=finish_reason,
                usage=usage,
                tool_calls=tool_calls,
                raw_response=response,
                latency_ms=latency_ms,
                request_id=request.request_id,
            )
        except ClientError as exc:
            self._record_failure(exc)
            raise

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamChunk]:
        if not self._client:
            raise RuntimeError("Bedrock client not initialised.")
        self._refresh_client_if_needed()

        converse_kwargs = self._build_converse_request(request)
        t0 = time.monotonic()

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._client.converse_stream(**converse_kwargs)
            )
            stream = response.get("stream", [])
            for event in stream:
                if "contentBlockDelta" in event:
                    delta = event["contentBlockDelta"].get("delta", {})
                    text = delta.get("text", "")
                    if text:
                        yield StreamChunk(
                            content=text,
                            model_id=request.model_id,
                            provider=ProviderType.BEDROCK,
                        )
                elif "messageStop" in event:
                    latency_ms = (time.monotonic() - t0) * 1000
                    self._record_success(latency_ms)
                    stop_reason = event["messageStop"].get("stopReason", "end_turn")
                    yield StreamChunk(
                        content="",
                        model_id=request.model_id,
                        provider=ProviderType.BEDROCK,
                        finish_reason=stop_reason,
                        is_final=True,
                    )
        except ClientError as exc:
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
        self._refresh_client_if_needed()
        try:
            t0 = time.monotonic()
            # Lightweight probe: describe the most commonly used model
            probe_model = "anthropic.claude-3-5-haiku-20241022-v1:0"
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._client.converse(
                    modelId=probe_model,
                    messages=[{"role": "user", "content": [{"text": "ping"}]}],
                    inferenceConfig={"maxTokens": 10},
                ),
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

    def _build_client(self):
        """
        Construct a boto3 bedrock-runtime client using the configured
        credential mechanism::

            BEDROCK_ROLE_ARN set?  →  assume role (STS)
            static keys set?       →  use them directly
            otherwise              →  boto3 default credential chain
        """
        key = os.getenv("AWS_ACCESS_KEY_ID", "").strip() or None
        secret = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip() or None
        token = os.getenv("AWS_SESSION_TOKEN", "").strip() or None
        endpoint_url = os.getenv("BEDROCK_ENDPOINT_URL", "").strip() or None

        # Build the source credentials session (used directly or as role-assumption base)
        if key and secret:
            source_session = boto3.Session(
                aws_access_key_id=key,
                aws_secret_access_key=secret,
                aws_session_token=token,
                region_name=self._region,
            )
            logger.debug("Bedrock credential source: static AWS keys.")
        else:
            source_session = boto3.Session(region_name=self._region)
            logger.debug("Bedrock credential source: default boto3 credential chain.")

        if self._role_arn:
            logger.info(
                "Bedrock: assuming IAM role %s (session=%s, duration=%ds).",
                self._role_arn,
                self._role_session_name,
                self._role_duration_seconds,
            )
            sts_client = source_session.client("sts")
            assume_kwargs: Dict = {
                "RoleArn": self._role_arn,
                "RoleSessionName": self._role_session_name,
                "DurationSeconds": self._role_duration_seconds,
            }
            if self._role_external_id:
                assume_kwargs["ExternalId"] = self._role_external_id

            resp = sts_client.assume_role(**assume_kwargs)
            creds = resp["Credentials"]
            # Store expiry for automatic refresh (boto3 expiry is a datetime)
            self._cred_expiry = creds["Expiration"].timestamp()

            assumed_session = boto3.Session(
                aws_access_key_id=creds["AccessKeyId"],
                aws_secret_access_key=creds["SecretAccessKey"],
                aws_session_token=creds["SessionToken"],
                region_name=self._region,
            )
            client_kwargs: Dict = {}
            if endpoint_url:
                client_kwargs["endpoint_url"] = endpoint_url
            return assumed_session.client("bedrock-runtime", **client_kwargs)

        # No role — use the source session directly
        client_kwargs = {}
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
        return source_session.client("bedrock-runtime", **client_kwargs)

    def _refresh_client_if_needed(self) -> None:
        """
        Re-assume the configured IAM role when the temporary credentials are
        within ``_REFRESH_BUFFER_SECONDS`` of expiring.  No-op when role
        assumption is not in use.

        The threading lock ensures only one thread rebuilds the client at a
        time; a second concurrent thread will find fresh credentials after the
        lock is released and skip the rebuild.
        """
        if not self._role_arn or self._cred_expiry is None:
            return
        if time.time() < self._cred_expiry - self._REFRESH_BUFFER_SECONDS:
            return

        with self._client_lock:
            # Re-check inside lock — another thread may have already refreshed
            if time.time() < self._cred_expiry - self._REFRESH_BUFFER_SECONDS:
                return
            logger.info(
                "Bedrock: assumed-role credentials expiring in <%.0fs — refreshing.",
                max(0.0, self._cred_expiry - time.time()),
            )
            try:
                self._client = self._build_client()
                logger.info("Bedrock: assumed-role credentials refreshed successfully.")
            except Exception as exc:
                logger.error("Bedrock: credential refresh failed: %s", exc)
                # Keep stale client — next call will likely fail with a 403
                # which the circuit breaker will handle

    @staticmethod
    def _build_converse_request(request: CompletionRequest) -> dict:
        messages = []
        system_parts = []

        for msg in request.messages:
            if msg.role == "system":
                if isinstance(msg.content, str):
                    system_parts.append({"text": msg.content})
                continue
            content = (
                [{"text": msg.content}]
                if isinstance(msg.content, str)
                else msg.content
            )
            messages.append({"role": msg.role, "content": content})

        # Override with explicit system_prompt if provided
        if request.system_prompt:
            system_parts = [{"text": request.system_prompt}]

        kwargs: dict = {
            "modelId": request.model_id,
            "messages": messages,
            "inferenceConfig": {
                "maxTokens": request.max_tokens,
                "temperature": request.temperature,
                "topP": request.top_p,
            },
        }
        if system_parts:
            kwargs["system"] = system_parts
        if request.tools:
            kwargs["toolConfig"] = {
                "tools": [
                    {"toolSpec": t} for t in request.tools
                ]
            }
        return kwargs
