# Agent-to-Agent (A2A) Framework — Complete Component Reference

> **Document scope**: Every service, shared module, protocol layer, infrastructure component, and supporting tool in this solution. Covers purpose, capabilities, resilience patterns, and performance characteristics.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture At a Glance](#2-architecture-at-a-glance)
3. [Core Infrastructure Services](#3-core-infrastructure-services)
   - 3.1 [Registry Service](#31-registry-service)
   - 3.2 [MCP Registry Service](#32-mcp-registry-service)
   - 3.3 [Redis (Shared State)](#33-redis-shared-state)
   - 3.4 [Qdrant (Vector Store)](#34-qdrant-vector-store)
4. [Orchestrator Service](#4-orchestrator-service)
   - 4.1 [Workflow Engine](#41-workflow-engine)
   - 4.2 [LLM Planning Layer](#42-llm-planning-layer)
   - 4.3 [Context Enrichment](#43-context-enrichment)
   - 4.4 [Parallel Executor](#44-parallel-executor)
   - 4.5 [Retry Manager & Circuit Breaker](#45-retry-manager--circuit-breaker)
   - 4.6 [WebSocket Handler](#46-websocket-handler)
   - 4.7 [Interaction Manager (Human-in-the-Loop)](#47-interaction-manager-human-in-the-loop)
   - 4.8 [Conversation Manager](#48-conversation-manager)
   - 4.9 [Workflow Database](#49-workflow-database)
   - 4.10 [HA Database Layer](#410-ha-database-layer)
5. [Specialized Agent Services](#5-specialized-agent-services)
   - 5.1 [Code Analyzer Agent](#51-code-analyzer-agent)
   - 5.2 [Data Processor Agent](#52-data-processor-agent)
   - 5.3 [Research Agent](#53-research-agent)
   - 5.4 [Math Agent](#54-math-agent)
   - 5.5 [Task Executor Agent](#55-task-executor-agent)
   - 5.6 [Observer Agent](#56-observer-agent)
6. [MCP Tool Layer](#6-mcp-tool-layer)
   - 6.1 [MCP Gateway Service](#61-mcp-gateway-service)
   - 6.2 [Calculator MCP Server](#62-calculator-mcp-server)
   - 6.3 [Database MCP Server](#63-database-mcp-server)
   - 6.4 [File Operations MCP Server](#64-file-operations-mcp-server)
   - 6.5 [Web Search MCP Server](#65-web-search-mcp-server)
7. [Shared Library Modules](#7-shared-library-modules)
   - 7.1 [A2A Protocol (Models & Client)](#71-a2a-protocol-models--client)
   - 7.2 [Safe LLM Client](#72-safe-llm-client)
   - 7.3 [Guardrail Service](#73-guardrail-service)
   - 7.4 [Audit Logger](#74-audit-logger)
   - 7.5 [Security Manager](#75-security-manager)
   - 7.6 [Identity Provider](#76-identity-provider)
   - 7.7 [Auth Dependencies](#77-auth-dependencies)
   - 7.8 [Vector Memory Store](#78-vector-memory-store)
   - 7.9 [Distributed State](#79-distributed-state)
   - 7.10 [Configuration Manager](#710-configuration-manager)
   - 7.11 [Agent Interaction Helper](#711-agent-interaction-helper)
8. [Deployment & Container Topology](#8-deployment--container-topology)
9. [Resilience Patterns Summary](#9-resilience-patterns-summary)
10. [Performance Characteristics](#10-performance-characteristics)
11. [Port Reference](#11-port-reference)

---

## 1. System Overview

The A2A (Agent-to-Agent) framework is an enterprise-grade, multi-agent orchestration platform. It allows a human operator (or another system) to describe a high-level task in natural language; the orchestrator then decomposes that task, selects the right specialized agents, executes the plan, and returns composed results — all while enforcing security guardrails, maintaining an immutable audit trail, and preserving full conversation context.

**Key design principles:**

| Principle | Implementation |
|---|---|
| Loose coupling | Every component is an independent FastAPI service communicating over HTTP |
| Protocol-driven | All agent-to-agent messages follow the shared A2A protocol schema |
| LLM-guided planning | AWS Bedrock (Claude 3.5 Sonnet) produces dynamic execution plans |
| Security-first | PII tokenization, guardrails, RBAC, and audit logging are non-negotiable |
| Cloud-native | Docker Compose dev topology; designed for production HA on any cloud |
| Human-in-the-loop | Workflows can pause mid-execution and wait for real user input |
| Pluggable backends | Vector store, distributed state, identity provider, and DB are all swappable |

---

## 2. Architecture At a Glance

```
                         ┌───────────────────────┐
                         │     Human / Client     │
                         │  REST  │  WebSocket     │
                         └────────┬──────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │      ORCHESTRATOR           │
                    │  ┌─────────────────────┐   │
                    │  │  LLM Planning (AWS  │   │
                    │  │  Bedrock / Claude)  │   │
                    │  └─────────────────────┘   │
                    │  Parallel Executor  Retry   │
                    │  HITL Interaction   WebSocket│
                    │  Conversation Mgr   Audit   │
                    └──────┬──────────────┬───────┘
                           │              │
              ┌────────────▼──┐     ┌─────▼─────────┐
              │    REGISTRY   │     │   MCP GATEWAY  │
              │  Agent disco- │     │  Tool routing  │
              │  very & HB    │     │  + auth        │
              └────────────┬──┘     └─────┬──────────┘
                           │              │
        ┌──────────────────┼──────────────┼──────────────────┐
        │                  │              │                    │
   ┌────▼────┐  ┌──────────▼┐  ┌─────────▼──┐   ┌───────────▼┐
   │  Code   │  │  Research  │  │  Math      │   │  Data      │
   │Analyzer │  │  Agent     │  │  Agent     │   │ Processor  │
   └─────────┘  └───────────┘  └────────────┘   └────────────┘
        │
┌───────▼───────────────────────────────────────────────┐
│                  MCP SERVERS TIER                      │
│  Calculator │ Database │ File Ops │ Web Search         │
└───────────────────────────────────────────────────────┘

Supporting:  Redis (distributed state)  │  Qdrant (vector memory)
             MCP Registry               │  SQLite / PostgreSQL (workflow DB)
```

---

## 3. Core Infrastructure Services

### 3.1 Registry Service

| Attribute | Value |
|---|---|
| Location | `services/registry/` |
| Default port | **8000** |
| Technology | FastAPI, httpx, A2A protocol |

**Purpose**

The Registry Service is the central directory for all agent services. Every agent — including the orchestrator itself — must register before it can participate in workflows. The registry maintains real-time agent availability using heartbeats.

**Features**

- **Agent registration** — accepts `AgentMetadata` (ID, name, role, capabilities list, endpoint URL, LLM support flag).
- **Capability indexing** — maintains an inverted index `capability → [agent_ids]` enabling the orchestrator to query "which agent can do X?" in O(1).
- **Role indexing** — agents are indexed by role (`orchestrator`, `specialized`, `worker`, `observer`).
- **Discovery API** — supports filtering by `capability` and/or `role` query parameters.
- **Heartbeat tracking** — each agent sends a `POST /api/registry/heartbeat/{agent_id}` every 30 seconds. The registry records the timestamp.
- **Stale agent eviction** — a background `asyncio` task runs every 30 seconds and removes agents whose last heartbeat is older than 60 seconds. This prevents the orchestrator from routing tasks to dead agents.
- **Statistics endpoint** — `GET /api/registry/stats` returns total agent count, per-role counts, and per-capability agent counts.

**Resilience**

- Stale-agent cleanup loop is crash-isolated from the HTTP request path; a failure in cleanup does not affect registrations or lookups.
- All storage is in-memory for speed. If the registry restarts, agents automatically re-register on their own startup health-check failures — every agent calls `register_with_registry()` inside its FastAPI `lifespan` function.
- Docker health check (`/health`) with 5 retries and 15-second start period prevents dependent services from starting before the registry is ready.

**Performance**

- Pure in-memory dictionary lookups: O(1) for registration, O(1) for discovery by capability.
- Async FastAPI with uvicorn workers; non-blocking I/O throughout.

---

### 3.2 MCP Registry Service

| Attribute | Value |
|---|---|
| Location | `services/mcp_registry/` |
| Default port | **8200** |
| Technology | FastAPI, Pydantic |

**Purpose**

Acts as the service directory for MCP (Model Context Protocol) tool servers. While the Agent Registry tracks agent services, the MCP Registry tracks fine-grained tools exposed by individual MCP servers.

**Features**

- **MCP server registration** — MCP servers register with their `name`, `description`, `base_url`, and full `tools` list (each tool has a `name`, `description`, and JSON input schema).
- **Tool indexing** — maintains an inverted index `tool_name → [server_ids]`.
- **Heartbeat support** — MCP servers can refresh their `last_heartbeat` timestamp.
- **Tool discovery** — `GET /api/mcp/tools` returns all available tools across all registered servers; filterable by tool name.
- **Server listing** — `GET /api/mcp/servers` lists all registered MCP servers with their full metadata.
- **Health endpoint** — reports number of registered servers and tools.

**Resilience**

- In-memory storage; MCP servers re-register at startup.
- Depends on the Agent Registry being healthy before starting (Docker `service_healthy` condition).
- Heartbeat-based status tracking; servers marked inactive if no heartbeat arrives within a configurable window.

**Performance**

- Sub-millisecond tool lookups via in-memory dict.
- Stateless HTTP; scales horizontally if needed.

---

### 3.3 Redis (Shared State)

| Attribute | Value |
|---|---|
| Image | `redis:7-alpine` |
| Port | **6379** |
| Configuration | AOF persistence, 256 MB max-memory with LRU eviction |

**Purpose**

Redis is the backbone for multi-instance (HA) orchestrator deployments. When `HA_BACKEND=redis` is configured, the orchestrator replaces all per-process Python dicts with Redis-backed stores, enabling any number of orchestrator replicas to share workflow state seamlessly.

**Features**

- **Workflow state store** — live `active_workflows` state serialised as JSON strings with configurable TTL (default 24 hours) after completion.
- **Session history store** — per-session conversation history lists (`RPUSH` / `LRANGE`).
- **Ownership with TTL** — each workflow is "claimed" by an orchestrator instance using `SETNX` with a 30-second TTL. Instances must send heartbeats to maintain ownership, preventing orphaned workflows.
- **Pub/Sub fan-out** — cross-instance WebSocket event broadcasting. When an orchestrator instance broadcasts a workflow event, it also publishes to a Redis channel. Other instances subscribe and forward events to their own WebSocket clients, eliminating the need for sticky sessions.
- **Instance registry** — records the public HTTP endpoint of each running orchestrator instance with a 60-second TTL, enabling the pub/sub receiver on one instance to proxy WebSocket upgrade requests to the owning instance.

**Resilience**

- AOF (Append-Only File) persistence (`--appendonly yes`) ensures Redis state survives a container restart.
- LRU eviction (`allkeys-lru`) prevents unbounded memory growth while preserving the most recently-accessed workflow states.
- Docker health check (`redis-cli ping`) gates dependent services.

**Performance**

- All operations are O(1) or O(log N). Workflow state reads/writes complete in < 1 ms on typical hardware.
- Pub/Sub latency is sub-millisecond within a local Docker network.

---

### 3.4 Qdrant (Vector Store)

| Attribute | Value |
|---|---|
| Image | `qdrant/qdrant:latest` |
| Ports | **6333** (REST), **6334** (gRPC) |
| Volume | `qdrant-data` persistent volume |

**Purpose**

Provides the vector database backend for the orchestrator's long-term semantic memory (`VECTOR_MEMORY_BACKEND=qdrant`). The orchestrator stores embeddings of completed workflow results and retrieves semantically similar past experiences to enrich future planning.

**Features**

- HNSW index for approximate nearest-neighbour search.
- Persistent storage on a named Docker volume (`qdrant-data`).
- REST and gRPC interfaces; the orchestrator uses REST via `qdrant-client`.

**Resilience**

- Data persisted to the `qdrant-data` Docker volume; survives container restarts.
- Startup health check using TCP probe. Orchestrator waits for Qdrant to be healthy before starting.

**Performance**

- HNSW queries are O(log N), providing millisecond retrieval even across millions of vectors.
- Top-K retrieval with configurable score threshold (`VECTOR_MEMORY_SCORE_THRESHOLD=0.3`) avoids irrelevant recall.

---

## 4. Orchestrator Service

| Attribute | Value |
|---|---|
| Location | `services/orchestrator/` |
| Default port | **8100** |
| Technology | FastAPI, AWS Bedrock, SQLite/PostgreSQL, Redis, Qdrant, WebSockets |

The Orchestrator is the central intelligence of the entire system. It accepts natural-language task descriptions from clients, uses an LLM to produce an execution plan, dispatches steps to specialised agents, aggregates results, and returns a final composed answer. It supports both REST and WebSocket interfaces and can pause mid-execution to collect human input.

---

### 4.1 Workflow Engine

**Features**

- Accepts `POST /api/orchestrate` with a `task_description` string plus optional `session_id`, `user_context`, and `workflow_config` overrides.
- Generates a unique `workflow_id` (UUID) for every execution.
- Persists workflow state immediately upon creation so that it survives restarts.
- Tracks workflow lifecycle through states: `pending → planning → running → completed / failed / cancelled`.
- Additional HITL states: `waiting_for_input → input_received` (or `input_timeout`).
- `GET /api/workflows/{workflow_id}` — retrieve full workflow record including all step results.
- `GET /api/workflows` — list workflows with configurable limit and status filter.
- `DELETE /api/workflows/{workflow_id}` — cancel a running or pending workflow.
- `GET /api/health` — liveness check reporting registry connectivity, Bedrock availability, active workflow count, and distributed-state backend type.

---

### 4.2 LLM Planning Layer

**Features**

- Sends the task description plus all currently-registered agent capabilities to Claude 3.5 Sonnet via AWS Bedrock `converse` API.
- The LLM returns a structured JSON execution plan listing steps in order, each with: `step_id`, `description`, `capability`, `agent` (optional preference), `parameters`, and `dependencies` (list of step IDs that must complete first).
- The plan supports **parallel steps** — any steps without overlapping dependencies are eligible for simultaneous execution.
- **Mustache template syntax** — the LLM may reference prior step results using `{{step_id.field}}` notation (e.g. `{{step_1.result}}`), which the context enrichment layer resolves at runtime.
- **Session memory injection** — before planning, the orchestrator retrieves the last 5 entries from the session's conversation history and injects them into the planning prompt, enabling multi-turn, context-aware task decomposition.
- **Vector memory recall** — the orchestrator queries the vector store for semantically similar past workflow summaries and optionally includes them in the system prompt to inform planning.

---

### 4.3 Context Enrichment

**Features**

The `enrich_with_workflow_context()` function dynamically resolves and injects upstream step results into downstream step parameters before dispatch. Resolution strategies (applied in priority order):

1. **Mustache template resolution** — replaces `{{step_id.field}}` patterns using the live step-results map.
2. **Generic template replacement** — resolves `<result_from_step_N>` and `<output_from_step_N>` placeholders.
3. **Capability-aware injection** — for `generate_report`, `analyze_data`, `summarize_data`: auto-injects the most recent relevant upstream result into the `data` or `content` parameter.
4. **Math-specific extraction** — for `calculate` and `advanced_math`: parses numeric step references and substitutes actual computed values.
5. **Session history injection** — for `answer_question`, `generate_report`, `research`, `explain_code`: prepends the last 5 turns of conversation history as `context`.
6. **Generic fallback** — maps the last completed step's result to the most likely parameter name.

This makes individual agents stateless and loosely coupled — they receive all required data in each task request without needing direct knowledge of other agents.

---

### 4.4 Parallel Executor

**Features**

- `ParallelExecutor` class manages concurrent step execution using an `asyncio.Semaphore` to cap simultaneous agent calls (default `MAX_PARALLEL_STEPS=5`).
- Builds a dependency graph from step definitions; only dispatches steps whose dependencies have all completed.
- Each step runs in its own `asyncio.Task` wrapped in `asyncio.wait_for` with a configurable timeout (`STEP_TIMEOUT=300` seconds).
- `WorkflowExecutor` drives the outer execution loop, polling for ready steps, dispatching them, and updating the distributed-state workflow record after each completion.

**Resilience**

- `TimeoutError` from `asyncio.wait_for` is caught and converted to a structured failure result, not an unhandled exception.
- Semaphore prevents agent overload during fan-out phases.
- Dependency graph ensures data integrity: a downstream step never executes before its inputs are available.

---

### 4.5 Retry Manager & Circuit Breaker

**Features**

`RetryManager` (in `retry.py`):

- Per-step configurable: `max_retries`, `initial_delay_seconds`, `max_delay_seconds`, `exponential_base`.
- **Exponential backoff with jitter** — delay = `min(initial × base^attempt, max_delay) × (0.5 + random())`. Jitter prevents thundering-herd re-attempts across multiple concurrent steps.
- **Error classification** — `is_retriable_error()` checks the error message against a configurable allowlist of retriable patterns: `timeout`, `connection`, `network`, `temporary`, `unavailable`, `503`, `502`, `500`. Non-retriable errors (e.g., validation errors) fail immediately without burning retry budget.
- `execute_with_retry()` wraps any async callable, transparently handling retries.

`CircuitBreaker`:

- Per-agent circuit breaker with configurable `failure_threshold` (default 5) and `reset_timeout`.
- States: `CLOSED` (normal) → `OPEN` (failing) → `HALF_OPEN` (trial) → `CLOSED` (recovered).
- Prevents cascading failures by fast-failing requests to a degraded agent instead of piling up timeouts.

**Default retry policy** (from `WorkflowConfig`):

```
max_retries: 3
initial_delay: 1.0s
max_delay: 60.0s
base: 2.0
jitter: true
```

---

### 4.6 WebSocket Handler

**Features**

- `ConnectionManager` tracks active WebSocket connections keyed by `workflow_id`, supporting multiple simultaneous subscribers per workflow (e.g., multiple browser tabs).
- Clients connect to `WS /api/ws/{workflow_id}` to receive real-time events for a specific workflow.
- Event types pushed to clients: `connection_established`, `workflow_started`, `step_started`, `step_completed`, `step_failed`, `workflow_completed`, `workflow_failed`, `waiting_for_input` (HITL prompt), `input_received`, `thought_update`, `message`.
- `WebSocketMessageHandler` also processes inbound messages from clients: `provide_input` (HITL response), `cancel_workflow`, `get_status`.

**HA Fan-out**

When the orchestrator runs as multiple replicas behind a load balancer, WebSocket clients may connect to a different instance than the one executing the workflow. The HA broadcast wrapper:

1. Delivers events directly to all WebSocket clients connected to the **local** instance.
2. Publishes the same event to the Redis pub/sub channel for `workflow_id`.
3. Every other orchestrator instance (subscribed to all pub/sub channels) receives the event and forwards it to any local WebSocket clients watching that workflow.

This eliminates the need for sticky-session load balancing and enables true horizontal scaling of the WebSocket layer.

**Cross-instance proxy**

If a WebSocket client connects to instance B but the workflow is owned by instance A, instance B looks up instance A's `ORCHESTRATOR_PUBLIC_ENDPOINT` from the instance registry and proxies the WebSocket upgrade request to instance A. The client is transparently redirected.

---

### 4.7 Interaction Manager (Human-in-the-Loop)

**Features**

`InteractionManager` enables agents to pause workflow execution and solicit structured human input:

- **Input types supported**: `text`, `single_choice`, `multiple_choice`, `confirmation`, `structured_data`, `file_upload`.
- When an agent returns `status: user_input_required`, the orchestrator:
  1. Saves an `InteractionRequest` to the database.
  2. Transitions the workflow to `waiting_for_input`.
  3. Broadcasts a `waiting_for_input` WebSocket event carrying the full `InteractionRequest` (question, options, reasoning, partial results, timeout).
  4. Suspends the affected step's coroutine, awaiting a response future.
- Clients respond via:
  - `POST /api/workflows/{workflow_id}/interact` (REST).
  - `provide_input` WebSocket message.
- On response receipt, the orchestrator:
  1. Saves the response and timestamps it.
  2. Resolves the awaiting future, resuming the suspended step coroutine.
  3. Transitions the workflow back to `running`.
  4. Broadcasts an `input_received` event.
- **Timeout handling** — each `InteractionRequest` carries a `timeout_at` timestamp. If no response arrives before the deadline, the interaction is marked `timeout` and the step fails gracefully (applying the normal retry policy if configured).
- Full HITL history is stored in the workflow context and surfaced on `GET /api/workflows/{workflow_id}/context`.

---

### 4.8 Conversation Manager

**Features**

`ConversationManager` maintains a rich, threaded conversation record for every workflow:

- **Messages** — every significant event (user task, orchestrator thought, agent message, HITL question, user response) is recorded as a `ConversationMessage` with role (`user`, `orchestrator`, `agent`, `system`), type (`task`, `thought`, `message`, `question`, `response`, `error`, `status`), and optional `parent_message_id` for threading.
- **Thought trail** — the orchestrator records its internal reasoning as `ThoughtTrailEntry` objects with types: `reasoning`, `decision`, `observation`, `question`. The full thought trail is visible to clients — making the system's decision process auditable and debuggable.
- **Persistent** — all messages and thoughts are written to the workflow database synchronously; they survive service restarts.
- **Retrieval** — full `WorkflowContext` (messages + thoughts + step results + pending interaction) is returned by `GET /api/workflows/{workflow_id}/context`, enabling rich UI visualisations (chat-style history, reasoning trace).

---

### 4.9 Workflow Database

**Features**

`WorkflowDatabase` (SQLite backend, `database.py`):

- **`workflows` table** — one row per workflow: ID, task description, status, step counts, timestamps, error message, execution plan (JSON), results (JSON), workflow state (JSON blob for in-progress state serialisation to support resume-after-restart).
- **`steps` table** — one row per step: workflow ID, step number, capability, agent endpoint used, status, parameters (JSON), result (JSON), retry count, max retries, execution time, dependencies (JSON), timestamps.
- **`interaction_requests` table** — HITL interaction records with full request/response lifecycle.
- **`conversation_messages` table** — full conversation thread.
- **`thought_trail` table** — orchestrator and agent reasoning entries.
- **`workflow_context` table** — serialised `WorkflowContext` snapshots for fast context retrieval.
- All writes use SQLite WAL mode for concurrent read access.
- Schema migrations handled by `migrate_db.py` and `migrate_schema.py`.

---

### 4.10 HA Database Layer

**Features**

`PostgreSQLWorkflowDatabase` (in `ha_database.py`):

- Drop-in replacement for the SQLite backend; identical API surface.
- Activated by `WORKFLOW_DB_BACKEND=postgresql` + `DATABASE_URL`.
- Uses `psycopg2` with `RealDictCursor` for dict-compatible row access.
- **Connection-per-request** pattern with explicit `commit` / `rollback` context manager — each database call is a minimal-lifetime connection from configurable pool settings.
- Table schema is identical to SQLite, enabling seamless backend migration.
- `get_workflow_database()` factory function returns the correct backend based on environment configuration — no code changes required to switch.

**When to use PostgreSQL**

Use `WORKFLOW_DB_BACKEND=postgresql` when running multiple orchestrator replicas, as SQLite is file-locked and cannot be shared across containers. PostgreSQL combined with `HA_BACKEND=redis` provides a fully distributed, stateless orchestrator tier.

---

## 5. Specialized Agent Services

All agents follow the same lifecycle pattern:
1. On startup, register with the Registry Service (`POST /api/registry/register`) including all capabilities and the agent's HTTP endpoint URL.
2. Start a background `send_heartbeats` coroutine (every 30 seconds).
3. Expose `POST /api/task` to receive `TaskRequest` objects.
4. On shutdown, unregister (`DELETE /api/registry/unregister/{agent_id}`).

---

### 5.1 Code Analyzer Agent

| Attribute | Value |
|---|---|
| Location | `services/agents/code_analyzer/` |
| Default port | **8001** |
| LLM required | Yes (AWS Bedrock / Claude 3.5 Sonnet) |

**Capabilities**

| Capability | LLM | Description |
|---|---|---|
| `analyze_python_code` | No | Static AST analysis: extracts classes, functions, imports, docstrings, and complexity metrics from Python source code |
| `explain_code` | Yes | Plain-English explanation of what a code snippet does |
| `suggest_improvements` | Yes | Refactoring and code quality recommendations |

**Features**

- AST parsing (`ast` module) for deterministic, LLM-free static analysis.
- Returns structured analysis JSON: list of classes with methods, list of functions with parameters and docstrings, list of imports, line count, and estimated cyclomatic complexity.
- LLM-powered capabilities use the `AgentInteractionHelper` to optionally pause and ask the user for clarification when code intent is ambiguous.

**Resilience**

- AST analysis is entirely synchronous and infallible for valid Python; syntax errors are caught and returned as structured error responses.
- LLM calls use retry logic inherited from agents' own exception handling; transient Bedrock errors are retried.
- Heartbeat failure does not crash the agent; the loop logs the error and continues.

---

### 5.2 Data Processor Agent

| Attribute | Value |
|---|---|
| Location | `services/agents/data_processor/` |
| Default port | **8002** |
| LLM required | Yes (for `analyze_data`, `summarize_data`) |

**Capabilities**

| Capability | LLM | Description |
|---|---|---|
| `transform_data` | No | Reformats data between JSON, CSV, and flat structures |
| `analyze_data` | Yes | Extract key insights from structured or unstructured data |
| `summarize_data` | Yes | Concise summary of large datasets or documents |

**Features**

- Supports context injection — the orchestrator injects previous step results as the `data` parameter using context enrichment.
- Non-LLM transform operations use Python's `json` module for fast, deterministic processing.
- LLM capabilities feed the full data payload to Claude 3.5 Sonnet with structured prompts for consistent output formatting.

---

### 5.3 Research Agent

| Attribute | Value |
|---|---|
| Location | `services/agents/research_agent/` |
| Default port | **8003** |
| LLM required | Yes (AWS Bedrock via `SafeLLMClient`) |

**Capabilities**

| Capability | LLM | Description |
|---|---|---|
| `answer_question` | Yes | Answer research questions, explain concepts, gather factual knowledge |
| `generate_report` | Yes | Produce a structured written report with configurable sections |
| `compare_concepts` | Yes | Side-by-side comparison of two topics or technologies |
| `research` | Yes | Open-ended research on a topic |

**Features**

- Uses the shared `SafeLLMClient`, which automatically applies guardrails, PII tokenization, and audit logging to all LLM calls.
- `answer_question` accepts a `context` parameter; the orchestrator injects session history for multi-turn coherence.
- `generate_report` accepts `aspects` (list of sections) and `data` (upstream step results); reports are rendered as Markdown.
- `compare_concepts` can receive empty `concept_a`/`concept_b` — the orchestrator fills them from prior step outputs via context enrichment.
- Supports `AgentInteractionHelper` for HITL disambiguation of ambiguous research requests.
- Optionally consults the MCP Gateway for web search results to ground answers in real-time data.

---

### 5.4 Math Agent

| Attribute | Value |
|---|---|
| Location | `services/agents/math_agent/` |
| Default port | **8006** |
| LLM required | No |

**Capabilities**

| Capability | LLM | Description |
|---|---|---|
| `calculate` | No | Basic arithmetic: add, subtract, multiply, divide |
| `advanced_math` | No | Power/exponent, square root, trigonometry (sin, cos, tan) |
| `solve_equation` | No | Solve algebraic equations expressed as strings |
| `statistics` | No | Mean, median, standard deviation, sum over a list of numbers |

**Features**

- All calculations are pure Python (`math` module); zero LLM calls, zero latency beyond network round-trip.
- Supports step references as input values (e.g. `"value": "<result_from_step_1>"`) — the context enrichment layer resolves these before dispatch.
- Uses the MCP Gateway's Calculator server for operation dispatch, providing a clean separation between the agent's orchestration logic and the actual computation tools.
- Equation solving uses symbolic algebraic evaluation of well-formed expression strings.
- Statistics operations accept lists of numbers directly or as JSON-encoded strings.
- Produces auditable step records via `AuditLogger` for every calculation.

---

### 5.5 Task Executor Agent

| Attribute | Value |
|---|---|
| Location | `services/agents/task_executor/` |
| Default port | **8004** |
| LLM required | No |

**Capabilities**

| Capability | LLM | Description |
|---|---|---|
| `execute_command` | No | Execute system commands (sandboxed/simulated for safety) |
| `file_operations` | No | Perform file read/write operations |
| `wait_task` | No | Wait for a specified duration (useful for testing sequential workflows) |

**Features**

- General-purpose worker agent with `AgentRole.WORKER`.
- `execute_command` is sandboxed — commands are simulated or optionally executed in an isolated environment, preventing arbitrary code execution.
- Acts as an extensible base for domain-specific worker implementations.

---

### 5.6 Observer Agent

| Attribute | Value |
|---|---|
| Location | `services/agents/observer/` |
| Default port | **8005** |
| LLM required | No |

**Capabilities**

| Capability | LLM | Description |
|---|---|---|
| `system_monitoring` | No | Monitor system activity and metrics |
| `event_logging` | No | Log and retrieve observed system events |
| `metrics_reporting` | No | Generate system metrics reports |
| `agent_statistics` | No | Statistics about registered agents and task volumes |

**Features**

- Passive observer with `AgentRole.OBSERVER`.
- Maintains in-memory event log (capped at 1,000 entries; oldest entries evicted).
- Tracks per-event-type counts, per-agent activity counters, and task execution time histograms.
- Background `monitor_system()` task polls the Registry Service every 60 seconds, recording the full agent roster snapshot as a timed event.
- Provides an aggregated system health view without impacting the processing pipeline.

**Resilience**

- Event log capping prevents unbounded memory growth in long-running deployments.
- Observer failures are non-fatal to the orchestrator — it is a passive, read-only consumer of system metrics.

---

## 6. MCP Tool Layer

MCP (Model Context Protocol) servers expose deterministic, side-effect-bearing tools that agents call to interact with external systems. They are distinct from agents: agents reason and plan; MCP servers simply execute well-defined tool functions.

---

### 6.1 MCP Gateway Service

| Attribute | Value |
|---|---|
| Location | `services/mcp_gateway/` |
| Default port | **8300** |
| Technology | FastAPI, httpx, AWS Bedrock (optional) |

**Purpose**

Single entry point for all tool invocations. Agents call the MCP Gateway rather than individual MCP servers, shielding them from service discovery complexity and enabling central authentication enforcement.

**Features**

- `POST /api/tools/execute` — accepts `ToolCall` (tool name, parameters, optional server preference) and routes to the appropriate MCP server.
- **Dynamic tool discovery** — on each request, queries the MCP Registry for the current tool-to-server mapping. No static configuration required.
- **Load balancing** — if multiple MCP servers offer the same tool, the gateway can round-robin or prioritise the `prefer_server` hint.
- **LLM-assisted routing** — `POST /api/gateway/query` accepts a free-form natural-language query and uses Claude 3.5 Sonnet to determine which tools to call and in what order, then executes them and returns collected results.
- **Authentication passthrough** — validates the caller's JWT (via `get_current_user`) and propagates identity metadata to MCP servers.
- **Execution timing** — records and returns `execution_time_ms` for every tool call.
- `GET /api/tools` — list all available tools from the registry.
- `GET /health` — reports registry connectivity and Bedrock availability.

**Resilience**

- `httpx.AsyncClient` with 30-second per-request timeout.
- Tool discovery failures fall back gracefully with an informative error rather than crashing.
- Auth dependency is injected via FastAPI's `Depends` mechanism — missing or invalid tokens result in `401 Unauthorized` before any tool execution.

---

### 6.2 Calculator MCP Server

| Attribute | Value |
|---|---|
| Location | `services/mcp_servers/calculator/` |
| Default port | **8213** |

**Tools provided**

| Tool | Description |
|---|---|
| `add` | Add two numbers |
| `subtract` | Subtract b from a |
| `multiply` | Multiply two numbers |
| `divide` | Divide a by b (zero-division guard) |
| `power` | Raise base to exponent |
| `modulo` | Remainder of a / b |
| `abs_value` | Absolute value |
| `round_number` | Round to specified decimal places |

**Features**

- Registers all tools with the MCP Registry on startup, including full JSON input schemas.
- Every tool call is logged to `calculator.log`.
- Periodic heartbeat to the MCP Registry.

---

### 6.3 Database MCP Server

| Attribute | Value |
|---|---|
| Location | `services/mcp_servers/database/` |
| Default port | **8211** |
| Storage | SQLite at `DATABASE_PATH` (default `/tmp/mcp_database.db`), persisted via `database-data` Docker volume |

**Tools provided**

| Tool | Description |
|---|---|
| `query_database` | Execute a read-only SQL SELECT query |
| `list_tables` | List all tables in the database |
| `describe_table` | Get column definitions and types for a table |
| `insert_record` | Insert a record into a table |
| `count_records` | Count records optionally filtered by a WHERE clause |

**Features**

- Pre-seeded with sample `users` and `products` tables for demonstration.
- `query_database` enforces read-only access — only `SELECT` statements are permitted; DML is rejected.
- Schema introspection (`describe_table`) allows agents to dynamically understand database structure.
- Persistent data via Docker volume; sample data is re-inserted only if the table is empty.

---

### 6.4 File Operations MCP Server

| Attribute | Value |
|---|---|
| Location | `services/mcp_servers/file_ops/` |
| Default port | **8210** |
| Storage | Sandboxed workspace at `WORKSPACE_DIR` (default `/tmp/mcp_workspace`), persisted via `workspace-data` Docker volume |

**Tools provided**

| Tool | Description |
|---|---|
| `read_file` | Read file contents from the sandbox |
| `write_file` | Write contents to a sandboxed file path |
| `list_files` | List files in a directory, optionally filtered by glob pattern |
| `delete_file` | Delete a sandboxed file |
| `file_exists` | Check if a file exists in the sandbox |

**Features**

- All paths are **sandboxed** to `WORKSPACE_DIR`; path traversal attacks (`../`) are neutralised by resolving paths relative to the workspace root and rejecting escapes.
- `write_file` auto-creates parent directories.
- Returns file metadata (size in bytes, line count) alongside content.

---

### 6.5 Web Search MCP Server

| Attribute | Value |
|---|---|
| Location | `services/mcp_servers/web_search/` |
| Default port | **8212** |

**Tools provided**

| Tool | Description |
|---|---|
| `search_web` | Search the web for a query (pluggable — mock by default) |
| `fetch_url` | Fetch raw HTML/text content from a URL |
| `extract_links` | Extract all hyperlinks from a given URL |

**Features**

- `search_web` is intentionally designed as a mock implementation with clear integration hooks. In production, replace the `search_web()` function body with a call to Google Custom Search API, Bing Web Search API, or a similar service.
- `fetch_url` uses `httpx` with redirect following; content is truncated at 5,000 characters to prevent runaway context.
- `extract_links` uses regex-based link extraction; for production, swap with an HTML parser (e.g. `beautifulsoup4`).

---

## 7. Shared Library Modules

All shared modules live in `/shared/` and are imported by every service. They provide the reusable security, protocol, and infrastructure plumbing that keeps individual services thin.

---

### 7.1 A2A Protocol (Models & Client)

**Location:** `shared/a2a_protocol/`

**`models.py` — canonical data types**

| Model | Purpose |
|---|---|
| `AgentMetadata` | Full agent description: ID, name, role, capabilities, endpoint, LLM flag |
| `AgentCapability` | Single capability: name, description, input/output schema, LLM requirement |
| `AgentRole` | Enum: `orchestrator`, `specialized`, `worker`, `observer` |
| `TaskRequest` | Task dispatch payload: capability, parameters, priority (1–10), timeout, context |
| `TaskResponse` | Task result: status, result dict, error, execution time, LLM token usage |
| `TaskStatus` | Enum: `pending`, `in_progress`, `completed`, `failed`, `cancelled` |
| `A2AMessage` | Envelope for all A2A messages: type, sender, receiver, correlation ID, payload |
| `MessageType` | Enum: `register`, `discover`, `task_request`, `task_response`, `heartbeat`, `error` … |

**`client.py` — A2AClient**

HTTP client wrapping the Registry and agent communication APIs:
- `register_agent()`, `unregister_agent()`, `heartbeat()`.
- `discover_agents(capability, role)` — find agents by capability or role.
- `get_all_agents()`, `get_registry_stats()`.
- `send_task(agent_endpoint, task)` — post a `TaskRequest` to a specific agent.
- Uses `httpx.AsyncClient` with configurable timeout (default 30 seconds).

---

### 7.2 Safe LLM Client

**Location:** `shared/llm_client.py`

`SafeLLMClient` wraps AWS Bedrock's `converse` API with a full enterprise security pipeline:

**Security pipeline (in order)**

1. **PII tokenization** — before the prompt reaches the LLM, all PII patterns (SSNs, credit cards, emails, etc.) are replaced with opaque tokens (`[PII_SSN_af3c8e…]`). The real values are stored in a per-request vault.
2. **Input guardrail validation** — the tokenised prompt is checked against configured input rails. Jailbreak patterns, prompt injection signatures, and forbidden topics trigger a BLOCK action; the LLM is never called.
3. **LLM invocation** — the sanitised prompt is sent to Bedrock with full tool configuration if provided.
4. **Output guardrail validation** — the LLM response is checked for policy violations, off-topic content, and accidental PII leakage.
5. **PII detokenization for tool calls** — when the LLM requests a tool call, parameters are detokenized (real PII values restored) before being passed to MCP tool servers. The LLM never sees or returns real PII.
6. **Audit logging** — every invocation (input token count, output token count, latency, guardrail outcomes) is written to the audit log.

**Features**

- Tracks `LLMInvocationMetrics`: input/output token counts, latency, PII token count, guardrail check count.
- Singleton-safe with separate Bedrock client initialization per region.
- Exposes `_total_invocations` and `_total_blocked` counters for observability.

---

### 7.3 Guardrail Service

**Location:** `shared/guardrails.py`

Enterprise content safety layer, configurable via external JSON files (no code changes needed to adjust policies).

**Input rails**

- **Jailbreak detection** — regex and keyword patterns that identify attempts to override system instructions.
- **Prompt injection prevention** — detects attempts to inject hidden instructions via user input.
- **Forbidden topics** — configurable list of topics the system should not engage with.

**Output rails**

- **Topic filtering** — ensures LLM responses stay on-topic.
- **Content moderation** — blocks harmful, hateful, or unsafe content.
- **PII leak detection** — checks that tokenized PII was not accidentally reconstructed in the output.

**PII handling**

- Regex-based detection for: SSNs, credit card numbers, email addresses, phone numbers, IP addresses, dates of birth, full names (configurable patterns).
- Sensitivity levels: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.
- Tokenization produces deterministic HMAC-based tokens: same value always produces the same token, enabling referential integrity across a workflow.
- Detokenization is authorised per-operation — only explicitly authorised tool calls receive real PII values.

**Violation actions**

`BLOCK`, `WARN`, `WARN_AND_DISCLAIM`, `REDACT`, `LOG_ONLY` — configurable per rule.

**`ValidationResult`** — returned for every input/output check:
- `is_valid: bool`
- `processed_text` — text after redaction/disclaimer injection.
- `violations` — list of `GuardrailViolation` records with timestamp, rule ID, action taken.
- `warnings` — non-blocking advisory messages.

---

### 7.4 Audit Logger

**Location:** `shared/audit.py`

Comprehensive compliance audit logging following WORM (Write Once, Read Many) semantics.

**Features**

- **Immutable records** — once written, audit entries cannot be modified. Each entry includes a SHA-256 hash chain linking it to the previous entry, creating tamper-evident sequences.
- **Structured events** typed by `AuditEventType`:
  - Workflow lifecycle: `WORKFLOW_STARTED`, `COMPLETED`, `FAILED`, `PAUSED`, `RESUMED`.
  - Step lifecycle: `STEP_STARTED`, `COMPLETED`, `FAILED`.
  - Agent events: `AGENT_INVOCATION`, `AGENT_RESPONSE`.
  - LLM events: `LLM_INVOCATION`, `LLM_RESPONSE`.
  - Tool events: `TOOL_INVOCATION`, `TOOL_RESPONSE`, `TOOL_AUTHORIZATION`.
  - Security events: `GUARDRAIL_VIOLATION`, `SECURITY_VIOLATION`, `AUTHENTICATION`, `AUTHORIZATION_DENIED`.
  - `CHAIN_OF_THOUGHT` — records LLM reasoning intermediate steps.
  - User interaction: `USER_INPUT_REQUESTED`, `USER_INPUT_RECEIVED`.
  - System: `SYSTEM_ERROR`, `CONFIGURATION_CHANGE`.
- **Chain of Thought capture** — `log_cot(workflow_id, step, thought, plan, observation, action)` records the full ReAct-style reasoning trace for every LLM invocation.
- **Asynchronous write queue** — log entries are enqueued in a `threading.Queue` and drained by a dedicated writer thread. The request path is never blocked waiting for disk I/O.
- **Log rotation and retention** — configurable retention period (default 90 days). Rotated logs are gzip-compressed.
- **Configurable WORM storage path** — default `./audit_logs`; maps to persistent volume in Docker.

---

### 7.5 Security Manager

**Location:** `shared/security.py`

Provides non-LLM-based deterministic security enforcement.

**Features**

- **Tool authorization (RBAC)** — `validate_tool_authorization(user_role, tool_name, parameters)` checks a policy matrix defining which roles may call which tools with which parameter constraints.
- **On-Behalf-Of (OBO) flow** — `get_user_context(headers)` extracts the propagated user identity from `X-User-ID`, `X-User-Role`, `X-Session-ID`, `X-Tenant-ID` headers, enabling end-user identity propagation through the entire agent chain.
- **Parameter-level constraints** — policies can restrict allowed parameter ranges (e.g., maximum transaction amount for a `transfer_funds` tool) without relying on LLM judgement.
- **Rate limiting** — per-user, per-tool rate limiting using sliding-window counters; configurable limits per role.
- **Security violation recording** — `SecurityViolation` records (timestamp, user, tool, violation type, severity) are written to the audit log.
- **`AuthorizationResult`** — `authorized`, `reason`, `requires_approval` (for high-sensitivity operations), `approval_id`, `warnings`.

---

### 7.6 Identity Provider

**Location:** `shared/identity_provider.py`

Pluggable enterprise IdP integration.

**Supported providers**

`AZURE_AD`, `OKTA`, `AUTH0`, `AWS_COGNITO`, `KEYCLOAK`, `GENERIC_OIDC`, `NONE` (development bypass).

**Features**

- **JWT validation** — RS256 and HS256 token signature verification using `PyJWT` and JWKS endpoint key discovery.
- **OIDC auto-discovery** — supply a `discovery_url` (`.well-known/openid-configuration`) and all endpoints are auto-populated.
- **OAuth 2.0 / OIDC flows** — client credentials, authorization code, and OBO token exchange.
- **Token caching** — validated tokens are cached with TTL based on the `exp` claim (minus a 5-minute safety buffer), eliminating repeated JWKS lookups.
- **Scope-based token retrieval** — `get_token(scopes)` acquires or returns a cached token with the requested scopes.
- **`UserContext`** — extracted from the validated token: `user_id`, `email`, `name`, `roles`, `tenant_id`, `scopes`, raw token.
- **`ToolAuthRequirement`** — per-tool authentication requirements (OAuth, API key, basic), enabling the MCP Gateway to obtain the correct credential type for each downstream tool server.
- Graceful degradation when `PyJWT` is not installed — token validation is disabled with a warning (useful in development).

---

### 7.7 Auth Dependencies

**Location:** `shared/auth_dependencies.py`

FastAPI dependency injection helpers:
- `get_current_user()` — `Depends` function that validates the Bearer token from `Authorization` header and returns a `UserContext`. Returns a default development context (unauthenticated) when `AUTH_ENABLED=false`.
- `get_user_headers()` — extracts `UserContext` from forwarded identity headers (`X-User-ID` etc.) for service-to-service calls where the original token is not forwarded.
- Used by the Orchestrator, MCP Gateway, and individual agents to enforce authentication on all inbound API calls.

---

### 7.8 Vector Memory Store

**Location:** `shared/vector_memory.py`

Pluggable long-term semantic memory — enables agents to recall relevant past workflows by semantic similarity.

**Supported vector backends**

| Backend | Status | Use case |
|---|---|---|
| `in_memory` | Default | Development; zero dependencies |
| `chromadb` | Production-ready | Local or self-hosted |
| `pinecone` | Cloud-native | Pinecone cloud |
| `qdrant` | **Default in Docker Compose** | Docker sidecar |
| `weaviate` | Production-ready | Self-hosted or cloud |
| `pgvector` | Production-ready | PostgreSQL + pgvector extension |
| `redis` | Production-ready | Redis Stack with vector search |
| `opensearch_aws` | AWS-native | Amazon OpenSearch Service k-NN |
| `azure_ai_search` | Azure-native | Azure AI Search with HNSW vector fields |
| `azure_cosmos` | Azure-native | Azure Cosmos DB DiskANN vector search |

**Supported embedding providers**

| Provider | Description |
|---|---|
| `bedrock` | Default — AWS Bedrock Titan Embeddings |
| `openai` | OpenAI `text-embedding-3-small` |
| `sentence_transformers` | Local model (e.g. `all-MiniLM-L6-v2`) |
| `none` | Disables semantic search; keyword fallback |

**Features**

- `store(session_id, content, metadata)` — embeds and stores a memory entry, enforcing `VECTOR_MEMORY_MAX_ENTRIES` per session (oldest entries evicted with LRU).
- `search(session_id, query, top_k)` — retrieves the most semantically similar memories above `VECTOR_MEMORY_SCORE_THRESHOLD`.
- All configuration via environment variables only — switching backends requires no code changes.
- Hybrid search supported on Azure AI Search (vector + BM25 keyword).
- Managed Identity authentication on Azure backends.
- SigV4 authentication on Amazon OpenSearch.

---

### 7.9 Distributed State

**Location:** `shared/distributed_state.py`

Replaces per-process Python dicts with backend-agnostic shared stores for HA orchestrator deployments.

**Namespaces**

| Store | Description |
|---|---|
| `dist_state.workflows` | Live workflow state (`set`, `get`, `delete`, `list_ids`); TTL-expiring after completion |
| `dist_state.sessions` | Per-session conversation history lists (`append`, `get`) |
| `dist_state.ownership` | Workflow-to-instance ownership with heartbeat (`claim`, `refresh`, `release`, `get_owner`) |
| `dist_state.pubsub` | Cross-instance event fan-out (`publish`, `subscribe`, `unsubscribe`) |
| `dist_state.instances` | Running instance registry with HTTP endpoints (`register`, `heartbeat`, `get_endpoint`, `list_all`) |

**Backends**

| Backend | Activation | Description |
|---|---|---|
| `in_memory` | Default | Asyncio-native in-process store; zero external dependencies |
| `redis` | `HA_BACKEND=redis` | Full Redis-backed HA; required for multi-instance deployments |

**Resilience**

- `startup()` registers the local instance and begins a background heartbeat coroutine (every `OWNERSHIP_TTL/2` seconds).
- `shutdown()` deregisters the instance and cancels heartbeat tasks.
- Ownership TTL ensures orphaned workflows (instance crashed without releasing) are automatically reclaimable after `OWNERSHIP_TTL` seconds (default 30).
- Instance TTL ensures stale instances are evicted from the registry after `INSTANCE_TTL` seconds (default 60).

---

### 7.10 Configuration Manager

**Location:** `shared/config.py`

Centralised, singleton configuration management with environment-based overrides.

**Configuration priority** (highest → lowest):
1. Environment variables
2. External JSON config files
3. Default values coded in dataclasses

**Config domains**

| Domain | Key settings |
|---|---|
| `FeatureFlags` | `enable_guardrails`, `enable_audit_logging`, `enable_pii_redaction`, `enable_prompt_caching`, `enable_chain_of_thought_logging`, `strict_mode` |
| `LLMConfig` | `region`, `model_id`, `max_tokens`, `temperature` |
| `NetworkConfig` | `bind_host`, `public_host` |
| `AuthConfig` | `enabled`, `provider`, `issuer`, `audience`, `jwks_uri`, `algorithms`, `role_claim` |
| `ComplianceConfig` | `worm_storage_path`, `log_retention_days`, `encryption_at_rest` |
| `VectorMemoryConfig` | `enabled`, `backend`, `embedding`, `collection`, `top_k`, `score_threshold` |

**Features**

- `ConfigManager.get_instance()` — singleton accessor; safe for concurrent access.
- `get_service_url(service_name)` — resolves service endpoints from `SERVICE_URLS` config section; each service only needs to know logical names rather than hard-coded addresses.
- `get_agent_config(agent_key)` — per-agent configuration lookup (port, name, timeouts).
- `feature_enabled(flag_name)` — boolean feature flag lookup.
- Supports hot-reloading of external JSON config files (triggered by filesystem change detection).

---

### 7.11 Agent Interaction Helper

**Location:** `shared/agent_interaction.py`

Convenience library enabling any agent to request structured user input with minimal boilerplate.

**Features**

- `AgentInteractionHelper(task_request)` — initialised from the incoming `TaskRequest`; automatically extracts `workflow_id`, `step_id`, `agent_name`, conversation history, and previous step results from the task context.
- `request_input(question, input_type, options, reasoning, context, default_value, partial_results)` — returns a properly formatted `user_input_required` response dict that the orchestrator recognises as a HITL pause.
- **Convenience methods**:
  - `ask_text(question, reasoning)` — free-text input.
  - `ask_single_choice(question, options, reasoning)` — radio-button style.
  - `ask_multiple_choice(question, options, reasoning)` — checkbox style.
  - `ask_confirmation(question, reasoning)` — yes/no.
  - `ask_structured_data(question, schema, reasoning)` — typed JSON input.
- `get_user_response()` — checks if the current task request already carries a user response (from a resumed workflow). Returns the response value, or `None` if still awaiting.
- `is_interaction_request(result)` — utility predicate: returns `True` if an agent's result dict is a HITL request rather than a completed result. Used by the orchestrator to detect and handle pause conditions.

---

## 8. Deployment & Container Topology

### Service startup order (enforced by Docker health checks)

```
1. registry          — health check: GET /health
2. mcp-registry      — waits for: registry healthy
3. qdrant            — independent
4. redis             — independent
5. orchestrator      — waits for: registry, redis, qdrant healthy
6. calculator-server,
   database-server,
   file-ops-server,
   web-search-server  — wait for: mcp-registry healthy
7. mcp-gateway       — waits for: all MCP servers started
8. code-analyzer,
   data-processor,
   research-agent,
   task-executor,
   observer,
   math-agent        — wait for: registry healthy
```

### Named Docker volumes

| Volume | Service(s) | Content |
|---|---|---|
| `redis-data` | redis | AOF persistence files |
| `qdrant-data` | qdrant | Vector index and segment files |
| `workflow-data` | orchestrator | SQLite database (`workflows.db`) |
| `database-data` | database-server | SQLite sample database |
| `workspace-data` | file-ops-server | Agent-written file workspace |

### AWS credential mounting

Services that call AWS Bedrock (`orchestrator`, `mcp-gateway`, `code-analyzer`, `data-processor`, `research-agent`, `math-agent`) mount `~/.aws` as a read-only volume, enabling credential chain fallback (IAM role → environment variables → shared credentials file) without baking secrets into images.

---

## 9. Resilience Patterns Summary

| Pattern | Where implemented | Details |
|---|---|---|
| **Health checks** | Every Docker service | HTTP probe on startup; dependent services wait for `service_healthy` |
| **Auto-restart** | Every Docker service | `restart: unless-stopped` |
| **Heartbeat + stale eviction** | Registry, agents | 30-second send interval; 60-second timeout; removed from registry automatically |
| **Exponential backoff with jitter** | RetryManager | Per-step: max 3 retries, 1s–60s range, 2× base, ±50% jitter |
| **Circuit breaker** | RetryManager / CircuitBreaker | Threshold 5 failures → OPEN; reset after configurable timeout |
| **Parallel execution with semaphore** | ParallelExecutor | Max 5 concurrent steps; prevents orchestrator fan-out overload |
| **Step timeout** | ParallelExecutor | `asyncio.wait_for` with `STEP_TIMEOUT=300s`; workflow timeout `3600s` |
| **Distributed ownership with TTL** | DistributedState | Orphaned workflows reclaimable after 30s; instance registry TTL 60s |
| **Redis pub/sub fan-out** | WebSocket HA layer | Cross-instance event delivery; eliminates sticky sessions |
| **Cross-instance WebSocket proxy** | ws_handler | Requests proxied to the owning orchestrator instance |
| **Pluggable DB backends** | ha_database | SQLite for dev; PostgreSQL for multi-instance HA |
| **Persistent volumes** | Docker Compose | All state-bearing services use named volumes; survive container restarts |
| **Guardrail violations** | SafeLLMClient | Blocked LLM calls never reach Bedrock; no latency cost for blocked content |
| **PII tokenization** | GuardrailService / SafeLLMClient | Real PII never transmitted to LLM; safe even if LLM is compromised |
| **HITL timeout** | InteractionManager | Configurable per-interaction (default 300s); auto-fails step on timeout |
| **Re-registration on restart** | All agents | `lifespan()` re-registers with registry on every cold start |
| **Workflow state persistence** | WorkflowDatabase | Full state serialised to DB after every step; resumable after restart |
| **Vector memory LRU eviction** | VectorMemoryStore | Per-session entry cap (`VECTOR_MEMORY_MAX_ENTRIES=1000`) |
| **Audit hash chain** | AuditLogger | SHA-256 chain links entries; tampering is detectable |
| **Async audit write queue** | AuditLogger | Background thread drains queue; request path never blocked on audit I/O |

---

## 10. Performance Characteristics

### Orchestrator throughput

| Scenario | Approximate latency |
|---|---|
| Single-step workflow (no LLM) | ~50–200 ms (network + agent execution) |
| Single-step LLM workflow | ~1–5 s (Bedrock Claude 3.5 Sonnet latency) |
| 5-step sequential workflow | ~5–25 s |
| 5-step parallel workflow (all LLM) | ~1–7 s (parallel reduces wall time to slowest step) |
| HITL workflow (excluding human think time) | Same as non-HITL; pause is cooperative suspension, zero CPU cost |

### Parallel execution

- Up to `MAX_PARALLEL_STEPS=5` steps run simultaneously (configurable).
- All concurrency is `asyncio`-native; no threads or processes consumed per step.
- Dependencies are resolved via the `build_dependency_graph` function in O(N) where N = total steps.

### Registry lookups

- Agent discovery: O(1) dictionary lookup by capability or role.
- Registry heartbeat processing: O(1) per agent per 30 seconds.
- Stale eviction sweep: O(N) where N = number of registered agents, runs every 30 seconds.

### LLM call optimisation

- `enable_prompt_caching` feature flag (off by default) — when enabled, the planning prompt's static portions are eligible for Bedrock prompt caching (reduces latency and cost on repeated similar tasks).
- PII tokenization adds ~1–5 ms per call (pure Python regex operations).
- Guardrail validation adds ~1–2 ms per call (in-memory regex matching).

### Vector memory

- Write (embed + store): dominated by Bedrock Titan embedding latency (~200–500 ms); asynchronous and non-blocking from the planning path.
- Read (semantic search): Qdrant HNSW query ~1–5 ms locally; results injected into planning prompt before LLM call.
- Score threshold filtering avoids returning low-relevance memories that would pollute the prompt.

### Message bus (Redis pub/sub)

- Publish-to-receive latency within a local Docker network: < 1 ms.
- No persistent storage of pub/sub events — purely ephemeral delivery. WebSocket events not received (client disconnected) are dropped and re-sent on reconnect via the `get_workflow_context` API.

### Audit logging

- Writes are fully asynchronous (background queue + writer thread).
- Zero impact on request latency even under high write volume.
- gzip compression on rotated log files reduces storage footprint by ~60–80%.

---

## 11. Port Reference

| Port | Service |
|---|---|
| **8000** | Agent Registry Service |
| **8001** | Code Analyzer Agent |
| **8002** | Data Processor Agent |
| **8003** | Research Agent |
| **8004** | Task Executor Agent |
| **8005** | Observer Agent |
| **8006** | Math Agent |
| **8100** | Orchestrator Service (REST + WebSocket) |
| **8200** | MCP Registry Service |
| **8210** | File Operations MCP Server |
| **8211** | Database MCP Server |
| **8212** | Web Search MCP Server |
| **8213** | Calculator MCP Server |
| **8300** | MCP Gateway Service |
| **6333** | Qdrant REST API |
| **6334** | Qdrant gRPC API |
| **6379** | Redis |

---

*Generated: 26 February 2026. Reflects codebase at branch `humaninloopochestrator`.*
