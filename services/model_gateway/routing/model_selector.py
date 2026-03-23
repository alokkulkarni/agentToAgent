"""
Model Selector

Analyses an incoming request and selects the best model (primary +
ordered fallbacks) based on:

Priority order:
  1. Explicit caller override  (`preferred_model`, `preferred_provider`)
  2. Required capabilities      (vision, tools, long context, …)
  3. Task type detection        (coding, reasoning, creative, …)
  4. Cost optimisation tier     (economy vs balanced vs premium)
  5. Provider health            (skip providers with OPEN circuit)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from providers.base import (
    ModelCapability,
    ModelInfo,
    ModelTier,
    ProviderType,
    TaskType,
)
from routing.model_registry import ModelRegistry, get_model_registry
from routing.provider_config import get_live_config

logger = logging.getLogger(__name__)

_SELECTOR_INSTANCE: Optional[ModelSelector] = None


# ---------------------------------------------------------------------------
# Task-type keyword heuristics
# ---------------------------------------------------------------------------
_TASK_PATTERNS: Dict[TaskType, List[str]] = {
    TaskType.CODING: [
        r"\bcode\b", r"\bprogram\b", r"\bscript\b", r"\bfunction\b",
        r"\bclass\b", r"\bdebugg?\b", r"\brefactor\b", r"\bunit test\b",
        r"\bimplement\b", r"\bsyntax\b", r"\bpython\b", r"\bjavascript\b",
        r"\btypescript\b", r"\bjava\b", r"\bc\+\+\b", r"\brust\b",
        r"\bsql\b", r"\bapi\b",
    ],
    TaskType.REASONING: [
        r"\bwhy\b", r"\banalyse\b", r"\banalyze\b", r"\binfer\b",
        r"\breason\b", r"\blogic\b", r"\bproof\b", r"\btheorem\b",
        r"\bargue\b", r"\bcritically\b", r"\bstep.by.step\b",
        r"\bchain of thought\b", r"\blet.s think\b",
    ],
    TaskType.MATH: [
        r"\bmath\b", r"\bcalculate\b", r"\bequation\b", r"\bsolve\b",
        r"\bintegral\b", r"\bderivative\b", r"\bstatistics\b",
        r"\bprobability\b", r"\balgebra\b", r"\bgeometry\b",
    ],
    TaskType.CREATIVE: [
        r"\bwrite\b", r"\bpoem\b", r"\bstory\b", r"\bnovel\b",
        r"\bsong\b", r"\blyric\b", r"\bnarrative\b", r"\bimagine\b",
        r"\bcreative\b", r"\bfiction\b", r"\bblog post\b",
    ],
    TaskType.SUMMARIZATION: [
        r"\bsummar[iy]ze?\b", r"\bsummarise\b", r"\bbriefly\b",
        r"\btldr\b", r"\bkey points\b", r"\boverview\b", r"\bdigest\b",
    ],
    TaskType.EXTRACTION: [
        r"\bextract\b", r"\bparse\b", r"\bpull out\b", r"\bidentify\b",
        r"\bfind all\b", r"\blocate\b", r"\blist (the|all)\b",
    ],
    TaskType.CLASSIFICATION: [
        r"\bclassif[iy]\b", r"\bcategor[iy]ze?\b", r"\blabel\b",
        r"\bsentiment\b", r"\bdetect\b", r"\bwhich category\b",
    ],
    TaskType.VISION: [
        r"\bimage\b", r"\bphoto\b", r"\bpicture\b", r"\bscreenshot\b",
        r"\bdiagram\b", r"\bchart\b", r"\bvisual\b", r"\bwhat is in\b",
        r"\bdescribe (this |the )?(image|photo|picture)\b",
    ],
    TaskType.LONG_CONTEXT: [
        r"\blong document\b", r"\btranscript\b", r"\bfull text\b",
        r"\bbook\b", r"\breport\b", r"\brepository\b", r"\bwhole file\b",
    ],
    TaskType.FAST: [
        r"\bquick\b", r"\bfast\b", r"\bbrief\b", r"\bshort answer\b",
        r"\byes or no\b", r"\bone word\b", r"\bone sentence\b",
    ],
}

_COMPILED_PATTERNS: Dict[TaskType, List[re.Pattern]] = {
    task: [re.compile(p, re.IGNORECASE) for p in patterns]
    for task, patterns in _TASK_PATTERNS.items()
}


@dataclass
class SelectionResult:
    """Result of model selection — primary model plus ranked fallbacks."""
    primary: ModelInfo
    fallbacks: List[ModelInfo]
    detected_task: TaskType
    required_capabilities: List[ModelCapability]
    selection_reason: str
    estimated_cost_usd_per_1k: Optional[float] = None
    preferred_by_caller: bool = False


class ModelSelector:
    """
    Stateless (except for registry reference) model selector.
    The health-aware logic is handled by the FallbackManager; here
    we only consider registry data and request hints.
    """

    def __init__(self, registry: Optional[ModelRegistry] = None) -> None:
        self._registry = registry or get_model_registry()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select(
        self,
        messages_text: str,
        *,
        preferred_model: Optional[str] = None,
        preferred_provider: Optional[ProviderType] = None,
        required_capabilities: Optional[List[ModelCapability]] = None,
        context_tokens_needed: Optional[int] = None,
        cost_tier: Optional[ModelTier] = None,
        unhealthy_providers: Optional[List[ProviderType]] = None,
        stream: bool = False,
    ) -> SelectionResult:
        """
        Select the best model for the given request context.

        Parameters
        ----------
        messages_text     : concatenation of all message contents for analysis
        preferred_model   : explicit model_id requested by the caller
        preferred_provider: restrict to a specific provider
        required_capabilities: capabilities that must be present (e.g. VISION)
        context_tokens_needed : total input context size in tokens (approx)
        cost_tier         : force a specific tier (economy / balanced / premium)
        unhealthy_providers   : providers whose circuit is OPEN
        stream            : whether streaming is needed (filters non-streaming models)
        """
        unhealthy = set(unhealthy_providers or [])
        caps = list(required_capabilities or [])
        if stream:
            if ModelCapability.STREAMING not in caps:
                caps.append(ModelCapability.STREAMING)

        # Read live provider config on every call so runtime updates take effect
        cfg = get_live_config()

        # ── 1. Explicit model override ─────────────────────────────
        if preferred_model:
            model = self._registry.get_model(preferred_model)
            if model and model.provider not in unhealthy:
                fallbacks = self._registry.find_similar_models(
                    preferred_model, exclude_provider=None
                )
                fallbacks = [f for f in fallbacks if f.provider not in unhealthy]
                return SelectionResult(
                    primary=model,
                    fallbacks=fallbacks,
                    detected_task=TaskType.GENERAL,
                    required_capabilities=caps,
                    selection_reason=f"Explicit model override: {preferred_model}",
                    preferred_by_caller=True,
                )

        # ── 2. Detect task type ────────────────────────────────────
        task = self._detect_task(messages_text)
        logger.debug("Detected task: %s", task.value)

        # Auto-add VISION capability when task is vision
        if task == TaskType.VISION and ModelCapability.VISION not in caps:
            caps.append(ModelCapability.VISION)
        if task == TaskType.REASONING and ModelCapability.REASONING not in caps:
            # Don't force it — reasoning models are expensive; just prefer them
            pass

        # ── 3. Determine effective tier ───────────────────────────
        effective_tier = cost_tier or self._tier_for_task(task, cfg.cost_optimize)

        # ── 4. Candidate filtering & ranking ──────────────────────
        providers_filter = None
        if preferred_provider and preferred_provider not in unhealthy:
            providers_filter = [preferred_provider]
        else:
            # Use live config's enabled providers in priority order
            enabled_ordered = cfg.enabled_providers  # excludes disabled providers
            healthy_enabled = [p for p in enabled_ordered if p not in unhealthy]
            providers_filter = healthy_enabled if healthy_enabled else None

        candidates = self._registry.best_models_for_task(
            task=task,
            min_score=0.5,
            providers=providers_filter,
            tiers=[effective_tier],
            require_capabilities=caps if caps else None,
            max_context_needed=context_tokens_needed,
        )

        # Widen tier if no candidates found at preferred tier
        if not candidates:
            candidates = self._registry.best_models_for_task(
                task=task,
                min_score=0.4,
                providers=providers_filter,
                require_capabilities=caps if caps else None,
                max_context_needed=context_tokens_needed,
            )

        # Fall back to any available model within enabled providers if still nothing
        if not candidates:
            candidates = self._registry.best_models_for_task(
                task=TaskType.GENERAL,
                providers=providers_filter if providers_filter else None,
            )

        # Filter out providers with open circuit
        candidates = [m for m in candidates if m.provider not in unhealthy]

        if not candidates:
            # Last resort: any non-deprecated model — still respect enabled providers
            candidates = self._registry.all_models()
            if providers_filter:
                _pf_set = set(providers_filter)
                candidates = [m for m in candidates if m.provider in _pf_set]
            candidates = [m for m in candidates if m.provider not in unhealthy]

        if not candidates:
            raise RuntimeError("No models available — all providers are unhealthy.")

        primary = candidates[0]

        # Fallbacks: next 4 candidates, prioritise different providers
        fallbacks = self._diversify_fallbacks(candidates[1:], primary.provider)

        reason = (
            f"Task={task.value}, Tier={effective_tier.value}, "
            f"Caps={[c.value for c in caps]}"
        )

        # Rough cost estimate per 1k tokens (avg in/out)
        est_cost = (
            (primary.cost.input_per_million + primary.cost.output_per_million)
            / 2_000  # per 1k tokens
        )

        return SelectionResult(
            primary=primary,
            fallbacks=fallbacks,
            detected_task=task,
            required_capabilities=caps,
            selection_reason=reason,
            estimated_cost_usd_per_1k=round(est_cost, 6),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _detect_task(self, text: str) -> TaskType:
        if not text:
            return TaskType.GENERAL

        # Score each task type by counting pattern hits
        scores: Dict[TaskType, int] = {}
        for task, patterns in _COMPILED_PATTERNS.items():
            score = sum(1 for p in patterns if p.search(text))
            if score:
                scores[task] = score

        if not scores:
            return TaskType.GENERAL

        # Apply rough context-length hint
        word_count = len(text.split())
        if word_count > 2000 and TaskType.LONG_CONTEXT not in scores:
            scores[TaskType.LONG_CONTEXT] = 1

        return max(scores, key=lambda t: scores[t])

    @staticmethod
    def _tier_for_task(task: TaskType, cost_optimize: bool = True) -> ModelTier:
        """Map task type to recommended tier, respecting the live cost_optimize flag."""
        tier_map: Dict[TaskType, ModelTier] = {
            TaskType.FAST: ModelTier.ECONOMY,
            TaskType.CLASSIFICATION: ModelTier.ECONOMY,
            TaskType.SUMMARIZATION: ModelTier.ECONOMY,
            TaskType.EXTRACTION: ModelTier.ECONOMY,
            TaskType.CHAT: ModelTier.BALANCED,
            TaskType.GENERAL: ModelTier.BALANCED,
            TaskType.CODING: ModelTier.BALANCED,
            TaskType.CREATIVE: ModelTier.BALANCED,
            TaskType.LONG_CONTEXT: ModelTier.BALANCED,
            TaskType.VISION: ModelTier.BALANCED,
            TaskType.REASONING: ModelTier.PREMIUM,
            TaskType.MATH: ModelTier.PREMIUM,
        }
        default = ModelTier.ECONOMY if cost_optimize else ModelTier.BALANCED
        tier = tier_map.get(task, default)

        # Downgrade if cost_optimize forces economy
        if cost_optimize and tier == ModelTier.PREMIUM:
            return ModelTier.BALANCED
        return tier

    @staticmethod
    def _diversify_fallbacks(
        candidates: List[ModelInfo], primary_provider: ProviderType
    ) -> List[ModelInfo]:
        """
        Select up to 4 fallbacks, preferring models from different providers
        so that a full provider outage is still handled.
        """
        seen_providers = {primary_provider}
        diverse: List[ModelInfo] = []

        # First pass: prefer different providers
        for m in candidates:
            if m.provider not in seen_providers:
                diverse.append(m)
                seen_providers.add(m.provider)
            if len(diverse) >= 4:
                break

        # Second pass: fill remaining with same-provider alternatives
        if len(diverse) < 4:
            for m in candidates:
                if m not in diverse:
                    diverse.append(m)
                if len(diverse) >= 4:
                    break

        return diverse


def get_model_selector() -> ModelSelector:
    global _SELECTOR_INSTANCE
    if _SELECTOR_INSTANCE is None:
        _SELECTOR_INSTANCE = ModelSelector()
    return _SELECTOR_INSTANCE
