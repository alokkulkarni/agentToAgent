"""
Provider Configuration Store
==============================
Runtime-mutable configuration for which providers are enabled, which is
primary, and what the fallback order is.

Design goals:
  - Zero-restart updates: configs are held in an asyncio-safe in-memory store
    and optionally persisted to a JSON file so they survive a restart.
  - Per-provider granularity: each provider has its own enabled flag,
    priority rank, allowed cost tiers, and optional model overrides.
  - Atomic SwapCopy semantics: a full new config object replaces the old one
    under an asyncio.Lock so no read sees a half-written state.

Environment bootstrap (read once on startup, overridable at runtime):
    GATEWAY_ENABLED_PROVIDERS   comma-separated list, default: all four
    GATEWAY_PRIMARY_PROVIDER    default: first in GATEWAY_ENABLED_PROVIDERS
    GATEWAY_FALLBACK_ORDER      comma-separated, default: rest in order
    GATEWAY_CONFIG_PATH         path to JSON persistence file
                                default: <service_dir>/gateway_provider_config.json
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from providers.base import ModelTier, ProviderType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path for persistence
# ---------------------------------------------------------------------------
_SERVICE_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parent
_DEFAULT_CONFIG_PATH = _SERVICE_DIR / "gateway_provider_config.json"
CONFIG_PATH = Path(os.getenv("GATEWAY_CONFIG_PATH", str(_DEFAULT_CONFIG_PATH)))

_ALL_PROVIDERS = [p.value for p in ProviderType]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ProviderPreference:
    """Per-provider runtime configuration."""
    provider: str                           # ProviderType.value (string)
    enabled: bool = True
    priority: int = 99                      # lower number = higher priority (1 = primary)
    max_cost_tier: Optional[str] = None     # cap at 'economy'/'balanced'/'premium'/'reasoning'
    preferred_model: Optional[str] = None  # force a specific model for this provider
    notes: str = ""                         # free-form operator comment

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "ProviderPreference":
        return ProviderPreference(
            provider=d["provider"],
            enabled=d.get("enabled", True),
            priority=d.get("priority", 99),
            max_cost_tier=d.get("max_cost_tier"),
            preferred_model=d.get("preferred_model"),
            notes=d.get("notes", ""),
        )


@dataclass
class GatewayProviderConfig:
    """
    Top-level config object.

    ``providers`` is an ordered dict keyed by provider value string.
    The ``enabled_ordered`` and ``fallback_order`` properties derive
    the live routing lists from the priority ranks.
    """
    providers: Dict[str, ProviderPreference] = field(default_factory=dict)
    global_default_tier: str = "balanced"
    cost_optimize: bool = True
    updated_at: float = field(default_factory=time.time)
    updated_by: str = "system"

    # ------------------------------------------------------------------
    # Derived views used by ModelSelector
    # ------------------------------------------------------------------

    @property
    def enabled_providers(self) -> List[ProviderType]:
        """All enabled providers, sorted by priority ascending."""
        prefs = [
            p for p in self.providers.values()
            if p.enabled
        ]
        prefs.sort(key=lambda p: p.priority)
        result = []
        for p in prefs:
            try:
                result.append(ProviderType(p.provider))
            except ValueError:
                pass
        return result

    @property
    def primary_provider(self) -> Optional[ProviderType]:
        """Provider with the lowest priority number among enabled ones."""
        enabled = self.enabled_providers
        return enabled[0] if enabled else None

    @property
    def fallback_order(self) -> List[ProviderType]:
        """Enabled providers after the primary, in priority order."""
        return self.enabled_providers[1:]

    def preference_for(self, provider: ProviderType) -> Optional[ProviderPreference]:
        return self.providers.get(provider.value)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "providers": {k: v.to_dict() for k, v in self.providers.items()},
            "global_default_tier": self.global_default_tier,
            "cost_optimize": self.cost_optimize,
            "updated_at": self.updated_at,
            "updated_by": self.updated_by,
        }

    @staticmethod
    def from_dict(d: dict) -> "GatewayProviderConfig":
        cfg = GatewayProviderConfig(
            global_default_tier=d.get("global_default_tier", "balanced"),
            cost_optimize=d.get("cost_optimize", True),
            updated_at=d.get("updated_at", time.time()),
            updated_by=d.get("updated_by", "system"),
        )
        raw_providers = d.get("providers", {})
        for k, v in raw_providers.items():
            cfg.providers[k] = ProviderPreference.from_dict(v)
        return cfg


# ---------------------------------------------------------------------------
# Default bootstrap from environment
# ---------------------------------------------------------------------------

def _build_default_config() -> GatewayProviderConfig:
    """
    Construct the default config from environment variables.
    Called once at module import; can be overridden at runtime.
    """
    raw_enabled = os.getenv("GATEWAY_ENABLED_PROVIDERS", ",".join(_ALL_PROVIDERS))
    enabled_list = [p.strip() for p in raw_enabled.split(",") if p.strip()]
    # Validate and de-duplicate
    validated: List[str] = []
    for p in enabled_list:
        if p in _ALL_PROVIDERS and p not in validated:
            validated.append(p)
    if not validated:
        validated = list(_ALL_PROVIDERS)

    # Primary / fallback order from env
    raw_primary = os.getenv("GATEWAY_PRIMARY_PROVIDER", "").strip()
    raw_fallback = os.getenv("GATEWAY_FALLBACK_ORDER", "").strip()

    if raw_primary and raw_primary in validated:
        order = [raw_primary]
    else:
        order = [validated[0]]

    if raw_fallback:
        for p in raw_fallback.split(","):
            p = p.strip()
            if p in validated and p not in order:
                order.append(p)
    # fill any remaining enabled providers not yet in order
    for p in validated:
        if p not in order:
            order.append(p)

    cfg = GatewayProviderConfig(
        global_default_tier=os.getenv("GATEWAY_DEFAULT_TIER", "balanced"),
        cost_optimize=os.getenv("GATEWAY_COST_OPTIMIZE", "true").lower() == "true",
    )
    for rank, pname in enumerate(order, start=1):
        cfg.providers[pname] = ProviderPreference(
            provider=pname,
            enabled=(pname in validated),
            priority=rank,
        )
    # disabled providers go in the map too (so they show up in GET responses)
    for pname in _ALL_PROVIDERS:
        if pname not in cfg.providers:
            cfg.providers[pname] = ProviderPreference(
                provider=pname,
                enabled=False,
                priority=len(order) + 1,
            )

    return cfg


# ---------------------------------------------------------------------------
# Live config store (singleton)
# ---------------------------------------------------------------------------

class ProviderConfigStore:
    """
    Thread/async-safe holder for the live GatewayProviderConfig.

    Supports:
      - get()   — zero-copy read of the current config
      - update()  — atomic swap with optional persistence
      - reload_from_disk() — hot-reload the JSON file
    """

    def __init__(self) -> None:
        self._config: GatewayProviderConfig = _build_default_config()
        self._lock = asyncio.Lock()
        self._load_from_disk_sync()   # overlay with persisted config if present

    # ------------------------------------------------------------------
    # Reads (synchronous — safe because reads are single-assignment)
    # ------------------------------------------------------------------

    def get(self) -> GatewayProviderConfig:
        """Return a snapshot of the current config. Immutable outside the store."""
        return self._config

    # ------------------------------------------------------------------
    # Writes (async — uses lock to prevent concurrent mutations)
    # ------------------------------------------------------------------

    async def update(
        self,
        new_config: GatewayProviderConfig,
        persist: bool = True,
    ) -> None:
        """
        Atomically replace the running config and optionally persist to disk.
        The lock ensures no partial reads during the swap.
        """
        async with self._lock:
            new_config.updated_at = time.time()
            self._config = new_config
            logger.info(
                "Provider config updated by '%s'. Enabled: %s",
                new_config.updated_by,
                [p.value for p in new_config.enabled_providers],
            )
        if persist:
            await self._persist(new_config)

    async def update_provider(
        self,
        provider: ProviderType,
        patch: dict,
        updated_by: str = "api",
    ) -> GatewayProviderConfig:
        """
        Patch a single provider's preference and return the new full config.
        ``patch`` is a dict of ProviderPreference fields to change.
        """
        async with self._lock:
            # Deep-copy so we never mutate the live object mid-read
            new_cfg = deepcopy(self._config)
            pref = new_cfg.providers.get(provider.value)
            if not pref:
                pref = ProviderPreference(provider=provider.value)
                new_cfg.providers[provider.value] = pref

            for key, value in patch.items():
                if hasattr(pref, key):
                    setattr(pref, key, value)

            new_cfg.updated_at = time.time()
            new_cfg.updated_by = updated_by
            self._config = new_cfg

        await self._persist(new_cfg)
        logger.info(
            "Provider '%s' config patched by '%s': %s",
            provider.value, updated_by, patch,
        )
        return new_cfg

    async def reload_from_disk(self) -> GatewayProviderConfig:
        """Hot-reload the JSON file into the running config."""
        if not CONFIG_PATH.exists():
            logger.warning("Config file %s not found; nothing to reload.", CONFIG_PATH)
            return self._config
        try:
            text = CONFIG_PATH.read_text(encoding="utf-8")
            raw = json.loads(text)
            new_cfg = GatewayProviderConfig.from_dict(raw)
            new_cfg.updated_by = "disk_reload"
            await self.update(new_cfg, persist=False)
            logger.info("Config hot-reloaded from %s", CONFIG_PATH)
            return new_cfg
        except Exception as exc:
            logger.error("Failed to reload config from disk: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load_from_disk_sync(self) -> None:
        """Synchronous load at startup (before the event loop is running)."""
        if not CONFIG_PATH.exists():
            return
        try:
            text = CONFIG_PATH.read_text(encoding="utf-8")
            raw = json.loads(text)
            loaded = GatewayProviderConfig.from_dict(raw)
            # Env vars may have changed; only overlay if the file has
            # explicit provider entries defined
            if loaded.providers:
                self._config = loaded
                logger.info("Provider config loaded from %s.", CONFIG_PATH)
        except Exception as exc:
            logger.warning(
                "Could not load provider config from %s: %s — using defaults.",
                CONFIG_PATH, exc,
            )

    async def _persist(self, cfg: GatewayProviderConfig) -> None:
        """Write config to disk asynchronously (best-effort)."""
        try:
            text = json.dumps(cfg.to_dict(), indent=2)
            CONFIG_PATH.write_text(text, encoding="utf-8")
            logger.debug("Provider config persisted to %s.", CONFIG_PATH)
        except Exception as exc:
            logger.warning("Could not persist provider config: %s", exc)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_STORE_INSTANCE: Optional[ProviderConfigStore] = None


def get_provider_config_store() -> ProviderConfigStore:
    global _STORE_INSTANCE
    if _STORE_INSTANCE is None:
        _STORE_INSTANCE = ProviderConfigStore()
    return _STORE_INSTANCE


def get_live_config() -> GatewayProviderConfig:
    """Convenience shortcut used throughout the gateway."""
    return get_provider_config_store().get()
