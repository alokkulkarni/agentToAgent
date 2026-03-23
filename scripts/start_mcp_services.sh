#!/bin/bash

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the project root directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$PROJECT_ROOT/venv"

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}MCP System + Math Agent Startup${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""

# Function to check if ports are in use
check_ports() {
    local ports_in_use=()
    
    # Check only MCP-specific ports (not Agent Registry 8000)
    for port in 8006 9000 9001 9100 9101 9102; do
        if lsof -i:$port -t >/dev/null 2>&1; then
            ports_in_use+=($port)
        fi
    done
    
    if [ ${#ports_in_use[@]} -gt 0 ]; then
        echo -e "${YELLOW}⚠ Some ports are already in use: ${ports_in_use[*]}${NC}"
        echo ""
        read -p "Stop existing services and continue? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${YELLOW}Stopping existing services...${NC}"
            ./stop_mcp_services.sh
            echo ""
        else
            echo -e "${RED}Cannot start - ports are in use${NC}"
            exit 1
        fi
    fi
}

# Function to check if Agent Registry is running
check_agent_registry() {
    if ! lsof -i:8000 -t >/dev/null 2>&1; then
        echo -e "${RED}✗ Agent Registry is not running on port 8000${NC}"
        echo -e "${YELLOW}Please start the main A2A system first using ./start_services.sh${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Agent Registry detected on port 8000${NC}"
}

# Check if Agent Registry is running
echo -e "${YELLOW}Checking Agent Registry...${NC}"
check_agent_registry
echo ""

# Check if ports are available
echo -e "${YELLOW}Checking ports...${NC}"
check_ports
echo -e "${GREEN}✓ All ports available${NC}"
echo ""

# Activate virtual environment
if [ -f "$VENV_PATH/bin/activate" ]; then
    source "$VENV_PATH/bin/activate"
    echo -e "${GREEN}✓ Virtual environment activated${NC}"
else
    echo -e "${RED}✗ Virtual environment not found. Run setup.sh first${NC}"
    exit 1
fi
echo ""

# Dependencies should be installed via setup.sh
echo -e "${GREEN}✓ Using dependencies from venv (installed via setup.sh)${NC}"
echo ""

# Start services
echo -e "${YELLOW}Starting MCP services...${NC}"
echo -e "${YELLOW}(Using existing Agent Registry on port 8000)${NC}"
echo ""

# Start MCP Registry
echo -e "${BLUE}Starting MCP Registry...${NC}"
cd "$PROJECT_ROOT/services/mcp_registry"
python app.py &
MCP_REGISTRY_PID=$!
echo -e "MCP Registry PID: ${GREEN}$MCP_REGISTRY_PID${NC}"
sleep 2

# Start MCP Servers
echo -e "${BLUE}Starting MCP Servers...${NC}"

# Calculator Server
cd "$PROJECT_ROOT/services/mcp_servers/calculator"
python app.py &
CALCULATOR_PID=$!
echo -e "Calculator Server PID: ${GREEN}$CALCULATOR_PID${NC}"

# Database Server
cd "$PROJECT_ROOT/services/mcp_servers/database"
python app.py &
DATABASE_PID=$!
echo -e "Database Server PID: ${GREEN}$DATABASE_PID${NC}"

# File Operations Server
cd "$PROJECT_ROOT/services/mcp_servers/file_ops"
python app.py &
FILE_OPS_PID=$!
echo -e "File Operations Server PID: ${GREEN}$FILE_OPS_PID${NC}"

# Web Search Server
cd "$PROJECT_ROOT/services/mcp_servers/web_search"
python app.py &
WEB_SEARCH_PID=$!
echo -e "Web Search Server PID: ${GREEN}$WEB_SEARCH_PID${NC}"

sleep 3

# Start MCP Gateway
echo -e "${BLUE}Starting MCP Gateway...${NC}"
cd "$PROJECT_ROOT/services/mcp_gateway"
python app.py &
MCP_GATEWAY_PID=$!
echo -e "MCP Gateway PID: ${GREEN}$MCP_GATEWAY_PID${NC}"
sleep 2

# Start Math Agent
echo -e "${BLUE}Starting Math Agent...${NC}"
cd "$PROJECT_ROOT/services/agents/math_agent"
python app.py &
MATH_AGENT_PID=$!
echo -e "Math Agent PID: ${GREEN}$MATH_AGENT_PID${NC}"

echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}All Services Started Successfully!${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo "Core Services:"
echo -e "  ${GREEN}Agent Registry:${NC}    http://localhost:8000 (shared)"
echo -e "  ${GREEN}MCP Registry:${NC}      http://localhost:9001"
echo -e "  ${GREEN}MCP Gateway:${NC}       http://localhost:9000"
echo ""
echo "MCP Servers:"
echo -e "  ${GREEN}Database:${NC}          http://localhost:9100"
echo -e "  ${GREEN}File Operations:${NC}   http://localhost:9101"
echo -e "  ${GREEN}Web Search:${NC}        http://localhost:9102"
echo ""
echo "Agents:"
echo -e "  ${GREEN}Math Agent:${NC}        http://localhost:8006"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Save PIDs to file
echo "$MCP_REGISTRY_PID" > .mcp_registry.pid
echo "$MCP_GATEWAY_PID" > .mcp_gateway.pid
echo "$DATABASE_PID" > .database.pid
echo "$FILE_OPS_PID" > .file_ops.pid
echo "$WEB_SEARCH_PID" > .web_search.pid
echo "$MATH_AGENT_PID" > .math_agent.pid

# Wait for Ctrl+C
trap "echo ''; echo 'Stopping MCP services...'; kill $MCP_REGISTRY_PID $DATABASE_PID $FILE_OPS_PID $WEB_SEARCH_PID $MCP_GATEWAY_PID $MATH_AGENT_PID 2>/dev/null; rm -f .mcp_registry.pid .mcp_gateway.pid .database.pid .file_ops.pid .web_search.pid .math_agent.pid; echo 'MCP services stopped (Agent Registry still running)'; exit" INT

# Keep script running
wait
