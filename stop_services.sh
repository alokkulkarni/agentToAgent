#!/bin/bash

# Stop all A2A services script

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo -e "${YELLOW}Stopping A2A Multi-Agent System Services...${NC}"
echo ""

# Function to kill process on a port
kill_port() {
    local port=$1
    local service=$2
    
    PID=$(lsof -ti:$port)
    if [ ! -z "$PID" ]; then
        echo -e "${YELLOW}Stopping $service on port $port (PID: $PID)...${NC}"
        kill $PID 2>/dev/null
        sleep 1
        
        # Force kill if still running
        if kill -0 $PID 2>/dev/null; then
            echo -e "${YELLOW}Force stopping...${NC}"
            kill -9 $PID 2>/dev/null
        fi
        echo -e "${GREEN}✓ $service stopped${NC}"
    else
        echo -e "${GREEN}✓ Port $port is free${NC}"
    fi
}

# Stop all services
kill_port 8000 "Registry"
kill_port 8100 "Orchestrator"
kill_port 8200 "MCP Registry"
kill_port 8300 "MCP Gateway"
kill_port 8213 "Calculator MCP Server"
kill_port 8210 "File Ops MCP Server"
kill_port 8211 "Database MCP Server"
kill_port 8212 "Web Search MCP Server"
kill_port 8001 "Code Analyzer"
kill_port 8002 "Data Processor"
kill_port 8003 "Research Agent"
kill_port 8004 "Task Executor"
kill_port 8005 "Observer"
kill_port 8006 "Math Agent"

echo ""
echo -e "${GREEN}All services stopped!${NC}"
echo ""

# Verify all ports are free
echo -e "${YELLOW}Verifying ports are free...${NC}"
PORTS_IN_USE=$(lsof -i :8000 -i :8001 -i :8002 -i :8003 -i :8004 -i :8005 -i :8006 -i :8100 -i :8200 -i :8210 -i :8211 -i :8212 -i :8213 -i :8300 | grep LISTEN)

if [ -z "$PORTS_IN_USE" ]; then
    echo -e "${GREEN}✓ All ports are now available${NC}"
else
    echo -e "${YELLOW}⚠ Some ports still in use:${NC}"
    lsof -i :8000 -i :8001 -i :8002 -i :8003 -i :8004 -i :8005 -i :8006 -i :8100 -i :8200 -i :8210 -i :8211 -i :8212 -i :8213 -i :8300 | grep LISTEN
fi

echo ""
