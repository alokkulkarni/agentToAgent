import boto3
import json
import logging
from typing import List, Dict, Any, Optional
from botocore.exceptions import ClientError, ParamValidationError

from .guardrails import GuardrailService
from .audit import AuditLogger
from .config import EnterpriseConfig

class SafeLLMClient:
    """
    Framework-level LLM Client that enforces:
    - Guardrails (Input/Output)
    - PII Tokenization (Input) & Detokenization (Tool Parameters)
    - Audit Logging
    """
    
    def __init__(self, region_name="us-east-1"):
        self.bedrock = boto3.client("bedrock-runtime", region_name=region_name)
        self.guardrails = GuardrailService()
        self.audit = AuditLogger()
        self.config = EnterpriseConfig

    def converse(
        self, 
        modelId: str, 
        messages: List[Dict], 
        system: Optional[List[Dict]] = None, 
        toolConfig: Optional[Dict] = None,
        inferenceConfig: Optional[Dict] = None,
        workflow_id: str = "unknown",
        user_id: str = "anonymous",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Secure wrapper around Bedrock converse API.
        Compatible with boto3 signature (camelCase).
        """
        model_id = modelId # Alias
        
        # 1. Input Processing & Guardrails
        safe_messages = []
        for msg in messages:
            if msg["role"] == "user":
                # Handle text content
                content_blocks = msg["content"]
                safe_blocks = []
                for block in content_blocks:
                    if "text" in block:
                        text = block["text"]
                        
                        # A. Tokenize PII
                        tokenized_text = self.guardrails.tokenize_pii(text)
                        
                        # B. Input Rails (Jailbreak check)
                        is_valid, reason = self.guardrails.validate_input(tokenized_text)
                        if not is_valid:
                            # Log the violation
                            self.audit.log_event(
                                workflow_id, user_id, "GUARDRAIL_VIOLATION", 
                                {"stage": "input", "reason": reason, "text_preview": text[:50]}
                            )
                            raise ValueError(f"Security Policy Violation: {reason}")
                        
                        safe_blocks.append({"text": tokenized_text})
                    else:
                        safe_blocks.append(block)
                safe_messages.append({"role": "user", "content": safe_blocks})
            else:
                safe_messages.append(msg)
        
        # Log the LLM invocation (CoT start)
        self.audit.log_event(workflow_id, user_id, "LLM_INVOCATION", {
            "model_id": model_id,
            "message_count": len(safe_messages)
        })

        # 2. Invoke Model (with fallback logic from previous fixes)
        try:
            kwargs = {
                "modelId": model_id,
                "messages": safe_messages
            }
            if system:
                kwargs["system"] = system
            if toolConfig:
                kwargs["toolConfig"] = toolConfig
            if inferenceConfig:
                kwargs["inferenceConfig"] = inferenceConfig

            response = self.bedrock.converse(**kwargs)
            
        except (ClientError, ParamValidationError) as e:
            # Fallback: Retry without system prompt caching if that was the issue
            if system and any('cachePoint' in s for s in system):
                # Remove cachePoint from system blocks
                clean_system = [{k: v for k, v in s.items() if k != 'cachePoint'} for s in system]
                kwargs["system"] = clean_system
                # Retry
                response = self.bedrock.converse(**kwargs)
            else:
                raise e

        # 3. Output Processing & Detokenization
        output_message = response["output"]["message"]
        content_blocks = output_message["content"]
        
        for block in content_blocks:
            # Output Rails for Text
            if "text" in block:
                is_valid, sanitized_text = self.guardrails.validate_output(block["text"])
                if not is_valid:
                    block["text"] = "[Content Blocked by Security Policy]"
                    self.audit.log_event(workflow_id, user_id, "GUARDRAIL_VIOLATION", {
                        "stage": "output", "reason": "content_policy"
                    })
                else:
                    block["text"] = sanitized_text
            
            # Detokenize Tool Parameters (The Core Requirement)
            if "toolUse" in block:
                tool_use = block["toolUse"]
                tool_input = tool_use["input"]
                
                # Recursively detokenize all string values in input
                detokenized_input = self._detokenize_params(tool_input)
                
                # Update the tool input with real values (PII) so the tool can work
                block["toolUse"]["input"] = detokenized_input
                
                self.audit.log_event(workflow_id, user_id, "TOOL_GENERATION", {
                    "tool_name": tool_use["name"],
                    "input_keys": list(detokenized_input.keys()) # Don't log values if PII
                })

        return response

    def _detokenize_params(self, params: Any) -> Any:
        """Recursively replace tokens with original values"""
        if isinstance(params, dict):
            return {k: self._detokenize_params(v) for k, v in params.items()}
        elif isinstance(params, list):
            return [self._detokenize_params(v) for v in params]
        elif isinstance(params, str):
            return self.guardrails.detokenize_content(params)
        return params
