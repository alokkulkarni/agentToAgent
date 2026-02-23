"""
MCP Server - Database Query
Provides database query tools via MCP protocol
"""
import os
import json
import uuid
import sqlite3
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import httpx
from datetime import datetime, timezone
from pathlib import Path


# Environment Configuration
SERVER_HOST = os.getenv("MCP_DATABASE_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("MCP_DATABASE_PORT", "8211"))
MCP_REGISTRY_URL = os.getenv("MCP_REGISTRY_URL", "http://localhost:8200")
DATABASE_PATH = os.getenv("DATABASE_PATH", "/tmp/mcp_database.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").lower()


# Models
class ToolExecutionRequest(BaseModel):
    """Tool execution request"""
    tool_name: str
    parameters: Dict[str, Any]


# FastAPI App
app = FastAPI(title="MCP Database Query Server", version="1.0.0")

# Server state
server_id = str(uuid.uuid4())
http_client = httpx.AsyncClient(timeout=10.0)


# Initialize database
def init_database():
    """Initialize sample database"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Create sample tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL,
            category TEXT,
            stock INTEGER DEFAULT 0
        )
    """)
    
    # Insert sample data if empty
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO users (name, email) VALUES (?, ?)",
            [
                ("Alice Johnson", "alice@example.com"),
                ("Bob Smith", "bob@example.com"),
                ("Charlie Davis", "charlie@example.com")
            ]
        )
    
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO products (name, price, category, stock) VALUES (?, ?, ?, ?)",
            [
                ("Laptop", 999.99, "Electronics", 10),
                ("Mouse", 29.99, "Electronics", 50),
                ("Desk Chair", 199.99, "Furniture", 15),
                ("Notebook", 4.99, "Stationery", 100)
            ]
        )
    
    conn.commit()
    conn.close()
    print(f"✓ Database initialized: {DATABASE_PATH}")


init_database()


# Tool implementations
def query_database(sql: str, parameters: Optional[List] = None) -> Dict[str, Any]:
    """Execute a SQL query"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if parameters:
            cursor.execute(sql, parameters)
        else:
            cursor.execute(sql)
        
        # Check if it's a SELECT query
        if sql.strip().upper().startswith("SELECT"):
            rows = cursor.fetchall()
            results = [dict(row) for row in rows]
            
            return {
                "query": sql,
                "row_count": len(results),
                "results": results
            }
        else:
            # For INSERT, UPDATE, DELETE
            conn.commit()
            return {
                "query": sql,
                "rows_affected": cursor.rowcount,
                "status": "success"
            }
    except Exception as e:
        return {"error": str(e), "query": sql}
    finally:
        conn.close()


def list_tables() -> Dict[str, Any]:
    """List all tables in the database"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT name, sql 
            FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        
        tables = []
        for row in cursor.fetchall():
            tables.append({
                "name": row[0],
                "schema": row[1]
            })
        
        conn.close()
        
        return {
            "tables": tables,
            "total": len(tables)
        }
    except Exception as e:
        return {"error": str(e)}


def describe_table(table_name: str) -> Dict[str, Any]:
    """Describe the structure of a table"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = []
        
        for row in cursor.fetchall():
            columns.append({
                "column_id": row[0],
                "name": row[1],
                "type": row[2],
                "not_null": bool(row[3]),
                "default_value": row[4],
                "primary_key": bool(row[5])
            })
        
        conn.close()
        
        if not columns:
            return {"error": f"Table not found: {table_name}"}
        
        return {
            "table_name": table_name,
            "columns": columns,
            "total_columns": len(columns)
        }
    except Exception as e:
        return {"error": str(e)}


def search_table(table_name: str, column: str, value: str) -> Dict[str, Any]:
    """Search for records in a table"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = f"SELECT * FROM {table_name} WHERE {column} LIKE ?"
        cursor.execute(query, [f"%{value}%"])
        
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        
        conn.close()
        
        return {
            "table_name": table_name,
            "search_column": column,
            "search_value": value,
            "results": results,
            "total_found": len(results)
        }
    except Exception as e:
        return {"error": str(e)}


# Tool registry
TOOLS = {
    "query_database": {
        "function": query_database,
        "description": "Execute a SQL query on the database",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "SQL query to execute"
                },
                "parameters": {
                    "type": "array",
                    "description": "Optional parameters for parameterized queries",
                    "items": {"type": "string"}
                }
            },
            "required": ["sql"]
        }
    },
    "list_tables": {
        "function": list_tables,
        "description": "List all tables in the database",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    "describe_table": {
        "function": describe_table,
        "description": "Describe the structure of a database table",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Name of the table to describe"
                }
            },
            "required": ["table_name"]
        }
    },
    "search_table": {
        "function": search_table,
        "description": "Search for records in a table",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Name of the table to search"
                },
                "column": {
                    "type": "string",
                    "description": "Column to search in"
                },
                "value": {
                    "type": "string",
                    "description": "Value to search for"
                }
            },
            "required": ["table_name", "column", "value"]
        }
    }
}


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "MCP Database Query Server",
        "status": "running",
        "server_id": server_id,
        "tools_available": len(TOOLS),
        "database": DATABASE_PATH
    }


@app.post("/api/tools/execute")
async def execute_tool(request: ToolExecutionRequest):
    """Execute a tool"""
    if request.tool_name not in TOOLS:
        raise HTTPException(status_code=404, detail=f"Tool not found: {request.tool_name}")
    
    tool = TOOLS[request.tool_name]
    
    try:
        result = tool["function"](**request.parameters)
        return {
            "tool_name": request.tool_name,
            "result": result,
            "executed_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {
            "tool_name": request.tool_name,
            "error": str(e)
        }


@app.get("/api/tools")
async def list_tools():
    """List available tools"""
    return {
        "tools": [
            {
                "name": name,
                "description": tool["description"],
                "input_schema": tool["input_schema"]
            }
            for name, tool in TOOLS.items()
        ]
    }


async def register_with_registry():
    """Register this server with the MCP registry"""
    tools = [
        {
            "name": name,
            "description": tool["description"],
            "input_schema": tool["input_schema"]
        }
        for name, tool in TOOLS.items()
    ]
    
    registration = {
        "server_id": server_id,
        "name": "DatabaseQueryServer",
        "description": "Provides database query operations (SQL queries, table inspection)",
        "base_url": f"http://{SERVER_HOST}:{SERVER_PORT}",
        "tools": tools,
        "metadata": {
            "database": DATABASE_PATH,
            "database_type": "SQLite"
        }
    }
    
    try:
        response = await http_client.post(
            f"{MCP_REGISTRY_URL}/api/mcp/register",
            json=registration
        )
        
        if response.status_code == 200:
            print(f"✓ Registered with MCP Registry: {server_id}")
            print(f"  Tools: {list(TOOLS.keys())}")
        else:
            print(f"✗ Failed to register: {response.status_code}")
    except Exception as e:
        print(f"✗ Error registering with registry: {e}")


async def unregister_from_registry():
    """Unregister this server from the MCP registry"""
    try:
        await http_client.delete(f"{MCP_REGISTRY_URL}/api/mcp/unregister/{server_id}")
        print(f"✓ Unregistered from MCP Registry")
    except Exception as e:
        print(f"Error unregistering: {e}")


@app.on_event("startup")
async def startup_event():
    """Register with registry on startup"""
    await register_with_registry()


@app.on_event("shutdown")
async def shutdown_event():
    """Unregister from registry on shutdown"""
    await unregister_from_registry()
    await http_client.aclose()


if __name__ == "__main__":
    print(f"🚀 Starting MCP Database Query Server on {SERVER_HOST}:{SERVER_PORT}")
    print(f"🗄️  Database: {DATABASE_PATH}")
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level=LOG_LEVEL)
