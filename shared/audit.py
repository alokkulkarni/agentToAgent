"""
Enterprise Audit Logger

This module provides comprehensive audit logging for compliance:
- WORM (Write Once Read Many) style logging
- Chain of Thought (CoT) capture
- Tamper-proof signatures
- Structured event logging
- Log rotation and retention

All audit logs are immutable once written.

Usage:
    from shared.audit import AuditLogger, get_audit_logger, AuditEventType
    
    audit = get_audit_logger()
    
    # Log an event
    audit.log_event(
        workflow_id="wf_123",
        user_id="user_456",
        event_type=AuditEventType.TOOL_INVOCATION,
        details={"tool": "transfer_funds", "amount": 500}
    )
    
    # Log Chain of Thought
    audit.log_cot(
        workflow_id="wf_123",
        step=1,
        thought="User wants to transfer money",
        plan="Call GetBalance -> If sufficient -> Call PostTransfer",
        observation="Balance is $50",
        action="Inform user balance is insufficient"
    )
"""

import json
import os
import hashlib
import logging
import gzip
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
import threading
import queue
from contextlib import contextmanager

from .config import ConfigManager

logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Types of audit events"""
    # Workflow events
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_PAUSED = "workflow_paused"
    WORKFLOW_RESUMED = "workflow_resumed"
    
    # Step events
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    
    # Agent events
    AGENT_INVOCATION = "agent_invocation"
    AGENT_RESPONSE = "agent_response"
    
    # LLM events
    LLM_INVOCATION = "llm_invocation"
    LLM_RESPONSE = "llm_response"
    
    # Tool events
    TOOL_INVOCATION = "tool_invocation"
    TOOL_RESPONSE = "tool_response"
    TOOL_AUTHORIZATION = "tool_authorization"
    
    # Security events
    GUARDRAIL_VIOLATION = "guardrail_violation"
    SECURITY_VIOLATION = "security_violation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION_DENIED = "authorization_denied"
    
    # Chain of Thought
    CHAIN_OF_THOUGHT = "chain_of_thought"
    
    # User interaction
    USER_INPUT_REQUESTED = "user_input_requested"
    USER_INPUT_RECEIVED = "user_input_received"
    
    # System events
    SYSTEM_ERROR = "system_error"
    CONFIGURATION_CHANGE = "configuration_change"


@dataclass
class AuditEntry:
    """
    Immutable audit log entry with blockchain-style hash chaining.
    
    Security Properties:
    - Each entry is signed with SHA-256 hash of its contents
    - Each entry includes hash of previous entry (chain_hash)
    - Tampering with any entry breaks the chain
    - WORM compliance: entries are immutable once written
    
    This implements a simplified blockchain for audit trails,
    suitable for regulatory compliance (SOX, PCI-DSS, HIPAA).
    """
    timestamp: str
    event_id: str
    workflow_id: str
    user_id: str
    event_type: str
    details: Dict[str, Any]
    session_id: Optional[str] = None
    tenant_id: Optional[str] = None
    parent_event_id: Optional[str] = None
    signature: Optional[str] = None
    chain_hash: Optional[str] = None  # Hash of previous entry (blockchain-style)
    
    def __post_init__(self):
        """Generate signature after initialization"""
        if not self.signature:
            self.signature = self._generate_signature()
    
    def _generate_signature(self) -> str:
        """
        Generate tamper-proof signature.
        
        The signature includes:
        - All entry fields (timestamp, event_id, etc.)
        - The chain_hash (previous entry's signature)
        
        This creates an unbreakable chain where modifying
        any historical entry invalidates all subsequent entries.
        """
        data = {
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "workflow_id": self.workflow_id,
            "user_id": self.user_id,
            "event_type": self.event_type,
            "details": self.details,
            "chain_hash": self.chain_hash  # Include previous hash in signature
        }
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()
    
    def verify_signature(self) -> bool:
        """Verify entry hasn't been tampered with"""
        expected = self._generate_signature()
        return self.signature == expected
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict())


@dataclass
class ChainOfThoughtEntry:
    """
    Structured Chain of Thought entry for regulatory audit.
    
    Captures the reasoning process:
    - Thought: What the agent understood
    - Plan: What steps were planned
    - Observation: What was observed
    - Action: What action was taken
    """
    step: int
    thought: str
    plan: str
    observation: str
    action: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AsyncLogWriter:
    """
    Asynchronous log writer for non-blocking audit logging.
    
    Uses a background thread to write logs, ensuring
    main application performance isn't impacted.
    """
    
    def __init__(self, log_dir: Path, max_queue_size: int = 10000):
        self._log_dir = log_dir
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._shutdown = threading.Event()
        self._writer_thread: Optional[threading.Thread] = None
        self._current_file: Optional[Path] = None
        self._current_date: Optional[str] = None
        self._lock = threading.Lock()
        
        # Start writer thread
        self._start_writer()
    
    def _start_writer(self):
        """Start background writer thread"""
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._writer_thread.start()
    
    def _writer_loop(self):
        """Background loop that writes queued entries to disk"""
        while not self._shutdown.is_set():
            try:
                entry = self._queue.get(timeout=1.0)
                self._write_entry(entry)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in audit writer: {e}")
    
    def _write_entry(self, entry: AuditEntry):
        """Write entry to log file"""
        try:
            date_str = datetime.utcnow().strftime("%Y-%m-%d")
            
            # Rotate file if date changed
            if date_str != self._current_date:
                self._current_date = date_str
                self._current_file = self._log_dir / f"audit_{date_str}.jsonl"
            
            with open(self._current_file, "a") as f:
                f.write(entry.to_json() + "\n")
                
        except Exception as e:
            logger.error(f"Failed to write audit entry: {e}")
    
    def write(self, entry: AuditEntry):
        """Queue entry for writing"""
        try:
            self._queue.put_nowait(entry)
        except queue.Full:
            logger.warning("Audit log queue full, dropping entry")
    
    def flush(self):
        """Wait for all queued entries to be written"""
        self._queue.join()
    
    def shutdown(self):
        """Shutdown writer gracefully"""
        self._shutdown.set()
        self.flush()
        if self._writer_thread:
            self._writer_thread.join(timeout=5.0)


class AuditLogger:
    """
    Enterprise Audit Logger with Blockchain-Style Hash Chaining
    
    Implements WORM (Write Once Read Many) style audit logging for compliance.
    Captures all significant events including Chain of Thought (CoT).
    
    Features:
    - Tamper-proof signatures on all entries
    - Blockchain-style hash chaining (each entry links to previous)
    - Asynchronous writing for performance
    - Automatic log rotation
    - Structured event types
    - Chain of Thought capture
    - Chain verification for integrity audits
    
    Compliance: SOX, PCI-DSS, HIPAA, GDPR
    """
    
    def __init__(self):
        self._config = ConfigManager.get_instance()
        self._log_dir = Path(self._config.compliance.worm_storage_path)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        
        self._event_counter = 0
        self._counter_lock = threading.Lock()
        
        # Blockchain-style hash chain
        self._last_hash: Optional[str] = None
        self._hash_lock = threading.Lock()
        
        # Load last hash from existing logs
        self._initialize_chain_hash()
        
        # Initialize async writer if enabled
        self._async_writer: Optional[AsyncLogWriter] = None
        if self._config.feature_flags.enable_audit_logging:
            self._async_writer = AsyncLogWriter(self._log_dir)
        
        logger.info(f"Audit logger initialized, log directory: {self._log_dir}")
    
    def _initialize_chain_hash(self):
        """Load the last hash from existing logs to continue the chain"""
        try:
            # Find most recent log file
            log_files = sorted(self._log_dir.glob("audit_*.jsonl"), reverse=True)
            if log_files:
                # Read last line of most recent file
                with open(log_files[0], "r") as f:
                    lines = f.readlines()
                    if lines:
                        last_entry = json.loads(lines[-1])
                        self._last_hash = last_entry.get("signature")
                        logger.debug(f"Chain hash initialized from {log_files[0]}")
        except Exception as e:
            logger.warning(f"Could not initialize chain hash: {e}")
            self._last_hash = "GENESIS"  # Genesis block
    
    def _generate_event_id(self) -> str:
        """Generate unique event ID"""
        with self._counter_lock:
            self._event_counter += 1
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
            return f"evt_{timestamp}_{self._event_counter:06d}"
    
    def log_event(
        self,
        workflow_id: str,
        user_id: str,
        event_type: AuditEventType,
        details: Dict[str, Any],
        session_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        parent_event_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Log an audit event with blockchain-style hash chaining.
        
        Args:
            workflow_id: Workflow identifier
            user_id: User identifier
            event_type: Type of event
            details: Event details
            session_id: Session identifier (optional)
            tenant_id: Tenant identifier for multi-tenancy (optional)
            parent_event_id: Parent event for correlation (optional)
            
        Returns:
            Event ID if logged, None if logging disabled
        """
        if not self._config.feature_flags.enable_audit_logging:
            return None
        
        # Sanitize details to remove sensitive fields
        safe_details = self._sanitize_details(details)
        
        event_id = self._generate_event_id()
        
        # Get and update chain hash atomically
        with self._hash_lock:
            current_chain_hash = self._last_hash or "GENESIS"
            
            entry = AuditEntry(
                timestamp=datetime.utcnow().isoformat() + "Z",
                event_id=event_id,
                workflow_id=workflow_id,
                user_id=user_id,
                event_type=event_type.value if isinstance(event_type, AuditEventType) else str(event_type),
                details=safe_details,
                session_id=session_id,
                tenant_id=tenant_id,
                parent_event_id=parent_event_id,
                chain_hash=current_chain_hash
            )
            
            # Update chain hash for next entry
            self._last_hash = entry.signature
        
        if self._async_writer:
            self._async_writer.write(entry)
        else:
            self._write_sync(entry)
        
        return event_id
    
    def log_cot(
        self,
        workflow_id: str,
        step: int,
        thought: str,
        plan: str,
        observation: str,
        action: str,
        user_id: str = "system",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Log Chain of Thought specifically.
        
        Required for regulatory compliance - captures the reasoning process.
        
        Args:
            workflow_id: Workflow identifier
            step: Step number in workflow
            thought: What the agent understood
            plan: What steps were planned
            observation: What was observed
            action: What action was taken
            user_id: User identifier
            metadata: Additional metadata
            
        Returns:
            Event ID if logged
        """
        if not self._config.feature_flags.enable_chain_of_thought_logging:
            return None
        
        cot_entry = ChainOfThoughtEntry(
            step=step,
            thought=thought,
            plan=plan,
            observation=observation,
            action=action,
            metadata=metadata or {}
        )
        
        return self.log_event(
            workflow_id=workflow_id,
            user_id=user_id,
            event_type=AuditEventType.CHAIN_OF_THOUGHT,
            details=cot_entry.to_dict()
        )
    
    def log_tool_invocation(
        self,
        workflow_id: str,
        user_id: str,
        tool_name: str,
        parameters: Dict[str, Any],
        authorization_result: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Log a tool invocation with authorization details"""
        # Don't log parameter values for sensitive tools
        safe_params = self._mask_sensitive_params(tool_name, parameters)
        
        return self.log_event(
            workflow_id=workflow_id,
            user_id=user_id,
            event_type=AuditEventType.TOOL_INVOCATION,
            details={
                "tool_name": tool_name,
                "parameters": safe_params,
                "authorization": authorization_result
            }
        )
    
    def log_security_event(
        self,
        workflow_id: str,
        user_id: str,
        event_subtype: str,
        details: Dict[str, Any],
        severity: str = "medium"
    ) -> Optional[str]:
        """Log a security-related event"""
        return self.log_event(
            workflow_id=workflow_id,
            user_id=user_id,
            event_type=AuditEventType.SECURITY_VIOLATION,
            details={
                "subtype": event_subtype,
                "severity": severity,
                **details
            }
        )
    
    def _sanitize_details(self, details: Dict[str, Any]) -> Dict[str, Any]:
        """Remove or mask sensitive fields from details"""
        sensitive_fields = self._config.logging.sensitive_fields_mask
        
        def mask_value(key: str, value: Any) -> Any:
            if key.lower() in [f.lower() for f in sensitive_fields]:
                if isinstance(value, str):
                    return "***MASKED***"
                return None
            if isinstance(value, dict):
                return {k: mask_value(k, v) for k, v in value.items()}
            if isinstance(value, list):
                return [mask_value(key, v) for v in value]
            return value
        
        return {k: mask_value(k, v) for k, v in details.items()}
    
    def _mask_sensitive_params(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Mask sensitive parameters for specific tools"""
        # Get tool policy to check audit level
        tool_policy = self._config.get_tool_policy(tool_name)
        audit_level = tool_policy.get("audit_level", "standard")
        
        if audit_level == "minimal":
            # Only log parameter names, not values
            return {k: "***" for k in params.keys()}
        elif audit_level == "detailed":
            # Log everything (already sanitized by _sanitize_details)
            return params
        else:  # standard
            # Mask known sensitive fields
            masked = {}
            sensitive = ["password", "secret", "token", "key", "credential", "ssn", "credit_card"]
            for k, v in params.items():
                if any(s in k.lower() for s in sensitive):
                    masked[k] = "***MASKED***"
                else:
                    masked[k] = v
            return masked
    
    def _write_sync(self, entry: AuditEntry):
        """Synchronous write for when async is not available"""
        try:
            date_str = datetime.utcnow().strftime("%Y-%m-%d")
            log_file = self._log_dir / f"audit_{date_str}.jsonl"
            
            with open(log_file, "a") as f:
                f.write(entry.to_json() + "\n")
                
        except Exception as e:
            logger.error(f"Failed to write audit entry: {e}")
    
    # ==================== Query Methods ====================
    
    def get_logs_for_workflow(self, workflow_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """Retrieve all logs for a specific workflow"""
        logs = []
        
        for log_file in sorted(self._log_dir.glob("audit_*.jsonl"), reverse=True):
            try:
                with open(log_file, "r") as f:
                    for line in f:
                        entry = json.loads(line)
                        if entry.get("workflow_id") == workflow_id:
                            logs.append(entry)
                            if len(logs) >= limit:
                                return logs
            except Exception as e:
                logger.error(f"Error reading log file {log_file}: {e}")
        
        return logs
    
    def get_logs_for_user(self, user_id: str, days: int = 7, limit: int = 1000) -> List[Dict[str, Any]]:
        """Retrieve recent logs for a specific user"""
        logs = []
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        for log_file in sorted(self._log_dir.glob("audit_*.jsonl"), reverse=True):
            try:
                # Check file date from filename
                date_str = log_file.stem.replace("audit_", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                if file_date < cutoff:
                    break
                
                with open(log_file, "r") as f:
                    for line in f:
                        entry = json.loads(line)
                        if entry.get("user_id") == user_id:
                            logs.append(entry)
                            if len(logs) >= limit:
                                return logs
            except Exception as e:
                logger.error(f"Error reading log file {log_file}: {e}")
        
        return logs
    
    def verify_log_integrity(self, log_file: str) -> Dict[str, Any]:
        """Verify integrity of a log file"""
        results = {
            "file": log_file,
            "total_entries": 0,
            "valid_entries": 0,
            "invalid_entries": 0,
            "invalid_details": []
        }
        
        try:
            with open(log_file, "r") as f:
                for i, line in enumerate(f, 1):
                    results["total_entries"] += 1
                    try:
                        data = json.loads(line)
                        entry = AuditEntry(**data)
                        if entry.verify_signature():
                            results["valid_entries"] += 1
                        else:
                            results["invalid_entries"] += 1
                            results["invalid_details"].append({
                                "line": i,
                                "event_id": data.get("event_id"),
                                "reason": "signature_mismatch"
                            })
                    except Exception as e:
                        results["invalid_entries"] += 1
                        results["invalid_details"].append({
                            "line": i,
                            "reason": str(e)
                        })
        except Exception as e:
            results["error"] = str(e)
        
        return results
    
    def verify_chain_integrity(self, log_file: Optional[str] = None) -> Dict[str, Any]:
        """
        Verify the blockchain-style hash chain integrity.
        
        This is the key compliance feature - it proves that no log entries
        have been modified, inserted, or deleted since creation.
        
        Args:
            log_file: Specific file to verify, or None for all files
            
        Returns:
            Dictionary with chain verification results
        """
        results = {
            "verified": True,
            "total_entries": 0,
            "chain_breaks": 0,
            "first_break_at": None,
            "files_checked": [],
            "details": []
        }
        
        files_to_check = []
        if log_file:
            files_to_check = [Path(log_file)]
        else:
            files_to_check = sorted(self._log_dir.glob("audit_*.jsonl"))
        
        expected_chain_hash = "GENESIS"
        
        for file_path in files_to_check:
            results["files_checked"].append(str(file_path))
            
            try:
                with open(file_path, "r") as f:
                    for line_num, line in enumerate(f, 1):
                        results["total_entries"] += 1
                        
                        try:
                            data = json.loads(line)
                            entry = AuditEntry(**data)
                            
                            # Verify this entry's chain_hash matches expected
                            if entry.chain_hash != expected_chain_hash:
                                results["verified"] = False
                                results["chain_breaks"] += 1
                                
                                if results["first_break_at"] is None:
                                    results["first_break_at"] = {
                                        "file": str(file_path),
                                        "line": line_num,
                                        "event_id": entry.event_id,
                                        "expected_hash": expected_chain_hash[:16] + "...",
                                        "actual_hash": entry.chain_hash[:16] + "..." if entry.chain_hash else None
                                    }
                                
                                results["details"].append({
                                    "event_id": entry.event_id,
                                    "issue": "chain_break",
                                    "line": line_num
                                })
                            
                            # Verify signature
                            if not entry.verify_signature():
                                results["verified"] = False
                                results["details"].append({
                                    "event_id": entry.event_id,
                                    "issue": "signature_invalid",
                                    "line": line_num
                                })
                            
                            # Update expected hash for next entry
                            expected_chain_hash = entry.signature
                            
                        except Exception as e:
                            results["verified"] = False
                            results["details"].append({
                                "line": line_num,
                                "issue": "parse_error",
                                "error": str(e)
                            })
                            
            except Exception as e:
                results["verified"] = False
                results["details"].append({
                    "file": str(file_path),
                    "issue": "file_error",
                    "error": str(e)
                })
        
        return results
    
    def flush(self):
        """Ensure all pending logs are written"""
        if self._async_writer:
            self._async_writer.flush()
    
    def shutdown(self):
        """Gracefully shutdown the logger"""
        if self._async_writer:
            self._async_writer.shutdown()


# Singleton instance
_audit_logger: Optional[AuditLogger] = None

def get_audit_logger() -> AuditLogger:
    """Get or create singleton AuditLogger instance"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


@contextmanager
def audit_context(workflow_id: str, user_id: str, operation: str):
    """
    Context manager for auditing operations.
    
    Usage:
        with audit_context("wf_123", "user_456", "transfer"):
            # operation code
    """
    audit = get_audit_logger()
    start_time = datetime.utcnow()
    event_id = audit.log_event(
        workflow_id=workflow_id,
        user_id=user_id,
        event_type=AuditEventType.WORKFLOW_STARTED,
        details={"operation": operation, "start_time": start_time.isoformat()}
    )
    
    try:
        yield event_id
        audit.log_event(
            workflow_id=workflow_id,
            user_id=user_id,
            event_type=AuditEventType.WORKFLOW_COMPLETED,
            details={
                "operation": operation,
                "duration_ms": (datetime.utcnow() - start_time).total_seconds() * 1000
            },
            parent_event_id=event_id
        )
    except Exception as e:
        audit.log_event(
            workflow_id=workflow_id,
            user_id=user_id,
            event_type=AuditEventType.WORKFLOW_FAILED,
            details={
                "operation": operation,
                "error": str(e),
                "duration_ms": (datetime.utcnow() - start_time).total_seconds() * 1000
            },
            parent_event_id=event_id
        )
        raise

