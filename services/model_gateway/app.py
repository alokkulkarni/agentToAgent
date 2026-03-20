"""
Model Gateway Service — Main Application
=========================================
A provider-agnostic LLM facade that:
  - Accepts normalised completion requests from the orchestrator or any agent
  - Selects the best model automatically (by task, tier, capabilities)
  - Executes with transparent fallback across providers
  - Audits every selection, call, response, and fallback
  - Exposes health, model-listing, and admin endpoints

Port: 8400 (configurable via MODEL_GATEWAY_PORT)
"""

from __future__ import annotations

import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Bootstrap: ensure the service directory is on sys.path so sub-modules resolve
# ---------------------------------------------------------------------------
_SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
if _SERVICE_DIR not in sys.path:
    sys.path.insert(0, _SERVICE_DIR)

load_dotenv()

# ---------------------------------------------------------------------------
# Internal imports (relative to services/model_gateway/)
# ---------------------------------------------------------------------------
from providers.base import (
    CompletionRequest,
    Message,
    ModelCapability,
    ModelTier,
    ProviderType,
    TaskType,
)
from providers.anthropic_provider import AnthropicProvider
from providers.bedrock_provider import BedrockProvider
from providers.gemini_provider import GeminiProvider
from providers.openai_provider import OpenAIProvider

from routing.model_registry import ModelRegistry, get_model_registry
from routing.model_selector import ModelSelector, get_model_selector
from routing.fallback_manager import FallbackManager, get_fallback_manager
from routing.provider_config import (
    GatewayProviderConfig,
    ProviderPreference,
    ProviderConfigStore,
    get_provider_config_store,
    get_live_config,
)

from audit.gateway_audit import GatewayAuditLogger, get_gateway_audit_logger
from health.provider_health import (
    ProviderHealthMonitor,
    get_health_monitor,
    set_health_monitor,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("model_gateway")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GATEWAY_HOST = os.getenv("MODEL_GATEWAY_HOST", "0.0.0.0")
GATEWAY_PORT = int(os.getenv("MODEL_GATEWAY_PORT", "8400"))

# ---------------------------------------------------------------------------
# Singletons (populated during lifespan)
# ---------------------------------------------------------------------------
_providers: Dict[ProviderType, Any] = {}
_registry: Optional[ModelRegistry] = None
_selector: Optional[ModelSelector] = None
_fallback_manager: Optional[FallbackManager] = None
_audit: Optional[GatewayAuditLogger] = None
_health_monitor: Optional[ProviderHealthMonitor] = None


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _providers, _registry, _selector, _fallback_manager, _audit, _health_monitor

    logger.info("Model Gateway starting up…")

    # Instantiate providers
    _providers = {
        ProviderType.ANTHROPIC: AnthropicProvider(),
        ProviderType.BEDROCK: BedrockProvider(),
        ProviderType.GEMINI: GeminiProvider(),
        ProviderType.OPENAI: OpenAIProvider(),
    }

    # Routing & registry
    _registry = get_model_registry()
    _selector = get_model_selector()
    _fallback_manager = get_fallback_manager()
    _audit = get_gateway_audit_logger()

    # Ensure provider config store is initialised (loads from disk or env)
    get_provider_config_store()

    # Health monitor
    _health_monitor = ProviderHealthMonitor(_providers, _fallback_manager)
    set_health_monitor(_health_monitor)
    await _health_monitor.start()

    logger.info(
        "Model Gateway ready — %d models registered across %d providers.",
        len(_registry.all_models()),
        len(_providers),
    )
    yield

    # Shutdown
    logger.info("Model Gateway shutting down…")
    if _health_monitor:
        await _health_monitor.stop()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Model Gateway",
    description=(
        "Provider-agnostic LLM gateway with intelligent model selection, "
        "transparent fallback, and full audit trail."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def get_providers() -> Dict[ProviderType, Any]:
    if not _providers:
        raise HTTPException(503, "Model Gateway not yet initialised.")
    return _providers

def get_selector() -> ModelSelector:
    return _selector or get_model_selector()

def get_fm() -> FallbackManager:
    return _fallback_manager or get_fallback_manager()

def get_audit() -> GatewayAuditLogger:
    return _audit or get_gateway_audit_logger()

def get_registry_dep() -> ModelRegistry:
    return _registry or get_model_registry()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class MessageSchema(BaseModel):
    role: str = Field(..., description="'system' | 'user' | 'assistant'")
    content: Any = Field(..., description="String or list of content parts")


class CompletionRequestSchema(BaseModel):
    messages: List[MessageSchema]
    system_prompt: Optional[str] = None
    max_tokens: int = Field(4096, ge=1, le=200000)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    top_p: float = Field(1.0, ge=0.0, le=1.0)
    stream: bool = False
    # Model / provider hints (optional — gateway selects automatically if omitted)
    preferred_model: Optional[str] = None
    preferred_provider: Optional[str] = None
    # Capability requirements
    require_vision: bool = False
    require_tools: bool = False
    require_json_mode: bool = False
    require_long_context: bool = False
    # Cost control
    cost_tier: Optional[str] = Field(
        None,
        description="Force tier: 'economy' | 'balanced' | 'premium' | 'reasoning'",
    )
    # Tools / function calling
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[str] = None
    # Traceability
    workflow_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    # Approximate context size for long-context routing
    context_tokens_hint: Optional[int] = None


class UsageSchema(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float


class CompletionResponseSchema(BaseModel):
    request_id: str
    content: str
    model_id: str
    provider: str
    finish_reason: str
    usage: UsageSchema
    tool_calls: Optional[List[Dict[str, Any]]] = None
    latency_ms: float
    fallback_used: bool = False
    original_model_id: Optional[str] = None
    fallback_reason: Optional[str] = None
    detected_task: Optional[str] = None
    selection_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _build_internal_request(
    schema: CompletionRequestSchema,
    request_id: str,
    provider_type: ProviderType,
    model_id: str,
) -> CompletionRequest:
    messages = [
        Message(role=m.role, content=m.content) for m in schema.messages
    ]
    return CompletionRequest(
        messages=messages,
        model_id=model_id,
        provider=provider_type,
        max_tokens=schema.max_tokens,
        temperature=schema.temperature,
        top_p=schema.top_p,
        stream=schema.stream,
        system_prompt=schema.system_prompt,
        tools=schema.tools,
        tool_choice=schema.tool_choice,
        json_mode=schema.require_json_mode,
        request_id=request_id,
        workflow_id=schema.workflow_id,
        session_id=schema.session_id,
        user_id=schema.user_id,
    )


def _capability_list(schema: CompletionRequestSchema) -> List[ModelCapability]:
    caps: List[ModelCapability] = []
    if schema.require_vision:
        caps.append(ModelCapability.VISION)
    if schema.require_tools:
        caps.append(ModelCapability.TOOLS)
    if schema.require_json_mode:
        caps.append(ModelCapability.JSON_MODE)
    if schema.require_long_context:
        caps.append(ModelCapability.LONG_CONTEXT)
    return caps


def _messages_text(schema: CompletionRequestSchema) -> str:
    parts = []
    for m in schema.messages:
        if isinstance(m.content, str):
            parts.append(m.content)
        elif isinstance(m.content, list):
            for part in m.content:
                if isinstance(part, dict) and "text" in part:
                    parts.append(part["text"])
    return " ".join(parts)


def _parse_tier(raw: Optional[str]) -> Optional[ModelTier]:
    if not raw:
        return None
    try:
        return ModelTier(raw.lower())
    except ValueError:
        return None


def _parse_provider(raw: Optional[str]) -> Optional[ProviderType]:
    if not raw:
        return None
    try:
        return ProviderType(raw.lower())
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", tags=["ops"])
async def health():
    """Liveness + provider health summary."""
    monitor = get_health_monitor()
    provider_health = monitor.get_all_health() if monitor else {}
    any_healthy = any(v.get("is_healthy") for v in provider_health.values())
    return {
        "status": "healthy" if any_healthy else "degraded",
        "service": "model_gateway",
        "version": "1.0.0",
        "providers": provider_health,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@app.get("/v1/models", tags=["models"])
async def list_models(
    registry: ModelRegistry = Depends(get_registry_dep),
):
    """List all registered models grouped by provider."""
    return registry.summary()


@app.get("/v1/models/{model_id}", tags=["models"])
async def get_model(
    model_id: str,
    registry: ModelRegistry = Depends(get_registry_dep),
):
    """Get metadata for a specific model."""
    model = registry.get_model(model_id)
    if not model:
        raise HTTPException(404, f"Model '{model_id}' not found in registry.")
    return {
        "id": model.model_id,
        "provider": model.provider.value,
        "display_name": model.display_name,
        "tier": model.tier.value,
        "context_window": model.context_window,
        "max_output_tokens": model.max_output_tokens,
        "capabilities": [c.value for c in model.capabilities],
        "task_suitability": {k.value: v for k, v in model.task_suitability.items()},
        "cost": {
            "input_per_million_usd": model.cost.input_per_million,
            "output_per_million_usd": model.cost.output_per_million,
        },
        "is_deprecated": model.is_deprecated,
    }


@app.post("/v1/complete", response_model=CompletionResponseSchema, tags=["inference"])
async def complete(
    body: CompletionRequestSchema,
    providers: Dict = Depends(get_providers),
    selector: ModelSelector = Depends(get_selector),
    fm: FallbackManager = Depends(get_fm),
    audit: GatewayAuditLogger = Depends(get_audit),
):
    """
    Main inference endpoint.

    The gateway automatically selects the best model based on the request
    content and constraints, then executes with transparent fallback.
    """
    request_id = str(uuid.uuid4())
    t_start = time.monotonic()

    # ── 1. Model selection ─────────────────────────────────────────────
    open_providers = fm.get_open_providers()
    caps = _capability_list(body)
    messages_text = _messages_text(body)

    try:
        selection = selector.select(
            messages_text=messages_text,
            preferred_model=body.preferred_model,
            preferred_provider=_parse_provider(body.preferred_provider),
            required_capabilities=caps if caps else None,
            context_tokens_needed=body.context_tokens_hint,
            cost_tier=_parse_tier(body.cost_tier),
            unhealthy_providers=open_providers,
            stream=False,
        )
    except RuntimeError as exc:
        raise HTTPException(503, f"Model selection failed: {exc}")

    # Audit selection
    audit.log_model_selection(
        request_id=request_id,
        selected_model=selection.primary.model_id,
        selected_provider=selection.primary.provider.value,
        detected_task=selection.detected_task.value,
        reason=selection.selection_reason,
        fallbacks=[m.model_id for m in selection.fallbacks],
        estimated_cost_per_1k=selection.estimated_cost_usd_per_1k,
        workflow_id=body.workflow_id,
        user_id=body.user_id,
    )

    # ── 2. Build internal request ──────────────────────────────────────
    internal_req = _build_internal_request(
        body, request_id,
        selection.primary.provider,
        selection.primary.model_id,
    )

    # Audit request
    audit.log_completion_request(
        request_id=request_id,
        model_id=selection.primary.model_id,
        provider=selection.primary.provider.value,
        message_count=len(body.messages),
        max_tokens=body.max_tokens,
        stream=False,
        workflow_id=body.workflow_id,
        session_id=body.session_id,
        user_id=body.user_id,
        content_preview=messages_text[:200],
    )

    # ── 3. Execute with fallback ───────────────────────────────────────
    try:
        response = await fm.execute(
            selection=selection,
            provider_map=providers,
            request=internal_req,
        )
    except RuntimeError as exc:
        audit.log_error(
            request_id=request_id,
            error=str(exc),
            model_id=selection.primary.model_id,
            provider=selection.primary.provider.value,
            workflow_id=body.workflow_id,
        )
        raise HTTPException(503, f"All providers failed: {exc}")

    total_ms = (time.monotonic() - t_start) * 1000

    # ── 4. Audit response ──────────────────────────────────────────────
    audit.log_completion_response(
        request_id=request_id,
        model_id=response.model_id,
        provider=response.provider.value,
        finish_reason=response.finish_reason,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        estimated_cost_usd=response.usage.estimated_cost_usd,
        latency_ms=total_ms,
        fallback_used=response.original_model_id is not None,
        original_model=response.original_model_id,
        fallback_reason=response.fallback_reason,
        workflow_id=body.workflow_id,
        user_id=body.user_id,
    )

    if response.fallback_reason:
        audit.log_fallback_event(
            request_id=request_id,
            original_model=response.original_model_id or selection.primary.model_id,
            original_provider=selection.primary.provider.value,
            fallback_model=response.model_id,
            fallback_provider=response.provider.value,
            reason=response.fallback_reason,
            attempt=1,
            workflow_id=body.workflow_id,
        )

    return CompletionResponseSchema(
        request_id=request_id,
        content=response.content,
        model_id=response.model_id,
        provider=response.provider.value,
        finish_reason=response.finish_reason,
        usage=UsageSchema(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=response.usage.total_tokens,
            estimated_cost_usd=response.usage.estimated_cost_usd,
        ),
        tool_calls=response.tool_calls,
        latency_ms=round(total_ms, 2),
        fallback_used=response.original_model_id is not None,
        original_model_id=response.original_model_id,
        fallback_reason=response.fallback_reason,
        detected_task=selection.detected_task.value,
        selection_reason=selection.selection_reason,
    )


@app.post("/v1/complete/stream", tags=["inference"])
async def complete_stream(
    body: CompletionRequestSchema,
    providers: Dict = Depends(get_providers),
    selector: ModelSelector = Depends(get_selector),
    fm: FallbackManager = Depends(get_fm),
    audit: GatewayAuditLogger = Depends(get_audit),
):
    """
    Streaming inference endpoint — returns server-sent events (SSE).
    """
    request_id = str(uuid.uuid4())
    open_providers = fm.get_open_providers()
    caps = _capability_list(body)
    messages_text = _messages_text(body)

    try:
        selection = selector.select(
            messages_text=messages_text,
            preferred_model=body.preferred_model,
            preferred_provider=_parse_provider(body.preferred_provider),
            required_capabilities=caps if caps else None,
            context_tokens_needed=body.context_tokens_hint,
            cost_tier=_parse_tier(body.cost_tier),
            unhealthy_providers=open_providers,
            stream=True,
        )
    except RuntimeError as exc:
        raise HTTPException(503, f"Model selection failed: {exc}")

    audit.log_model_selection(
        request_id=request_id,
        selected_model=selection.primary.model_id,
        selected_provider=selection.primary.provider.value,
        detected_task=selection.detected_task.value,
        reason=selection.selection_reason,
        fallbacks=[m.model_id for m in selection.fallbacks],
        workflow_id=body.workflow_id,
        user_id=body.user_id,
    )

    internal_req = _build_internal_request(
        body, request_id,
        selection.primary.provider,
        selection.primary.model_id,
    )
    internal_req.stream = True

    import json as _json

    async def event_generator():
        try:
            async for chunk in fm.execute_stream(
                selection=selection,
                provider_map=providers,
                request=internal_req,
            ):
                data = _json.dumps({
                    "request_id": request_id,
                    "content": chunk.content,
                    "model_id": chunk.model_id,
                    "provider": chunk.provider.value,
                    "finish_reason": chunk.finish_reason,
                    "is_final": chunk.is_final,
                    "usage": (
                        {
                            "input_tokens": chunk.usage.input_tokens,
                            "output_tokens": chunk.usage.output_tokens,
                            "total_tokens": chunk.usage.total_tokens,
                        }
                        if chunk.usage
                        else None
                    ),
                })
                yield f"data: {data}\n\n"
        except RuntimeError as exc:
            audit.log_error(
                request_id=request_id,
                error=str(exc),
                workflow_id=body.workflow_id,
            )
            err = _json.dumps({"error": str(exc), "request_id": request_id})
            yield f"data: {err}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"X-Request-Id": request_id},
    )


@app.get("/v1/admin/circuit-breakers", tags=["admin"])
async def circuit_breakers(fm: FallbackManager = Depends(get_fm)):
    """Current circuit-breaker state for every provider."""
    return fm.get_breaker_health()


@app.post("/v1/admin/circuit-breakers/{provider}/reset", tags=["admin"])
async def reset_circuit_breaker(
    provider: str,
    fm: FallbackManager = Depends(get_fm),
):
    """Manually reset (close) a provider's circuit breaker."""
    try:
        ptype = ProviderType(provider.lower())
    except ValueError:
        raise HTTPException(404, f"Unknown provider '{provider}'.")
    breaker = fm._breakers.get(ptype)
    if not breaker:
        raise HTTPException(404, f"No circuit breaker for '{provider}'.")
    from providers.base import CircuitState
    old_state = breaker.state.value
    breaker.state = CircuitState.CLOSED
    breaker.consecutive_failures = 0
    breaker.consecutive_successes = 0
    breaker.opened_at = None
    logger.info("Circuit breaker for %s manually reset from %s to CLOSED.", provider, old_state)
    return {"provider": provider, "old_state": old_state, "new_state": "closed"}


@app.get("/v1/admin/fallback-events", tags=["admin"])
async def fallback_events(
    limit: int = 50,
    fm: FallbackManager = Depends(get_fm),
):
    """Recent fallback events (most recent first)."""
    return {"events": fm.recent_fallback_events(limit=limit)}


@app.get("/v1/admin/audit-log", tags=["admin"])
async def audit_log(
    limit: int = 100,
    event_type: Optional[str] = None,
    audit: GatewayAuditLogger = Depends(get_audit),
):
    """Recent audit log entries from the current log file."""
    from audit.gateway_audit import GatewayAuditEventType
    etype = None
    if event_type:
        try:
            etype = GatewayAuditEventType(event_type)
        except ValueError:
            raise HTTPException(400, f"Unknown event_type '{event_type}'.")
    events = audit.recent_events(limit=limit, event_type=etype)
    return {"count": len(events), "events": events}


@app.get("/v1/select", tags=["models"])
async def preview_selection(
    query: str,
    preferred_provider: Optional[str] = None,
    cost_tier: Optional[str] = None,
    require_vision: bool = False,
    require_tools: bool = False,
    stream: bool = False,
    selector: ModelSelector = Depends(get_selector),
    fm: FallbackManager = Depends(get_fm),
):
    """
    Preview which model would be selected for a given query — without
    actually calling any provider. Useful for debugging and cost estimation.
    """
    open_providers = fm.get_open_providers()
    caps: List[ModelCapability] = []
    if require_vision:
        caps.append(ModelCapability.VISION)
    if require_tools:
        caps.append(ModelCapability.TOOLS)

    try:
        selection = selector.select(
            messages_text=query,
            preferred_provider=_parse_provider(preferred_provider),
            required_capabilities=caps if caps else None,
            cost_tier=_parse_tier(cost_tier),
            unhealthy_providers=open_providers,
            stream=stream,
        )
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))

    return {
        "primary": {
            "model_id": selection.primary.model_id,
            "provider": selection.primary.provider.value,
            "tier": selection.primary.tier.value,
            "display_name": selection.primary.display_name,
        },
        "fallbacks": [
            {
                "model_id": m.model_id,
                "provider": m.provider.value,
                "tier": m.tier.value,
                "display_name": m.display_name,
            }
            for m in selection.fallbacks
        ],
        "detected_task": selection.detected_task.value,
        "selection_reason": selection.selection_reason,
        "estimated_cost_usd_per_1k_tokens": selection.estimated_cost_usd_per_1k,
        "required_capabilities": [c.value for c in selection.required_capabilities],
        "preferred_by_caller": selection.preferred_by_caller,
    }


# ---------------------------------------------------------------------------
# Provider config admin endpoints
# ---------------------------------------------------------------------------

class ProviderPreferenceSchema(BaseModel):
    """Pydantic schema mirroring ProviderPreference (all fields optional for PATCH)."""
    enabled: Optional[bool] = None
    priority: Optional[int] = Field(None, ge=1, le=100)
    max_cost_tier: Optional[str] = Field(
        None,
        description="economy | balanced | premium | reasoning  (null = no cap)",
    )
    preferred_model: Optional[str] = Field(
        None, description="Pin a specific model_id for this provider (null = auto)"
    )
    notes: Optional[str] = None


class ProviderConfigUpdateSchema(BaseModel):
    """Full provider-config replacement payload."""
    providers: Dict[str, ProviderPreferenceSchema] = Field(
        default_factory=dict,
        description="Keyed by provider name: anthropic | bedrock | gemini | openai",
    )
    global_default_tier: Optional[str] = Field(
        None, description="economy | balanced | premium | reasoning"
    )
    cost_optimize: Optional[bool] = None
    updated_by: Optional[str] = Field(None, description="Operator identifier")


def _config_to_response(cfg: GatewayProviderConfig) -> dict:
    """Serialize config + add convenient derived views."""
    import datetime
    return {
        "providers": {k: v.to_dict() for k, v in cfg.providers.items()},
        "global_default_tier": cfg.global_default_tier,
        "cost_optimize": cfg.cost_optimize,
        "updated_at": datetime.datetime.utcfromtimestamp(cfg.updated_at).isoformat() + "Z",
        "updated_by": cfg.updated_by,
        # Derived views for quick inspection
        "_derived": {
            "primary_provider": cfg.primary_provider.value if cfg.primary_provider else None,
            "fallback_order": [p.value for p in cfg.fallback_order],
            "enabled_providers": [p.value for p in cfg.enabled_providers],
        },
    }


@app.get("/v1/admin/provider-config", tags=["admin"])
async def get_provider_config():
    """
    Return the current runtime provider configuration.

    The ``_derived`` block shows the live routing order without needing to
    read the ``providers`` dict manually.
    """
    cfg = get_live_config()
    return _config_to_response(cfg)


@app.put("/v1/admin/provider-config", tags=["admin"])
async def replace_provider_config(body: ProviderConfigUpdateSchema):
    """
    Atomically replace the entire provider configuration.

    All subsequent requests use the new config immediately — no restart needed.
    The new config is also persisted to disk so it survives a restart.

    To set priority order send providers with ``priority`` 1 (primary),
    2 (first fallback), 3 (second fallback), etc.
    """
    store = get_provider_config_store()
    current = store.get()

    # Build a new GatewayProviderConfig from the body, falling back to
    # current values for any omitted fields.
    from copy import deepcopy
    new_cfg = deepcopy(current)

    if body.global_default_tier is not None:
        valid_tiers = {t.value for t in ModelTier}
        if body.global_default_tier not in valid_tiers:
            raise HTTPException(400, f"Unknown tier '{body.global_default_tier}'. Valid: {sorted(valid_tiers)}")
        new_cfg.global_default_tier = body.global_default_tier

    if body.cost_optimize is not None:
        new_cfg.cost_optimize = body.cost_optimize

    for pname, pschema in body.providers.items():
        try:
            pt = ProviderType(pname)
        except ValueError:
            raise HTTPException(400, f"Unknown provider '{pname}'.")
        existing = new_cfg.providers.get(pt.value) or ProviderPreference(provider=pt.value)
        if pschema.enabled is not None:
            existing.enabled = pschema.enabled
        if pschema.priority is not None:
            existing.priority = pschema.priority
        if pschema.max_cost_tier is not None:
            valid = {t.value for t in ModelTier}
            if pschema.max_cost_tier not in valid:
                raise HTTPException(400, f"Unknown max_cost_tier '{pschema.max_cost_tier}'.")
            existing.max_cost_tier = pschema.max_cost_tier
        if pschema.preferred_model is not None:
            existing.preferred_model = pschema.preferred_model
        if pschema.notes is not None:
            existing.notes = pschema.notes
        new_cfg.providers[pt.value] = existing

    new_cfg.updated_by = body.updated_by or "api"
    await store.update(new_cfg, persist=True)
    return _config_to_response(store.get())


@app.patch("/v1/admin/provider-config/{provider_name}", tags=["admin"])
async def patch_single_provider(
    provider_name: str,
    body: ProviderPreferenceSchema,
):
    """
    Patch a single provider's preferences (e.g. enable/disable, change priority).

    This is the quickest way to toggle a provider or adjust its rank without
    sending the entire config.  Changes are live immediately and persisted.

    Example — disable Bedrock:
    ```json
    {"enabled": false}
    ```

    Example — make OpenAI primary (priority=1) and Anthropic first fallback (priority=2):
    ```
    PATCH /v1/admin/provider-config/openai   {"priority": 1}
    PATCH /v1/admin/provider-config/anthropic {"priority": 2}
    ```
    """
    try:
        pt = ProviderType(provider_name)
    except ValueError:
        raise HTTPException(400, f"Unknown provider '{provider_name}'. Valid: {[p.value for p in ProviderType]}")

    patch_dict = {k: v for k, v in body.model_dump().items() if v is not None}
    if not patch_dict:
        raise HTTPException(400, "No fields to update — body was empty.")

    store = get_provider_config_store()
    new_cfg = await store.update_provider(pt, patch_dict, updated_by="api")
    return _config_to_response(new_cfg)


@app.post("/v1/admin/provider-config/reset", tags=["admin"])
async def reset_provider_config():
    """
    Reset the provider configuration back to the values derived from
    environment variables (GATEWAY_ENABLED_PROVIDERS, GATEWAY_PRIMARY_PROVIDER,
    GATEWAY_FALLBACK_ORDER, etc.).

    The reset config is persisted to disk, overwriting the previous file.
    """
    from routing.provider_config import _build_default_config
    default_cfg = _build_default_config()
    default_cfg.updated_by = "api_reset"
    store = get_provider_config_store()
    await store.update(default_cfg, persist=True)
    return _config_to_response(store.get())


@app.post("/v1/admin/provider-config/reload", tags=["admin"])
async def reload_provider_config_from_disk():
    """
    Hot-reload the provider configuration from the on-disk JSON file without
    restarting the service.

    Useful if you've edited the file directly or deployed a new config file.
    Returns the reloaded configuration.
    """
    store = get_provider_config_store()
    try:
        new_cfg = await store.reload_from_disk()
    except Exception as exc:
        raise HTTPException(500, f"Reload failed: {exc}")
    return _config_to_response(new_cfg)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=GATEWAY_HOST,
        port=GATEWAY_PORT,
        log_level=LOG_LEVEL.lower(),
        reload=False,
    )
