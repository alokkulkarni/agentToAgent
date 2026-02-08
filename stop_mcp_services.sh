#!/bin/bash

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Stopping MCP Services + Math Agent...${NC}"
echo -e "${YELLOW}(Keeping Agent Registry running)${NC}"

# Stop services by PID files
if [ -f .mcp_registry.pid ]; then
    kill $(cat .mcp_registry.pid) 2>/dev/null
    rm -f .mcp_registry.pid
    echo -e "${GREEN}✓ Stopped MCP Registry${NC}"
fi

if [ -f .mcp_gateway.pid ]; then
    kill $(cat .mcp_gateway.pid) 2>/dev/null
    rm -f .mcp_gateway.pid
    echo -e "${GREEN}✓ Stopped MCP Gateway${NC}"
fi

if [ -f .calculator.pid ]; then
    kill $(cat .calculator.pid) 2>/dev/null
    rm -f .calculator.pid
    echo -e "${GREEN}✓ Stopped Calculator Server${NC}"
fi

if [ -f .database.pid ]; then
    kill $(cat .database.pid) 2>/dev/null
    rm -f .database.pid
    echo -e "${GREEN}✓ Stopped Database Server${NC}"
fi

if [ -f .file_ops.pid ]; then
    kill $(cat .file_ops.pid) 2>/dev/null
    rm -f .file_ops.pid
    echo -e "${GREEN}✓ Stopped File Operations Server${NC}"
fi

if [ -f .web_search.pid ]; then
    kill $(cat .web_search.pid) 2>/dev/null
    rm -f .web_search.pid
    echo -e "${GREEN}✓ Stopped Web Search Server${NC}"
fi

if [ -f .math_agent.pid ]; then
    kill $(cat .math_agent.pid) 2>/dev/null
    rm -f .math_agent.pid
    echo -e "${GREEN}✓ Stopped Math Agent${NC}"
fi

# Also try to kill by port (excluding 8000 which is Agent Registry)
for port in 8006 9000 9001 9100 9101 9102; do
    if lsof -i:$port -t >/dev/null 2>&1; then
        kill $(lsof -i:$port -t) 2>/dev/null
    fi
done

echo -e "${GREEN}All MCP services stopped (Agent Registry still running)${NC}"
