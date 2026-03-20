"""
Provider Health Monitor

Runs a background asyncio task that periodically calls each provider's
health_check() method and updates their circuit-breaker state.

Health check interval is controlled by:
    GATEWAY_HEALTH_CHECK_INTERVAL_SEC  default 30
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Dict, List, Optional

from providers.base import BaseProvider, ProviderHealth, ProviderType
from routing.fallback_manager import FallbackManager

logger = logging.getLogger(__name__)

_HEALTH_CHECK_INTERVAL = int(os.getenv("GATEWAY_HEALTH_CHECK_INTERVAL_SEC", "30"))
_MONITOR_INSTANCE: Optional[ProviderHealthMonitor] = None


class ProviderHealthMonitor:
    """
    Background task that polls each provider for liveness and records
    the results so the FallbackManager and API can surface health state.
    """

    def __init__(
        self,
        providers: Dict[ProviderType, BaseProvider],
        fallback_manager: FallbackManager,
    ) -> None:
        self._providers = providers
        self._fm = fallback_manager
        self._latest: Dict[ProviderType, ProviderHealth] = {}
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Kick off the background polling loop."""
        # Run an immediate check before accepting traffic
        await self._run_checks()
        self._task = asyncio.create_task(self._loop(), name="provider_health_monitor")
        logger.info(
            "ProviderHealthMonitor started (interval=%ds).", _HEALTH_CHECK_INTERVAL
        )

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("ProviderHealthMonitor stopped.")

    def get_all_health(self) -> Dict[str, dict]:
        result = {}
        for ptype, health in self._latest.items():
            cb_info = self._fm.get_breaker_health().get(ptype.value, {})
            result[ptype.value] = {
                "is_healthy": health.is_healthy,
                "circuit_state": health.circuit_state.value,
                "avg_latency_ms": round(health.avg_latency_ms, 1),
                "error_rate": round(health.error_rate, 4),
                "success_count": health.success_count,
                "failure_count": health.failure_count,
                "last_checked": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(health.checked_at)
                ),
                "circuit_breaker": cb_info,
            }
        # Fill in any provider not yet checked
        for ptype in ProviderType:
            if ptype.value not in result:
                result[ptype.value] = {
                    "is_healthy": False,
                    "circuit_state": "unknown",
                    "avg_latency_ms": 0,
                    "error_rate": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "last_checked": None,
                    "circuit_breaker": {},
                }
        return result

    def is_any_healthy(self) -> bool:
        return any(h.is_healthy for h in self._latest.values())

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(_HEALTH_CHECK_INTERVAL)
            await self._run_checks()

    async def _run_checks(self) -> None:
        tasks = {
            ptype: provider.health_check()
            for ptype, provider in self._providers.items()
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for ptype, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.warning(
                    "Health check for %s raised exception: %s", ptype.value, result
                )
            elif isinstance(result, ProviderHealth):
                old_health = self._latest.get(ptype)
                self._latest[ptype] = result
                # Log circuit state transitions
                if old_health and old_health.circuit_state != result.circuit_state:
                    logger.info(
                        "Provider %s circuit state: %s → %s",
                        ptype.value,
                        old_health.circuit_state.value,
                        result.circuit_state.value,
                    )


def get_health_monitor() -> Optional[ProviderHealthMonitor]:
    """Return the singleton monitor (set by app.py at startup)."""
    return _MONITOR_INSTANCE


def set_health_monitor(monitor: ProviderHealthMonitor) -> None:
    global _MONITOR_INSTANCE
    _MONITOR_INSTANCE = monitor
