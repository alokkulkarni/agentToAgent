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
    
    @classmethod
    def get_settings(cls) -> Dict[str, Any]:
        return {
            "guardrails": cls.ENABLE_GUARDRAILS,
            "audit": cls.ENABLE_AUDIT_LOGGING,
            "security": cls.ENABLE_SECURITY_CHECKS
        }
