# Shared Library

This directory contains shared components, utilities, and configuration used across the Agent-to-Agent (A2A) framework.

## Components

*   **`config.py`**: Central configuration manager. Loads settings from environment variables and external JSON files.
*   **`security.py`**: Handles identity propagation and tool authorization. Uses `security_policies.json` for deterministic policy enforcement.
*   **`guardrails.py`**: Provides integration with safety guardrails (e.g., Bedrock Guardrails).
*   **`audit.py`**: Handles audit logging to WORM storage.
*   **`llm_client.py`**: Wraps LLM interactions with safety and monitoring checks.
*   **`a2a_protocol/`**: Definitions of the communication protocol and data models.

## Configuration

This shared library is designed to be configurable via external files, allowing you to customize security policies and guardrails without modifying the code.

### 1. Security Policies (`security_policies.json`)

Define limits and constraints for tool execution.

**Default Path:** `shared/security_policies.json` (Override with `SECURITY_POLICY_PATH` env var)

**Structure:**
```json
{
    "policies": {
        "tool_name": {
            "limits": {
                "parameter_name": value
            }
        }
    },
    "global_settings": {
        "enable_security_checks": true
    }
}
```

### 2. Guardrails Configuration (`guardrails_config.json`)

Define PII patterns, sensitive terms, denied topics, and content disclaimers.

**Default Path:** `shared/guardrails_config.json` (Override with `GUARDRAIL_CONFIG_PATH` env var)

**Structure:**
```json
{
    "pii_patterns": {
        "SSN": "\\b\\d{3}-\\d{2}-\\d{4}\\b",
        "Email": "regex_pattern"
    },
    "sensitive_terms": ["jailbreak", "ignore instructions"],
    "denied_topics": ["political advice"],
    "disclaimers": [
        {
            "trigger_keywords": ["financial", "stock"],
            "message": "\n[Disclaimer...]"
        }
    ]
}
```

### Environment Variables

Common environment variables used:
*   `ENABLE_SECURITY_CHECKS`: (True/False) Enable deterministic tool checks.
*   `ENABLE_GUARDRAILS`: (True/False) Enable LLM guardrails.
*   `ENABLE_AUDIT_LOGGING`: (True/False) Enable audit logging.
*   `SECURITY_POLICY_PATH`: Path to the security policies JSON file.
*   `GUARDRAIL_CONFIG_PATH`: Path to the guardrails config JSON file.
*   `WORM_STORAGE_PATH`: Path for audit logs.

## Integration
Services using this shared library automatically pick up the configuration.
*   **Agents**: Use `SecurityManager` to validate tool calls against the loaded policies.
*   **Orchestrator**: Uses `EnterpriseConfig` to determine global behavior.
