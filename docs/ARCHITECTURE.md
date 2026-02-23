# System Architecture

## Overview

The Agent-to-Agent (A2A) framework is a distributed, microservices-based system designed for autonomous multi-agent collaboration. It leverages AWS Bedrock for LLM capabilities and the Model Context Protocol (MCP) for standardized tool integration. The system is designed with enterprise-grade security, auditability, and context preservation at its core.

### High-Level Architecture

```ascii
[ USER / CLI ] <---> [ ORCHESTRATOR (The Brain) ] <---> [ MCP GATEWAY ]
      |                       ^     |                         ^
      |                       |     |                         |
[ INTERACTION ]               |     +---> [ REGISTRY ]        |
[ MANAGER     ]               |                               |
                              |                               |
                   +----------+-----------+                   |
                   |                      |                   |
           [ CONTEXT STORE ]      [ SECURITY LAYER ]          |
           (Session History)      (Guardrails/Vault)          |
                                          |                   |
                                          v                   |
                                 +------------------+         |
                                 |   AGENT MESH     | --------+
                                 | (Research, Code, |
                                 |  Data, Math...)  |
                                 +------------------+
```

---

## 1. Core Services

### Orchestrator (Port 8100)
The central nervous system of the framework.
- **Workflow Planning**: Uses Claude 3.5 Sonnet to decompose user requests into executable steps.
- **Context Management**: Maintains global conversation history across multiple workflows using a `session_id`.
- **State Management**: Persists workflow state in SQLite/PostgreSQL.
- **Security Integration**: Enforces identity propagation and guardrails.

### Interaction Manager
Handles human-in-the-loop scenarios.
- **Suspension**: Pauses workflows when agent requires user input.
- **Resumption**: Resumes execution with user feedback.
- **Context Switching**: Allows users to branch off into new tasks while keeping the original workflow paused.

### Security Layer (New)
Enterprise-grade security features embedded in the framework.
- **SafeLLMClient**: A wrapper around AWS Bedrock client that enforces input/output guardrails.
- **PII Vault**: Tokenizes sensitive data (Credit Cards, SSN) before sending to LLM; detokenizes for authorized tool calls.
- **Audit Logger**: WORM (Write Once Read Many) compliant logging of "Thought, Plan, Observation, Action".
- **Identity Propagation**: Propagates User ID and Roles (IAM style) to every agent and tool.

### MCP Gateway (Port 8300)
The router for tool execution.
- **Tool Discovery**: dynamically finds tools registered in MCP Registry.
- **Load Balancing**: Distributes requests across available tool servers.
- **Protocol Translation**: Converts Agent HTTP requests to MCP JSON-RPC protocol.

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

## 4. MCP Tool Integration

The system uses the Model Context Protocol to standardize tool usage.

### Web Search Integration
*   **Server**: `services/mcp_servers/web_search`
*   **Tool**: `search(query)`, `get_content(url)`
*   **Flow**: Research Agent -> MCP Gateway -> Web Search Server -> DuckDuckGo/Google API -> Agent.
*   **Caching**: Prompt caching enabled for search results to reduce latency and cost on repeated queries.

---

## 5. Performance Optimizations

### Prompt Caching
*   **Static Context**: System instructions and tool definitions are marked as `cachePoint` (block type `system`).
*   **Dynamic Context**: Conversation history and variable inputs are appended after the cache point.
*   **Benefit**: Reduces input token processing time and cost by ~90% for long conversations.

### Parallel Execution
*   **Independent Steps**: The Orchestrator identifies steps with no dependencies and schedules them concurrently.
*   **AsyncIO**: All services use Python `asyncio` for non-blocking I/O.

---

**Version**: 2.1
**Last Updated**: 2026-02-13
