# MCP System CURL Examples

This document contains CURL examples for interacting with the Model Context Protocol (MCP) distributed system.

## Prerequisites

Start all MCP services:
```bash
./start_mcp_services.sh
```

## MCP Registry (Port 8200)

### 1. Check Registry Health
```bash
curl http://localhost:8200/ | jq .
```

### 2. List All Registered Servers
```bash
curl http://localhost:8200/api/mcp/servers | jq .
```

### 3. Get Specific Server Details
```bash
# First get a server_id from the list above, then:
curl http://localhost:8200/api/mcp/servers/{server_id} | jq .
```

### 4. List All Available Tools
```bash
curl http://localhost:8200/api/mcp/tools | jq .
```

### 5. Find Servers with Specific Tool
```bash
curl http://localhost:8200/api/mcp/tools/read_file | jq .
curl http://localhost:8200/api/mcp/tools/query_database | jq .
curl http://localhost:8200/api/mcp/tools/search_web | jq .
```

### 6. Discover MCP Ecosystem Capabilities
```bash
curl http://localhost:8200/api/mcp/discovery | jq .
```

---

## MCP Gateway (Port 8201)

### 1. Check Gateway Health
```bash
curl http://localhost:8201/ | jq .
```

### 2. Gateway Discovery
```bash
curl http://localhost:8201/api/gateway/discovery | jq .
```

### 3. List Available Tools via Gateway
```bash
curl http://localhost:8201/api/gateway/tools | jq .
```

### 4. Execute Tool Directly via Gateway
```bash
# List database tables
curl -X POST http://localhost:8201/api/gateway/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "list_tables",
    "parameters": {}
  }' | jq .

# Read a file
curl -X POST http://localhost:8201/api/gateway/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "read_file",
    "parameters": {
      "file_path": "test_mcp.txt"
    }
  }' | jq .

# Query database
curl -X POST http://localhost:8201/api/gateway/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "query_database",
    "parameters": {
      "sql": "SELECT * FROM users"
    }
  }' | jq .
```

### 5. Natural Language Query (Requires AWS Bedrock)
```bash
# Simple database query
curl -X POST http://localhost:8201/api/gateway/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Show me all users in the database",
    "auto_execute": true
  }' | jq .

# File operations
curl -X POST http://localhost:8201/api/gateway/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Create a file called hello.txt with the content Hello World",
    "auto_execute": true
  }' | jq .

# Complex multi-tool query
curl -X POST http://localhost:8201/api/gateway/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "List all database tables, then show me the users table structure",
    "auto_execute": true
  }' | jq .
```

---

## File Operations Server (Port 8210)

### 1. Server Health
```bash
curl http://localhost:8210/ | jq .
```

### 2. List Available Tools
```bash
curl http://localhost:8210/api/tools | jq .
```

### 3. Write File
```bash
curl -X POST http://localhost:8210/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "write_file",
    "parameters": {
      "file_path": "hello.txt",
      "content": "Hello from MCP File Operations!\nThis is line 2.\nAnd this is line 3."
    }
  }' | jq .
```

### 4. Read File
```bash
curl -X POST http://localhost:8210/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "read_file",
    "parameters": {
      "file_path": "hello.txt"
    }
  }' | jq .
```

### 5. List Files
```bash
# List all files
curl -X POST http://localhost:8210/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "list_files",
    "parameters": {
      "directory": ".",
      "pattern": "*"
    }
  }' | jq .

# List only text files
curl -X POST http://localhost:8210/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "list_files",
    "parameters": {
      "directory": ".",
      "pattern": "*.txt"
    }
  }' | jq .
```

### 6. Delete File
```bash
curl -X POST http://localhost:8210/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "delete_file",
    "parameters": {
      "file_path": "hello.txt"
    }
  }' | jq .
```

---

## Database Query Server (Port 8211)

### 1. Server Health
```bash
curl http://localhost:8211/ | jq .
```

### 2. List Available Tools
```bash
curl http://localhost:8211/api/tools | jq .
```

### 3. List Tables
```bash
curl -X POST http://localhost:8211/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "list_tables",
    "parameters": {}
  }' | jq .
```

### 4. Describe Table Structure
```bash
curl -X POST http://localhost:8211/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "describe_table",
    "parameters": {
      "table_name": "users"
    }
  }' | jq .

curl -X POST http://localhost:8211/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "describe_table",
    "parameters": {
      "table_name": "products"
    }
  }' | jq .
```

### 5. Query Database
```bash
# Select all users
curl -X POST http://localhost:8211/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "query_database",
    "parameters": {
      "sql": "SELECT * FROM users"
    }
  }' | jq .

# Select all products
curl -X POST http://localhost:8211/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "query_database",
    "parameters": {
      "sql": "SELECT * FROM products"
    }
  }' | jq .

# Filter products by category
curl -X POST http://localhost:8211/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "query_database",
    "parameters": {
      "sql": "SELECT * FROM products WHERE category = \"Electronics\""
    }
  }' | jq .

# Count users
curl -X POST http://localhost:8211/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "query_database",
    "parameters": {
      "sql": "SELECT COUNT(*) as user_count FROM users"
    }
  }' | jq .
```

### 6. Search Table
```bash
curl -X POST http://localhost:8211/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "search_table",
    "parameters": {
      "table_name": "users",
      "column": "name",
      "value": "Alice"
    }
  }' | jq .

curl -X POST http://localhost:8211/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "search_table",
    "parameters": {
      "table_name": "products",
      "column": "name",
      "value": "Laptop"
    }
  }' | jq .
```

### 7. Insert Data
```bash
curl -X POST http://localhost:8211/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "query_database",
    "parameters": {
      "sql": "INSERT INTO users (name, email) VALUES (\"John Doe\", \"john@example.com\")"
    }
  }' | jq .
```

---

## Web Search Server (Port 8212)

### 1. Server Health
```bash
curl http://localhost:8212/ | jq .
```

### 2. List Available Tools
```bash
curl http://localhost:8212/api/tools | jq .
```

### 3. Search Web (Mock Implementation)
```bash
curl -X POST http://localhost:8212/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "search_web",
    "parameters": {
      "query": "Model Context Protocol",
      "max_results": 5
    }
  }' | jq .

curl -X POST http://localhost:8212/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "search_web",
    "parameters": {
      "query": "Python multi-agent systems",
      "max_results": 3
    }
  }' | jq .
```

### 4. Fetch URL Content
```bash
curl -X POST http://localhost:8212/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "fetch_url",
    "parameters": {
      "url": "https://example.com"
    }
  }' | jq .
```

### 5. Extract Links from Webpage
```bash
curl -X POST http://localhost:8212/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "extract_links",
    "parameters": {
      "url": "https://example.com"
    }
  }' | jq .
```

### 6. Summarize Text
```bash
curl -X POST http://localhost:8212/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "summarize_text",
    "parameters": {
      "text": "The Model Context Protocol (MCP) is an open protocol that standardizes how applications provide context to Large Language Models. MCP enables secure, controlled interactions between AI systems and various data sources including databases, file systems, and web services. The protocol defines a client-server architecture where MCP servers expose tools and resources that MCP clients can discover and utilize. This creates a standardized, interoperable way for LLMs to interact with external systems while maintaining security and control.",
      "max_length": 30
    }
  }' | jq .
```

---

## Complex Multi-Tool Workflows

### Example 1: Database Analysis and File Export
```bash
# Step 1: Query users
curl -X POST http://localhost:8211/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "query_database",
    "parameters": {
      "sql": "SELECT * FROM users"
    }
  }' > users_data.json

# Step 2: Write results to file
# (Extract the results from users_data.json and format as needed)
curl -X POST http://localhost:8210/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "write_file",
    "parameters": {
      "file_path": "users_export.txt",
      "content": "User Export from Database\n========================\n[Results would go here]"
    }
  }' | jq .
```

### Example 2: Using Gateway for Complex Query
```bash
curl -X POST http://localhost:8201/api/gateway/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Get all products from the database with price greater than 100, then write the results to a file called expensive_products.txt",
    "auto_execute": true,
    "context": {
      "user": "analyst",
      "task": "product_analysis"
    }
  }' | jq .
```

---

## Troubleshooting Commands

### Check if all services are running
```bash
echo "MCP Registry:" && curl -s http://localhost:8200/ | jq -r .status
echo "MCP Gateway:" && curl -s http://localhost:8201/ | jq -r .status
echo "File Ops:" && curl -s http://localhost:8210/ | jq -r .status
echo "Database:" && curl -s http://localhost:8211/ | jq -r .status
echo "Web Search:" && curl -s http://localhost:8212/ | jq -r .status
```

### Check server registration status
```bash
curl -s http://localhost:8200/api/mcp/servers | jq '[.[] | {name: .name, status: .status, tools: [.tools[].name]}]'
```

### View logs
```bash
tail -f logs/mcp/registry.log
tail -f logs/mcp/gateway.log
tail -f logs/mcp/file_ops.log
tail -f logs/mcp/database.log
tail -f logs/mcp/web_search.log
```

---

## Notes

1. **jq** is used for JSON formatting. Install with: `brew install jq` (macOS) or `apt install jq` (Linux)

2. **Natural Language Queries** via the Gateway require AWS Bedrock to be configured with valid credentials.

3. **Mock Web Search**: The web search server uses mock data. In production, integrate with a real search API.

4. **File Operations**: Files are stored in `/tmp/mcp_workspace` by default. Change via `WORKSPACE_DIR` environment variable.

5. **Database**: Uses SQLite with sample data. Path: `/tmp/mcp_database.db`

For more information, see **MCP_README.md**
