import re
from typing import Tuple, Optional
from .config import EnterpriseConfig

class GuardrailService:
    """
    Simulates an Enterprise Guardrail Proxy (e.g. Bedrock Guardrails / NeMo).
    """
    
    def __init__(self):
        self.config = EnterpriseConfig
        self.guardrail_config = self.config.load_guardrail_config()
        self.pii_patterns = self.guardrail_config.get("pii_patterns", {})
        self.token_map = {} # In-memory vault for demo purposes

    def tokenize_pii(self, text: str) -> str:
        """
        Replace PII with secure tokens (e.g., [SSN_1]).
        Stores the mapping in a secure vault (self.token_map).
        """
        if not self.config.PII_REDACTION_ENABLED:
            return text
            
        sanitized_text = text
        for pii_type, pattern in self.pii_patterns.items():
            matches = re.finditer(pattern, text)
            for i, match in enumerate(matches):
                value = match.group()
                # Check if already tokenized
                existing_token = None
                for t, v in self.token_map.items():
                    if v == value:
                        existing_token = t
                        break
                
                if existing_token:
                    token = existing_token
                else:
                    token = f"[{pii_type}_{len(self.token_map) + 1}]"
                    self.token_map[token] = value
                
                # Replace only this occurrence (careful with multiple same values)
                sanitized_text = sanitized_text.replace(value, token)
        
        return sanitized_text

    def detokenize_content(self, text: str) -> str:
        """
        Restore PII from tokens. Used when sending data to authorized tools.
        """
        restored_text = text
        for token, value in self.token_map.items():
            if token in restored_text:
                restored_text = restored_text.replace(token, value)
        return restored_text

    def validate_input(self, prompt: str) -> Tuple[bool, Optional[str]]:
        """
        Input Rails: Block malicious prompts.
        Returns (is_valid, rejection_reason)
        """
        if not self.config.ENABLE_GUARDRAILS:
            return True, None
            
        # Check for jailbreak attempts using configured sensitive terms
        sensitive_terms = self.guardrail_config.get("sensitive_terms", self.config.SENSITIVE_TERMS)
        prompt_lower = prompt.lower()
        for term in sensitive_terms:
            if term.lower() in prompt_lower:
                return False, f"Guardrail Violation: blocked term '{term}' detected."
                
        return True, None

    def validate_output(self, text: str) -> Tuple[bool, str]:
        """
        Output Rails: PII Filtering and Topic Deny-list.
        Returns (is_valid, sanitized_text)
        """
        if not self.config.ENABLE_GUARDRAILS:
            return True, text
            
        sanitized_text = text
        
        # Topic Deny-list (Simple keyword check for simulation)
        # In production, this would use a topic classification model
        denied_topics = self.guardrail_config.get("denied_topics", self.config.DENIED_TOPICS)
        for topic in denied_topics:
            if topic and topic.replace("_", " ").lower() in sanitized_text.lower():
                return False, f"Guardrail Violation: Output contains denied topic '{topic}'."
        
        # PII Redaction
        if self.config.PII_REDACTION_ENABLED:
            for pii_type, pattern in self.pii_patterns.items():
                sanitized_text = re.sub(pattern, f"[{pii_type}_REDACTED]", sanitized_text)
                
        # Financial & Other Disclaimers (Configurable)
        disclaimers = self.guardrail_config.get("disclaimers", [])
        text_lower = sanitized_text.lower()
        
        for disclaimer in disclaimers:
            keywords = disclaimer.get("trigger_keywords", [])
            message = disclaimer.get("message", "")
            
            should_apply = any(kw.lower() in text_lower for kw in keywords)
            if should_apply and message not in sanitized_text:
                sanitized_text += message
            
        return True, sanitized_text
