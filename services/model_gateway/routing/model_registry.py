"""
Model Registry

Aggregates the model catalogues from all providers into a single,
query-able registry. Provides lookup by model ID, provider, capability,
tier, and task suitability.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from providers.base import (
    ModelCapability,
    ModelInfo,
    ModelTier,
    ProviderType,
    TaskType,
)
from providers.anthropic_provider import AnthropicProvider
from providers.bedrock_provider import BedrockProvider
from providers.gemini_provider import GeminiProvider
from providers.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

_REGISTRY_INSTANCE: Optional[ModelRegistry] = None


class ModelRegistry:
    """
    Single source of truth for all available LLM models across every provider.

    The registry is populated at startup from each provider's static catalogue
    and can be queried by various dimensions.
    """

    def __init__(self) -> None:
        self._models: Dict[str, ModelInfo] = {}
        self._build()

    def _build(self) -> None:
        """Populate registry from provider catalogues."""
        providers = [
            AnthropicProvider(),
            BedrockProvider(),
            GeminiProvider(),
            OpenAIProvider(),
        ]
        for provider in providers:
            for model in provider.list_models():
                self._models[model.model_id] = model
        logger.info("ModelRegistry built with %d models.", len(self._models))

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def all_models(self, include_deprecated: bool = False) -> List[ModelInfo]:
        """Return all registered models."""
        models = list(self._models.values())
        if not include_deprecated:
            models = [m for m in models if not m.is_deprecated]
        return models

    def get_model(self, model_id: str) -> Optional[ModelInfo]:
        """Return a specific model by its ID."""
        return self._models.get(model_id)

    def models_for_provider(
        self, provider: ProviderType, include_deprecated: bool = False
    ) -> List[ModelInfo]:
        models = [m for m in self._models.values() if m.provider == provider]
        if not include_deprecated:
            models = [m for m in models if not m.is_deprecated]
        return models

    def models_with_capability(
        self, capability: ModelCapability, include_deprecated: bool = False
    ) -> List[ModelInfo]:
        models = [
            m for m in self._models.values()
            if capability in m.capabilities and (include_deprecated or not m.is_deprecated)
        ]
        return models

    def models_for_tier(
        self, tier: ModelTier, include_deprecated: bool = False
    ) -> List[ModelInfo]:
        models = [
            m for m in self._models.values()
            if m.tier == tier and (include_deprecated or not m.is_deprecated)
        ]
        return models

    def best_models_for_task(
        self,
        task: TaskType,
        min_score: float = 0.0,
        providers: Optional[List[ProviderType]] = None,
        tiers: Optional[List[ModelTier]] = None,
        require_capabilities: Optional[List[ModelCapability]] = None,
        max_context_needed: Optional[int] = None,
        include_deprecated: bool = False,
    ) -> List[ModelInfo]:
        """
        Return models ranked by suitability for a given task, with optional filters.
        """
        candidates = [
            m for m in self._models.values()
            if not (m.is_deprecated and not include_deprecated)
        ]

        if providers:
            candidates = [m for m in candidates if m.provider in providers]
        if tiers:
            candidates = [m for m in candidates if m.tier in tiers]
        if require_capabilities:
            candidates = [
                m for m in candidates
                if all(cap in m.capabilities for cap in require_capabilities)
            ]
        if max_context_needed is not None:
            candidates = [
                m for m in candidates if m.context_window >= max_context_needed
            ]

        scored = [
            (m, m.supports_task(task))
            for m in candidates
        ]
        scored = [(m, s) for m, s in scored if s >= min_score]
        # Primary sort: score desc; secondary: cost asc (prefer cheaper at equal score)
        scored.sort(key=lambda x: (-x[1], x[0].cost.input_per_million))
        return [m for m, _ in scored]

    def find_similar_models(
        self,
        model_id: str,
        exclude_provider: Optional[ProviderType] = None,
        max_results: int = 3,
    ) -> List[ModelInfo]:
        """
        Find models from other providers that are similar in tier and
        task suitability to the given model. Used for cross-provider fallback.
        """
        source = self.get_model(model_id)
        if not source:
            return []

        candidates = [
            m for m in self._models.values()
            if m.model_id != model_id
            and not m.is_deprecated
            and (exclude_provider is None or m.provider != exclude_provider)
        ]

        # Score by tier match + task profile similarity
        def similarity(m: ModelInfo) -> float:
            tier_match = 1.0 if m.tier == source.tier else 0.5
            # Cosine-like similarity between task suitability vectors
            common_tasks = set(source.task_suitability) & set(m.task_suitability)
            if not common_tasks:
                return 0.0
            dot = sum(
                source.task_suitability[t] * m.task_suitability[t]
                for t in common_tasks
            )
            mag_src = sum(v ** 2 for v in source.task_suitability.values()) ** 0.5
            mag_tgt = sum(v ** 2 for v in m.task_suitability.values()) ** 0.5
            cosine = dot / (mag_src * mag_tgt) if (mag_src and mag_tgt) else 0.0
            return tier_match * cosine

        ranked = sorted(candidates, key=similarity, reverse=True)
        return ranked[:max_results]

    def summary(self) -> Dict:
        """Return a summary dict for /v1/models listing."""
        by_provider: Dict[str, List[dict]] = {}
        for model in self.all_models():
            pname = model.provider.value
            by_provider.setdefault(pname, []).append({
                "id": model.model_id,
                "name": model.display_name,
                "tier": model.tier.value,
                "context_window": model.context_window,
                "max_output_tokens": model.max_output_tokens,
                "capabilities": [c.value for c in model.capabilities],
                "task_suitability": {k.value: v for k, v in model.task_suitability.items()},
                "cost": {
                    "input_per_million_usd": model.cost.input_per_million,
                    "output_per_million_usd": model.cost.output_per_million,
                },
                "supports_streaming": model.supports_streaming,
                "is_deprecated": model.is_deprecated,
            })
        return {
            "total": len(self._models),
            "providers": by_provider,
        }


def get_model_registry() -> ModelRegistry:
    global _REGISTRY_INSTANCE
    if _REGISTRY_INSTANCE is None:
        _REGISTRY_INSTANCE = ModelRegistry()
    return _REGISTRY_INSTANCE
