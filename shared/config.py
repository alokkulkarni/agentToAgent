import os
from typing import Dict, Any

class EnterpriseConfig:
    """Central configuration for Enterprise features"""
    
    # Feature Flags
    ENABLE_GUARDRAILS = os.getenv("ENABLE_GUARDRAILS", "True").lower() == "true"
    ENABLE_AUDIT_LOGGING = os.getenv("ENABLE_AUDIT_LOGGING", "True").lower() == "true"
    ENABLE_SECURITY_CHECKS = os.getenv("ENABLE_SECURITY_CHECKS", "True").lower() == "true"
    
    # Compliance Settings
    PII_REDACTION_ENABLED = os.getenv("PII_REDACTION_ENABLED", "True").lower() == "true"
    WORM_STORAGE_PATH = os.getenv("WORM_STORAGE_PATH", "./audit_logs")
    
    # Safety Settings
    DENIED_TOPICS = os.getenv("DENIED_TOPICS", "political_advice,medical_advice,competitor_mentions").split(",")
    SENSITIVE_TERMS = ["jailbreak", "ignore previous instructions", "system override"]
    
    # Financial Limits (Example of deterministic logic parameterization)
    MAX_TRANSACTION_LIMIT = float(os.getenv("MAX_TRANSACTION_LIMIT", "2000.0"))

    # Load External Security Policies
    SECURITY_POLICY_PATH = os.getenv("SECURITY_POLICY_PATH", os.path.join(os.path.dirname(__file__), "security_policies.json"))
    _security_policies = {}
    
    # Load External Guardrail Config
    GUARDRAIL_CONFIG_PATH = os.getenv("GUARDRAIL_CONFIG_PATH", os.path.join(os.path.dirname(__file__), "guardrails_config.json"))
    _guardrail_config = {}

    @classmethod
    def load_security_policies(cls) -> Dict[str, Any]:
        """Load security policies from external JSON file"""
        if cls._security_policies:
            return cls._security_policies
            
        try:
            import json
            if os.path.exists(cls.SECURITY_POLICY_PATH):
                with open(cls.SECURITY_POLICY_PATH, 'r') as f:
                    cls._security_policies = json.load(f)
            else:
                # Fallback default if file missing
                cls._security_policies = {
                    "policies": {},
                    "global_settings": {"enable_security_checks": True}
                }
        except Exception as e:
            print(f"Error loading security policies: {e}")
            cls._security_policies = {}
            
        return cls._security_policies

    @classmethod
    def load_guardrail_config(cls) -> Dict[str, Any]:
        """Load guardrail configuration from external JSON file"""
        if cls._guardrail_config:
            return cls._guardrail_config
            
        try:
            import json
            if os.path.exists(cls.GUARDRAIL_CONFIG_PATH):
                with open(cls.GUARDRAIL_CONFIG_PATH, 'r') as f:
                    cls._guardrail_config = json.load(f)
            else:
                # Fallback if config file is missing
                cls._guardrail_config = {
                    "pii_patterns": {
                        "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
                        "CreditCard": r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",
                        "Email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
                    },
                    "sensitive_terms": ["jailbreak", "ignore previous instructions", "system override"],
                    "denied_topics": ["political advice", "medical advice"],
                    "disclaimers": []
                }
        except Exception as e:
            print(f"Error loading guardrail config: {e}")
            cls._guardrail_config = {}
            
        return cls._guardrail_config

    @classmethod
    def get_tool_limit(cls, tool_name: str, param_name: str) -> Optional[float]:
        """Get limit for a specific tool parameter"""
        policies = cls.load_security_policies().get("policies", {})
        tool_policy = policies.get(tool_name)
        if tool_policy and "limits" in tool_policy:
            return tool_policy["limits"].get(param_name)
        return None

    @classmethod
    def get_settings(cls) -> Dict[str, Any]:
        return {
            "guardrails": cls.ENABLE_GUARDRAILS,
            "audit": cls.ENABLE_AUDIT_LOGGING,
            "security": cls.ENABLE_SECURITY_CHECKS
        }
