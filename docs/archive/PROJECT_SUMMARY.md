# Project Summary: A2A Multi-Agent System + MCP Distributed System

## 📋 Overview

This project implements **two complementary distributed systems** for AI-powered automation:

1. **A2A (Agent-to-Agent) Multi-Agent System** - Orchestrated AI agents using AWS Bedrock
2. **MCP (Model Context Protocol) System** - Standardized tool/resource access for LLMs

Both systems are fully modular, distributed, and production-ready with externalized configuration.

---

## 🏗️ Architecture

### A2A Multi-Agent System

```
┌──────────────────┐
│   Orchestrator   │  ← Think-Plan-Execute-Verify-Reflect Pattern
│   (Port 8100)    │
└────────┬─────────┘
         │
         ├──────────────────────────┐
         ▼                          ▼
┌─────────────────┐      ┌──────────────────┐
│  Agent Registry │      │   Specialized    │
│  (Port 8000)    │◄─────┤     Agents       │
└─────────────────┘      └──────────────────┘
         │                         │
         │                         ├─► ResearchAgent (8001)
         │                         ├─► CodeAnalyzer (8002)
         │                         ├─► DataProcessor (8003)
         │                         ├─► TaskExecutor (8004)
         │                         └─► Observer (8005)
         │
         └──► Discovers agents and capabilities
```

### MCP Distributed System

```
┌─────────────────┐
│   MCP Gateway   │  ← Intelligent routing with Bedrock
│   (Port 8201)   │
└────────┬────────┘
         │
         ├──────────────────────────┐
         ▼                          ▼
┌─────────────────┐      ┌──────────────────┐
│  MCP Registry   │      │   MCP Servers    │
│  (Port 8200)    │◄─────┤  (Auto-register) │
└─────────────────┘      └──────────────────┘
         │                         │
         │                         ├─► File Operations (8210)
         │                         ├─► Database Query (8211)
         │                         └─► Web Search (8212)
         │                         └─► Calculator (8213)
         └──► Tool capability indexing
```

---

## 🚀 Services

### A2A System Services

| Service | Port | Description | Key Features |
|---------|------|-------------|--------------|
| **Agent Registry** | 8000 | Agent discovery & management | Auto-registration, capability tracking |
| **Orchestrator** | 8100 | Workflow orchestration | Think-Plan-Execute-Verify-Reflect, Bedrock integration |
| **ResearchAgent** | 8001 | Research & Q&A | Answer questions, generate reports, compare concepts |
| **CodeAnalyzer** | 8002 | Code analysis | Python code analysis, explanations, improvements |
| **DataProcessor** | 8003 | Data transformation | Transform, analyze, summarize data |
| **TaskExecutor** | 8004 | Task execution | Command execution, file ops, system monitoring |
| **Observer** | 8005 | System monitoring | Event logging, metrics, agent statistics |

### MCP System Services

| Service | Port | Description | Key Tools |
|---------|------|-------------|-----------|
| **MCP Registry** | 8200 | Service discovery | Server registration, tool indexing |
| **MCP Gateway** | 8201 | Request routing | NL query processing, tool execution |
| **File Ops Server** | 8210 | File operations | read_file, write_file, list_files, delete_file |
| **Database Server** | 8211 | Database queries | query_database, list_tables, describe_table, search_table |
| **Web Search Server** | 8212 | Web search & fetch | search_web, fetch_url, extract_links, summarize_text |

---

## 📁 Project Structure

```
agentToAgent/
├── services/
│   ├── registry/              # A2A Agent Registry
│   │   ├── app.py
│   │   ├── .env
│   │   └── requirements.txt
│   ├── orchestrator/          # A2A Orchestrator
│   │   ├── app.py
│   │   ├── .env
│   │   └── requirements.txt
│   ├── agents/                # A2A Agents
│   │   ├── research_agent/
│   │   ├── code_analyzer/
│   │   ├── data_processor/
│   │   ├── task_executor/
│   │   └── observer/
│   ├── mcp_registry/          # MCP Registry
│   │   ├── app.py
│   │   ├── .env
│   │   └── requirements.txt
│   ├── mcp_gateway/           # MCP Gateway
│   │   ├── app.py
│   │   ├── .env
│   │   └── requirements.txt
│   └── mcp_servers/           # MCP Servers
│       ├── file_ops/
│       ├── database/
│       └── web_search/
├── shared/                    # Shared utilities
│   └── bedrock_client.py
├── logs/                      # Service logs
│   ├── a2a/
│   └── mcp/
├── setup.sh                   # Setup all dependencies
├── start_services.sh          # Start A2A system
├── stop_services.sh           # Stop A2A system
├── start_mcp_services.sh      # Start MCP system
├── stop_mcp_services.sh       # Stop MCP system
├── test_distributed_system.py # A2A system tests
├── test_mcp_system.py         # MCP system tests
├── DISTRIBUTED_README.md      # A2A documentation
├── MCP_README.md              # MCP documentation
├── CURL_EXAMPLES.md           # A2A API examples
└── MCP_CURL_EXAMPLES.md       # MCP API examples
```

---

## 🎯 Key Features

### A2A Multi-Agent System

✅ **Think-Plan-Execute-Verify-Reflect Pattern**
- Orchestrator analyzes tasks using Bedrock
- Creates multi-step execution plans
- Dynamically routes to appropriate agents
- Verifies results and reflects on performance

✅ **Distributed Architecture**
- Each agent is an independent microservice
- Auto-registration with central registry
- RESTful A2A protocol communication
- Graceful startup/shutdown

✅ **Specialized Agents**
- ResearchAgent: Q&A, reports, comparisons
- CodeAnalyzer: Code analysis and suggestions
- DataProcessor: Data transformation
- TaskExecutor: System operations
- Observer: Monitoring and metrics

✅ **AWS Bedrock Integration**
- Claude 3.5 Sonnet model
- Falls back to local config if env vars not set
- Supports eu-west-2 region

✅ **Context Management**
- Results passed between workflow steps
- Capability-based output tracking
- Full execution history

### MCP Distributed System

✅ **Service Discovery**
- Auto-registration of MCP servers
- Tool capability indexing
- Server health monitoring

✅ **Intelligent Gateway**
- Natural language query processing
- Bedrock-powered tool selection
- Multi-server orchestration

✅ **Multiple MCP Servers**
- File Operations: CRUD on files
- Database: SQL query execution
- Web Search: Search, fetch, summarize

✅ **Production-Ready**
- Modular design
- Easy to add new servers
- Comprehensive error handling
- Full logging

---

## 🛠️ Setup & Usage

### Initial Setup
```bash
# Install dependencies for both systems
./setup.sh

# Configure AWS credentials in .env files or use local AWS config
# Region is set to eu-west-2 by default
```

### Starting Services

**A2A System:**
```bash
./start_services.sh
```

**MCP System:**
```bash
./start_mcp_services.sh
```

**Stop Services:**
```bash
./stop_services.sh        # Stop A2A
./stop_mcp_services.sh    # Stop MCP
```

### Testing

**A2A System:**
```bash
python test_distributed_system.py
```

**MCP System:**
```bash
python test_mcp_system.py
```

### Example Usage

**A2A - Complex Workflow:**
```bash
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Research microservices architecture, then research monolithic architecture, and create a comparison report",
    "workflow_id": "architecture-comparison"
  }' | jq .
```

**MCP - Natural Language Query:**
```bash
curl -X POST http://localhost:8201/api/gateway/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Show me all users in the database and save them to a file",
    "auto_execute": true
  }' | jq .
```

**MCP - Direct Tool Execution:**
```bash
curl -X POST http://localhost:8211/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "query_database",
    "parameters": {
      "sql": "SELECT * FROM products WHERE price > 100"
    }
  }' | jq .
```

---

## 📊 Technology Stack

- **Language**: Python 3.11-3.13
- **Framework**: FastAPI + Uvicorn
- **AI/ML**: AWS Bedrock (Claude 3.5 Sonnet)
- **Database**: SQLite (MCP Database Server)
- **HTTP Client**: httpx
- **Configuration**: python-dotenv
- **Data Validation**: Pydantic

---

## 🔒 Security & Configuration

### Environment Variables

All services use `.env` files for configuration:

**Common Variables:**
- `*_HOST` - Service host (default: 0.0.0.0)
- `*_PORT` - Service port
- `LOG_LEVEL` - Logging level

**AWS Configuration:**
- `AWS_REGION` - AWS region (default: eu-west-2)
- `AWS_ACCESS_KEY_ID` - AWS access key (optional)
- `AWS_SECRET_ACCESS_KEY` - AWS secret key (optional)
- `BEDROCK_MODEL_ID` - Model ID

**Registry URLs:**
- `REGISTRY_URL` - A2A Agent Registry URL
- `MCP_REGISTRY_URL` - MCP Registry URL

### Security Best Practices

✅ Credentials externalized to `.env` files
✅ Falls back to local AWS credentials
✅ No secrets in code
✅ Input validation with Pydantic
✅ Structured logging
✅ Graceful error handling

---

## 📖 Documentation

| Document | Description |
|----------|-------------|
| **DISTRIBUTED_README.md** | Complete A2A system guide |
| **MCP_README.md** | Complete MCP system guide |
| **CURL_EXAMPLES.md** | A2A API usage examples |
| **MCP_CURL_EXAMPLES.md** | MCP API usage examples |
| **DISTRIBUTED_ARCHITECTURE.md** | A2A architecture details |
| **TESTING_GUIDE.md** | Testing strategies |

---

## 🧪 Testing

### A2A System Tests
1. ✅ Registry health and agent registration
2. ✅ Agent capability discovery
3. ✅ Individual agent execution
4. ✅ Observer monitoring
5. ✅ Orchestrator workflow execution
6. ✅ Multi-step workflows with context

### MCP System Tests
1. ✅ MCP Registry server discovery
2. ✅ File operations (CRUD)
3. ✅ Database queries (SQLite)
4. ✅ Web search operations
5. ✅ Gateway routing and execution
6. ✅ Natural language query processing

---

## 🚦 Current Status

### ✅ Completed Features

**A2A System:**
- [x] Distributed agent architecture
- [x] Agent registry with auto-registration
- [x] 5 specialized agents implemented
- [x] Orchestrator with TPEVR pattern
- [x] AWS Bedrock integration
- [x] Context-aware workflow execution
- [x] Comprehensive logging
- [x] Startup/shutdown scripts
- [x] Full test suite

**MCP System:**
- [x] MCP Registry for service discovery
- [x] MCP Gateway with Bedrock integration
- [x] File Operations Server
- [x] Database Query Server (SQLite)
- [x] Web Search Server
- [x] Auto-registration protocol
- [x] Natural language query support
- [x] Startup/shutdown scripts
- [x] Full test suite

### 🎯 Future Enhancements

**Both Systems:**
- [ ] Authentication & authorization
- [ ] HTTPS/TLS support
- [ ] Rate limiting
- [ ] Kubernetes deployment configs
- [ ] Prometheus metrics
- [ ] Distributed tracing

**A2A System:**
- [ ] Agent-to-agent direct communication
- [ ] Workflow persistence
- [ ] Retry mechanisms
- [ ] Parallel agent execution

**MCP System:**
- [ ] Real web search API integration
- [ ] PostgreSQL/MySQL support
- [ ] Additional MCP servers (email, calendar, etc.)
- [ ] Tool composition support

---

## 💡 Use Cases

### A2A Multi-Agent System
- Research and analysis workflows
- Code review and improvement
- Data processing pipelines
- Multi-step task automation
- System monitoring and reporting

### MCP System
- LLM-powered file management
- Database query interfaces
- Web research and content extraction
- Multi-tool workflow automation
- Tool discovery and execution

### Combined Integration
- A2A agents can use MCP tools for enhanced capabilities
- MCP Gateway can route complex tasks to A2A agents
- Unified system for comprehensive automation

---

## 📝 Notes

1. **Python Version**: Use 3.11-3.13 (3.14 not supported due to dependency compatibility)
2. **AWS Credentials**: Can be provided via `.env` or use local AWS configuration
3. **Region**: Hardcoded to eu-west-2 for consistency
4. **Bedrock Model**: Uses Claude 3.5 Sonnet v2
5. **Logs**: Stored in `logs/a2a/` and `logs/mcp/`
6. **Database**: Sample SQLite database with users and products tables
7. **File Workspace**: `/tmp/mcp_workspace` for file operations

---

## 🤝 Contributing

To add new agents or MCP servers:

1. Create service directory
2. Implement FastAPI app with required endpoints
3. Add `.env` configuration
4. Add `requirements.txt`
5. Update startup scripts
6. Add tests
7. Update documentation

---

## 📄 License

This is a demonstration project showcasing distributed agent systems and the Model Context Protocol.

---

## 🎉 Summary

This project provides two powerful, modular, distributed systems:

1. **A2A Multi-Agent System**: Orchestrated AI agents using Think-Plan-Execute-Verify-Reflect pattern
2. **MCP Distributed System**: Standardized tool/resource access following Model Context Protocol

Both systems are:
- ✅ Fully distributed and modular
- ✅ Production-ready with proper error handling
- ✅ AWS Bedrock integrated
- ✅ Externalized configuration
- ✅ Comprehensive testing
- ✅ Well-documented

**Ready to use, easy to extend!** 🚀
