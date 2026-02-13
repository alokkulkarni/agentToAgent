import json
import os
import datetime
from .config import EnterpriseConfig

class AuditLogger:
    """
    Implements WORM (Write Once Read Many) style audit logging for compliance.
    Captures Chain of Thought (CoT).
    """
    
    def __init__(self):
        self.config = EnterpriseConfig
        self.log_dir = self.config.WORM_STORAGE_PATH
        os.makedirs(self.log_dir, exist_ok=True)
        
    def log_event(self, workflow_id: str, user_id: str, event_type: str, details: dict):
        """
        Log an event with traceability.
        """
        if not self.config.ENABLE_AUDIT_LOGGING:
            return
            
        timestamp = datetime.datetime.utcnow().isoformat()
        log_entry = {
            "timestamp": timestamp,
            "workflow_id": workflow_id,
            "user_id": user_id,
            "event_type": event_type,
            "details": details,
            "signature": self._generate_signature(details) # Simulation of tamper-proof seal
        }
        
        # WORM simulation: Append to a daily log file
        date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        log_file = os.path.join(self.log_dir, f"audit_{date_str}.jsonl")
        
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
            
    def log_cot(self, workflow_id: str, step: int, thought: str, plan: str, observation: str, action: str):
        """
        Log Chain of Thought specifically.
        """
        self.log_event(workflow_id, "system", "CHAIN_OF_THOUGHT", {
            "step": step,
            "thought": thought,
            "plan": plan,
            "observation": observation,
            "action": action
        })
        
    def _generate_signature(self, data):
        # In a real system, this would be a cryptographic hash
        return hash(str(data))
