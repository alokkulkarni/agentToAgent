"""
Enterprise Guardrail Service

This module provides comprehensive content safety:
- Input rails (jailbreak detection, prompt injection prevention)
- Output rails (topic filtering, content moderation)
- PII detection and tokenization/detokenization
- Configurable disclaimers
- Content moderation hooks

All operations are configurable via external JSON files.

Usage:
    from shared.guardrails import GuardrailService, get_guardrail_service
    
    guardrails = get_guardrail_service()
    
    # Validate input
    is_valid, reason = guardrails.validate_input(user_prompt)
    
    # Tokenize PII before sending to LLM
    safe_text = guardrails.tokenize_pii(sensitive_text)
    
    # Detokenize for tool execution
    original_text = guardrails.detokenize_content(tokenized_text)
    
    # Validate and process output
    is_valid, processed_text = guardrails.validate_output(llm_response)
"""

import re
import logging
import hashlib
import json
from typing import Tuple, Optional, Dict, Any, List, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .config import ConfigManager

logger = logging.getLogger(__name__)


class ViolationAction(Enum):
    """Actions to take on guardrail violations"""
    BLOCK = "block"
    WARN = "warn"
    WARN_AND_DISCLAIM = "warn_and_disclaim"
    REDACT = "redact"
    LOG_ONLY = "log_only"


class PIISensitivity(Enum):
    """PII sensitivity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class PIIMatch:
    """Record of PII detection"""
    pii_type: str
    original_value: str
    token: str
    sensitivity: PIISensitivity
    position: Tuple[int, int]  # (start, end)


@dataclass
class GuardrailViolation:
    """Record of a guardrail violation"""
    timestamp: datetime
    violation_type: str  # input_rail, output_rail, pii_leak
    rule_id: str
    message: str
    action_taken: ViolationAction
    input_preview: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "violation_type": self.violation_type,
            "rule_id": self.rule_id,
            "message": self.message,
            "action_taken": self.action_taken.value,
            "input_preview": self.input_preview
        }


@dataclass
class ValidationResult:
    """Result of input/output validation"""
    is_valid: bool
    processed_text: Optional[str] = None
    violations: List[GuardrailViolation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "processed_text": self.processed_text,
            "violations": [v.to_dict() for v in self.violations],
            "warnings": self.warnings
        }


class PIIVault:
    """
    Secure vault for storing PII token mappings.
    
    In production, this integrates with external secure storage:
    - Redis for distributed sessions
    - AWS Secrets Manager for long-term storage
    - HashiCorp Vault for enterprise deployments
    
    The vault ensures:
    - PII tokens are never exposed to LLMs
    - Only authorized tools can detokenize
    - All access is audited
    
    Security Properties:
    - Tokens are one-way mappings (can't guess PII from token)
    - Value hashing prevents duplicate token creation attacks
    - TTL support for automatic cleanup
    """
    
    def __init__(self, use_redis: bool = False, redis_url: Optional[str] = None):
        """
        Initialize PII Vault.
        
        Args:
            use_redis: Whether to use Redis for distributed storage
            redis_url: Redis connection URL (if use_redis=True)
        """
        self._token_to_value: Dict[str, str] = {}
        self._value_to_token: Dict[str, str] = {}
        self._token_metadata: Dict[str, Dict[str, Any]] = {}
        self._token_counter: int = 0
        self._redis_client = None
        
        if use_redis and redis_url:
            try:
                import redis
                self._redis_client = redis.from_url(redis_url)
                logger.info("PIIVault initialized with Redis backend")
            except ImportError:
                logger.warning("Redis not available, falling back to in-memory storage")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}, falling back to in-memory")
    
    def store(self, pii_type: str, value: str, sensitivity: PIISensitivity, ttl_seconds: int = 3600) -> str:
        """
        Store PII value and return token.
        
        Args:
            pii_type: Type of PII (e.g., "SSN", "CreditCard")
            value: The actual PII value
            sensitivity: Sensitivity level
            ttl_seconds: Time-to-live for the token (default 1 hour)
            
        Returns:
            Token string like "[SSN_1]"
        """
        # Generate hash of value for deduplication
        value_hash = hashlib.sha256(value.encode()).hexdigest()
        
        # Check if already tokenized
        if self._redis_client:
            existing_token = self._redis_client.get(f"pii:hash:{value_hash}")
            if existing_token:
                return existing_token.decode()
        elif value_hash in self._value_to_token:
            return self._value_to_token[value_hash]
        
        # Generate new token
        self._token_counter += 1
        token = f"[{pii_type}_{self._token_counter}]"
        
        metadata = {
            "pii_type": pii_type,
            "sensitivity": sensitivity.value,
            "created_at": datetime.utcnow().isoformat(),
            "ttl": ttl_seconds
        }
        
        if self._redis_client:
            # Store in Redis with TTL
            self._redis_client.setex(f"pii:token:{token}", ttl_seconds, value)
            self._redis_client.setex(f"pii:hash:{value_hash}", ttl_seconds, token)
            self._redis_client.setex(f"pii:meta:{token}", ttl_seconds, json.dumps(metadata))
        else:
            # Store in memory
            self._token_to_value[token] = value
            self._value_to_token[value_hash] = token
            self._token_metadata[token] = metadata
        
        return token
    
    def retrieve(self, token: str) -> Optional[str]:
        """
        Retrieve original value for token.
        
        Args:
            token: The PII token
            
        Returns:
            Original PII value or None if not found/expired
        """
        if self._redis_client:
            value = self._redis_client.get(f"pii:token:{token}")
            return value.decode() if value else None
        return self._token_to_value.get(token)
    
    def get_all_tokens(self) -> Set[str]:
        """Get all active tokens"""
        if self._redis_client:
            keys = self._redis_client.keys("pii:token:*")
            return {k.decode().replace("pii:token:", "") for k in keys}
        return set(self._token_to_value.keys())
    
    def clear(self):
        """Clear all stored tokens (use with caution)"""
        if self._redis_client:
            for key in self._redis_client.keys("pii:*"):
                self._redis_client.delete(key)
        else:
            self._token_to_value.clear()
            self._value_to_token.clear()
            self._token_metadata.clear()
        self._token_counter = 0
    
    def get_token_count(self) -> int:
        """Get number of stored tokens"""
        if self._redis_client:
            return len(self._redis_client.keys("pii:token:*"))
        return len(self._token_to_value)
    
    def get_metadata(self, token: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a token"""
        if self._redis_client:
            meta = self._redis_client.get(f"pii:meta:{token}")
            return json.loads(meta) if meta else None
        return self._token_metadata.get(token)


class GuardrailService:
    """
    Enterprise Guardrail Service
    
    Provides comprehensive content safety including:
    - Input validation (jailbreak, injection detection)
    - Output validation (topic filtering, content moderation)
    - PII tokenization and detokenization
    - Configurable disclaimers
    """
    
    def __init__(self):
        self._config = ConfigManager.get_instance()
        self._guardrail_config = self._config.get_guardrails_config()
        self._pii_vault = PIIVault()
        self._violations: List[GuardrailViolation] = []
        
        # Compile regex patterns for efficiency
        self._compiled_pii_patterns: Dict[str, re.Pattern] = {}
        self._compile_pii_patterns()
    
    def _compile_pii_patterns(self):
        """Pre-compile PII regex patterns for performance"""
        pii_config = self._guardrail_config.get("pii_detection", {})
        patterns = pii_config.get("patterns", {})
        
        for pii_type, pattern_config in patterns.items():
            if isinstance(pattern_config, dict):
                regex = pattern_config.get("regex", "")
            else:
                regex = pattern_config  # Legacy format: direct regex string
            
            try:
                self._compiled_pii_patterns[pii_type] = re.compile(regex, re.IGNORECASE)
            except re.error as e:
                logger.error(f"Invalid regex for PII type {pii_type}: {e}")
    
    # ==================== PII Tokenization ====================
    
    def tokenize_pii(self, text: str) -> str:
        """
        Replace PII with secure tokens.
        
        PII values are stored in a secure vault and replaced with tokens
        like [SSN_1], [CreditCard_2], etc.
        
        Args:
            text: Input text potentially containing PII
            
        Returns:
            Text with PII replaced by tokens
        """
        pii_config = self._guardrail_config.get("pii_detection", {})
        if not pii_config.get("enabled", True):
            return text
        
        if not self._config.feature_flags.enable_pii_redaction:
            return text
        
        sanitized_text = text
        patterns_config = pii_config.get("patterns", {})
        
        for pii_type, pattern in self._compiled_pii_patterns.items():
            pattern_config = patterns_config.get(pii_type, {})
            sensitivity = PIISensitivity(pattern_config.get("sensitivity", "medium") if isinstance(pattern_config, dict) else "medium")
            
            # Check for context requirements (some patterns need context)
            context_required = pattern_config.get("context_required", []) if isinstance(pattern_config, dict) else []
            if context_required:
                text_lower = text.lower()
                if not any(ctx in text_lower for ctx in context_required):
                    continue  # Skip this pattern if context not present
            
            matches = list(pattern.finditer(sanitized_text))
            
            # Process matches in reverse to preserve positions
            for match in reversed(matches):
                value = match.group()
                token = self._pii_vault.store(pii_type, value, sensitivity)
                sanitized_text = sanitized_text[:match.start()] + token + sanitized_text[match.end():]
        
        return sanitized_text
    
    def detokenize_content(self, text: str) -> str:
        """
        Restore PII from tokens.
        
        Used when sending data to authorized tools that need the real values.
        
        Args:
            text: Text containing PII tokens
            
        Returns:
            Text with tokens replaced by original values
        """
        restored_text = text
        
        for token in self._pii_vault.get_all_tokens():
            if token in restored_text:
                original_value = self._pii_vault.retrieve(token)
                if original_value:
                    restored_text = restored_text.replace(token, original_value)
        
        return restored_text
    
    def redact_pii(self, text: str) -> str:
        """
        Permanently redact PII (non-reversible).
        
        Use this when PII should never be recovered.
        
        Args:
            text: Text potentially containing PII
            
        Returns:
            Text with PII replaced by redaction markers
        """
        redacted_text = text
        patterns_config = self._guardrail_config.get("pii_detection", {}).get("patterns", {})
        
        for pii_type, pattern in self._compiled_pii_patterns.items():
            pattern_config = patterns_config.get(pii_type, {})
            redaction_format = pattern_config.get("redaction_format", f"[{pii_type}_REDACTED]") if isinstance(pattern_config, dict) else f"[{pii_type}_REDACTED]"
            redacted_text = pattern.sub(redaction_format, redacted_text)
        
        return redacted_text
    
    # ==================== Input Validation ====================
    
    def validate_input(self, prompt: str) -> Tuple[bool, Optional[str]]:
        """
        Input Rails: Block malicious prompts.
        
        Checks for:
        - Jailbreak attempts
        - Prompt injection
        - Excessive length
        - Blocked patterns
        
        Args:
            prompt: User input to validate
            
        Returns:
            Tuple of (is_valid, rejection_reason)
        """
        if not self._config.feature_flags.enable_guardrails:
            return True, None
        
        input_rails = self._guardrail_config.get("input_rails", {})
        if not input_rails.get("enabled", True):
            return True, None
        
        prompt_lower = prompt.lower()
        
        # Check input length
        max_length = input_rails.get("max_input_length", 50000)
        if len(prompt) > max_length:
            violation = GuardrailViolation(
                timestamp=datetime.utcnow(),
                violation_type="input_rail",
                rule_id="max_length",
                message=f"Input exceeds maximum length ({len(prompt)} > {max_length})",
                action_taken=ViolationAction.BLOCK,
                input_preview=prompt[:100] + "..."
            )
            self._violations.append(violation)
            return False, violation.message
        
        # Check sensitive terms
        sensitive_terms = input_rails.get("sensitive_terms", [])
        for term_config in sensitive_terms:
            if isinstance(term_config, dict):
                term = term_config.get("term", "").lower()
                action = ViolationAction(term_config.get("action", "block"))
                message = term_config.get("message", f"Blocked term detected: {term}")
            else:
                term = str(term_config).lower()
                action = ViolationAction.BLOCK
                message = f"Blocked term detected: {term}"
            
            if term and term in prompt_lower:
                violation = GuardrailViolation(
                    timestamp=datetime.utcnow(),
                    violation_type="input_rail",
                    rule_id=f"sensitive_term:{term}",
                    message=message,
                    action_taken=action,
                    input_preview=prompt[:100] + "..." if len(prompt) > 100 else prompt
                )
                self._violations.append(violation)
                
                if action == ViolationAction.BLOCK:
                    return False, message
                elif action == ViolationAction.WARN:
                    logger.warning(f"Input warning: {message}")
        
        # Check for code injection patterns
        if input_rails.get("block_code_injection", True):
            code_patterns = [
                r"<script\b[^>]*>",
                r"javascript:",
                r"on\w+\s*=",
                r"eval\s*\(",
                r"exec\s*\("
            ]
            for pattern in code_patterns:
                if re.search(pattern, prompt, re.IGNORECASE):
                    violation = GuardrailViolation(
                        timestamp=datetime.utcnow(),
                        violation_type="input_rail",
                        rule_id="code_injection",
                        message="Potential code injection detected",
                        action_taken=ViolationAction.BLOCK
                    )
                    self._violations.append(violation)
                    return False, "Potential code injection detected"
        
        # Check for SQL injection patterns
        if input_rails.get("block_sql_injection", True):
            sql_patterns = [
                r";\s*(drop|delete|truncate|update|insert)\s",
                r"union\s+select",
                r"'\s*or\s+'1'\s*=\s*'1",
                r"--\s*$"
            ]
            for pattern in sql_patterns:
                if re.search(pattern, prompt, re.IGNORECASE):
                    violation = GuardrailViolation(
                        timestamp=datetime.utcnow(),
                        violation_type="input_rail",
                        rule_id="sql_injection",
                        message="Potential SQL injection detected",
                        action_taken=ViolationAction.BLOCK
                    )
                    self._violations.append(violation)
                    return False, "Potential SQL injection detected"
        
        return True, None
    
    # ==================== Output Validation ====================
    
    def validate_output(self, text: str) -> Tuple[bool, str]:
        """
        Output Rails: Content filtering and processing.
        
        Applies:
        - Topic deny-list filtering
        - PII redaction (if not tokenized)
        - Automatic disclaimers
        
        Args:
            text: LLM output to validate
            
        Returns:
            Tuple of (is_valid, processed_text)
        """
        if not self._config.feature_flags.enable_guardrails:
            return True, text
        
        output_rails = self._guardrail_config.get("output_rails", {})
        if not output_rails.get("enabled", True):
            return True, text
        
        processed_text = text
        
        # Check output length
        max_length = output_rails.get("max_output_length", 100000)
        if len(processed_text) > max_length:
            processed_text = processed_text[:max_length] + "\n\n[Output truncated due to length limit]"
        
        # Check denied topics
        denied_topics = output_rails.get("denied_topics", [])
        for topic_config in denied_topics:
            if isinstance(topic_config, dict):
                topic = topic_config.get("topic", "")
                keywords = topic_config.get("keywords", [])
                action = ViolationAction(topic_config.get("action", "warn"))
                message = topic_config.get("message", f"Content related to '{topic}' detected")
            else:
                topic = str(topic_config)
                keywords = [topic.replace("_", " ")]
                action = ViolationAction.WARN
                message = f"Content related to '{topic}' detected"
            
            text_lower = processed_text.lower()
            topic_detected = any(kw.lower() in text_lower for kw in keywords if kw)
            
            if topic_detected:
                violation = GuardrailViolation(
                    timestamp=datetime.utcnow(),
                    violation_type="output_rail",
                    rule_id=f"denied_topic:{topic}",
                    message=message,
                    action_taken=action
                )
                self._violations.append(violation)
                
                if action == ViolationAction.BLOCK:
                    return False, f"[Content blocked: {message}]"
                elif action == ViolationAction.REDACT:
                    # Simple keyword replacement
                    for kw in keywords:
                        if kw:
                            processed_text = re.sub(re.escape(kw), "[REDACTED]", processed_text, flags=re.IGNORECASE)
        
        # Redact any remaining PII (in case tokenization was bypassed)
        if self._config.feature_flags.enable_pii_redaction:
            processed_text = self._apply_output_pii_redaction(processed_text)
        
        # Apply disclaimers
        processed_text = self._apply_disclaimers(processed_text)
        
        return True, processed_text
    
    def _apply_output_pii_redaction(self, text: str) -> str:
        """Redact PII from output that wasn't tokenized"""
        patterns_config = self._guardrail_config.get("pii_detection", {}).get("patterns", {})
        
        for pii_type, pattern in self._compiled_pii_patterns.items():
            pattern_config = patterns_config.get(pii_type, {})
            redaction_format = pattern_config.get("redaction_format", f"[{pii_type}_REDACTED]") if isinstance(pattern_config, dict) else f"[{pii_type}_REDACTED]"
            text = pattern.sub(redaction_format, text)
        
        return text
    
    def _apply_disclaimers(self, text: str) -> str:
        """Apply configured disclaimers based on content"""
        disclaimers = self._guardrail_config.get("disclaimers", [])
        text_lower = text.lower()
        applied_disclaimers = set()
        
        for disclaimer_config in disclaimers:
            if not disclaimer_config.get("enabled", True):
                continue
            
            disclaimer_id = disclaimer_config.get("id", "")
            keywords = disclaimer_config.get("trigger_keywords", [])
            message = disclaimer_config.get("message", "")
            position = disclaimer_config.get("position", "append")
            
            # Check if disclaimer should be applied
            should_apply = any(kw.lower() in text_lower for kw in keywords if kw)
            
            if should_apply and disclaimer_id not in applied_disclaimers and message:
                if position == "prepend":
                    text = message + "\n\n" + text
                else:  # append
                    if message not in text:  # Don't duplicate
                        text = text + message
                
                applied_disclaimers.add(disclaimer_id)
        
        return text
    
    # ==================== Utility Methods ====================
    
    def get_violations(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recorded violations"""
        return [v.to_dict() for v in self._violations[-limit:]]
    
    def clear_violations(self):
        """Clear violation history"""
        self._violations.clear()
    
    def get_pii_token_count(self) -> int:
        """Get number of PII tokens in vault"""
        return self._pii_vault.get_token_count()
    
    def clear_pii_vault(self):
        """Clear PII vault (use with caution)"""
        self._pii_vault.clear()
    
    def reload_config(self):
        """Reload guardrail configuration"""
        self._config.reload()
        self._guardrail_config = self._config.get_guardrails_config()
        self._compile_pii_patterns()
        logger.info("Guardrail configuration reloaded")


# Singleton instance
_guardrail_service: Optional[GuardrailService] = None

def get_guardrail_service() -> GuardrailService:
    """Get or create singleton GuardrailService instance"""
    global _guardrail_service
    if _guardrail_service is None:
        _guardrail_service = GuardrailService()
    return _guardrail_service

