# System Architecture

## Overview

The Agent-to-Agent (A2A) framework is a distributed, microservices-based system designed for autonomous multi-agent collaboration. It leverages AWS Bedrock for LLM capabilities and the Model Context Protocol (MCP) for standardized tool integration. The system is designed with enterprise-grade security, auditability, and context preservation at its core.

### High-Level Architecture

```ascii
                       +--------------------------------+
                       |      IDENTITY PROVIDER         |
                       |  (Azure AD / Okta / Auth0 /    |
                       |   Cognito / Keycloak / OIDC)   |
                       +------+-------------------+-----+
                              |                   |
                  JWT Validate|                   |OBO Token
                   (JWKS/OIDC)|                   |Exchange
                              |                   |
[ USER / CLI ] -(Bearer JWT)->+                   |
      |                       |                   |
      |              +--------+--------+          |
[ INTERACTION ]      |   ORCHESTRATOR  |<---------+
[ MANAGER     ]<---->|  (Port 8100)    |
                     +--------+--------+
                              |
              +---------------+---------------+
              |                               |
     +--------+--------+           +----------+---------+
     |  CONTEXT STORE  |           |   SECURITY LAYER   |
     | (Session History|           | (Guardrails / PII  |
     |  & State)       |           |  Vault / Audit Log)|
     +-----------------+           +--------------------+
                              |
                     +--------+--------+
                     |   AGENT MESH    |
                     | (Research, Code,|
                     |  Data, Math...) |
                     +--------+--------+
                              |
            +-----------------+------------------+
            |  MCP GATEWAY (Port 8300)           |
            |  - Validates JWT                   |
            |  - Fetches Tool Auth from Registry |
            |  - Performs OBO Token Exchange     |
            +--------+-----------+---------------+
                     |           |
         (Tool Token)|           |(Auth Schema)
                     v           v
            +--------+--+  +-----+-----------+
            | MCP SERVERS|  |  MCP REGISTRY  |
            | (Search,   |  | (Tool Auth     |
            |  Calc, DB) |  |  Requirements) |
            +------------+  +----------------+
```

---

## 1. Core Services

### Orchestrator (Port 8100)
The central nervous system of the framework.
- **Workflow Planning**: Uses Claude 3.5 Sonnet to decompose user requests into executable steps.
- **Context Management**: Maintains global conversation history across multiple workflows using a `session_id`.
- **State Management**: Persists workflow state in SQLite/PostgreSQL.
- **Authentication**: Validates JWT tokens via `shared/auth_dependencies.py`; injects `UserContext` into all workflow executions.
- **Security Integration**: Enforces identity propagation and guardrails.

### Interaction Manager
Handles human-in-the-loop scenarios.
- **Suspension**: Pauses workflows when agent requires user input.
- **Resumption**: Resumes execution with user feedback.
- **Context Switching**: Allows users to branch off into new tasks while keeping the original workflow paused.

### Security Layer
Enterprise-grade security features embedded in the framework.
- **SafeLLMClient**: A wrapper around AWS Bedrock client that enforces input/output guardrails.
- **PII Vault**: Tokenizes sensitive data (Credit Cards, SSN) before sending to LLM; detokenizes for authorized tool calls.
- **Audit Logger**: WORM (Write Once Read Many) compliant logging of "Thought, Plan, Observation, Action".
- **Identity Propagation**: Propagates User ID and Roles (IAM style) to every agent and tool.

### MCP Gateway (Port 8300)
The router for tool execution.
- **Tool Discovery**: Dynamically finds tools registered in MCP Registry.
- **Authentication**: Validates JWT bearer tokens before executing any tool.
- **Token Exchange**: Fetches tool auth requirements from the Registry and performs OBO token exchange for tool-scoped tokens.
- **Load Balancing**: Distributes requests across available tool servers.
- **Protocol Translation**: Converts Agent HTTP requests to MCP JSON-RPC protocol.

### MCP Registry (Port 8200)
Central catalog of all available MCP tools.
- **Tool Registration**: MCP servers register their tools and capabilities on startup.
- **Auth Schema**: Each tool can declare its authentication requirements via `ToolAuthSchema` (required scopes, audience, token endpoint).
- **Auth Endpoint**: `GET /api/mcp/tools/{tool_name}/auth` — queried by the Gateway before executing a tool.

---

## 2. Context Preservation Architecture

The system implements a hierarchical context model to support multi-turn, multi-workflow conversations.

```ascii
Session (Global Context)
   |
   +--- Workflow A (Completed)
   |      |
   |      +--- Step 1 Result
   |      +--- Step 2 Result
   |
   +--- Workflow B (Active)
          |
          +--- Step 1 (Current)
```

1.  **Session ID**: A unique identifier generated at the start of a CLI/Web session.
2.  **History Aggregation**: When a new workflow starts, the Orchestrator aggregates summaries of previous workflows in the same session.
3.  **Prompt Injection**: This aggregated history is injected into the "Memory" section of the Planner LLM's prompt.
4.  **Result Persistence**: Workflow results are stored with the Session ID to facilitate retrieval.

---

## 3. Enterprise Security Architecture

### Sequence Diagram: Secure Request Flow

```ascii
      User           Orchestrator      Guardrail       PII Vault         Agent           LLM            Tool
       |                 |                 |               |               |              |               |
       | "Transfer $500" |                 |               |               |              |               |
       |---------------->|                 |               |               |              |               |
       |                 | Validate Input  |               |               |              |               |
       |                 |---------------->|               |               |              |               |
       |                 |      Safe       |               |               |              |               |
       |                 |<----------------|               |               |              |               |
       |                 |                 |               |               |              |               |
       |                 | Tokenize("1234")|               |               |              |               |
       |                 |-------------------------------->|               |              |               |
       |                 |   "TOKEN_99"    |               |               |              |               |
       |                 |<--------------------------------|               |              |               |
       |                 |                 |               |               |              |               |
       |                 | Execute Task ("Transfer... TOKEN_99")           |              |               |
       |                 |------------------------------------------------>|              |               |
       |                 |                 |               |               | Generate Plan|               |
       |                 |                 |               |               | (Tokenized)  |               |
       |                 |                 |               |               |------------->|               |
       |                 |                 |               |               | Call Tool    |               |
       |                 |                 |               |               | transfer(...) |              |
       |                 |                 |               |               |<-------------|               |
       |                 |                 |               |               |              |               |
       |                 |                 |               | Detokenize("TOKEN_99")       |               |
       |                 |                 |               |<-----------------------------|               |
       |                 |                 |               |   "1234-5678" |              |               |
       |                 |                 |               |-------------->|              |               |
       |                 |                 |               |               |              |               |
       |                 |                 |               |               | Execute transfer(500, "1234")|
       |                 |                 |               |               |----------------------------->|
       |                 |                 |               |               |              Success         |
       |                 |                 |               |               |<-----------------------------|
       |                 |                 |               |               |              |               |
       |                 | Task Complete   |               |               |              |               |
       |                 |<------------------------------------------------|              |               |
       |    "Success"    |                 |               |               |              |               |
       |<----------------|                 |               |               |              |               |
       |                 |                 |               |               |              |               |
```

### Components

1.  **Guardrails**:
    *   **Input**: Blocks malicious prompts, prompt injection, and banned topics.
    *   **Output**: Filters PII that wasn't caught by the Vault, blocks harmful content.
    *   **Implementation**: AWS Bedrock Guardrails or NeMo Guardrails proxy.

2.  **PII Vault**:
    *   **Tokenization**: Replaces sensitive patterns (Regex-based) with UUID tokens.
    *   **Storage**: Secure ephemeral dictionary or Redis.
    *   **Detokenization**: Only allowed for "Authorized Tools" (e.g., a banking API). The LLM never sees the real data.

3.  **Audit Logging**:
    *   **Structure**: `{timestamp, trace_id, actor, action, thought, input, output, hash}`.
    *   **Tamper-Evidence**: Each log entry includes a hash of the previous entry (Blockchain-style chaining).

---

## 4. Identity Provider Architecture

### Overview

The framework integrates with any OIDC-compliant identity provider via the pluggable `shared/identity_provider.py` module. Authentication is configured entirely through environment variables — no code changes are required to switch providers.

**Supported Providers:** Azure AD (Microsoft Entra ID), Okta, Auth0, AWS Cognito, Keycloak, Generic OIDC

### Authentication Request Flow

```ascii
 Client              Orchestrator /       Identity Provider       MCP Gateway         MCP Server
 (Bearer JWT)        MCP Gateway          (Azure AD / Okta)       (Port 8300)         (Tool)
    |                    |                       |                     |                  |
    | POST /workflow     |                       |                     |                  |
    | Authorization:     |                       |                     |                  |
    |  Bearer <JWT>      |                       |                     |                  |
    |------------------->|                       |                     |                  |
    |                    | GET /jwks_uri         |                     |                  |
    |                    |---------------------->|                     |                  |
    |                    |   {keys: [...]}       |                     |                  |
    |                    |<----------------------|                     |                  |
    |                    |                       |                     |                  |
    |                    | Verify signature,     |                     |                  |
    |                    | expiry, audience      |                     |                  |
    |                    | issuer (local)        |                     |                  |
    |                    |                       |                     |                  |
    |                    | Extract UserContext   |                     |                  |
    |                    | (user_id, roles,      |                     |                  |
    |                    |  scopes, tenant)      |                     |                  |
    |                    |                       |                     |                  |
    |                    |    Forward request + UserContext            |                  |
    |                    |-------------------------------------------->|                  |
    |                    |                       |                     |                  |
    |                    |                       |         GET /api/mcp/tools/{t}/auth   |
    |                    |                       |      (fetch auth schema from Registry) |
    |                    |                       |                     |                  |
    |                    |                       |  OBO Token Exchange |                  |
    |                    |                       |<--------------------|                  |
    |                    |     POST /oauth2/token (on_behalf_of)       |                  |
    |                    |---------------------->|                     |                  |
    |                    |  tool-scoped JWT      |                     |                  |
    |                    |<----------------------|                     |                  |
    |                    |                       |                     |                  |
    |                    |                       | Execute tool with tool-scoped token   |
    |                    |                       |-------------------->|                  |
    |                    |                       |                     | Call tool(...)   |
    |                    |                       |                     |----------------->|
    |                    |                       |                     |    result        |
    |                    |                       |                     |<-----------------||
    |    result          |                       |                     |                  |
    |<-------------------|                       |                     |                  |
```

### Module Structure

```
shared/
├── identity_provider.py     # Core IdP module
│   ├── IdentityProvider      # Main class; validate_token(), get_token_for_scope()
│   ├── UserContext           # Dataclass: user_id, email, roles, scopes, tenant_id
│   ├── TokenCache            # In-memory cache with TTL expiration
│   ├── IdPProvider (enum)    # azure_ad | okta | auth0 | aws_cognito | keycloak | oidc
│   └── ToolAuthRequirement   # Carries required_scopes, audience, token_endpoint
│
└── auth_dependencies.py     # FastAPI Depends() helpers
    ├── get_current_user()    # Validate JWT → return UserContext (401 if invalid)
    ├── get_optional_user()   # Same, but returns anonymous instead of 401
    ├── require_role()        # Factory: enforce a specific role
    ├── require_scope()       # Factory: enforce a specific OAuth scope
    └── get_user_headers()    # Serialize UserContext to HTTP propagation headers
```

### Configuration via Environment Variables

All identity provider settings are externalized. No hardcoded values exist in the codebase.

| Variable | Description | Example |
|---|---|---|
| `AUTH_ENABLED` | Enable/disable authentication | `true` / `false` |
| `AUTH_PROVIDER` | IdP type | `azure_ad`, `okta`, `auth0`, `aws_cognito`, `keycloak`, `oidc` |
| `AUTH_ISSUER` | JWT issuer (`iss` claim) | `https://login.microsoftonline.com/{tid}/v2.0` |
| `AUTH_AUDIENCE` | JWT audience (`aud` claim) | `api://{client-id}` |
| `AUTH_JWKS_URI` | JWKS endpoint for signature validation | `https://.../.well-known/jwks.json` |
| `AUTH_DISCOVERY_URL` | OIDC discovery URL (auto-fills above) | `https://.../.well-known/openid-configuration` |
| `AUTH_CLIENT_ID` | Client ID for client credentials / OBO | `{uuid}` |
| `AUTH_CLIENT_SECRET` | Client secret | `{secret}` |
| `AUTH_VALIDATE_EXPIRY` | Enforce token expiry | `true` |
| `AUTH_REQUIRED_SCOPES` | Comma-separated default required scopes | `api.access` |

### MCP Tool Authentication Schema

Each MCP tool can declare its authentication requirements at registration time. The MCP Gateway queries the Registry before executing a tool, then performs On-Behalf-Of (OBO) token exchange to obtain a tool-scoped token.

```json
{
  "name": "database_query",
  "description": "Query the production database",
  "auth_schema": {
    "auth_type": "oauth",
    "required_scopes": ["database.read", "database.query"],
    "audience": "api://database-service",
    "token_endpoint": "https://login.microsoftonline.com/{tid}/oauth2/v2.0/token"
  }
}
```

The Gateway automatically:
1. Calls `GET /api/mcp/tools/{tool_name}/auth` on the Registry
2. Detects the required scopes and audience
3. Exchanges the user's token for a tool-scoped token via OBO
4. Forwards the tool-scoped token to the MCP server

---

## 5. MCP Tool Integration

The system uses the Model Context Protocol to standardize tool usage.

### Web Search Integration
*   **Server**: `services/mcp_servers/web_search`
*   **Tool**: `search(query)`, `get_content(url)`
*   **Flow**: Research Agent -> MCP Gateway -> Web Search Server -> DuckDuckGo/Google API -> Agent.
*   **Caching**: Prompt caching enabled for search results to reduce latency and cost on repeated queries.

---

## 6. Performance Optimizations

### Prompt Caching
*   **Static Context**: System instructions and tool definitions are marked as `cachePoint` (block type `system`).
*   **Dynamic Context**: Conversation history and variable inputs are appended after the cache point.
*   **Benefit**: Reduces input token processing time and cost by ~90% for long conversations.

### Parallel Execution
*   **Independent Steps**: The Orchestrator identifies steps with no dependencies and schedules them concurrently.
*   **AsyncIO**: All services use Python `asyncio` for non-blocking I/O.

---

**Version**: 2.2
**Last Updated**: 2026-02-23
