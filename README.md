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
      [ USER / CLI ]
            |
            v
    +----------------+       +-------------------+
    |  ORCHESTRATOR  |<----->|  CONTEXT & STATE  |
    +-------+--------+       +-------------------+
            |
            | (Plan & Delegate)
            v
    +----------------+       +-------------------+
    |   AGENT MESH   |<----->|  SECURITY LAYER   |
    | (Research,Math)|       | (Guardrails/PII)  |
    +-------+--------+       +-------------------+
            |
            | (Tool Call)
            v
    +----------------+       +-------------------+
    |   MCP GATEWAY  |------>|   MCP SERVERS     |
    +----------------+       | (Search, Calc...) |
                             +-------------------+
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

**Version**: 2.1
**Last Updated**: 2026-02-13
