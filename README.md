# Agent-to-Agent (A2A) Framework

A generic, extensible framework for autonomous multi-agent collaboration using **AWS Bedrock** and **Model Context Protocol (MCP)**. This system enables complex workflow orchestration, interactive human-in-the-loop tasks, and enterprise-grade security.

## 🌟 Key Features

*   **🤖 Multi-Agent Orchestration**: Intelligent planning and task delegation using Claude 3.5 Sonnet.
*   **🔌 MCP Integration**: Standardized tool integration via the Model Context Protocol.
*   **🗣️ Interactive Workflows**: Pause/Resume capabilities for human feedback and clarification.
*   **💾 Context Preservation**: Maintains conversation history across multiple workflows in a session.
*   **🔒 Enterprise Security**:
    *   **Guardrails**: Input/Output filtering for safety and compliance.
    *   **PII Vault**: Automatic tokenization of sensitive data before LLM processing.
    *   **Audit Logging**: Immutable, tamper-evident logs of all agent actions.
    *   **Identity Propagation**: Secure user context passing.
*   **⚡ Performance**: Parallel execution, prompt caching, and exponential backoff retries.

```ascii
                    +---------------------------+
                    |    IDENTITY PROVIDER      |
                    | (Azure AD / Okta / Auth0  |
                    |  Cognito / Keycloak / OIDC)|
                    +------------+--------------+
                                 | JWT Validation /
                                 | Token Issuance
      [ USER / CLI ]             |
            | (Bearer JWT)       |
            v                    v
    +------------------+  Validate   +-------------------+
    |   ORCHESTRATOR   |<----------->|   AUTH MODULE     |
    |   (Port 8100)    |    Token    | (identity_provider|
    +--------+---------+             |  .py + JWKS)      |
             |                      +-------------------+
             | (Plan & Delegate +         |
             |  User Context)             | OBO Token
             v                           | Exchange
    +------------------+  +------------------+
    |   AGENT MESH     |  |  SECURITY LAYER  |
    | (Research, Math, |  | (Guardrails/PII/ |
    |  Code, Data...)  |  |  Audit Logging)  |
    +--------+---------+  +------------------+
             |
             | (Tool Call + User Token)
             v
    +------------------+  Auth Schema  +-------------------+
    |   MCP GATEWAY    |<------------->|   MCP REGISTRY    |
    |   (Port 8300)    |  Fetch/Verify | (Tool Auth Reqs)  |
    +--------+---------+               +-------------------+
             |
             | (Tool-Scoped Token via OBO)
             v
    +--------------------------------------+
    |           MCP SERVERS                |
    | (Web Search / Calculator / File Ops  |
    |  Database / Custom Tools...)         |
    +--------------------------------------+
```

---

## 🚀 Quick Start

### Prerequisites
*   Python 3.10+
*   Docker & Docker Compose
*   AWS Credentials (with Bedrock access enabled)

### 1. Setup Environment
```bash
# Clone the repository
git clone https://github.com/your-username/agentToAgent.git
cd agentToAgent

# Run initial setup (creates venv, installs dependencies)
./setup.sh

# Configure environment variables
cp .env.example .env
# Edit .env and add your AWS credentials
```

### 2. Start Services
```bash
./start_services.sh
```
*This starts the Orchestrator, Agents, MCP Gateway, and Tool Servers.*

### 3. Run Interactive Chat
Use the new terminal-based chat application to interact with the system:
```bash
python cli_chat.py
```

**Example Interaction:**
> **You**: "Compare the top cloud providers."
> **Agent**: "I need to know which specific providers you are interested in."
> **You**: "AWS, Azure, and GCP."
> **Agent**: *Proceeds with research...*

---

## 🔒 Enterprise Security Setup

The framework includes a comprehensive security layer. To configure it:

### 1. Guardrails
The system uses `SafeLLMClient` which wraps standard Bedrock calls.
*   **Configuration**: Edit `services/shared/security_config.py` (mock) or point to real AWS Bedrock Guardrails ID in `.env`.
*   **Behavior**: Blocks prompts containing malicious patterns or banned topics.

### 2. PII Vault
Sensitive data is automatically detected and tokenized.
*   **Detected Types**: Credit Card numbers, SSN, Email addresses.
*   **Storage**: Ephemeral in-memory vault (default). Configure Redis for production.
*   **Usage**: Agents see tokens (e.g., `TOKEN_CC_1`); only authorized tools (like `transfer_funds`) can access real data.

### 3. Audit Logging
All actions are logged to `logs/audit_chain.json`.
*   **Format**: JSON-structured logs with cryptographic chaining (hash of previous entry).
*   **Content**: "Thought", "Plan", "Observation", "Action".

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
*   **[Identity Provider Setup Guide](docs/IDENTITY_PROVIDER_SETUP.md)**: Detailed configuration for each IdP
*   **[Identity Integration Summary](docs/IDENTITY_INTEGRATION_SUMMARY.md)**: Architecture and features overview
*   **Setup Script**: `./scripts/setup_identity_provider.sh` - Automated setup helper
*   **Test Script**: `./scripts/test_identity_provider.py` - Verify your configuration

#### Development Mode
For local development, you can disable authentication:
```bash
# In .env
AUTH_ENABLED=false
```
This allows testing without configuring an identity provider.

---

## 📚 Documentation

*   **[ARCHITECTURE.md](ARCHITECTURE.md)**: Detailed system design, security flow, and component interaction.
*   **[DEPLOYMENT_SUMMARY.md](DEPLOYMENT_SUMMARY.md)**: Central hub for all deployment guides.
*   **[AWS Deployment](DEPLOYMENT_AWS.md)**: Deployment on ECS Fargate, EKS, and EC2.
*   **[Azure Deployment](DEPLOYMENT_AZURE.md)**: Deployment on ACA, AKS, and VMs.
*   **[General Deployment](DEPLOYMENT.md)**: Local Docker Compose setup.
*   **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)**: Common issues and fixes.

---

## 🛠️ Service Architecture

### Agents (The "Brain")
*   **Orchestrator (Port 8100)**: Planner and Context Manager.
*   **Research Agent (Port 8003)**: Web search and report generation.
*   **Math Agent (Port 8006)**: Complex calculations via Calculator Tool.
*   **Data Processor (Port 8002)**: Analysis and transformation.

### MCP Servers (The "Hands")
*   **Web Search**: Real-time web data via DuckDuckGo/Google.
*   **Calculator**: Mathematical operations.
*   **File Ops**: Safe filesystem access.
*   **Database**: SQLite operations.

---

## 🧪 Testing

Run the automated test suite to verify all components:
```bash
# Run generic tests
python -m pytest tests/

# Run specific interactive workflow test
python tests/test_websocket_interactive.py
```

---

**Version**: 2.2
**Last Updated**: 2026-02-23
