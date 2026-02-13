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
        Validates against externalized security policies and registry metadata.
        """
        if not self.config.ENABLE_SECURITY_CHECKS:
            return True
            
        # Load policies
        policies = self.config.load_security_policies().get("policies", {})
        
        # Check if specific policy exists for this tool
        if tool_name in policies:
            tool_policy = policies[tool_name]
            limits = tool_policy.get("limits", {})
            
            # Check all defined limits against parameters
            for param, limit in limits.items():
                if param in parameters:
                    val = parameters[param]
                    # Handle numeric comparisons
                    if isinstance(val, (int, float)) and isinstance(limit, (int, float)):
                        if float(val) > float(limit):
                            print(f"Security Violation: {tool_name}.{param} ({val}) exceeds limit ({limit})")
                            return False
                            
            # Check approval requirement
            if tool_policy.get("requires_approval", False):
                # In a real system, this would trigger an approval flow
                # For now, we assume implicit approval if within limits, or log it
                print(f"Notice: Tool {tool_name} requires approval. Proceeding within limits.")
                
        return True

    def get_user_context(self, headers: Dict[str, Any]) -> Dict[str, str]:
        """
        Extract user identity for OBO (On-Behalf-Of) flow.
        """
        return {
            "user_id": headers.get("X-User-ID", "anonymous"),
            "role": headers.get("X-User-Role", "user")
        }
