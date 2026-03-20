"""
Gateway Audit Logger

Provides immutable, structured audit logging for every event that
passes through the Model Gateway:

  - MODEL_SELECTION: which model was chosen, why, and what the alternatives were
  - COMPLETION_REQUEST: full request metadata (no raw content by default)
  - COMPLETION_RESPONSE: provider, model, usage, latency, cost
  - FALLBACK_EVENT: when the primary model fails and another is used
  - PROVIDER_HEALTH_CHANGE: circuit breaker state transitions
  - RATE_LIMIT: provider rate limit events
  - ERROR: unexpected errors

All log entries are:
  - Written to a rotating JSONL file under GATEWAY_AUDIT_LOG_DIR
  - Written to the Python log stream (structured JSON)
  - Signed with a SHA-256 chain hash (WORM-style tamper detection)
  - Optionally forwarded to the shared AuditLogger (if available)

Environment:
    GATEWAY_AUDIT_LOG_DIR   default ./audit_logs
    GATEWAY_AUDIT_LOG_LEVEL default INFO
    GATEWAY_AUDIT_REDACT_CONTENT  default true — do NOT log raw message content
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_AUDIT_INSTANCE: Optional[GatewayAuditLogger] = None

_AUDIT_LOG_DIR = Path(os.getenv("GATEWAY_AUDIT_LOG_DIR", "./audit_logs"))
_REDACT_CONTENT = os.getenv("GATEWAY_AUDIT_REDACT_CONTENT", "true").lower() == "true"
_MAX_BYTES_PER_FILE = int(os.getenv("GATEWAY_AUDIT_MAX_FILE_BYTES", str(50 * 1024 * 1024)))  # 50 MB


class GatewayAuditEventType(str, Enum):
    MODEL_SELECTION = "model_selection"
    COMPLETION_REQUEST = "completion_request"
    COMPLETION_RESPONSE = "completion_response"
    FALLBACK_EVENT = "fallback_event"
    PROVIDER_HEALTH_CHANGE = "provider_health_change"
    RATE_LIMIT = "rate_limit_hit"
    ERROR = "error"
    HEALTH_CHECK = "health_check"


@dataclass
class GatewayAuditEvent:
    event_type: GatewayAuditEventType
    request_id: str
    timestamp: float = field(default_factory=time.time)
    workflow_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    # Chain-hash for tamper detection
    prev_hash: Optional[str] = None
    event_hash: Optional[str] = None


class GatewayAuditLogger:
    """
    Thread-safe, rotating JSONL audit logger for the Model Gateway.
    """

    def __init__(self) -> None:
        _AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._prev_hash: str = "GENESIS"
        self._current_file: Optional[Path] = None
        self._current_size: int = 0
        self._rotate()
        logger.info("GatewayAuditLogger initialised. Log dir: %s", _AUDIT_LOG_DIR)

    # ------------------------------------------------------------------
    # Core log method
    # ------------------------------------------------------------------

    def log(self, event: GatewayAuditEvent) -> None:
        """Write an audit event. Thread-safe."""
        with self._lock:
            event.prev_hash = self._prev_hash
            event.event_hash = self._compute_hash(event)
            self._prev_hash = event.event_hash
            self._write(event)

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def log_model_selection(
        self,
        request_id: str,
        selected_model: str,
        selected_provider: str,
        detected_task: str,
        reason: str,
        fallbacks: List[str],
        estimated_cost_per_1k: Optional[float] = None,
        workflow_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        self.log(GatewayAuditEvent(
            event_type=GatewayAuditEventType.MODEL_SELECTION,
            request_id=request_id,
            workflow_id=workflow_id,
            user_id=user_id,
            details={
                "selected_model": selected_model,
                "selected_provider": selected_provider,
                "detected_task": detected_task,
                "reason": reason,
                "fallback_chain": fallbacks,
                "estimated_cost_usd_per_1k_tokens": estimated_cost_per_1k,
            },
        ))

    def log_completion_request(
        self,
        request_id: str,
        model_id: str,
        provider: str,
        message_count: int,
        max_tokens: int,
        stream: bool,
        workflow_id: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        content_preview: Optional[str] = None,   # only logged if REDACT_CONTENT=false
    ) -> None:
        details: Dict[str, Any] = {
            "model_id": model_id,
            "provider": provider,
            "message_count": message_count,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if not _REDACT_CONTENT and content_preview:
            details["content_preview"] = content_preview[:500]
        self.log(GatewayAuditEvent(
            event_type=GatewayAuditEventType.COMPLETION_REQUEST,
            request_id=request_id,
            workflow_id=workflow_id,
            session_id=session_id,
            user_id=user_id,
            details=details,
        ))

    def log_completion_response(
        self,
        request_id: str,
        model_id: str,
        provider: str,
        finish_reason: str,
        input_tokens: int,
        output_tokens: int,
        estimated_cost_usd: float,
        latency_ms: float,
        fallback_used: bool = False,
        original_model: Optional[str] = None,
        fallback_reason: Optional[str] = None,
        workflow_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        self.log(GatewayAuditEvent(
            event_type=GatewayAuditEventType.COMPLETION_RESPONSE,
            request_id=request_id,
            workflow_id=workflow_id,
            user_id=user_id,
            details={
                "model_id": model_id,
                "provider": provider,
                "finish_reason": finish_reason,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "estimated_cost_usd": round(estimated_cost_usd, 8),
                "latency_ms": round(latency_ms, 2),
                "fallback_used": fallback_used,
                "original_model": original_model,
                "fallback_reason": fallback_reason,
            },
        ))

    def log_fallback_event(
        self,
        request_id: str,
        original_model: str,
        original_provider: str,
        fallback_model: str,
        fallback_provider: str,
        reason: str,
        attempt: int,
        workflow_id: Optional[str] = None,
    ) -> None:
        self.log(GatewayAuditEvent(
            event_type=GatewayAuditEventType.FALLBACK_EVENT,
            request_id=request_id,
            workflow_id=workflow_id,
            details={
                "original_model": original_model,
                "original_provider": original_provider,
                "fallback_model": fallback_model,
                "fallback_provider": fallback_provider,
                "reason": reason,
                "attempt": attempt,
            },
        ))

    def log_provider_health_change(
        self,
        provider: str,
        old_state: str,
        new_state: str,
        reason: Optional[str] = None,
    ) -> None:
        self.log(GatewayAuditEvent(
            event_type=GatewayAuditEventType.PROVIDER_HEALTH_CHANGE,
            request_id=f"health_{uuid.uuid4().hex[:8]}",
            details={
                "provider": provider,
                "old_state": old_state,
                "new_state": new_state,
                "reason": reason,
            },
        ))

    def log_error(
        self,
        request_id: str,
        error: str,
        model_id: Optional[str] = None,
        provider: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> None:
        self.log(GatewayAuditEvent(
            event_type=GatewayAuditEventType.ERROR,
            request_id=request_id,
            workflow_id=workflow_id,
            details={
                "error": error,
                "model_id": model_id,
                "provider": provider,
            },
        ))

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def recent_events(
        self,
        limit: int = 100,
        event_type: Optional[GatewayAuditEventType] = None,
    ) -> List[Dict[str, Any]]:
        """
        Read and return recent events from the current log file.
        Filters by event_type if specified.
        """
        if not self._current_file or not self._current_file.exists():
            return []

        try:
            with open(self._current_file, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError:
            return []

        events = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
                if event_type and evt.get("event_type") != event_type.value:
                    continue
                events.append(evt)
            except json.JSONDecodeError:
                continue
            if len(events) >= limit:
                break
        return events

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _rotate(self) -> None:
        ts = time.strftime("%Y%m%d_%H%M%S")
        self._current_file = _AUDIT_LOG_DIR / f"model_gateway_{ts}.jsonl"
        self._current_size = 0

    def _write(self, event: GatewayAuditEvent) -> None:
        line = json.dumps(self._serialise(event), default=str) + "\n"
        encoded = line.encode("utf-8")

        if self._current_size + len(encoded) > _MAX_BYTES_PER_FILE:
            self._compress_and_rotate()

        try:
            with open(self._current_file, "a", encoding="utf-8") as fh:
                fh.write(line)
            self._current_size += len(encoded)
        except OSError as exc:
            logger.error("Failed to write audit log: %s", exc)

        # Also emit to Python log stream
        logger.info("GATEWAY_AUDIT %s", json.dumps(self._serialise(event), default=str))

    def _compress_and_rotate(self) -> None:
        """Gzip the current file, then start a new one."""
        if self._current_file and self._current_file.exists():
            gz_path = self._current_file.with_suffix(".jsonl.gz")
            try:
                with open(self._current_file, "rb") as f_in:
                    with gzip.open(gz_path, "wb") as f_out:
                        f_out.write(f_in.read())
                self._current_file.unlink()
                logger.info("Rotated audit log to %s", gz_path)
            except OSError as exc:
                logger.warning("Could not compress audit log: %s", exc)
        self._rotate()

    @staticmethod
    def _serialise(event: GatewayAuditEvent) -> dict:
        return {
            "event_type": event.event_type.value,
            "request_id": event.request_id,
            "timestamp": event.timestamp,
            "timestamp_iso": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(event.timestamp)
            ),
            "workflow_id": event.workflow_id,
            "session_id": event.session_id,
            "user_id": event.user_id,
            "details": event.details,
            "prev_hash": event.prev_hash,
            "event_hash": event.event_hash,
        }

    @staticmethod
    def _compute_hash(event: GatewayAuditEvent) -> str:
        payload = json.dumps(
            {
                "event_type": event.event_type.value,
                "request_id": event.request_id,
                "timestamp": event.timestamp,
                "details": event.details,
                "prev_hash": event.prev_hash,
            },
            sort_keys=True,
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


def get_gateway_audit_logger() -> GatewayAuditLogger:
    global _AUDIT_INSTANCE
    if _AUDIT_INSTANCE is None:
        _AUDIT_INSTANCE = GatewayAuditLogger()
    return _AUDIT_INSTANCE
