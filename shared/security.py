from typing import Dict, Any, Optional
from .config import EnterpriseConfig

class SecurityManager:
    """
    Handles Identity Propagation and Tool Authorization (Deterministic Layer).
    """
    
    def __init__(self):
        self.config = EnterpriseConfig

    def validate_tool_authorization(self, user_role: str, tool_name: str, parameters: Dict[str, Any]) -> bool:
        """
        Deterministic code layer to validate limits independent of LLM.
        """
        if not self.config.ENABLE_SECURITY_CHECKS:
            return True
            
        # Example: Limit transfer amounts
        if tool_name == "transfer_funds" or tool_name == "calculate": # utilizing calculate as proxy for demo
            amount = parameters.get("amount") or parameters.get("a") # 'a' for calculate proxy
            if amount and isinstance(amount, (int, float)):
                if float(amount) > self.config.MAX_TRANSACTION_LIMIT:
                    return False
        
        return True

    def get_user_context(self, headers: Dict[str, Any]) -> Dict[str, str]:
        """
        Extract user identity for OBO (On-Behalf-Of) flow.
        """
        return {
            "user_id": headers.get("X-User-ID", "anonymous"),
            "role": headers.get("X-User-Role", "user")
        }
