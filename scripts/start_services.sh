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
echo -e "${GREEN}A2A Multi-Agent System Setup & Start${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""

# Function to check if ports are in use
check_ports() {
    local ports_in_use=()
    
    for port in 8000 8001 8002 8003 8004 8005 8006 8100 8200 8208 8210 8211 8212 8213 8300; do
        if lsof -i:$port -t >/dev/null 2>&1; then
            ports_in_use+=($port)
        fi
    done
    
    if [ ${#ports_in_use[@]} -gt 0 ]; then
        echo -e "${YELLOW}⚠ Some ports are already in use: ${ports_in_use[*]}${NC}"
        echo -e "${YELLOW}Services may already be running.${NC}"
        echo ""
        read -p "Stop existing services and continue? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${YELLOW}Stopping existing services...${NC}"
            ./stop_services.sh
            echo ""
        else
            echo -e "${RED}Cannot start - ports are in use${NC}"
            echo -e "${YELLOW}Run: ./stop_services.sh to stop existing services${NC}"
            exit 1
        fi
    fi
}

# Check if ports are available
echo -e "${YELLOW}Step 0: Checking ports...${NC}"
check_ports
echo -e "${GREEN}✓ All ports available${NC}"
echo ""

# Function to find compatible Python version
find_python() {
    # Try python3.13, python3.12, python3.11, python3
    for py_cmd in python3.13 python3.12 python3.11 python3; do
        if command -v $py_cmd &> /dev/null; then
            local version=$($py_cmd --version 2>&1 | cut -d' ' -f2)
            local major=$(echo $version | cut -d. -f1)
            local minor=$(echo $version | cut -d. -f2)
            
            # Check if version is 3.11, 3.12, or 3.13
            if [ "$major" = "3" ] && [ "$minor" -ge 11 ] && [ "$minor" -le 13 ]; then
                echo $py_cmd
                return 0
            fi
        fi
    done
    echo ""
    return 1
}

# Function to check if venv exists
check_venv() {
    if [ ! -d "$VENV_PATH" ]; then
        echo -e "${YELLOW}Virtual environment not found. Creating...${NC}"
        
        PYTHON_CMD=$(find_python)
        if [ -z "$PYTHON_CMD" ]; then
            echo -e "${RED}✗ Compatible Python version not found${NC}"
            echo -e "${YELLOW}Please install Python 3.11, 3.12, or 3.13${NC}"
            echo -e "${YELLOW}Run: ./setup.sh for guided setup${NC}"
            exit 1
        fi
        
        $PYTHON_CMD -m venv "$VENV_PATH"
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✓ Virtual environment created${NC}"
        else
            echo -e "${RED}✗ Failed to create virtual environment${NC}"
            exit 1
        fi
    else
        echo -e "${GREEN}✓ Virtual environment found${NC}"
    fi
}

# Function to activate venv
activate_venv() {
    if [ -f "$VENV_PATH/bin/activate" ]; then
        source "$VENV_PATH/bin/activate"
        echo -e "${GREEN}✓ Virtual environment activated${NC}"
    else
        echo -e "${RED}✗ Failed to activate virtual environment${NC}"
        exit 1
    fi
}

# Function to install dependencies for a service
install_dependencies() {
    local service_path=$1
    local service_name=$2
    
    if [ -f "$service_path/requirements.txt" ]; then
        echo -e "${BLUE}Installing dependencies for $service_name...${NC}"
        pip install -q -r "$service_path/requirements.txt"
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✓ Dependencies installed for $service_name${NC}"
        else
            echo -e "${RED}✗ Failed to install dependencies for $service_name${NC}"
            exit 1
        fi
    fi
}

# Step 1: Check and create venv
echo -e "${YELLOW}Step 1: Checking virtual environment...${NC}"
check_venv
echo ""

# Step 2: Activate venv
echo -e "${YELLOW}Step 2: Activating virtual environment...${NC}"
activate_venv
echo ""

# Step 3: Upgrade pip
echo -e "${YELLOW}Step 3: Upgrading pip...${NC}"
pip install -q --upgrade pip
echo -e "${GREEN}✓ pip upgraded${NC}"
echo ""

# Step 4: Install dependencies for all services
echo -e "${YELLOW}Step 4: Installing dependencies for all services...${NC}"
echo ""

# Registry
install_dependencies "$PROJECT_ROOT/services/registry" "Registry"

# Orchestrator
install_dependencies "$PROJECT_ROOT/services/orchestrator" "Orchestrator"

# MCP Services (skip - already installed by setup.sh)
echo -e "${GREEN}✓ Skipping MCP services (already installed)${NC}"
install_dependencies "$PROJECT_ROOT/services/mcp_registry" "MCP Registry"
install_dependencies "$PROJECT_ROOT/services/mcp_gateway" "MCP Gateway"

# All Agents
install_dependencies "$PROJECT_ROOT/services/agents/code_analyzer" "Code Analyzer"
install_dependencies "$PROJECT_ROOT/services/agents/data_processor" "Data Processor"
install_dependencies "$PROJECT_ROOT/services/agents/research_agent" "Research Agent"
install_dependencies "$PROJECT_ROOT/services/agents/task_executor" "Task Executor"
install_dependencies "$PROJECT_ROOT/services/agents/observer" "Observer"
install_dependencies "$PROJECT_ROOT/services/agents/math_agent" "Math Agent"

echo ""
echo -e "${GREEN}✓ All dependencies installed successfully${NC}"
echo ""

# Step 5: Start all services
echo -e "${YELLOW}Step 5: Starting all services...${NC}"
echo ""

# Start Registry Service
echo -e "${BLUE}Starting Registry Service...${NC}"
cd "$PROJECT_ROOT/services/registry"
python app.py &
REGISTRY_PID=$!
echo -e "Registry PID: ${GREEN}$REGISTRY_PID${NC}"

# Wait for registry to be ready
sleep 3

# Start Orchestrator Service
echo -e "${BLUE}Starting Orchestrator Service...${NC}"
cd "$PROJECT_ROOT/services/orchestrator"
python app.py > "$PROJECT_ROOT/logs/orchestrator.log" 2>&1 &
ORCHESTRATOR_PID=$!
echo -e "Orchestrator PID: ${GREEN}$ORCHESTRATOR_PID${NC}"
sleep 2

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

# Start All Agents
echo -e "${BLUE}Starting Agent Services...${NC}"

# Code Analyzer
cd "$PROJECT_ROOT/services/agents/code_analyzer"
python app.py &
CODE_ANALYZER_PID=$!
echo -e "Code Analyzer PID: ${GREEN}$CODE_ANALYZER_PID${NC}"

# Data Processor
cd "$PROJECT_ROOT/services/agents/data_processor"
python app.py > "$PROJECT_ROOT/logs/data_processor.log" 2>&1 &
DATA_PROCESSOR_PID=$!
echo -e "Data Processor PID: ${GREEN}$DATA_PROCESSOR_PID${NC}"

# Research Agent
cd "$PROJECT_ROOT/services/agents/research_agent"
python app.py &
RESEARCH_AGENT_PID=$!
echo -e "Research Agent PID: ${GREEN}$RESEARCH_AGENT_PID${NC}"

# Task Executor
cd "$PROJECT_ROOT/services/agents/task_executor"
python app.py &
TASK_EXECUTOR_PID=$!
echo -e "Task Executor PID: ${GREEN}$TASK_EXECUTOR_PID${NC}"

# Observer
cd "$PROJECT_ROOT/services/agents/observer"
python app.py &
OBSERVER_PID=$!
echo -e "Observer PID: ${GREEN}$OBSERVER_PID${NC}"

# Math Agent (uses MCP Gateway)
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
echo -e "  ${GREEN}Registry:${NC}        http://localhost:8000"
echo -e "  ${GREEN}Orchestrator:${NC}    http://localhost:8100"
echo -e "  ${GREEN}MCP Registry:${NC}    http://localhost:8200"
echo -e "  ${GREEN}MCP Gateway:${NC}     http://localhost:8300"
echo ""
echo "MCP Servers:"
echo -e "  ${GREEN}Calculator:${NC}      http://localhost:8213"
echo -e "  ${GREEN}Database:${NC}        http://localhost:8211"
echo -e "  ${GREEN}File Ops:${NC}        http://localhost:8210"
echo -e "  ${GREEN}Web Search:${NC}      http://localhost:8212"
echo ""
echo "Agents:"
echo -e "  ${GREEN}Code Analyzer:${NC}   http://localhost:8001"
echo -e "  ${GREEN}Data Processor:${NC}  http://localhost:8002"
echo -e "  ${GREEN}Research Agent:${NC}  http://localhost:8003"
echo -e "  ${GREEN}Task Executor:${NC}   http://localhost:8004"
echo -e "  ${GREEN}Observer:${NC}        http://localhost:8005"
echo -e "  ${GREEN}Math Agent:${NC}      http://localhost:8006"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Wait for Ctrl+C
trap "echo ''; echo 'Stopping services...'; kill $REGISTRY_PID $ORCHESTRATOR_PID $MCP_REGISTRY_PID $CALCULATOR_PID $DATABASE_PID $FILE_OPS_PID $WEB_SEARCH_PID $MCP_GATEWAY_PID $CODE_ANALYZER_PID $DATA_PROCESSOR_PID $RESEARCH_AGENT_PID $TASK_EXECUTOR_PID $OBSERVER_PID $MATH_AGENT_PID 2>/dev/null; echo 'Services stopped'; exit" INT

# Keep script running
wait
