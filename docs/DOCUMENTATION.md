# A2A System Documentation Index

**Comprehensive Documentation Guide**

Last Updated: 2026-03-23

---

## 📚 Main Documentation

### Essential Reading

1. **[../README.md](../README.md)** — Start here!
   - Project overview and quick start
   - Key features (per service and overall)
   - Architecture diagram (identity, security, Model Gateway, agent mesh)
   - Model Gateway, Human-in-the-Loop, HA orchestrator, and Vector Memory descriptions
   - Individual service details and API reference
   - How to run (shell script and Docker Compose)
   - Example workflows and use cases

2. **[QUICK_START.md](QUICK_START.md)** — Quick Reference
   - Fast deployment options (shell scripts and Docker Compose)
   - Common commands
   - Complete service endpoint table (including Model Gateway port 8400)
   - Basic troubleshooting including Model Gateway health checks

3. **[ARCHITECTURE.md](ARCHITECTURE.md)** — System Design
   - High-level architecture diagram (identity layer, security layer, context layer)
   - Component details and responsibilities for every service
   - Model Gateway: provider routing, circuit breakers, model catalogue, audit
   - Service communication flows
   - Port allocation
   - Data flow walkthrough
   - MCP integration
   - Workflow execution (parallel, sequential, retry, circuit breaker)
   - HA orchestrator and distributed state via Redis
   - Vector Memory architecture
   - Scalability and performance

### Deployment Guides

4. **[DEPLOYMENT.md](DEPLOYMENT.md)** — Local / Docker Compose Setup
   - Docker Compose configuration
   - Container environment variables
   - Volume management

5. **[DEPLOYMENT_AWS.md](DEPLOYMENT_AWS.md)** — AWS Deployment
   - ECS Fargate deployment
   - EKS (Kubernetes) deployment
   - EC2 setup
   - IAM roles and Bedrock access

6. **[DEPLOYMENT_AZURE.md](DEPLOYMENT_AZURE.md)** — Azure Deployment
   - Azure Container Apps (ACA)
   - AKS (Kubernetes) deployment
   - Azure OpenAI integration with Model Gateway

7. **[AWS_CREDENTIALS_GUIDE.md](AWS_CREDENTIALS_GUIDE.md)** — AWS Configuration
   - Credential management options
   - Shell script vs Docker credential handling (mount path `/app/.aws`)
   - Security best practices
   - IAM role configuration for Bedrock

8. **[ENTERPRISE_DEPLOYMENT.md](ENTERPRISE_DEPLOYMENT.md)** — Enterprise Guide
   - HA orchestrator with Redis
   - PostgreSQL backend
   - Guardrails, PII Vault, and Audit Logging
   - Identity provider integration

9. **[IDENTITY_PROVIDER_SETUP.md](IDENTITY_PROVIDER_SETUP.md)** — Authentication
   - Azure AD / Okta / Auth0 / Cognito / Keycloak setup
   - JWT token validation
   - RBAC and scope-based access control
   - On-Behalf-Of (OBO) token exchange for MCP tools

### Testing & Development

10. **[CURL_EXAMPLES.md](CURL_EXAMPLES.md)** — REST API Examples
    - Workflow execution examples
    - Registry and agent API calls
    - Model Gateway inference examples (`/v1/complete`, `/v1/models`, `/v1/select`)
    - Health-check commands

11. **[MCP_CURL_EXAMPLES.md](MCP_CURL_EXAMPLES.md)** — MCP Tool Examples
    - Calculator operations via MCP Gateway
    - Database query examples
    - File operation examples
    - Web search examples

12. **[INTERACTIVE_WORKFLOW_EXAMPLES.md](INTERACTIVE_WORKFLOW_EXAMPLES.md)** — Human-in-the-Loop
    - Pausing workflows for user input
    - WebSocket interaction examples
    - CLI chat usage

13. **[COMPONENT_REFERENCE.md](COMPONENT_REFERENCE.md)** — Component Reference
    - Per-service environment variable reference
    - Configuration options
    - Integration points

### Architecture Supplements

14. **[MULTI_STEP_INTERACTIONS.md](MULTI_STEP_INTERACTIONS.md)** — Multi-Step Flows
    - Complex multi-agent workflow patterns
    - Context enrichment and mustache template resolution

15. **[README_INTERACTIVE_WORKFLOWS.md](README_INTERACTIVE_WORKFLOWS.md)** — Interactive Workflows
    - Human-in-the-loop design patterns
    - Workflow state machine

---

## 🗂️ Documentation by Topic

### Getting Started
1. Read [../README.md](../README.md)
2. Follow [QUICK_START.md](QUICK_START.md)
3. Choose deployment: [DEPLOYMENT.md](DEPLOYMENT.md) (local/Docker), [DEPLOYMENT_AWS.md](DEPLOYMENT_AWS.md), or [DEPLOYMENT_AZURE.md](DEPLOYMENT_AZURE.md)
4. Configure AWS: [AWS_CREDENTIALS_GUIDE.md](AWS_CREDENTIALS_GUIDE.md)

### Understanding the System
1. Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
2. Component details: [ARCHITECTURE.md#component-details](ARCHITECTURE.md#component-details)
3. Model Gateway: [ARCHITECTURE.md#model-gateway-port-8400](ARCHITECTURE.md#model-gateway-port-8400)
4. Data flow: [ARCHITECTURE.md#data-flow](ARCHITECTURE.md#data-flow)
5. Service descriptions: [../README.md#service-architecture](../README.md#service-architecture)

### Deploying
1. Local shell scripts: [QUICK_START.md](QUICK_START.md)
2. Docker Compose: [DEPLOYMENT.md](DEPLOYMENT.md)
3. AWS (ECS/EKS): [DEPLOYMENT_AWS.md](DEPLOYMENT_AWS.md)
4. Azure (ACA/AKS): [DEPLOYMENT_AZURE.md](DEPLOYMENT_AZURE.md)
5. Enterprise HA: [ENTERPRISE_DEPLOYMENT.md](ENTERPRISE_DEPLOYMENT.md)

### Testing
1. API examples: [CURL_EXAMPLES.md](CURL_EXAMPLES.md)
2. MCP tool examples: [MCP_CURL_EXAMPLES.md](MCP_CURL_EXAMPLES.md)
3. Interactive workflow tests: [INTERACTIVE_WORKFLOW_EXAMPLES.md](INTERACTIVE_WORKFLOW_EXAMPLES.md)

### Model Gateway
1. Architecture: [ARCHITECTURE.md#model-gateway-port-8400](ARCHITECTURE.md#model-gateway-port-8400)
2. API examples: [CURL_EXAMPLES.md](CURL_EXAMPLES.md)
3. Environment variables: [COMPONENT_REFERENCE.md](COMPONENT_REFERENCE.md)
4. Source: `services/model_gateway/`

### Advanced Features
1. Human-in-the-loop: [INTERACTIVE_WORKFLOW_EXAMPLES.md](INTERACTIVE_WORKFLOW_EXAMPLES.md)
2. Retry & Circuit Breaker: [ARCHITECTURE.md#workflow-execution](ARCHITECTURE.md#workflow-execution)
3. Parallel Execution: [ARCHITECTURE.md#workflow-execution](ARCHITECTURE.md#workflow-execution)
4. Vector Memory: [../README.md#vector-memory-long-term-recall](../README.md#vector-memory-long-term-recall)
5. HA Orchestrator: [ENTERPRISE_DEPLOYMENT.md](ENTERPRISE_DEPLOYMENT.md)

---

## 📖 Documentation by Role

### For Users
- [../README.md](../README.md) — Overview, features, example workflows
- [QUICK_START.md](QUICK_START.md) — How to start and use the system
- [CURL_EXAMPLES.md](CURL_EXAMPLES.md) — API call examples
- [INTERACTIVE_WORKFLOW_EXAMPLES.md](INTERACTIVE_WORKFLOW_EXAMPLES.md) — Human-in-the-loop examples

### For Operators
- [DEPLOYMENT.md](DEPLOYMENT.md) — Container deployment
- [DEPLOYMENT_AWS.md](DEPLOYMENT_AWS.md) — AWS deployment
- [DEPLOYMENT_AZURE.md](DEPLOYMENT_AZURE.md) — Azure deployment
- [AWS_CREDENTIALS_GUIDE.md](AWS_CREDENTIALS_GUIDE.md) — Credential configuration
- [ENTERPRISE_DEPLOYMENT.md](ENTERPRISE_DEPLOYMENT.md) — Enterprise HA and security

### For Developers
- [ARCHITECTURE.md](ARCHITECTURE.md) — System design and internals
- [COMPONENT_REFERENCE.md](COMPONENT_REFERENCE.md) — Configuration reference
- [../README.md#service-architecture](../README.md#service-architecture) — Service overview
- `services/model_gateway/` — Model Gateway source code

---

## 🔍 Quick Links

### Common Tasks

| Task | Documentation |
|------|---------------|
| Install and start (local) | [QUICK_START.md](QUICK_START.md) |
| Deploy with Docker Compose | [DEPLOYMENT.md](DEPLOYMENT.md) |
| Deploy to AWS | [DEPLOYMENT_AWS.md](DEPLOYMENT_AWS.md) |
| Deploy to Azure | [DEPLOYMENT_AZURE.md](DEPLOYMENT_AZURE.md) |
| Configure AWS credentials | [AWS_CREDENTIALS_GUIDE.md](AWS_CREDENTIALS_GUIDE.md) |
| Understand the architecture | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Use the Model Gateway | [ARCHITECTURE.md#model-gateway-port-8400](ARCHITECTURE.md#model-gateway-port-8400) |
| Set up enterprise auth | [IDENTITY_PROVIDER_SETUP.md](IDENTITY_PROVIDER_SETUP.md) |
| Enable HA / Redis | [ENTERPRISE_DEPLOYMENT.md](ENTERPRISE_DEPLOYMENT.md) |

### API References

| Service | Port | Documentation |
|---------|------|---------------|
| Registry | 8000 | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Orchestrator | 8100 | [ARCHITECTURE.md](ARCHITECTURE.md) |
| MCP Registry | 8200 | [ARCHITECTURE.md](ARCHITECTURE.md) |
| MCP Gateway | 8300 | [ARCHITECTURE.md](ARCHITECTURE.md) |
| **Model Gateway** | **8400** | **[ARCHITECTURE.md#model-gateway-port-8400](ARCHITECTURE.md#model-gateway-port-8400)** |
| Agents | 8001–8006 | [ARCHITECTURE.md](ARCHITECTURE.md) |
| MCP Tools | 8210–8213 | [ARCHITECTURE.md](ARCHITECTURE.md) |

---

## 📝 Documentation Standards

### File Naming
- `*.md` — Markdown format
- UPPERCASE filenames for `docs/` directory
- Descriptive names matching the content scope

### Structure
- Clear hierarchical headings
- Code examples with syntax highlighting
- Tables for structured data
- ASCII diagrams for architecture

### Content
- Start with overview/summary
- Step-by-step instructions
- Examples for common use cases
- Troubleshooting sections

---

## 🔄 Documentation Updates

### Version History
- **v3.1** (2026-03-23) — Added Model Gateway (port 8400) throughout; updated all links to `docs/` structure; added enterprise, AWS, and Azure deployment guides; added identity provider, interactive workflow, and HA orchestrator documentation
- **v2.1** (2026-03-23) — Updated with accurate API endpoints, complete capability lists, and detailed how-to-run instructions
- **v2.0** (2026-02-07) — Consolidated documentation, added enhancements guide
- **v1.0** (2025-12-15) — Initial documentation

---

## 🆘 Need Help?

1. **Can't find something?** Check this index
2. **Getting started?** Read [../README.md](../README.md) or [QUICK_START.md](QUICK_START.md)
3. **Deployment issues?** See [DEPLOYMENT.md](DEPLOYMENT.md) or [AWS_CREDENTIALS_GUIDE.md](AWS_CREDENTIALS_GUIDE.md)
4. **Model Gateway issues?** See troubleshooting in [QUICK_START.md](QUICK_START.md) and [ARCHITECTURE.md](ARCHITECTURE.md)
5. **Enterprise / HA?** See [ENTERPRISE_DEPLOYMENT.md](ENTERPRISE_DEPLOYMENT.md)
6. **Identity / Auth?** See [IDENTITY_PROVIDER_SETUP.md](IDENTITY_PROVIDER_SETUP.md)

---

**Last Updated**: 2026-03-23  
**Documentation Version**: 3.1  
**System Version**: 3.1
