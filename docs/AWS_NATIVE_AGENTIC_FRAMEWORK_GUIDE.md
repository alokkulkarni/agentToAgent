# Building a Secure, Compliant Enterprise Agentic Framework on AWS

This document provides a step-by-step guide to achieving the high-assurance security, auditability, and guardrail requirements discussed in our custom implementation using AWS Native Agentic Frameworks (specifically **Amazon Bedrock Agents** and **Amazon Bedrock Guardrails**).

---

## Architecture Overview

The solution maps the custom components to AWS managed services:

| Custom Component | AWS Native Equivalent |
| :--- | :--- |
| **Agent Orchestrator** | **Amazon Bedrock Agents** (Orchestration & Reasoning) |
| **Safety Net (Guardrails)** | **Amazon Bedrock Guardrails** (Content Filtering, PII Redaction) |
| **Identity Propagation** | **AWS IAM Roles** + **Session Attributes** (Cognito/OIDC) |
| **Tool Execution** | **Action Groups** (AWS Lambda Functions) |
| **PII Tokenization Vault** | **Amazon DynamoDB** (Token Store) + **AWS KMS** (Encryption) |
| **Auditability (CoT)** | **Amazon CloudWatch Logs** + **AWS CloudTrail** |

---

## Phase 1: Security Foundation (Identity & Encryption)

### 1.1. Create IAM Roles for Agent Identity
Agents must operate with the least privilege necessary. Instead of a single role for all agents, create granular roles.

1.  **Create an IAM Role (`AgentExecutionRole`)**:
    *   **Trust Policy**: Allow `bedrock.amazonaws.com` to assume this role.
    *   **Permissions**: `InvokeFunction` on specific Lambda functions (Tools).
2.  **Create a KMS Key (`PIITokenKey`)**:
    *   Use this key to encrypt the DynamoDB table storing PII tokens.
    *   Grant usage permission only to the `TokenizationService` Lambda role.

### 1.2. Set Up PII Token Vault (DynamoDB)
Create a DynamoDB table named `PIITokenVault` with:
*   **Partition Key**: `token_id` (String)
*   **Encryption**: AWS KMS (using `PIITokenKey`)
*   **Attributes**: `original_value` (Encrypted string), `data_type` (String), `expiry` (TTL)

---

## Phase 2: Implementing Guardrails (The "Safety Net")

### 2.1. Configure Amazon Bedrock Guardrails
This layer intercepts all model inputs and outputs.

1.  Navigate to **Amazon Bedrock > Safeguards > Guardrails**.
2.  **Create Guardrail**: `EnterpriseSafetyNet`.
3.  **Content Filters**:
    *   Enable **Hate**, **Insults**, **Sexual**, **Violence**.
    *   Set filter strength to **High** for strict compliance.
4.  **Denied Topics**:
    *   Add topics like "Financial Advice" or "Competitor Analysis" if restricted.
    *   Provide natural language descriptions (e.g., "Any request asking for investment recommendations").
5.  **Sensitive Information Filters (PII)**:
    *   **Select PII Types**: Email, Phone, SSN, Credit Card.
    *   **Action**: Select **Mask** or **Block**. For our tokenization strategy, we use a custom Lambda hook (see Phase 4), but native masking provides a baseline.
6.  **Contextual Grounding Check**:
    *   Enable to detect hallucinations in RAG responses.

---

## Phase 3: Tool Implementation (Action Groups)

Agents interact with systems via "Action Groups" which wrap Lambda functions. This is where we implement **Tool Authorization** and **PII Detokenization**.

### 3.1. Create the Tool Lambda (`FinancialToolsFunction`)
This function handles requests like `transfer_money`.

```python
import boto3
import json

dynamodb = boto3.client('dynamodb')

def lambda_handler(event, context):
    agent = event['agent']
    actionGroup = event['actionGroup']
    function = event['function']
    parameters = event.get('parameters', [])
    
    # 1. Identity Propagation Check (Simulated)
    user_context = event.get('sessionAttributes', {}).get('user_id')
    if not user_context:
        raise Exception("Unauthorized: Missing User Context")

    # 2. Input Validation (Deterministic Guardrail)
    if function == 'transfer_money':
        amount = next((p['value'] for p in parameters if p['name'] == 'amount'), 0)
        if float(amount) > 2000:
            return format_response(actionGroup, function, "Error: Transfer limit exceeded ($2000)")

    # 3. PII Handling (Detokenization if needed)
    # If the input account_number is a token (e.g., "TOKEN_123"), retrieve real value from DynamoDB
    
    # 4. Execute Business Logic
    result = perform_transfer(user_context, amount)
    
    return format_response(actionGroup, function, result)

def format_response(group, func, body):
    return {
        "actionGroup": group,
        "function": func,
        "functionResponse": {
            "responseBody": {"TEXT": {"body": json.dumps(body)}}
        }
    }
```

### 3.2. Define OpenAPI Schema
Upload an OpenAPI schema (JSON/YAML) defining the API contract for the Lambda function.

---

## Phase 4: Constructing the Agent (Amazon Bedrock Agents)

### 4.1. Create the Agent
1.  Navigate to **Amazon Bedrock > Agents**.
2.  **Name**: `FinancialAssistantAgent`.
3.  **Role**: Select the `AgentExecutionRole` created in Phase 1.
4.  **Model**: Select Claude 3 Sonnet (or Haiku for speed).

### 4.2. Instructions (System Prompt)
Embed the core directives and persona here.
> "You are a helpful financial assistant. You operate on behalf of the authenticated user. You must never reveal PII. Always check your plan before executing actions."

### 4.3. Associate Action Groups
1.  **Add Action Group**: `FinancialOperations`.
2.  **Select Lambda**: `FinancialToolsFunction`.
3.  **Select API Schema**: Upload the OpenAPI file.

### 4.4. Attach Guardrail
1.  In the Agent configuration, look for **Guardrail details**.
2.  Select `EnterpriseSafetyNet` (created in Phase 2).
3.  This ensures every turn of conversation passes through the guardrail *before* reaching the model or the user.

---

## Phase 5: Auditability (Chain of Thought)

Amazon Bedrock Agents provides built-in tracing.

### 5.1. Enable Tracing
1.  Ensure the agent has permission to write to **CloudWatch Logs**.
2.  When invoking the agent, enable `enableTrace=True`.

### 5.2. Analyzing Traces
Traces in CloudWatch contain the full Chain of Thought (CoT):
*   **Pre-Processing**: Input guardrail checks.
*   **Orchestration**:
    *   **Rationale**: The model's "Thought" process (e.g., "I need to call transfer_money").
    *   **Invocation**: The actual call to Lambda.
    *   **Observation**: The result from Lambda.
*   **Post-Processing**: Output guardrail checks and final response generation.

### 5.3. WORM Compliance
1.  Configure **CloudTrail** to log all `InvokeAgent` data events.
2.  Configure an S3 Bucket with **Object Lock** (Governance Mode) to store these logs immutably (WORM) for the required retention period.

---

## Phase 6: Invocation & Context (The Client Application)

When your application calls the Agent (via `InvokeAgent` API), you must pass the context.

```python
import boto3

client = boto3.client('bedrock-agent-runtime')

response = client.invoke_agent(
    agentId='<AGENT_ID>',
    agentAliasId='<ALIAS_ID>',
    sessionId='<SESSION_ID>',
    enableTrace=True, 
    sessionState={
        'sessionAttributes': {
            'user_id': 'user_12345',  # Identity Propagation
            'user_role': 'premium'
        }
    },
    inputText="Transfer $500 to account TOKEN_9876"
)
```

The `sessionAttributes` are passed to your Lambda Action Group, allowing your code to perform authorization checks ("On-Behalf-Of" the user).

---

## Summary of Guarantees

1.  **Safety**: Guardrails enforce policy (No bad topics, no PII leakage).
2.  **Security**: IAM Roles limit what the agent can touch. KMS protects the data.
3.  **Control**: Deterministic validation in Lambda prevents "hallucinated" high-value transactions.
4.  **Audit**: Full execution trace (Thought -> Plan -> Action) is logged and locked in S3.
