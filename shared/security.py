"""
Enterprise Security Manager

This module provides:
- Identity propagation (OBO - On-Behalf-Of flow)
- Tool authorization with deterministic validation
- Role-based access control (RBAC)
- Rate limiting enforcement
- Security policy evaluation

All security checks are performed independent of LLM outputs.

Usage:
    from shared.security import SecurityManager
    
    security = SecurityManager()
    
    # Validate tool authorization
    if security.validate_tool_authorization(user_role="user", tool_name="transfer_funds", parameters={"amount": 500}):
        # proceed
    
    # Get user context from headers
    user_ctx = security.get_user_context(request.headers)
"""

import logging
import time
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import hashlib

from .config import ConfigManager

logger = logging.getLogger(__name__)


@dataclass
class UserContext:
    """User identity context for OBO flow"""
    user_id: str
    role: str
    session_id: Optional[str] = None
    tenant_id: Optional[str] = None
    permissions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    authenticated_at: Optional[datetime] = None
    
    def has_permission(self, permission: str) -> bool:
        """Check if user has specific permission"""
        return permission in self.permissions or "*" in self.permissions
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "user_id": self.user_id,
            "role": self.role,
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "permissions": self.permissions,
            "authenticated_at": self.authenticated_at.isoformat() if self.authenticated_at else None
        }


@dataclass
class SecurityViolation:
    """Record of a security violation"""
    timestamp: datetime
    user_id: str
    tool_name: str
    violation_type: str
    details: Dict[str, Any]
    severity: str = "medium"  # low, medium, high, critical
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user_id,
            "tool_name": self.tool_name,
            "violation_type": self.violation_type,
            "details": self.details,
            "severity": self.severity
        }


@dataclass
class AuthorizationResult:
    """Result of authorization check"""
    authorized: bool
    reason: Optional[str] = None
    requires_approval: bool = False
    approval_id: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "authorized": self.authorized,
            "reason": self.reason,
            "requires_approval": self.requires_approval,
            "approval_id": self.approval_id,
            "warnings": self.warnings
        }


class RateLimiter:
    """Token bucket rate limiter for tool calls"""
    
    def __init__(self, max_calls: int, window_seconds: int):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._calls: Dict[str, List[float]] = defaultdict(list)
    
    def is_allowed(self, key: str) -> Tuple[bool, Optional[str]]:
        """Check if request is allowed under rate limit"""
        now = time.time()
        window_start = now - self.window_seconds
        
        # Clean old entries
        self._calls[key] = [t for t in self._calls[key] if t > window_start]
        
        if len(self._calls[key]) >= self.max_calls:
            return False, f"Rate limit exceeded: {self.max_calls} calls per {self.window_seconds}s"
        
        self._calls[key].append(now)
        return True, None
    
    def get_remaining(self, key: str) -> int:
        """Get remaining calls in current window"""
        now = time.time()
        window_start = now - self.window_seconds
        self._calls[key] = [t for t in self._calls[key] if t > window_start]
        return max(0, self.max_calls - len(self._calls[key]))


class SecurityManager:
    """
    Enterprise Security Manager
    
    Handles Identity Propagation and Tool Authorization (Deterministic Layer).
    All security decisions are made independent of LLM outputs.
    """
    
    def __init__(self):
        self._config = ConfigManager.get_instance()
        self._violations: List[SecurityViolation] = []
        self._rate_limiters: Dict[str, RateLimiter] = {}
        self._user_violation_counts: Dict[str, int] = defaultdict(int)
        self._blocked_users: Dict[str, datetime] = {}
        
        # Initialize rate limiters from config
        self._init_rate_limiters()
    
    def _init_rate_limiters(self):
        """Initialize rate limiters for tools that have rate limit config"""
        policies = self._config.get_security_policies().get("tool_policies", {})
        
        for tool_name, policy in policies.items():
            rate_limit = policy.get("rate_limit", {})
            if rate_limit:
                max_calls = rate_limit.get("max_calls_per_hour", 100)
                # Convert to per-minute for finer granularity
                max_per_minute = rate_limit.get("max_calls_per_minute", max_calls // 60 or 1)
                self._rate_limiters[tool_name] = RateLimiter(max_per_minute, 60)
    
    def get_user_context(self, headers: Dict[str, Any]) -> UserContext:
        """
        Extract user identity for OBO (On-Behalf-Of) flow.
        
        Headers expected:
        - X-User-ID: Unique user identifier
        - X-User-Role: User's role (admin, operator, user, guest)
        - X-Session-ID: Current session ID
        - X-Tenant-ID: Multi-tenant ID (optional)
        - X-Auth-Token: Authentication token (validated elsewhere)
        
        Args:
            headers: HTTP headers dictionary
            
        Returns:
            UserContext with extracted identity information
        """
        user_id = headers.get("X-User-ID") or headers.get("x-user-id", "anonymous")
        role = headers.get("X-User-Role") or headers.get("x-user-role", "guest")
        session_id = headers.get("X-Session-ID") or headers.get("x-session-id")
        tenant_id = headers.get("X-Tenant-ID") or headers.get("x-tenant-id")
        
        # Get role permissions from config
        role_perms = self._config.get_role_permissions(role)
        allowed_tools = role_perms.get("allowed_tools", [])
        
        return UserContext(
            user_id=user_id,
            role=role,
            session_id=session_id,
            tenant_id=tenant_id,
            permissions=allowed_tools,
            authenticated_at=datetime.utcnow() if user_id != "anonymous" else None,
            metadata={
                "can_bypass_approval": role_perms.get("can_bypass_approval", False),
                "can_access_pii": role_perms.get("can_access_pii", False),
                "max_transaction_limit": role_perms.get("max_transaction_limit", 0)
            }
        )
    
    def validate_tool_authorization(
        self, 
        user_role: str, 
        tool_name: str, 
        parameters: Dict[str, Any],
        user_id: str = "anonymous"
    ) -> AuthorizationResult:
        """
        Deterministic code layer to validate limits independent of LLM.
        Validates against externalized security policies and registry metadata.
        
        Args:
            user_role: User's role (admin, operator, user, guest)
            tool_name: Name of the tool being invoked
            parameters: Parameters being passed to the tool
            user_id: User identifier for rate limiting and tracking
            
        Returns:
            AuthorizationResult with authorization decision and details
        """
        if not self._config.feature_flags.enable_security_checks:
            return AuthorizationResult(authorized=True, reason="Security checks disabled")
        
        warnings = []
        
        # Check if user is blocked
        if user_id in self._blocked_users:
            block_until = self._blocked_users[user_id]
            if datetime.utcnow() < block_until:
                return AuthorizationResult(
                    authorized=False,
                    reason=f"User blocked until {block_until.isoformat()} due to security violations"
                )
            else:
                del self._blocked_users[user_id]
                self._user_violation_counts[user_id] = 0
        
        # Get role permissions
        role_perms = self._config.get_role_permissions(user_role)
        allowed_tools = role_perms.get("allowed_tools", [])
        
        # Check tool permission
        if "*" not in allowed_tools and tool_name not in allowed_tools:
            self._record_violation(user_id, tool_name, "unauthorized_tool", 
                                   {"role": user_role, "tool": tool_name}, "high")
            return AuthorizationResult(
                authorized=False,
                reason=f"Role '{user_role}' is not authorized to use tool '{tool_name}'"
            )
        
        # Get tool policy
        tool_policy = self._config.get_tool_policy(tool_name)
        
        # Check tool-specific limits
        limits = tool_policy.get("limits", {})
        for param_name, limit_config in limits.items():
            if param_name in parameters:
                value = parameters[param_name]
                
                if isinstance(limit_config, dict):
                    # Complex limit configuration
                    limit_type = limit_config.get("type", "numeric")
                    
                    if limit_type == "numeric" and isinstance(value, (int, float)):
                        max_val = limit_config.get("max")
                        min_val = limit_config.get("min")
                        
                        if max_val is not None and float(value) > float(max_val):
                            self._record_violation(user_id, tool_name, "limit_exceeded",
                                                   {"param": param_name, "value": value, "max": max_val}, "medium")
                            return AuthorizationResult(
                                authorized=False,
                                reason=f"Parameter '{param_name}' value {value} exceeds maximum {max_val}"
                            )
                        
                        if min_val is not None and float(value) < float(min_val):
                            self._record_violation(user_id, tool_name, "limit_exceeded",
                                                   {"param": param_name, "value": value, "min": min_val}, "medium")
                            return AuthorizationResult(
                                authorized=False,
                                reason=f"Parameter '{param_name}' value {value} below minimum {min_val}"
                            )
                    
                    elif limit_type == "string_length" and isinstance(value, str):
                        max_len = limit_config.get("max", 10000)
                        if len(value) > max_len:
                            return AuthorizationResult(
                                authorized=False,
                                reason=f"Parameter '{param_name}' length {len(value)} exceeds maximum {max_len}"
                            )
                
                elif isinstance(limit_config, (int, float)) and isinstance(value, (int, float)):
                    # Simple numeric limit (legacy format)
                    if float(value) > float(limit_config):
                        self._record_violation(user_id, tool_name, "limit_exceeded",
                                               {"param": param_name, "value": value, "max": limit_config}, "medium")
                        return AuthorizationResult(
                            authorized=False,
                            reason=f"Parameter '{param_name}' value {value} exceeds limit {limit_config}"
                        )
        
        # Check role-specific transaction limit
        role_max_limit = role_perms.get("max_transaction_limit", float('inf'))
        for param_name in ["amount", "value", "total"]:
            if param_name in parameters:
                value = parameters[param_name]
                if isinstance(value, (int, float)) and float(value) > role_max_limit:
                    return AuthorizationResult(
                        authorized=False,
                        reason=f"Transaction amount {value} exceeds role limit {role_max_limit}"
                    )
        
        # Check rate limiting
        if tool_name in self._rate_limiters:
            rate_key = f"{user_id}:{tool_name}"
            allowed, rate_reason = self._rate_limiters[tool_name].is_allowed(rate_key)
            if not allowed:
                return AuthorizationResult(authorized=False, reason=rate_reason)
        
        # Check if approval is required
        requires_approval = tool_policy.get("requires_approval", False)
        can_bypass = role_perms.get("can_bypass_approval", False)
        
        if requires_approval and not can_bypass:
            # Check approval threshold
            approval_threshold = tool_policy.get("approval_threshold", 0)
            for param_name in ["amount", "value", "total"]:
                if param_name in parameters:
                    value = parameters[param_name]
                    if isinstance(value, (int, float)) and float(value) >= approval_threshold:
                        approval_id = self._generate_approval_id(user_id, tool_name, parameters)
                        warnings.append(f"Transaction above {approval_threshold} requires approval")
                        return AuthorizationResult(
                            authorized=True,  # Conditionally authorized pending approval
                            requires_approval=True,
                            approval_id=approval_id,
                            warnings=warnings
                        )
        
        # Log successful authorization at detailed audit level
        audit_level = tool_policy.get("audit_level", "standard")
        if audit_level == "detailed":
            logger.info(f"Tool authorized: {tool_name} for user {user_id} (role: {user_role})")
        
        return AuthorizationResult(authorized=True, warnings=warnings)
    
    def _record_violation(
        self, 
        user_id: str, 
        tool_name: str, 
        violation_type: str, 
        details: Dict[str, Any],
        severity: str = "medium"
    ):
        """Record a security violation"""
        violation = SecurityViolation(
            timestamp=datetime.utcnow(),
            user_id=user_id,
            tool_name=tool_name,
            violation_type=violation_type,
            details=details,
            severity=severity
        )
        self._violations.append(violation)
        self._user_violation_counts[user_id] += 1
        
        # Check if user should be blocked
        guardrails_config = self._config.get_guardrails_config()
        rate_limit_config = guardrails_config.get("rate_limiting", {})
        max_violations = rate_limit_config.get("max_violations_per_session", 5)
        block_duration = rate_limit_config.get("block_duration_minutes", 30)
        
        if self._user_violation_counts[user_id] >= max_violations:
            self._blocked_users[user_id] = datetime.utcnow() + timedelta(minutes=block_duration)
            logger.warning(f"User {user_id} blocked for {block_duration} minutes due to security violations")
    
    def _generate_approval_id(self, user_id: str, tool_name: str, parameters: Dict[str, Any]) -> str:
        """Generate unique approval ID for pending approvals"""
        data = f"{user_id}:{tool_name}:{str(parameters)}:{datetime.utcnow().isoformat()}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def get_violations(self, user_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recorded violations, optionally filtered by user"""
        violations = self._violations
        if user_id:
            violations = [v for v in violations if v.user_id == user_id]
        return [v.to_dict() for v in violations[-limit:]]
    
    def clear_violations(self, user_id: Optional[str] = None):
        """Clear violations (admin function)"""
        if user_id:
            self._violations = [v for v in self._violations if v.user_id != user_id]
            self._user_violation_counts[user_id] = 0
            if user_id in self._blocked_users:
                del self._blocked_users[user_id]
        else:
            self._violations = []
            self._user_violation_counts.clear()
            self._blocked_users.clear()
    
    def is_pii_access_allowed(self, user_role: str) -> bool:
        """Check if role is allowed to access PII data"""
        role_perms = self._config.get_role_permissions(user_role)
        return role_perms.get("can_access_pii", False)
    
    def get_effective_limits(self, user_role: str, tool_name: str) -> Dict[str, Any]:
        """Get effective limits for user/tool combination"""
        role_perms = self._config.get_role_permissions(user_role)
        tool_policy = self._config.get_tool_policy(tool_name)
        
        # Merge role and tool limits (role takes precedence for transaction limits)
        effective = {
            "tool_limits": tool_policy.get("limits", {}),
            "role_transaction_limit": role_perms.get("max_transaction_limit"),
            "requires_approval": tool_policy.get("requires_approval", False),
            "can_bypass_approval": role_perms.get("can_bypass_approval", False)
        }
        
        return effective


# Singleton instance
_security_manager: Optional[SecurityManager] = None

def get_security_manager() -> SecurityManager:
    """Get or create singleton SecurityManager instance"""
    global _security_manager
    if _security_manager is None:
        _security_manager = SecurityManager()
    return _security_manager

