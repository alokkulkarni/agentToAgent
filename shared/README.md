# Shared Library - Enterprise Agent Framework

This directory contains the core enterprise utilities for the Agent-to-Agent framework. These modules provide configurable, production-ready implementations for security, guardrails, audit logging, and more.

## Architecture Overview

```
shared/
├── config/                     # Configuration files
│   ├── enterprise_config.json  # Main enterprise configuration
│   ├── security_policies.json  # Security policies and tool limits
│   └── guardrails_config.json  # Guardrail rules and PII patterns
├── config.py                   # Configuration management
├── security.py                 # Security manager (RBAC, tool authorization)
├── guardrails.py               # Guardrail service (PII, input/output rails)
├── audit.py                    # Audit logging (WORM, Chain of Thought, Blockchain)
├── llm_client.py               # Safe LLM client wrapper
├── agent_interaction.py        # Agent interaction helpers
└── a2a_protocol/               # Agent-to-Agent protocol definitions
```

## Enterprise Security Flow

The security architecture follows this sequence for every request:

```
User Input -> [Guardrails] -> [PII Vault] -> [LLM] -> [Output Rails] -> [Tool Authorization] -> Tool Execution
                  |               |                         |                  |
                  v               v                         v                  v
            Input Rails      Tokenize PII           Detokenize PII        Check Limits
           (Jailbreak)       (SSN -> [SSN_1])       (For tools only)      (RBAC, Rate)
                  |               |                         |                  |
                  +---------------+---------+---------------+------------------+
                                            |
                                      [Audit Logger]
                                  (Blockchain-style Chain)
```

## Quick Start

```python
from shared import (
    ConfigManager,
    get_security_manager,
    get_guardrail_service,
    get_audit_logger,
    SafeLLMClient,
    AuditEventType
)

# Get singleton instances
config = ConfigManager.get_instance()
security = get_security_manager()
guardrails = get_guardrail_service()
audit = get_audit_logger()

# Use SafeLLMClient for automatic security
client = SafeLLMClient()
response = client.converse(
    modelId="anthropic.claude-3-sonnet-20240229-v1:0",
    messages=[{"role": "user", "content": [{"text": "My SSN is 123-45-6789"}]}],
    workflow_id="wf_123",
    user_id="user_456"
)
# LLM sees: "My SSN is [SSN_1]"
# Tool calls receive: "123-45-6789"
```

## Configuration

### Environment Variables

All configuration can be overridden via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_GUARDRAILS` | Enable guardrail checks | `true` |
| `ENABLE_AUDIT_LOGGING` | Enable audit logging | `true` |
| `ENABLE_SECURITY_CHECKS` | Enable security validation | `true` |
| `ENABLE_PII_REDACTION` | Enable PII tokenization | `true` |
| `STRICT_MODE` | Enable strict security mode | `false` |
| `WORM_STORAGE_PATH` | Audit log directory | `./audit_logs` |
| `DEFAULT_LLM_MODEL` | Default LLM model ID | `anthropic.claude-3-sonnet-20240229-v1:0` |
| `AWS_REGION` | AWS region for Bedrock | `us-east-1` |
| `REGISTRY_URL` | Registry service URL | `http://localhost:8000` |
| `ORCHESTRATOR_URL` | Orchestrator service URL | `http://localhost:8100` |
| `MCP_GATEWAY_URL` | MCP Gateway URL | `http://localhost:8010` |

### Configuration Files

#### enterprise_config.json

Main configuration file containing:
- Feature flags
- Compliance settings
- LLM configuration
- Session management
- Rate limiting
- Service URLs

```json
{
  "environment": "development",
  "feature_flags": {
    "enable_guardrails": true,
    "enable_audit_logging": true,
    "enable_security_checks": true,
    "strict_mode": false
  },
  "llm": {
    "default_model": "anthropic.claude-3-sonnet-20240229-v1:0",
    "region": "us-east-1",
    "max_tokens": 4096
  }
}
```

#### security_policies.json

Security policies including:
- Role permissions (RBAC)
- Tool-specific limits
- Rate limiting per tool
- Approval requirements

```json
{
  "role_permissions": {
    "admin": {
      "allowed_tools": ["*"],
      "max_transaction_limit": 100000.0,
      "can_bypass_approval": true
    },
    "user": {
      "allowed_tools": ["calculate", "answer_question"],
      "max_transaction_limit": 2000.0
    }
  },
  "tool_policies": {
    "transfer_funds": {
      "limits": {
        "amount": {"type": "numeric", "max": 2000.0}
      },
      "requires_approval": true,
      "approval_threshold": 500.0
    }
  }
}
```

#### guardrails_config.json

Guardrail configuration including:
- PII detection patterns
- Input rails (jailbreak detection)
- Output rails (topic filtering)
- Disclaimers

```json
{
  "pii_detection": {
    "enabled": true,
    "patterns": {
      "SSN": {
        "regex": "\\b\\d{3}-\\d{2}-\\d{4}\\b",
        "sensitivity": "high"
      }
    }
  },
  "input_rails": {
    "sensitive_terms": [
      {"term": "jailbreak", "action": "block"}
    ]
  },
  "disclaimers": [
    {
      "trigger_keywords": ["financial", "investment"],
      "message": "This is not financial advice."
    }
  ]
}
```

## Modules

### ConfigManager (`config.py`)

Centralized configuration management with:
- Environment-based configuration
- External JSON file loading
- Environment variable overrides
- Hot-reload capability

```python
from shared.config import ConfigManager

config = ConfigManager.get_instance()

# Check features
if config.feature_enabled("guardrails"):
    pass

# Get LLM config
llm_config = config.get_llm_config()

# Get tool policy
policy = config.get_tool_policy("transfer_funds")

# Reload configuration
config.reload()
```

### SecurityManager (`security.py`)

Enterprise security with:
- Identity propagation (OBO flow)
- Role-based access control (RBAC)
- Tool authorization with limits
- Rate limiting
- Violation tracking

```python
from shared.security import get_security_manager

security = get_security_manager()

# Extract user context from headers
user_ctx = security.get_user_context(request.headers)

# Validate tool authorization
result = security.validate_tool_authorization(
    user_role=user_ctx.role,
    tool_name="transfer_funds",
    parameters={"amount": 1500},
    user_id=user_ctx.user_id
)

if not result.authorized:
    print(f"Denied: {result.reason}")
elif result.requires_approval:
    print(f"Approval required: {result.approval_id}")
```

### GuardrailService (`guardrails.py`)

Content safety with:
- PII tokenization/detokenization
- Input validation (jailbreak detection)
- Output validation (topic filtering)
- Automatic disclaimers

```python
from shared.guardrails import get_guardrail_service

guardrails = get_guardrail_service()

# Tokenize PII before sending to LLM
safe_input = guardrails.tokenize_pii("My SSN is 123-45-6789")
# Result: "My SSN is [SSN_1]"

# Validate input
is_valid, reason = guardrails.validate_input(user_prompt)
if not is_valid:
    print(f"Blocked: {reason}")

# Process output
is_valid, processed = guardrails.validate_output(llm_response)

# Detokenize for tool execution
original = guardrails.detokenize_content(safe_input)
# Result: "My SSN is 123-45-6789"
```

### AuditLogger (`audit.py`)

Compliance logging with:
- WORM (Write Once Read Many) storage
- Tamper-proof signatures
- **Blockchain-style hash chaining** (each entry links to previous)
- Chain of Thought capture
- Asynchronous writing
- Chain integrity verification

```python
from shared.audit import get_audit_logger, AuditEventType

audit = get_audit_logger()

# Log event (automatically chain-linked)
audit.log_event(
    workflow_id="wf_123",
    user_id="user_456",
    event_type=AuditEventType.TOOL_INVOCATION,
    details={"tool": "transfer", "amount": 500}
)

# Log Chain of Thought
audit.log_cot(
    workflow_id="wf_123",
    step=1,
    thought="User wants to transfer money",
    plan="Check balance -> Execute transfer",
    observation="Balance sufficient",
    action="Executed transfer"
)

# Query logs
logs = audit.get_logs_for_workflow("wf_123")

# Verify single file integrity
result = audit.verify_log_integrity("audit_logs/audit_2025-02-13.jsonl")

# Verify blockchain chain integrity (proves no tampering)
chain_result = audit.verify_chain_integrity()
if not chain_result["verified"]:
    print(f"Chain broken at: {chain_result['first_break_at']}")
```

### SafeLLMClient (`llm_client.py`)

Secure LLM wrapper with:
- Automatic guardrail enforcement
- PII tokenization on input
- PII detokenization for tools
- Tool authorization checks
- Comprehensive audit logging
- Chain of Thought support

```python
from shared.llm_client import SafeLLMClient

client = SafeLLMClient(region_name="us-east-1")

# Basic usage - all security automatic
response = client.converse(
    modelId="anthropic.claude-3-sonnet-20240229-v1:0",
    messages=[{"role": "user", "content": [{"text": prompt}]}],
    workflow_id="wf_123",
    user_id="user_456"
)

# With Chain of Thought logging
response, cot_event_id = client.converse_with_cot(
    modelId="anthropic.claude-3-sonnet-20240229-v1:0",
    messages=[{"role": "user", "content": [{"text": prompt}]}],
    workflow_id="wf_123",
    user_id="user_456",
    step=1,
    task_description="Process customer request"
)
```

## Security Best Practices

1. **Always validate tools**: Use `SecurityManager.validate_tool_authorization()` before executing any tool
2. **Tokenize PII**: Use `GuardrailService.tokenize_pii()` before sending data to LLMs
3. **Detokenize for tools**: Use `GuardrailService.detokenize_content()` when tools need real values
4. **Log everything**: Use `AuditLogger` for compliance and debugging
5. **Use SafeLLMClient**: It automatically handles guardrails and audit

## Extending for New Agents

When creating new agents, follow this pattern:

```python
from shared.config import ConfigManager
from shared.security import get_security_manager
from shared.guardrails import get_guardrail_service
from shared.audit import get_audit_logger, AuditEventType
from shared.llm_client import SafeLLMClient

class MyNewAgent:
    def __init__(self):
        self.config = ConfigManager.get_instance()
        self.security = get_security_manager()
        self.guardrails = get_guardrail_service()
        self.audit = get_audit_logger()
        self.llm = SafeLLMClient()
    
    def execute_task(self, task, user_context):
        # 1. Validate input
        is_valid, reason = self.guardrails.validate_input(task.input)
        if not is_valid:
            return {"error": reason}
        
        # 2. Check authorization
        auth_result = self.security.validate_tool_authorization(
            user_role=user_context.role,
            tool_name=task.capability,
            parameters=task.parameters,
            user_id=user_context.user_id
        )
        if not auth_result.authorized:
            return {"error": auth_result.reason}
        
        # 3. Process with LLM (guardrails automatic)
        response = self.llm.converse(
            modelId=self.config.llm.default_model,
            messages=[...],
            workflow_id=task.workflow_id,
            user_id=user_context.user_id
        )
        
        # 4. Audit is automatic via SafeLLMClient
        
        return response
```

## Testing

Run tests for shared modules:

```bash
# From project root
python -m pytest tests/test_shared/ -v
```

## Production Deployment

For production deployment:

1. Set `environment` to `"production"` in `enterprise_config.json`
2. Enable `strict_mode` for enhanced security
3. Configure proper `worm_storage_path` for audit logs (ideally S3 or compliant storage)
4. Set up log rotation and retention policies
5. Configure rate limiting appropriately
6. Review and customize security policies for your use case

## License

Part of the Agent-to-Agent Framework. See root LICENSE file.
