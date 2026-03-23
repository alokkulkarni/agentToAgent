"""
distributed_state.py — Shared distributed state layer for HA multi-instance orchestrator.

This module replaces per-process Python dicts with backend-agnostic stores so that
multiple orchestrator replicas can share workflow state, session history, and
WebSocket events without sticky sessions.

Backends:
  - InMemory (default for single-node dev/testing)
  - Redis  (recommended for production HA)

Environment variables:
  HA_BACKEND                  redis | in_memory  (default: in_memory)
  REDIS_URL                   redis://localhost:6379  (default)
  ORCHESTRATOR_INSTANCE_ID    unique ID for this replica (default: hostname-pid)
  ORCHESTRATOR_PUBLIC_ENDPOINT http://host:port   (optional, for cross-instance proxy)
  WORKFLOW_STATE_TTL          seconds to keep workflow state after completion (default: 86400)

Usage:
    from shared.distributed_state import get_distributed_state

    dist = get_distributed_state()

    # Workflow state (replaces active_workflows dict)
    await dist.workflows.set(workflow_id, state_dict)
    state = await dist.workflows.get(workflow_id)        # None if not found
    await dist.workflows.delete(workflow_id)
    ids = await dist.workflows.list_ids()

    # Session history (replaces session_store defaultdict)
    await dist.sessions.append(session_id, item)
    hist = await dist.sessions.get(session_id)

    # Ownership (claim/heartbeat/release per workflow)
    claimed = await dist.ownership.claim(workflow_id, instance_id)
    await dist.ownership.refresh(workflow_id, instance_id)
    owner = await dist.ownership.get_owner(workflow_id)
    await dist.ownership.release(workflow_id, instance_id)

    # Pub/Sub (cross-instance WebSocket fan-out)
    await dist.pubsub.publish(workflow_id, event_dict)
    await dist.pubsub.subscribe(workflow_id, async_callback)
    await dist.pubsub.unsubscribe(workflow_id)

    # Instance registry
    await dist.instances.register(instance_id, endpoint_url)
    await dist.instances.heartbeat(instance_id)
    endpoint = await dist.instances.get_endpoint(instance_id)
    all_instances = await dist.instances.list_all()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

class HABackend(str, Enum):
    in_memory = "in_memory"
    redis = "redis"


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _default_instance_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


WORKFLOW_STATE_TTL = int(_env("WORKFLOW_STATE_TTL", "86400"))  # 1 day
OWNERSHIP_TTL = int(_env("OWNERSHIP_TTL", "30"))               # 30 s heartbeat window
INSTANCE_TTL = int(_env("INSTANCE_TTL", "60"))                 # 60 s instance heartbeat


# ---------------------------------------------------------------------------
# Abstract interfaces
# ---------------------------------------------------------------------------

class AbstractWorkflowStore(ABC):
    """Key-value store for live `active_workflows` state."""

    @abstractmethod
    async def set(self, workflow_id: str, state: Dict[str, Any]) -> None: ...

    @abstractmethod
    async def get(self, workflow_id: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    async def delete(self, workflow_id: str) -> None: ...

    @abstractmethod
    async def list_ids(self) -> List[str]: ...

    async def update(self, workflow_id: str, updates: Dict[str, Any]) -> None:
        """Atomic read-modify-write (non-atomic on in-memory, atomic via WATCH on Redis)."""
        state = await self.get(workflow_id) or {}
        state.update(updates)
        await self.set(workflow_id, state)


class AbstractSessionStore(ABC):
    """Append-only session history store."""

    @abstractmethod
    async def append(self, session_id: str, item: Dict[str, Any]) -> None: ...

    @abstractmethod
    async def get(self, session_id: str) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def clear(self, session_id: str) -> None: ...


class AbstractOwnershipRegistry(ABC):
    """Per-workflow exclusive ownership with TTL heartbeat for failover."""

    @abstractmethod
    async def claim(self, workflow_id: str, instance_id: str, ttl: int = OWNERSHIP_TTL) -> bool: ...

    @abstractmethod
    async def release(self, workflow_id: str, instance_id: str) -> None: ...

    @abstractmethod
    async def get_owner(self, workflow_id: str) -> Optional[str]: ...

    @abstractmethod
    async def refresh(self, workflow_id: str, instance_id: str, ttl: int = OWNERSHIP_TTL) -> bool: ...


class AbstractPubSubBroker(ABC):
    """Cross-instance event broker (for WebSocket fan-out)."""

    @abstractmethod
    async def publish(self, workflow_id: str, event: Dict[str, Any]) -> None: ...

    @abstractmethod
    async def subscribe(self, workflow_id: str, callback: Callable[[Dict[str, Any]], Any]) -> None: ...

    @abstractmethod
    async def unsubscribe(self, workflow_id: str) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...


class AbstractInstanceRegistry(ABC):
    """Live instance discovery — register / heartbeat / enumerate."""

    @abstractmethod
    async def register(self, instance_id: str, endpoint: str) -> None: ...

    @abstractmethod
    async def heartbeat(self, instance_id: str) -> None: ...

    @abstractmethod
    async def get_endpoint(self, instance_id: str) -> Optional[str]: ...

    @abstractmethod
    async def list_all(self) -> Dict[str, str]: ...

    @abstractmethod
    async def deregister(self, instance_id: str) -> None: ...


# ===========================================================================
# IN-MEMORY BACKENDS  (single-node, dev/test)
# ===========================================================================

class InMemoryWorkflowStore(AbstractWorkflowStore):
    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}

    async def set(self, workflow_id: str, state: Dict[str, Any]) -> None:
        self._store[workflow_id] = state

    async def get(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        return self._store.get(workflow_id)

    async def delete(self, workflow_id: str) -> None:
        self._store.pop(workflow_id, None)

    async def list_ids(self) -> List[str]:
        return list(self._store.keys())


class InMemorySessionStore(AbstractSessionStore):
    def __init__(self) -> None:
        self._store: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    async def append(self, session_id: str, item: Dict[str, Any]) -> None:
        self._store[session_id].append(item)

    async def get(self, session_id: str) -> List[Dict[str, Any]]:
        return list(self._store.get(session_id, []))

    async def clear(self, session_id: str) -> None:
        self._store.pop(session_id, None)


class InMemoryOwnershipRegistry(AbstractOwnershipRegistry):
    """Single-instance ownership — always grants the claim."""

    def __init__(self) -> None:
        # {workflow_id: (instance_id, expires_at)}
        self._owned: Dict[str, tuple] = {}

    async def claim(self, workflow_id: str, instance_id: str, ttl: int = OWNERSHIP_TTL) -> bool:
        entry = self._owned.get(workflow_id)
        now = time.monotonic()
        if entry and entry[0] != instance_id and entry[1] > now:
            return False  # another owner holds it
        self._owned[workflow_id] = (instance_id, now + ttl)
        return True

    async def release(self, workflow_id: str, instance_id: str) -> None:
        entry = self._owned.get(workflow_id)
        if entry and entry[0] == instance_id:
            self._owned.pop(workflow_id, None)

    async def get_owner(self, workflow_id: str) -> Optional[str]:
        entry = self._owned.get(workflow_id)
        if entry and entry[1] > time.monotonic():
            return entry[0]
        return None

    async def refresh(self, workflow_id: str, instance_id: str, ttl: int = OWNERSHIP_TTL) -> bool:
        entry = self._owned.get(workflow_id)
        now = time.monotonic()
        if entry and entry[0] == instance_id:
            self._owned[workflow_id] = (instance_id, now + ttl)
            return True
        return False


class InMemoryPubSubBroker(AbstractPubSubBroker):
    """In-process pub/sub using asyncio queues — no cross-instance fan-out."""

    def __init__(self) -> None:
        # workflow_id -> list of async callback functions
        self._subs: Dict[str, List[Callable]] = defaultdict(list)

    async def publish(self, workflow_id: str, event: Dict[str, Any]) -> None:
        cbs = list(self._subs.get(workflow_id, []))
        for cb in cbs:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(event)
                else:
                    cb(event)
            except Exception as exc:
                logger.warning("pubsub callback error for %s: %s", workflow_id, exc)

    async def subscribe(self, workflow_id: str, callback: Callable) -> None:
        self._subs[workflow_id].append(callback)

    async def unsubscribe(self, workflow_id: str) -> None:
        self._subs.pop(workflow_id, None)

    async def close(self) -> None:
        self._subs.clear()


class InMemoryInstanceRegistry(AbstractInstanceRegistry):
    def __init__(self) -> None:
        self._instances: Dict[str, Dict[str, Any]] = {}

    async def register(self, instance_id: str, endpoint: str) -> None:
        self._instances[instance_id] = {"endpoint": endpoint, "last_seen": time.monotonic()}

    async def heartbeat(self, instance_id: str) -> None:
        if instance_id in self._instances:
            self._instances[instance_id]["last_seen"] = time.monotonic()

    async def get_endpoint(self, instance_id: str) -> Optional[str]:
        entry = self._instances.get(instance_id)
        return entry["endpoint"] if entry else None

    async def list_all(self) -> Dict[str, str]:
        now = time.monotonic()
        return {
            iid: v["endpoint"]
            for iid, v in self._instances.items()
            if now - v["last_seen"] < INSTANCE_TTL
        }

    async def deregister(self, instance_id: str) -> None:
        self._instances.pop(instance_id, None)


# ===========================================================================
# REDIS BACKENDS  (production HA)
# ===========================================================================

def _redis_client():
    """Lazy import of redis.asyncio to avoid hard dependency for in-memory mode."""
    try:
        import redis.asyncio as aioredis  # type: ignore
        return aioredis
    except ImportError:
        raise RuntimeError(
            "redis package is required for HA_BACKEND=redis. "
            "Install with: pip install redis>=5.0.0"
        )


class _RedisBase:
    """Shared Redis connection management."""

    def __init__(self, redis_url: str) -> None:
        aioredis = _redis_client()
        self._redis = aioredis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        logger.info("Redis connection pool created → %s", redis_url)

    @property
    def redis(self):
        return self._redis

    async def close(self) -> None:
        await self._redis.aclose()


class RedisWorkflowStore(_RedisBase, AbstractWorkflowStore):
    """Stores workflow state in Redis hashes: key = wf:<workflow_id>"""

    PREFIX = "wf:"

    async def set(self, workflow_id: str, state: Dict[str, Any]) -> None:
        key = self.PREFIX + workflow_id
        serialized = json.dumps(state, default=str)
        await self.redis.set(key, serialized, ex=WORKFLOW_STATE_TTL)

    async def get(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        key = self.PREFIX + workflow_id
        raw = await self.redis.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error("Failed to decode workflow state for %s", workflow_id)
            return None

    async def delete(self, workflow_id: str) -> None:
        await self.redis.delete(self.PREFIX + workflow_id)

    async def list_ids(self) -> List[str]:
        keys = await self.redis.keys(self.PREFIX + "*")
        return [k[len(self.PREFIX):] for k in keys]

    async def update(self, workflow_id: str, updates: Dict[str, Any]) -> None:
        """Atomic update via WATCH/MULTI/EXEC optimistic lock."""
        key = self.PREFIX + workflow_id
        async with self.redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(key)
                    raw = await pipe.get(key)
                    state = json.loads(raw) if raw else {}
                    state.update(updates)
                    pipe.multi()
                    await pipe.set(key, json.dumps(state, default=str), ex=WORKFLOW_STATE_TTL)
                    await pipe.execute()
                    break
                except Exception:  # WatchError or transient
                    continue


class RedisSessionStore(_RedisBase, AbstractSessionStore):
    """Stores session history in Redis lists: key = sess:<session_id>"""

    PREFIX = "sess:"
    SESSION_TTL = int(_env("SESSION_TTL", "604800"))  # 7 days

    async def append(self, session_id: str, item: Dict[str, Any]) -> None:
        key = self.PREFIX + session_id
        await self.redis.rpush(key, json.dumps(item, default=str))
        await self.redis.expire(key, self.SESSION_TTL)

    async def get(self, session_id: str) -> List[Dict[str, Any]]:
        key = self.PREFIX + session_id
        raw_items = await self.redis.lrange(key, 0, -1)
        result = []
        for raw in raw_items:
            try:
                result.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
        return result

    async def clear(self, session_id: str) -> None:
        await self.redis.delete(self.PREFIX + session_id)


class RedisOwnershipRegistry(_RedisBase, AbstractOwnershipRegistry):
    """
    Per-workflow ownership using Redis SET NX EX:
      key = own:<workflow_id>  /  value = <instance_id>
    Only the owner can extend or release the key.
    """

    PREFIX = "own:"

    async def claim(self, workflow_id: str, instance_id: str, ttl: int = OWNERSHIP_TTL) -> bool:
        key = self.PREFIX + workflow_id
        # NX = only set if not exists
        result = await self.redis.set(key, instance_id, nx=True, ex=ttl)
        if result:
            return True
        # Check if we already own it
        current = await self.redis.get(key)
        if current == instance_id:
            await self.redis.expire(key, ttl)  # refresh TTL
            return True
        return False

    async def release(self, workflow_id: str, instance_id: str) -> None:
        key = self.PREFIX + workflow_id
        current = await self.redis.get(key)
        if current == instance_id:
            await self.redis.delete(key)

    async def get_owner(self, workflow_id: str) -> Optional[str]:
        return await self.redis.get(self.PREFIX + workflow_id)

    async def refresh(self, workflow_id: str, instance_id: str, ttl: int = OWNERSHIP_TTL) -> bool:
        key = self.PREFIX + workflow_id
        current = await self.redis.get(key)
        if current == instance_id:
            await self.redis.expire(key, ttl)
            return True
        return False


class RedisPubSubBroker(AbstractPubSubBroker):
    """
    Redis pub/sub for cross-instance WebSocket fan-out.

    Each instance subscribes to channels it cares about and forwards messages
    to its local WebSocket connection manager.

    Channel naming: wfevt:<workflow_id>
    """

    CHANNEL_PREFIX = "wfevt:"

    def __init__(self, redis_url: str) -> None:
        aioredis = _redis_client()
        self._pub_redis = aioredis.from_url(
            redis_url, encoding="utf-8", decode_responses=True
        )
        self._sub_redis = aioredis.from_url(
            redis_url, encoding="utf-8", decode_responses=True
        )
        self._subscriptions: Dict[str, asyncio.Task] = {}
        self._callbacks: Dict[str, List[Callable]] = defaultdict(list)

    async def publish(self, workflow_id: str, event: Dict[str, Any]) -> None:
        channel = self.CHANNEL_PREFIX + workflow_id
        try:
            await self._pub_redis.publish(channel, json.dumps(event, default=str))
        except Exception as exc:
            logger.warning("Redis publish failed for %s: %s", workflow_id, exc)

    async def subscribe(self, workflow_id: str, callback: Callable) -> None:
        self._callbacks[workflow_id].append(callback)
        if workflow_id not in self._subscriptions:
            task = asyncio.create_task(self._listen_loop(workflow_id))
            self._subscriptions[workflow_id] = task

    async def _listen_loop(self, workflow_id: str) -> None:
        channel = self.CHANNEL_PREFIX + workflow_id
        pubsub = self._sub_redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for msg in pubsub.listen():
                if msg["type"] != "message":
                    continue
                try:
                    event = json.loads(msg["data"])
                except json.JSONDecodeError:
                    continue
                for cb in list(self._callbacks.get(workflow_id, [])):
                    try:
                        if asyncio.iscoroutinefunction(cb):
                            await cb(event)
                        else:
                            cb(event)
                    except Exception as exc:
                        logger.warning("pubsub callback error for %s: %s", workflow_id, exc)
        except asyncio.CancelledError:
            pass
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
            except Exception:
                pass

    async def unsubscribe(self, workflow_id: str) -> None:
        task = self._subscriptions.pop(workflow_id, None)
        if task:
            task.cancel()
        self._callbacks.pop(workflow_id, None)

    async def close(self) -> None:
        for task in list(self._subscriptions.values()):
            task.cancel()
        self._subscriptions.clear()
        self._callbacks.clear()
        try:
            await self._pub_redis.aclose()
            await self._sub_redis.aclose()
        except Exception:
            pass


class RedisInstanceRegistry(_RedisBase, AbstractInstanceRegistry):
    """
    Instance registry backed by Redis.
    Key: inst:<instance_id>   Value: endpoint URL
    """

    PREFIX = "inst:"

    async def register(self, instance_id: str, endpoint: str) -> None:
        await self.redis.set(self.PREFIX + instance_id, endpoint, ex=INSTANCE_TTL)

    async def heartbeat(self, instance_id: str) -> None:
        await self.redis.expire(self.PREFIX + instance_id, INSTANCE_TTL)

    async def get_endpoint(self, instance_id: str) -> Optional[str]:
        return await self.redis.get(self.PREFIX + instance_id)

    async def list_all(self) -> Dict[str, str]:
        keys = await self.redis.keys(self.PREFIX + "*")
        if not keys:
            return {}
        values = await self.redis.mget(*keys)
        result = {}
        for key, val in zip(keys, values):
            if val:
                iid = key[len(self.PREFIX):]
                result[iid] = val
        return result

    async def deregister(self, instance_id: str) -> None:
        await self.redis.delete(self.PREFIX + instance_id)


# ===========================================================================
# DISTRIBUTED STATE  — top-level container
# ===========================================================================

class DistributedState:
    """
    Single entry-point for all distributed state operations.

    Attributes:
        workflows   — AbstractWorkflowStore    (active_workflows replacement)
        sessions    — AbstractSessionStore     (session_store replacement)
        ownership   — AbstractOwnershipRegistry
        pubsub      — AbstractPubSubBroker
        instances   — AbstractInstanceRegistry
        instance_id — str, unique ID of this replica
        endpoint    — Optional[str], HTTP endpoint of this replica
        backend     — HABackend enum value
    """

    def __init__(
        self,
        workflows: AbstractWorkflowStore,
        sessions: AbstractSessionStore,
        ownership: AbstractOwnershipRegistry,
        pubsub: AbstractPubSubBroker,
        instances: AbstractInstanceRegistry,
        instance_id: str,
        endpoint: Optional[str],
        backend: HABackend,
    ) -> None:
        self.workflows = workflows
        self.sessions = sessions
        self.ownership = ownership
        self.pubsub = pubsub
        self.instances = instances
        self.instance_id = instance_id
        self.endpoint = endpoint
        self.backend = backend
        self._heartbeat_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """Register this instance and start the ownership heartbeat loop."""
        if self.endpoint:
            await self.instances.register(self.instance_id, self.endpoint)
            logger.info("Registered instance %s at %s", self.instance_id, self.endpoint)
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("DistributedState started — backend=%s instance=%s", self.backend.value, self.instance_id)

    async def shutdown(self) -> None:
        """Deregister this instance and clean up connections."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        await self.pubsub.close()
        if self.endpoint:
            await self.instances.deregister(self.instance_id)
        if isinstance(self.workflows, _RedisBase):
            await self.workflows.close()
        if isinstance(self.sessions, _RedisBase):
            await self.sessions.close()
        if isinstance(self.ownership, _RedisBase):
            await self.ownership.close()
        if isinstance(self.instances, _RedisBase):
            await self.instances.close()
        logger.info("DistributedState shut down.")

    async def _heartbeat_loop(self) -> None:
        """Periodically refresh instance registration and owned workflow leases."""
        while True:
            try:
                await asyncio.sleep(OWNERSHIP_TTL // 2)
                if self.endpoint:
                    await self.instances.heartbeat(self.instance_id)
                # Refresh ownership for any active workflows this instance handles
                workflow_ids = await self.workflows.list_ids()
                for wid in workflow_ids:
                    owner = await self.ownership.get_owner(wid)
                    if owner == self.instance_id:
                        await self.ownership.refresh(wid, self.instance_id)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Heartbeat error: %s", exc)

    # ------------------------------------------------------------------
    # Convenience helpers matching the old active_workflows dict interface
    # ------------------------------------------------------------------

    async def get_workflow_state(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Drop-in replacement for: active_workflows.get(workflow_id)"""
        return await self.workflows.get(workflow_id)

    async def set_workflow_state(self, workflow_id: str, state: Dict[str, Any]) -> None:
        """Drop-in replacement for: active_workflows[workflow_id] = state"""
        await self.workflows.set(workflow_id, state)

    async def update_workflow_state(self, workflow_id: str, updates: Dict[str, Any]) -> None:
        """Atomic partial update: active_workflows[wid].update(...)"""
        await self.workflows.update(workflow_id, updates)

    async def delete_workflow_state(self, workflow_id: str) -> None:
        """Drop-in replacement for: del active_workflows[workflow_id]"""
        await self.workflows.delete(workflow_id)

    async def workflow_exists(self, workflow_id: str) -> bool:
        """Drop-in replacement for: workflow_id in active_workflows"""
        state = await self.workflows.get(workflow_id)
        return state is not None

    # ------------------------------------------------------------------
    # Fanout helper: publish and also deliver locally if WS connections exist
    # ------------------------------------------------------------------

    async def broadcast_event(
        self,
        workflow_id: str,
        event: Dict[str, Any],
        local_connection_manager=None,
    ) -> None:
        """
        Publish event via pub/sub so ALL replicas can forward it to their
        local WebSocket connections.

        If `local_connection_manager` is provided it is called immediately
        for connections on THIS instance (avoids the round-trip).
        """
        if local_connection_manager and local_connection_manager.has_connections(workflow_id):
            await local_connection_manager.broadcast_to_workflow(workflow_id, event)
        # Always publish so other instances can pick it up
        await self.pubsub.publish(workflow_id, event)

    async def subscribe_local_websocket(
        self,
        workflow_id: str,
        connection_manager,
    ) -> None:
        """
        Subscribe to pub/sub events for `workflow_id` and forward them to
        the local WebSocket connection manager.  Called when a WS client
        connects to THIS instance for a workflow that might be executing on
        a DIFFERENT instance.
        """

        async def _forward(event: Dict[str, Any]) -> None:
            if connection_manager.has_connections(workflow_id):
                # Use local-only broadcast to avoid a pub/sub feedback loop:
                # the HA-wrapped broadcast_to_workflow also publishes back to
                # pub/sub, which would re-trigger this handler infinitely.
                local_bcast = getattr(
                    connection_manager,
                    "_local_broadcast",
                    connection_manager.broadcast_to_workflow,
                )
                await local_bcast(workflow_id, event)

        await self.pubsub.subscribe(workflow_id, _forward)


# ===========================================================================
# FACTORY  — singleton
# ===========================================================================

_distributed_state_singleton: Optional[DistributedState] = None


def get_distributed_state(
    *,
    backend: Optional[str] = None,
    redis_url: Optional[str] = None,
    instance_id: Optional[str] = None,
    endpoint: Optional[str] = None,
    force_new: bool = False,
) -> DistributedState:
    """
    Return the singleton DistributedState, creating it on first call.

    Parameters override environment variables when explicitly provided.
    Call `await get_distributed_state().startup()` in the app lifespan.
    """
    global _distributed_state_singleton
    if _distributed_state_singleton is not None and not force_new:
        return _distributed_state_singleton

    backend_str = backend or _env("HA_BACKEND", HABackend.in_memory.value)
    try:
        ha_backend = HABackend(backend_str)
    except ValueError:
        logger.warning("Unknown HA_BACKEND=%s, falling back to in_memory", backend_str)
        ha_backend = HABackend.in_memory

    _instance_id = instance_id or _env("ORCHESTRATOR_INSTANCE_ID", _default_instance_id())
    _endpoint = endpoint or _env("ORCHESTRATOR_PUBLIC_ENDPOINT") or None

    if ha_backend == HABackend.redis:
        _redis_url = redis_url or _env("REDIS_URL", "redis://localhost:6379")
        workflows_store = RedisWorkflowStore(_redis_url)
        sessions_store = RedisSessionStore(_redis_url)
        ownership_reg = RedisOwnershipRegistry(_redis_url)
        pubsub_broker = RedisPubSubBroker(_redis_url)
        instance_reg = RedisInstanceRegistry(_redis_url)
        logger.info("DistributedState initialising with Redis backend (%s)", _redis_url)
    else:
        # in_memory: suitable for single-instance dev/test only
        workflows_store = InMemoryWorkflowStore()
        sessions_store = InMemorySessionStore()
        ownership_reg = InMemoryOwnershipRegistry()
        pubsub_broker = InMemoryPubSubBroker()
        instance_reg = InMemoryInstanceRegistry()
        logger.info("DistributedState initialising with in-memory backend (single-node)")

    _distributed_state_singleton = DistributedState(
        workflows=workflows_store,
        sessions=sessions_store,
        ownership=ownership_reg,
        pubsub=pubsub_broker,
        instances=instance_reg,
        instance_id=_instance_id,
        endpoint=_endpoint,
        backend=ha_backend,
    )
    return _distributed_state_singleton
