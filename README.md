# Agent-to-Agent (A2A) Framework

A generic, extensible framework for autonomous multi-agent collaboration using **AWS Bedrock** and **Model Context Protocol (MCP)**. This system enables complex workflow orchestration, interactive human-in-the-loop tasks, and enterprise-grade security — built for production deployment from day one.

## 🌟 Key Features

*   **🤖 Multi-Agent Orchestration**: Intelligent planning and task delegation via a dedicated **Model Gateway** supporting multiple LLM providers and AWS regions. Uses Amazon Nova Pro (default) with automatic fallback and circuit-breaker protection.
*   **🌐 Real-Time Web Search**: The Research Agent includes a dedicated `search_web` capability that routes live/current-data queries (time, weather, prices, news) to the MCP web-search server — distinct from the `answer_question` LLM-knowledge path.
*   **🔌 MCP Integration**: Standardized tool integration via the Model Context Protocol.
*   **🗣️ Interactive Human-in-the-Loop**: First-class support for pausing workflows mid-execution to request user guidance (text, choices, confirmations) and resuming exactly where the workflow left off.
*   **💾 Context Preservation**: Session-scoped conversation history and thought trails persist across multiple workflows. Supports semantic recall via a pluggable **Vector Memory Store**.
*   **🏗️ High-Availability Orchestrator**: Multi-replica orchestrator support backed by **Redis** for shared workflow state, ownership leasing, cross-instance WebSocket pub/sub fan-out, and an **instance registry**. Pluggable database backend supports **SQLite** (dev) and **PostgreSQL** (production).
*   **🔒 Enterprise Security**:
    *   **Guardrails**: Input/Output filtering for safety and compliance (AWS Bedrock Guardrails).
    *   **PII Vault**: Automatic tokenization of sensitive data (credit cards, SSN, email) before LLM processing; detokenization only for authorized tools.
    *   **Audit Logging**: Immutable, cryptographically chained (blockchain-style) WORM-compliant logs of all agent thoughts, plans, observations, and actions.
    *   **Identity Propagation**: Full user context (`user_id`, `roles`, `scopes`, `tenant_id`) carried through every agent call and tool execution.
*   **⚡ Performance**: Parallel step execution (dependency-graph-aware), prompt caching, exponential backoff retries with jitter, and mustache template resolution for inter-step data passing.
*   **🧠 Pluggable Vector Memory**: Long-term semantic agent recall across sessions. Supports 10+ backends: in-memory, ChromaDB, Pinecone, Qdrant, Weaviate, pgvector, Redis, Amazon OpenSearch, Azure AI Search, and Azure Cosmos DB. Supports multiple embedding providers (AWS Bedrock Titan, OpenAI, Sentence Transformers).
*   **📡 WebSocket Real-Time Interface**: Persistent bidirectional WebSocket connections per workflow for real-time status, thought-trail streaming, and interactive user prompts.

```ascii
                    +---------------------------+
                    |    IDENTITY PROVIDER      |
                    | (Azure AD / Okta / Auth0  |
                    |  Cognito / Keycloak / OIDC)|
                    +------------+--------------+
                                 | JWT Validation /
                                 | Token Issuance
      [ USER / CLI / WS ]        |
            | (Bearer JWT)       |
            v                    v
    +------------------+  Validate   +-------------------+
    |   ORCHESTRATOR   |<----------->|   AUTH MODULE     |
    |   (Port 8100)    |    Token    | (identity_provider|
    +--------+---------+             |  .py + JWKS)      |
             |    |                 +-------------------+
             |    | WebSocket            |
             |    | (real-time)     OBO Token Exchange
             v    v                      |
    +------------------+  +------------------+
    |   AGENT MESH     |  |  SECURITY LAYER  |
    | (Research, Math, |  | (Guardrails/PII/ |
    |  Code, Data...)  |  |  Audit Logging)  |
    +--------+---------+  +------------------+
             |
    +--------+--------+
    |  CONTEXT LAYER  |
    | Vector Memory   |
    | (Qdrant / Redis |
    |  OpenSearch...) |
    +--------+--------+
             |
             | (Tool Call + User Token)
             v
    +------------------+  Auth Schema  +-------------------+
    |   MCP GATEWAY    |<------------->|   MCP REGISTRY    |
    |   (Port 8300)    |  Fetch/Verify | (Tool Auth Reqs)  |
    +--------+---------+               +-------------------+

    LLM Routing (Orchestrator → Model Gateway → Bedrock):
    +-------------------------------------------+
    |          MODEL GATEWAY (Port 8400)        |
    | Provider routing | Circuit breaker        |
    | Amazon Nova / Claude | Multi-region        |
    +-------------------------------------------+
             |
             | (Tool-Scoped Token via OBO)
             v
    +--------------------------------------+
    |           MCP SERVERS                |
    | (Web Search / Calculator / File Ops  |
    |  Database / Custom Tools...)         |
    +--------------------------------------+

    HA Shared State (Redis / PostgreSQL):
    +-------------------------------------------+
    | Workflow State | Session Store | Ownership |
    | Pub/Sub Events | Instance Registry         |
    +-------------------------------------------+
```

---

## 🚀 Quick Start

### Prerequisites
*   Python 3.11+
*   Docker & Docker Compose
*   AWS Credentials (with Bedrock access enabled)

### 1. Setup Environment
```bash
# Clone the repository
git clone https://github.com/alokkulkarni/agentToAgent.git
cd agentToAgent

# Run initial setup (creates venv, installs dependencies)
./scripts/setup.sh

# Configure environment variables
cp services/orchestrator/.env.example services/orchestrator/.env
# Edit .env and add your AWS credentials / identity provider settings
```

> **AWS Credentials**: Docker Compose mounts `~/.aws` into containers at `/app/.aws` (not `/root/.aws`).  
> The env vars `AWS_SHARED_CREDENTIALS_FILE=/app/.aws/credentials` and `AWS_CONFIG_FILE=/app/.aws/config`  
> are set automatically — no manual credential injection needed.

### 2. Start All Services
```bash
# Start everything via Docker Compose (Registry, Redis, Qdrant, Orchestrator,
# MCP Servers, MCP Gateway, all Agents)
docker compose up --build

# Or use the helper script for local non-Docker runs
./scripts/start_services.sh
```

### 3. Run Interactive Chat (CLI)
```bash
python scripts/cli_chat.py
```

**Example Interaction:**
> **You**: "Compare the top cloud providers."
> **Agent**: "I need to know which specific providers you are interested in."
> **You**: "AWS, Azure, and GCP."
> **Agent**: *Proceeds with research...*

### 4. Connect via WebSocket (Real-Time)
```bash
# Open the built-in WebSocket test client
open services/orchestrator/websocket_test_client.html
# Or connect programmatically
python examples/websocket_interactive_workflow.py
```

---

## � Real-Time Web Search Routing

The orchestrator planner automatically distinguishes between queries that need **live data** and those that can be answered from **LLM knowledge**:

| Query type | Capability selected | Agent |
|---|---|---|
| Current time / today's date | `search_web` | ResearchAgent |
| Live prices, weather, news | `search_web` | ResearchAgent |
| Concept explanation, history | `answer_question` | ResearchAgent |
| Arithmetic / math | `calculate` | MathAgent |

The planner enforces this via a hard routing rule: *any query that asks for real-time or live information must use `search_web`, not `answer_question`*.

### Replacing the Mock Web Search with a Real API

The default web search MCP server (`services/mcp_servers/web_search/app.py`) returns placeholder results. To integrate a real search engine:

```bash
# services/mcp_servers/web_search/.env
SEARCH_PROVIDER=brave          # brave | google | bing
BRAVE_API_KEY=your-key-here    # for Brave Search
# GOOGLE_API_KEY / GOOGLE_CSE_ID for Google Custom Search
# BING_API_KEY for Bing
```

Once set, the `search_web` tool in `app.py` will call the real API instead of returning mock results.

---

## �🗣️ Human-in-the-Loop Workflows

The framework treats human interaction as a first-class concern. At any point during execution, an agent can pause the workflow and ask the user for guidance.

### How It Works

1.  An agent determines it needs human input and returns a structured `user_input_required` response via `shared/agent_interaction.py`.
2.  The **Interaction Manager** (`orchestrator/interaction.py`) serializes the request to the database and broadcasts it over WebSocket.
3.  The workflow status transitions to `waiting_for_input`.
4.  The user responds (via REST API, WebSocket, or CLI).
5.  The workflow resumes from the paused step with the user's response injected into agent context.

### Supported Input Types
*   `text` — free-form text answer
*   `single_choice` — pick one option from a list
*   `multiple_choice` — pick multiple options
*   `confirmation` — yes/no approval
*   `file_upload` — provide a file path
*   `number` — numeric value
*   `date` / `rating` / `scale` — specialized input types

### Workflow Status Model
```
pending → planning → running → waiting_for_input → input_received → running → completed
                                                ↓ (timeout)
                                           input_timeout
```

---

## 🔒 Enterprise Security Setup

The framework includes a comprehensive security layer. To configure it:

### 1. Guardrails
The system uses `SafeLLMClient` which wraps standard Bedrock calls.
*   **Configuration**: Point to a real AWS Bedrock Guardrails ID in `.env` (`GUARDRAIL_ID`).
*   **Behavior**: Blocks prompts containing malicious patterns or banned topics; filters outputs.

### 2. PII Vault
Sensitive data is automatically detected and tokenized.
*   **Detected Types**: Credit card numbers, SSN, email addresses.
*   **Storage**: Ephemeral in-memory vault (default). Configure Redis for production.
*   **Usage**: Agents see tokens (e.g., `TOKEN_CC_1`); only authorized tools (like `transfer_funds`) can access real data via the detokenization API.

### 3. Audit Logging
All actions are logged to `audit_logs/`.
*   **Format**: JSON-structured logs with cryptographic chaining (hash of previous entry — blockchain-style WORM).
*   **Content**: `timestamp`, `trace_id`, `actor`, `action`, `thought`, `input`, `output`, `hash`.

### 4. Identity Provider Integration (Enterprise Authentication)
The framework supports integration with multiple identity providers for JWT-based authentication and authorization.

#### Supported Identity Providers
*   **Azure AD (Microsoft Entra ID)**
*   **Okta**
*   **Auth0**
*   **AWS Cognito**
*   **Keycloak**
*   **Any OIDC-compliant provider**

#### Quick Setup
```bash
# 1. Install authentication dependencies
pip install PyJWT[crypto] cryptography httpx

# 2. Configure your identity provider in .env
AUTH_ENABLED=true
AUTH_PROVIDER=azure_ad  # or okta, auth0, cognito, keycloak, oidc
AUTH_ISSUER=https://login.microsoftonline.com/{tenant-id}/v2.0
AUTH_AUDIENCE=api://{your-api-client-id}
AUTH_CLIENT_ID={your-client-id}
AUTH_CLIENT_SECRET={your-client-secret}

# 3. Test your setup
python scripts/test_identity_provider.py
```

#### Features
*   **JWT Token Validation**: RS256/HS256 signature verification with JWKS auto-discovery
*   **Role-Based Access Control (RBAC)**: Enforce roles on endpoints
*   **Scope-Based Access Control**: Fine-grained permissions via OAuth scopes
*   **On-Behalf-Of (OBO) Token Exchange**: Automatically exchange user tokens for tool-specific tokens
*   **Token Caching**: Performance optimization with automatic expiry handling
*   **MCP Tool Authentication**: MCP servers can declare authentication requirements; gateway handles token exchange

#### API Usage
```bash
# Get JWT token from your identity provider
TOKEN=$(curl -X POST https://your-idp.com/oauth2/token \
  -d grant_type=client_credentials \
  -d client_id=your-client-id \
  -d client_secret=your-client-secret \
  -d scope=api.access | jq -r .access_token)

# Use token to execute workflow
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Analyze sales data"}'
```

#### Documentation
*   **[Identity Provider Setup Guide](docs/IDENTITY_PROVIDER_SETUP.md)**: Detailed configuration for each IdP.
*   **[Identity Integration Summary](docs/IDENTITY_INTEGRATION_SUMMARY.md)**: Architecture and features overview.
*   **Setup Script**: `./scripts/setup_identity_provider.sh` — Automated setup helper.
*   **Test Script**: `./scripts/test_identity_provider.py` — Verify your configuration.

#### Development Mode
For local development, you can disable authentication:
```bash
# In .env
AUTH_ENABLED=false
```

---

## 🏗️ High-Availability Configuration

The orchestrator supports multi-replica deployment with shared state via Redis and PostgreSQL.

### Distributed State (Redis)
```bash
# In services/orchestrator/.env
HA_BACKEND=redis
REDIS_URL=redis://redis:6379
ORCHESTRATOR_INSTANCE_ID=orchestrator-1
ORCHESTRATOR_PUBLIC_ENDPOINT=http://orchestrator-1:8100
WORKFLOW_STATE_TTL=86400
```

Shared capabilities:
*   **Workflow state** — active workflows readable by any replica
*   **Session store** — session history shared across instances
*   **Ownership leasing** — only one replica executes a given workflow at a time (prevents duplicate execution)
*   **Pub/Sub fan-out** — WebSocket events broadcast to all replicas so any connected client receives updates

### Pluggable Database Backend
```bash
# SQLite (default — single-node development)
WORKFLOW_DB_BACKEND=sqlite
SQLITE_DB_PATH=/app/data/workflows.db

# PostgreSQL (recommended for production HA)
WORKFLOW_DB_BACKEND=postgresql
DATABASE_URL=postgresql://user:pass@postgres:5432/orchestrator
```

---

## 🧠 Vector Memory (Long-Term Recall)

Agents can store and semantically retrieve memories across sessions.

```bash
# Enable in .env
VECTOR_MEMORY_ENABLED=true
VECTOR_MEMORY_BACKEND=qdrant        # qdrant is included in docker-compose
VECTOR_MEMORY_EMBEDDING=bedrock     # uses AWS Titan Embeddings
VECTOR_MEMORY_COLLECTION=a2a_memories
VECTOR_MEMORY_TOP_K=5
VECTOR_MEMORY_SCORE_THRESHOLD=0.3
```

**Supported Backends**: `in_memory`, `chromadb`, `pinecone`, `qdrant`, `weaviate`, `pgvector`, `redis`, `opensearch_aws`, `azure_ai_search`, `azure_cosmos`

**Supported Embedding Providers**: `bedrock` (Titan), `openai`, `sentence_transformers`, `none`

---

## 📚 Documentation

*   **[ARCHITECTURE.md](docs/ARCHITECTURE.md)**: Detailed system design, HA architecture, security flows, and component interaction.
*   **[DEPLOYMENT_SUMMARY.md](docs/DEPLOYMENT_SUMMARY.md)**: Central hub for all deployment guides.
*   **[AWS Deployment](docs/DEPLOYMENT_AWS.md)**: Deployment on ECS Fargate, EKS, and EC2.
*   **[Azure Deployment](docs/DEPLOYMENT_AZURE.md)**: Deployment on ACA, AKS, and VMs.
*   **[General Deployment](docs/DEPLOYMENT.md)**: Local Docker Compose setup.
*   **[Testing Guide](docs/TESTING_GUIDE.md)**: Test suite overview and how to run tests.
*   **[Interactive Workflow Examples](docs/INTERACTIVE_WORKFLOW_EXAMPLES.md)**: Human-in-the-loop usage examples.

---

## 🛠️ Service Architecture

### Orchestrator (Port 8100) — The "Brain"
*   **Workflow Planning**: Decomposes tasks into dependency-ordered steps using Claude 3.5 Sonnet.
*   **Parallel Execution**: Executes independent steps concurrently via a dependency-graph-aware `ParallelExecutor` with configurable concurrency (`max_parallel_steps`).
*   **Context Enrichment**: Auto-resolves `{{step_id.result}}` mustache templates to pass outputs from earlier steps into later steps.
*   **Retry Engine**: Per-step exponential backoff with jitter; configurable `max_retries`, `retriable_errors`.
*   **Conversation Manager**: Persists per-workflow `ConversationMessage` and `ThoughtTrailEntry` records.
*   **Interaction Manager**: Suspends/resumes workflows for human-in-the-loop input with configurable timeouts.
*   **WebSocket Handler**: `ConnectionManager` maintains per-workflow WebSocket fan-out; broadcasts status, thoughts, and interaction requests in real time.

### Agent Mesh

| Agent | Port | Capabilities |
|---|---|---|
| Code Analyzer | 8001 | `analyze_python_code`, `explain_code`, `suggest_improvements`, `detect_bugs` |
| Data Processor | 8002 | `transform_data`, `analyze_data`, `summarize_data` |
| Research Agent | 8003 | `search_web` *(real-time/live data)*, `answer_question` *(LLM knowledge)*, `generate_report`, `compare_concepts` |
| Task Executor | 8004 | `execute_command`, `file_operations`, `wait_task` |
| Observer | 8005 | `system_monitoring`, `event_logging`, `metrics_reporting`, `agent_statistics` |
| Math Agent | 8006 | `calculate`, `advanced_math`, `solve_equation`, `statistics` |

### MCP Servers (The "Hands")

| Server | Port | Tools |
|---|---|---|
| File Ops | 8210 | `read_file`, `write_file`, `list_files` |
| Database | 8211 | `query_database`, `execute_sql` |
| Web Search | 8212 | `search_web` — returns live search results (mock by default; swap with Brave/Google API) |
| Calculator | 8213 | `calculate` |

### Infrastructure Services

| Service | Port | Purpose |
|---|---|---|
| Agent Registry | 8000 | Agent discovery, heartbeat, health |
| MCP Registry | 8200 | Tool catalog, auth schemas |
| MCP Gateway | 8300 | JWT validation, OBO exchange, tool routing |
| Model Gateway | 8400 | LLM provider routing, circuit breaker, multi-region Bedrock support |
| Redis | 6379 | HA shared state, pub/sub, session store |
| Qdrant | 6333 | Vector memory store |

### Model Gateway (Port 8400)

The Model Gateway decouples LLM provider selection from agent code. The orchestrator sends all planning requests through the gateway, which handles:

*   **Provider routing** — Bedrock (default), with hookpoints for Azure OpenAI, OpenAI, and other providers.
*   **Circuit breaker** — Opens automatically after repeated `ValidationException` / 5xx errors; resets on recovery.
*   **Health probe** — Periodic lightweight inference call (configurable model) to gate the circuit state.
*   **Multi-region awareness** — Amazon Nova models are available in all AWS regions. Claude models require `us-east-1`; the gateway enforces this at routing time.

#### Key Environment Variables

```bash
# services/model_gateway/.env  (or docker-compose environment)
BEDROCK_REGION=eu-west-2                         # AWS region for Bedrock calls
BEDROCK_HEALTH_PROBE_MODEL=amazon.nova-micro-v1:0  # Lightweight model for health checks

# services/orchestrator/.env
LLM_PROVIDER=model_gateway                        # Route all LLM calls through the gateway
MODEL_GATEWAY_URL=http://model-gateway:8400
# Use a Nova model when deploying in non-us-east-1 regions (Claude unavailable there)
MODEL_GATEWAY_PREFERRED_MODEL=amazon.nova-pro-v1:0
```

> **Region note**: If you are running in `us-east-1` you may set `MODEL_GATEWAY_PREFERRED_MODEL=anthropic.claude-3-5-sonnet-20241022-v2:0`. For any other region use an Amazon Nova model (e.g. `amazon.nova-pro-v1:0`).

---

## 🧪 Testing

```bash
# Run core test suite
python -m pytest tests/

# Interactive workflow tests
python scripts/test_interactive_complete.py
python scripts/test_websocket_interactive.py

# Identity provider tests
python scripts/test_identity_provider.py

# MCP math agent tests
python scripts/test_mcp_math_agent.py

# Full distributed system test
python scripts/test_distributed_system.py
```

---

**Version**: 3.1
**Last Updated**: 2026-03-20

### Recent Changes (v3.1)
- **Model Gateway** (port 8400): New LLM routing service with circuit breaker, health probe, and multi-region Bedrock support.
- **Amazon Nova model support**: `MODEL_GATEWAY_PREFERRED_MODEL=amazon.nova-pro-v1:0` enables deployment in all AWS regions, not just `us-east-1`.
- **`search_web` capability** on ResearchAgent: Dedicated routing path for real-time/live queries via the MCP web-search server.
- **Smart planner routing rule**: Orchestrator planner enforces mandatory `search_web` selection for any time/date/live-data query.
- **AWS credential mount fix**: Credentials now mounted to `/app/.aws` (previously `/root/.aws`, which was inaccessible to the container user).
- **Health probe model fix**: Model Gateway health check uses `amazon.nova-micro-v1:0` (configurable via `BEDROCK_HEALTH_PROBE_MODEL`).
