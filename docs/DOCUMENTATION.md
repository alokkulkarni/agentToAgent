# A2A System Documentation Index

**Comprehensive Documentation Guide**

Last Updated: 2026-03-23

---

## 📚 Main Documentation

### Essential Reading

1. **[README.md](README.md)** — Start here!
   - Project overview and quick start
   - Key features (per service and overall)
   - Architecture diagram
   - Individual service details and API reference
   - How to run (shell script and Docker)
   - Example workflows and use cases

2. **[QUICK_START.md](QUICK_START.md)** — Quick Reference
   - Fast deployment options
   - Common commands
   - Service endpoint table
   - Basic troubleshooting

3. **[ARCHITECTURE.md](ARCHITECTURE.md)** — System Design
   - High-level architecture diagram
   - Component details and responsibilities
   - Service communication flows
   - Port allocation
   - Data flow walkthrough
   - MCP integration
   - Workflow execution (parallel, sequential, retry, circuit breaker)
   - Scalability and performance

### Deployment Guides

4. **[DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md)** — Docker Guide
   - Docker Compose setup
   - Container configuration
   - Volume management
   - Production deployment notes

5. **[AWS_CREDENTIALS_GUIDE.md](AWS_CREDENTIALS_GUIDE.md)** — AWS Configuration
   - Credential management options
   - Shell script vs Docker credential handling
   - Security best practices
   - IAM role configuration

6. **[DEPLOYMENT_COMPARISON.md](DEPLOYMENT_COMPARISON.md)** — Deployment Methods
   - Shell script vs Docker Compose
   - Pros, cons, and trade-offs
   - Use-case recommendations

### Testing & Development

7. **[TESTING_GUIDE.md](TESTING_GUIDE.md)** — Testing Guide
   - How to run each test suite
   - Expected output examples
   - Common test failure causes and fixes

8. **[CURL_EXAMPLES.md](CURL_EXAMPLES.md)** — API Examples
   - Workflow execution examples
   - Registry and agent API calls
   - Health-check commands

9. **[MCP_CURL_EXAMPLES.md](MCP_CURL_EXAMPLES.md)** — MCP Tool Examples
   - Calculator operations via Gateway
   - Database query examples
   - File operation examples

### New Features

10. **[ENHANCEMENTS_COMPLETE.md](ENHANCEMENTS_COMPLETE.md)** — Feature Guide
    - Workflow persistence implementation
    - Retry mechanism details
    - Parallel execution implementation
    - Integration instructions

---

## 🗂️ Documentation by Topic

### Getting Started
1. Read [README.md](README.md)
2. Follow [QUICK_START.md](QUICK_START.md)
3. Choose deployment: [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) or shell scripts
4. Configure AWS: [AWS_CREDENTIALS_GUIDE.md](AWS_CREDENTIALS_GUIDE.md)

### Understanding the System
1. Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
2. Components: [ARCHITECTURE.md#component-details](ARCHITECTURE.md#component-details)
3. Data Flow: [ARCHITECTURE.md#data-flow](ARCHITECTURE.md#data-flow)
4. Service descriptions: [README.md#individual-service-details](README.md#individual-service-details)

### Deploying
1. Shell Script: [QUICK_START.md](QUICK_START.md)
2. Docker Compose: [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md)
3. Comparison: [DEPLOYMENT_COMPARISON.md](DEPLOYMENT_COMPARISON.md)

### Testing
1. Test procedures: [TESTING_GUIDE.md](TESTING_GUIDE.md)
2. API examples: [CURL_EXAMPLES.md](CURL_EXAMPLES.md)
3. MCP tool examples: [MCP_CURL_EXAMPLES.md](MCP_CURL_EXAMPLES.md)

### Advanced Features
1. Persistence: [ENHANCEMENTS_COMPLETE.md](ENHANCEMENTS_COMPLETE.md)
2. Retry & Circuit Breaker: [ARCHITECTURE.md#workflow-execution](ARCHITECTURE.md#workflow-execution)
3. Parallel Execution: [ARCHITECTURE.md#workflow-execution](ARCHITECTURE.md#workflow-execution)

---

## 📖 Documentation by Role

### For Users
- [README.md](README.md) — Overview, features, example workflows
- [QUICK_START.md](QUICK_START.md) — How to start and use the system
- [CURL_EXAMPLES.md](CURL_EXAMPLES.md) — API call examples

### For Operators
- [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) — Container deployment
- [AWS_CREDENTIALS_GUIDE.md](AWS_CREDENTIALS_GUIDE.md) — Credential configuration
- [TESTING_GUIDE.md](TESTING_GUIDE.md) — System validation

### For Developers
- [ARCHITECTURE.md](ARCHITECTURE.md) — System design and internals
- [ENHANCEMENTS_COMPLETE.md](ENHANCEMENTS_COMPLETE.md) — New feature implementation
- [README.md#adding-new-agents](README.md#adding-new-agents) — Extension guide

---

## 🔍 Quick Links

### Common Tasks

| Task | Documentation |
|------|---------------|
| Install and start (local) | [QUICK_START.md](QUICK_START.md) |
| Deploy with Docker | [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) |
| Configure AWS credentials | [AWS_CREDENTIALS_GUIDE.md](AWS_CREDENTIALS_GUIDE.md) |
| Test the system | [TESTING_GUIDE.md](TESTING_GUIDE.md) |
| Understand the architecture | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Use workflow persistence / retry | [ENHANCEMENTS_COMPLETE.md](ENHANCEMENTS_COMPLETE.md) |

### API References

| Service | Port | Documentation |
|---------|------|---------------|
| Registry | 8000 | [ARCHITECTURE.md#registry-service-port-8000](ARCHITECTURE.md) |
| Orchestrator | 8100 | [ARCHITECTURE.md#orchestrator-service-port-8100](ARCHITECTURE.md) |
| MCP Registry | 8200 | [ARCHITECTURE.md#mcp-registry-port-8200](ARCHITECTURE.md) |
| MCP Gateway | 8300 | [ARCHITECTURE.md#mcp-gateway-port-8300](ARCHITECTURE.md) |
| Agents | 8001–8006 | [ARCHITECTURE.md#2-agent-services](ARCHITECTURE.md) |
| MCP Tools | 8210–8213 | [ARCHITECTURE.md#3-mcp-tool-servers](ARCHITECTURE.md) |

---

## 📝 Documentation Standards

### File Naming
- `*.md` — Markdown format
- UPPERCASE filenames for root-level docs
- Descriptive names

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
- **v2.1** (2026-03-23) — Updated with accurate API endpoints, complete capability lists, and detailed how-to-run instructions
- **v2.0** (2026-02-07) — Consolidated documentation, added enhancements guide
- **v1.0** (2025-12-15) — Initial documentation

---

## 📦 Archive

Older documentation files have been archived in `docs/archive/` for historical reference:
- Historical implementation summaries
- Deprecated guides
- Development notes

---

## 🆘 Need Help?

1. **Can't find something?** Check this index
2. **Getting started?** Read [README.md](README.md) or [QUICK_START.md](QUICK_START.md)
3. **Deployment issues?** See [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) or [AWS_CREDENTIALS_GUIDE.md](AWS_CREDENTIALS_GUIDE.md)
4. **Test failures?** See [TESTING_GUIDE.md](TESTING_GUIDE.md)
5. **Feature questions?** Check [ENHANCEMENTS_COMPLETE.md](ENHANCEMENTS_COMPLETE.md)

---

**Last Updated**: 2026-03-23  
**Documentation Version**: 2.1  
**System Version**: 2.1
