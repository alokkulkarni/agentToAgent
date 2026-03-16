# System Architecture

## Overview

The Agent-to-Agent (A2A) framework is a distributed, microservices-based system designed for autonomous multi-agent collaboration. It leverages **AWS Bedrock (Claude 3.5 Sonnet)** for LLM capabilities and the **Model Context Protocol (MCP)** for standardized tool integration. The system is designed with enterprise-grade security, auditability, high-availability, and context preservation at its core.

**Current version**: 3.0 — adds HA multi-replica orchestrator, distributed state via Redis, Vector Memory with 10+ backends, WebSocket real-time interface, pluggable database backends, mustache inter-step template resolution, and a full Conversation + Thought Trail persistence layer.

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
[ USER / CLI / WS ] -(Bearer JWT)->+              |
      |                        |                  |
      | WebSocket              |                  |
      | (real-time)   +--------+--------+         |
[ INTERACTION  ]      |   ORCHESTRATOR  |<--------+
[ MANAGER      ]<---->|  (Port 8100)    |
                      +--------+--------+
                               |
               +---------------+---------------+
               |               |               |
      +--------+--------+  +---+---+  +--------+---------+
      |  CONTEXT STORE  |  | RETRY |  |  SECURITY LAYER  |
      | (Conversation + |  | ENGINE|  | (Guardrails/PII  |
      |  Thought Trail) |  |       |  |  Vault/Audit Log)|
      +-----------------+  +-------+  +------------------+
               |
      +--------+--------+
      |  VECTOR MEMORY  |
      | (Qdrant/OpenSearch
      |  /Redis/Pinecone)|
      +--------+--------+
               |
      +--------+--------+
      |   AGENT MESH    |
      | (Research, Code,|
      |  Data, Math...) |
      +--------+--------+
               |
   +-----------+-------------------+
   |  MCP GATEWAY (Port 8300)      |
   |  - Validates JWT              |
   |  - Fetches Tool Auth Schema   |
   |  - Performs OBO Token Exchange|
   +--------+-----------+----------+
            |           |
(Tool Token)|           |(Auth Schema)
            v           v
   +--------+--+  +-----+-----------+
   | MCP SERVERS|  |  MCP REGISTRY  |
   | (Search,   |  | (Tool Auth     |
   |  Calc, DB) |  |  Requirements) |
   +------------+  +----------------+

   HA Shared State Layer:
   +---------------------------------------------------+
   | Redis: Workflow State | Session Store | Ownership |
   |        Pub/Sub Fan-out | Instance Registry        |
   |                                                   |
   | PostgreSQL / SQLite: Workflow + Step records,     |
   |  Conversation messages, Thought trail, Interaction|
   |  requests + responses                             |
   +---------------------------------------------------+
```

---

## 1. Core Services

### Orchestrator (Port 8100)
The central nervous system of the framework.
- **Workflow Planning**: Uses Claude 3.5 Sonnet to decompose user requests into dependency-ordered, executable steps.
- **Context Management**: Maintains global conversation history across multiple workflows using a `session_id`. Aggregates summaries of prior workflows and injects them into new planner prompts.
- **State Management**: Persists all workflow, step, conversation, thought trail, and interaction records via a pluggable `WorkflowDatabase` (SQLite default, PostgreSQL for production).
- **Context Enrichment**: Resolves `{{step_id.result}}` mustache templates at execution time, passing outputs from earlier steps as inputs to later steps.
- **Authentication**: Validates JWT tokens via `shared/auth_dependencies.py`; injects `UserContext` into all workflow executions.
- **Security Integration**: Enforces guardrails, PII vault, audit logging, and identity propagation.

### Interaction Manager (`orchestrator/interaction.py`)
Handles human-in-the-loop scenarios with first-class database + WebSocket support.
- **Suspension**: Pauses workflows when an agent returns a `user_input_required` response; transitions status to `waiting_for_input`.
- **Resumption**: Resumes execution from the suspended step with user response injected into agent context; transitions to `running`.
- **Timeout Handling**: Auto-transitions to `input_timeout` if no response is received within a configurable window (`default_timeout_seconds`).
- **Input Types**: `text`, `single_choice`, `multiple_choice`, `confirmation`, `file_upload`, `number`, `date`, `rating`, `scale`.
- **Persistence**: `InteractionRequest` and `InteractionResponse` are stored in the database, enabling audit and replay.

### WebSocket Handler (`orchestrator/websocket_handler.py`)
Real-time bidirectional interface for interactive workflows.
- **ConnectionManager**: Maintains a `workflow_id → Set[WebSocket]` map with async locking.
- **Fan-out**: Broadcasts status updates, thought trail entries, agent messages, and interaction requests to all connected clients for a workflow.
- **Cross-Instance Fan-out (HA)**: When Redis pub/sub is configured (`HA_BACKEND=redis`), events are published cross-replica so any connected client — on any orchestrator instance — receives updates.
- **Events**: `connection_established`, `workflow_status`, `agent_thought`, `interaction_request`, `workflow_complete`, `workflow_error`.

### Parallel Executor (`orchestrator/executor.py`)
Dependency-graph-aware concurrent step execution.
- **Dependency Graph**: Builds a DAG from `StepRecord.dependencies` (list of step IDs).
- **Ready Steps**: Continuously identifies steps whose dependencies are all completed.
- **Semaphore Control**: `asyncio.Semaphore(max_parallel_steps)` caps concurrency.
- **Per-Step Timeout**: `asyncio.wait_for` with a configurable `step_timeout_seconds`.

### Retry Manager (`orchestrator/retry.py`)
- **Exponential Backoff**: `initial_delay * (base ** retry_count)` capped at `max_delay_seconds`.
- **Jitter**: Random multiplier in `[0.5, 1.5]` to prevent thundering herd.
- **Retriable Error Classification**: Configurable list of error substrings that trigger a retry.

### Conversation Manager (`orchestrator/conversation.py`)
- **Per-workflow context**: Tracks `ConversationMessage` records (role: `user | agent | orchestrator | system`; type: `task | message | thought | result | interaction_request | interaction_response`).
- **Thought Trail**: Separate `ThoughtTrailEntry` records log orchestrator reasoning steps (type: `reasoning | planning | observation | decision`).
- **Persistence**: All records saved to the workflow database; full history retrievable for audit or replay.

### Security Layer
Enterprise-grade security features embedded in the framework.
- **SafeLLMClient (`shared/llm_client.py`)**: A wrapper around the AWS Bedrock client that enforces input/output guardrails before and after every LLM call.
- **PII Vault (`shared/security.py`)**: Regex-based detection and UUID tokenization of credit cards, SSNs, and email addresses. Only authorized tools can call the detokenization API; the LLM never receives raw sensitive values.
- **Audit Logger (`shared/audit.py`)**: WORM-compliant cryptographic chain logging. Each entry includes `{timestamp, trace_id, actor, action, thought, input, output, hash}` where `hash = SHA256(previous_hash + current_entry)`.
- **Identity Propagation**: Propagates `UserContext` (user_id, roles, scopes, tenant_id) to every agent call and MCP tool execution via HTTP headers.

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
