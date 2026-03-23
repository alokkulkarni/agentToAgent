"""
Enterprise Safe LLM Client

This module provides a secure wrapper around AWS Bedrock that enforces:
- Input Guardrails (jailbreak detection, prompt injection prevention)
- PII Tokenization (sensitive data never reaches LLM)
- Output Guardrails (content filtering, topic blocking)
- PII Detokenization for tool calls (real values sent to authorized tools)
- Comprehensive Audit Logging (Chain of Thought capture)

The security flow follows this sequence:
1. User Input -> Tokenize PII -> Validate Input Rails -> Send to LLM
2. LLM Response -> Validate Output Rails -> Detokenize Tool Params -> Return

Usage:
    from shared.llm_client import SafeLLMClient
    
    client = SafeLLMClient()
    
    response = client.converse(
        modelId="anthropic.claude-3-sonnet-20240229-v1:0",
        messages=[{"role": "user", "content": [{"text": "Process account 1234-5678"}]}],
        workflow_id="wf_123",
        user_id="user_456"
    )
    
    # Tool calls in response will have real PII values (detokenized)
    # LLM never saw the real values
"""

import boto3
import json
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from botocore.exceptions import ClientError, ParamValidationError

from .config import ConfigManager
from .guardrails import get_guardrail_service, GuardrailService
from .audit import get_audit_logger, AuditLogger, AuditEventType
from .security import get_security_manager, SecurityManager

logger = logging.getLogger(__name__)


@dataclass
class LLMInvocationMetrics:
    """Metrics for LLM invocation"""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0
    pii_tokens_created: int = 0
    guardrail_checks: int = 0
    cache_hit: bool = False


class SafeLLMClient:
    """
    Enterprise-grade LLM Client with built-in security.
    
    Enforces the security architecture:
    - Guardrails: Input/Output validation
    - PII Vault: Tokenization before LLM, detokenization for tools
    - Audit: Comprehensive logging for compliance
    - Security: Tool authorization checks
    
    Thread-safe and suitable for production use.
    """
    
    def __init__(self, region_name: Optional[str] = None):
        """
        Initialize SafeLLMClient.
        
        Args:
            region_name: AWS region. If None, uses config default.
        """
        self._config = ConfigManager.get_instance()
        self._region = region_name or self._config.llm.region
        
        # Initialize AWS Bedrock client
        self.bedrock = boto3.client("bedrock-runtime", region_name=self._region)
        
        # Get singleton instances of security services
        self.guardrails = get_guardrail_service()
        self.audit = get_audit_logger()
        self.security = get_security_manager()
        
        # Metrics tracking
        self._total_invocations = 0
        self._total_blocked = 0
        
        logger.info(f"SafeLLMClient initialized for region {self._region}")

    def converse(
        self, 
        modelId: str, 
        messages: List[Dict], 
        system: Optional[List[Dict]] = None, 
        toolConfig: Optional[Dict] = None,
        inferenceConfig: Optional[Dict] = None,
        workflow_id: str = "unknown",
        user_id: str = "anonymous",
        user_role: str = "user",
        skip_guardrails: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Secure wrapper around Bedrock converse API.
        
        Security Flow:
        1. Input Processing:
           - Tokenize PII (SSN, CC, etc.) -> stored in vault
           - Validate against input rails (jailbreak, injection)
        2. LLM Invocation:
           - Safe content sent to LLM
           - LLM generates response with tokenized references
        3. Output Processing:
           - Validate against output rails
           - Detokenize tool parameters (real values for tool execution)
        
        Args:
            modelId: Bedrock model ID
            messages: Conversation messages
            system: System prompts (optional)
            toolConfig: Tool configuration for function calling
            inferenceConfig: Inference settings
            workflow_id: Workflow ID for audit trail
            user_id: User ID for audit trail
            user_role: User role for authorization
            skip_guardrails: Skip guardrails (for admin/testing only)
            **kwargs: Additional parameters
            
        Returns:
            Bedrock converse response with detokenized tool inputs
            
        Raises:
            ValueError: If input violates security policy
        """
        start_time = time.time()
        metrics = LLMInvocationMetrics()
        self._total_invocations += 1
        
        model_id = modelId  # Alias for consistency
        
        # ==================== PHASE 1: INPUT PROCESSING ====================
        safe_messages = []
        pii_tokens_before = self.guardrails.get_pii_token_count()
        
        for msg in messages:
            if msg["role"] == "user":
                content_blocks = msg.get("content", [])
                safe_blocks = []
                
                for block in content_blocks:
                    if "text" in block:
                        text = block["text"]
                        
                        # A. PII Tokenization (unless skipped)
                        if not skip_guardrails and self._config.feature_flags.enable_pii_redaction:
                            tokenized_text = self.guardrails.tokenize_pii(text)
                        else:
                            tokenized_text = text
                        
                        # B. Input Rails Validation
                        if not skip_guardrails and self._config.feature_flags.enable_guardrails:
                            is_valid, reason = self.guardrails.validate_input(tokenized_text)
                            metrics.guardrail_checks += 1
                            
                            if not is_valid:
                                self._total_blocked += 1
                                
                                # Log the violation
                                self.audit.log_event(
                                    workflow_id=workflow_id,
                                    user_id=user_id,
                                    event_type=AuditEventType.GUARDRAIL_VIOLATION,
                                    details={
                                        "stage": "input",
                                        "reason": reason,
                                        "text_preview": text[:100] if len(text) > 100 else text
                                    }
                                )
                                raise ValueError(f"Security Policy Violation: {reason}")
                        
                        safe_blocks.append({"text": tokenized_text})
                    else:
                        safe_blocks.append(block)
                        
                safe_messages.append({"role": "user", "content": safe_blocks})
            else:
                safe_messages.append(msg)
        
        metrics.pii_tokens_created = self.guardrails.get_pii_token_count() - pii_tokens_before
        
        # Log LLM invocation start (Chain of Thought - Thought phase)
        invocation_event_id = self.audit.log_event(
            workflow_id=workflow_id,
            user_id=user_id,
            event_type=AuditEventType.LLM_INVOCATION,
            details={
                "model_id": model_id,
                "message_count": len(safe_messages),
                "pii_tokens_created": metrics.pii_tokens_created,
                "has_tools": toolConfig is not None
            }
        )

        # ==================== PHASE 2: LLM INVOCATION ====================
        try:
            invoke_kwargs = {
                "modelId": model_id,
                "messages": safe_messages
            }
            
            if system:
                invoke_kwargs["system"] = system
            if toolConfig:
                invoke_kwargs["toolConfig"] = toolConfig
            if inferenceConfig:
                invoke_kwargs["inferenceConfig"] = inferenceConfig

            response = self.bedrock.converse(**invoke_kwargs)
            
        except (ClientError, ParamValidationError) as e:
            # Fallback: Remove cachePoint if not supported
            if system and any('cachePoint' in str(s) for s in system):
                clean_system = []
                for s in system:
                    if isinstance(s, dict):
                        clean_system.append({k: v for k, v in s.items() if k != 'cachePoint'})
                    else:
                        clean_system.append(s)
                invoke_kwargs["system"] = clean_system
                response = self.bedrock.converse(**invoke_kwargs)
            else:
                # Log error and re-raise
                self.audit.log_event(
                    workflow_id=workflow_id,
                    user_id=user_id,
                    event_type=AuditEventType.SYSTEM_ERROR,
                    details={"error": str(e), "model_id": model_id}
                )
                raise

        # ==================== PHASE 3: OUTPUT PROCESSING ====================
        output_message = response.get("output", {}).get("message", {})
        content_blocks = output_message.get("content", [])
        
        # Track token usage
        usage = response.get("usage", {})
        metrics.input_tokens = usage.get("inputTokens", 0)
        metrics.output_tokens = usage.get("outputTokens", 0)
        
        for block in content_blocks:
            # A. Output Rails for Text
            if "text" in block:
                if not skip_guardrails and self._config.feature_flags.enable_guardrails:
                    is_valid, sanitized_text = self.guardrails.validate_output(block["text"])
                    metrics.guardrail_checks += 1
                    
                    if not is_valid:
                        block["text"] = "[Content Blocked by Security Policy]"
                        self.audit.log_event(
                            workflow_id=workflow_id,
                            user_id=user_id,
                            event_type=AuditEventType.GUARDRAIL_VIOLATION,
                            details={"stage": "output", "reason": "content_policy"}
                        )
                    else:
                        block["text"] = sanitized_text
            
            # B. Detokenize Tool Parameters (THE CORE SECURITY REQUIREMENT)
            # Real PII values are passed to tools, but LLM never saw them
            if "toolUse" in block:
                tool_use = block["toolUse"]
                tool_name = tool_use.get("name", "unknown")
                tool_input = tool_use.get("input", {})
                
                # Check tool authorization before detokenization
                if self._config.feature_flags.enable_security_checks:
                    auth_result = self.security.validate_tool_authorization(
                        user_role=user_role,
                        tool_name=tool_name,
                        parameters=tool_input,
                        user_id=user_id
                    )
                    
                    if not auth_result.authorized:
                        self.audit.log_event(
                            workflow_id=workflow_id,
                            user_id=user_id,
                            event_type=AuditEventType.AUTHORIZATION_DENIED,
                            details={
                                "tool_name": tool_name,
                                "reason": auth_result.reason
                            }
                        )
                        # Mark tool as blocked
                        block["toolUse"]["_blocked"] = True
                        block["toolUse"]["_reason"] = auth_result.reason
                        continue
                
                # Detokenize: Replace PII tokens with real values for tool execution
                detokenized_input = self._detokenize_params(tool_input)
                block["toolUse"]["input"] = detokenized_input
                
                # Audit tool generation (don't log actual PII values)
                self.audit.log_event(
                    workflow_id=workflow_id,
                    user_id=user_id,
                    event_type=AuditEventType.TOOL_INVOCATION,
                    details={
                        "tool_name": tool_name,
                        "input_keys": list(tool_input.keys()),
                        "detokenized": True
                    }
                )

        # Calculate latency
        metrics.latency_ms = (time.time() - start_time) * 1000
        
        # Log completion
        self.audit.log_event(
            workflow_id=workflow_id,
            user_id=user_id,
            event_type=AuditEventType.LLM_RESPONSE,
            details={
                "model_id": model_id,
                "input_tokens": metrics.input_tokens,
                "output_tokens": metrics.output_tokens,
                "latency_ms": round(metrics.latency_ms, 2),
                "guardrail_checks": metrics.guardrail_checks
            },
            parent_event_id=invocation_event_id
        )

        return response

    def _detokenize_params(self, params: Any) -> Any:
        """
        Recursively replace PII tokens with original values.
        
        This is the critical security step that ensures:
        - LLM only sees tokens (e.g., "[SSN_1]")
        - Tools receive real values (e.g., "123-45-6789")
        
        Args:
            params: Parameters that may contain PII tokens
            
        Returns:
            Parameters with tokens replaced by real values
        """
        if isinstance(params, dict):
            return {k: self._detokenize_params(v) for k, v in params.items()}
        elif isinstance(params, list):
            return [self._detokenize_params(v) for v in params]
        elif isinstance(params, str):
            return self.guardrails.detokenize_content(params)
        return params
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get client metrics for monitoring"""
        return {
            "total_invocations": self._total_invocations,
            "total_blocked": self._total_blocked,
            "block_rate": self._total_blocked / max(1, self._total_invocations)
        }
    
    def converse_with_cot(
        self,
        modelId: str,
        messages: List[Dict],
        workflow_id: str,
        user_id: str,
        step: int,
        task_description: str,
        **kwargs
    ) -> Tuple[Dict[str, Any], str]:
        """
        Converse with full Chain of Thought logging.
        
        This method wraps converse() with structured CoT logging
        for regulatory compliance.
        
        Args:
            modelId: Model ID
            messages: Messages
            workflow_id: Workflow ID
            user_id: User ID
            step: Step number in workflow
            task_description: Description of what this step does
            **kwargs: Additional converse parameters
            
        Returns:
            Tuple of (response, cot_event_id)
        """
        # Log thought phase
        thought = f"Processing step {step}: {task_description}"
        plan = f"Invoke LLM ({modelId}) with {len(messages)} messages"
        
        # Execute
        response = self.converse(
            modelId=modelId,
            messages=messages,
            workflow_id=workflow_id,
            user_id=user_id,
            **kwargs
        )
        
        # Extract observation from response
        output_text = ""
        tool_calls = []
        for block in response.get("output", {}).get("message", {}).get("content", []):
            if "text" in block:
                output_text = block["text"][:200]
            if "toolUse" in block:
                tool_calls.append(block["toolUse"].get("name", "unknown"))
        
        observation = output_text if output_text else f"Tool calls: {tool_calls}"
        action = "Generated response" if output_text else f"Invoked tools: {', '.join(tool_calls)}"
        
        # Log full Chain of Thought
        cot_event_id = self.audit.log_cot(
            workflow_id=workflow_id,
            step=step,
            thought=thought,
            plan=plan,
            observation=observation[:500],
            action=action,
            user_id=user_id,
            metadata={
                "model_id": modelId,
                "tool_calls": tool_calls
            }
        )
        
        return response, cot_event_id
