"""
Shared Library - Enterprise Agent Framework

This package provides enterprise-ready utilities for the Agent-to-Agent framework:
- Configuration management
- Security and authorization
- Guardrails (PII, content filtering)
- Audit logging (WORM compliance)
- Safe LLM client
- Agent interaction helpers

Usage:
    from shared import (
        ConfigManager,
        get_security_manager,
        get_guardrail_service,
        get_audit_logger,
        SafeLLMClient,
        AuditEventType
    )
"""

from .config import ConfigManager, EnterpriseConfig
from .security import SecurityManager, get_security_manager, UserContext, AuthorizationResult
from .guardrails import GuardrailService, get_guardrail_service, ValidationResult
from .audit import AuditLogger, get_audit_logger, AuditEventType, audit_context
from .llm_client import SafeLLMClient
from .agent_interaction import AgentInteractionHelper, is_interaction_request

__all__ = [
    # Configuration
    "ConfigManager",
    "EnterpriseConfig",  # Legacy compatibility
    
    # Security
    "SecurityManager",
    "get_security_manager",
    "UserContext",
    "AuthorizationResult",
    
    # Guardrails
    "GuardrailService", 
    "get_guardrail_service",
    "ValidationResult",
    
    # Audit
    "AuditLogger",
    "get_audit_logger",
    "AuditEventType",
    "audit_context",
    
    # LLM
    "SafeLLMClient",
    
    # Agent Interaction
    "AgentInteractionHelper",
    "is_interaction_request",
]

__version__ = "1.0.0"
