#!/bin/bash

# Setup script for A2A Multi-Agent System
# This script sets up the virtual environment and installs all dependencies

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the project root directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$PROJECT_ROOT/venv"

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                                              ║${NC}"
echo -e "${GREEN}║   A2A Multi-Agent System Setup Script       ║${NC}"
echo -e "${GREEN}║                                              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
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

# Check if Python 3 is installed
echo -e "${YELLOW}Checking Python installation...${NC}"
PYTHON_CMD=$(find_python)

if [ -z "$PYTHON_CMD" ]; then
    echo -e "${RED}✗ Compatible Python version not found${NC}"
    echo -e "${YELLOW}Please install Python 3.11, 3.12, or 3.13${NC}"
    echo -e "${YELLOW}Python 3.14+ is not yet supported by pydantic${NC}"
    echo ""
    echo -e "${BLUE}Install options:${NC}"
    echo "  macOS: brew install python@3.13"
    echo "  Ubuntu: sudo apt-get install python3.13"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version | cut -d' ' -f2)
echo -e "${GREEN}✓ Python $PYTHON_VERSION found ($PYTHON_CMD)${NC}"
echo ""

# Create virtual environment
echo -e "${YELLOW}Creating virtual environment with $PYTHON_CMD...${NC}"
if [ -d "$VENV_PATH" ]; then
    echo -e "${YELLOW}Virtual environment already exists. Removing old one...${NC}"
    rm -rf "$VENV_PATH"
fi

$PYTHON_CMD -m venv "$VENV_PATH"
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Virtual environment created at: $VENV_PATH${NC}"
else
    echo -e "${RED}✗ Failed to create virtual environment${NC}"
    exit 1
fi
echo ""

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source "$VENV_PATH/bin/activate"
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Virtual environment activated${NC}"
else
    echo -e "${RED}✗ Failed to activate virtual environment${NC}"
    exit 1
fi
echo ""

# Upgrade pip
echo -e "${YELLOW}Upgrading pip...${NC}"
pip install --upgrade pip > /dev/null 2>&1
echo -e "${GREEN}✓ pip upgraded${NC}"
echo ""

# Function to install dependencies for a service
install_dependencies() {
    local service_path=$1
    local service_name=$2
    
    if [ -f "$service_path/requirements.txt" ]; then
        echo -e "${BLUE}Installing dependencies for $service_name...${NC}"
        pip install -r "$service_path/requirements.txt"
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✓ Dependencies installed for $service_name${NC}"
        else
            echo -e "${RED}✗ Failed to install dependencies for $service_name${NC}"
            return 1
        fi
    else
        echo -e "${YELLOW}⚠ No requirements.txt found for $service_name${NC}"
    fi
}

# Install dependencies for all services
echo -e "${YELLOW}Installing dependencies for all services...${NC}"
echo ""

# Registry
install_dependencies "$PROJECT_ROOT/services/registry" "Registry Service"
echo ""

# Orchestrator
install_dependencies "$PROJECT_ROOT/services/orchestrator" "Orchestrator Service"
echo ""

# All Agents
echo -e "${BLUE}Installing dependencies for agents...${NC}"
install_dependencies "$PROJECT_ROOT/services/agents/code_analyzer" "Code Analyzer Agent"
echo ""
install_dependencies "$PROJECT_ROOT/services/agents/data_processor" "Data Processor Agent"
echo ""
install_dependencies "$PROJECT_ROOT/services/agents/research_agent" "Research Agent"
echo ""
install_dependencies "$PROJECT_ROOT/services/agents/task_executor" "Task Executor Agent"
echo ""
install_dependencies "$PROJECT_ROOT/services/agents/observer" "Observer Agent"
echo ""

# MCP Services
echo -e "${BLUE}Installing dependencies for MCP services...${NC}"
install_dependencies "$PROJECT_ROOT/services/mcp_registry" "MCP Registry"
echo ""
install_dependencies "$PROJECT_ROOT/services/mcp_gateway" "MCP Gateway"
echo ""
install_dependencies "$PROJECT_ROOT/services/mcp_servers/calculator" "MCP Calculator Server"
echo ""
install_dependencies "$PROJECT_ROOT/services/mcp_servers/file_ops" "MCP File Operations Server"
echo ""
install_dependencies "$PROJECT_ROOT/services/mcp_servers/database" "MCP Database Server"
echo ""
install_dependencies "$PROJECT_ROOT/services/mcp_servers/web_search" "MCP Web Search Server"
echo ""
install_dependencies "$PROJECT_ROOT/services/agents/math_agent" "Math Agent"
echo ""

# Create .env files from examples if they don't exist
echo -e "${YELLOW}Setting up environment configuration files...${NC}"

setup_env_file() {
    local env_example=$1
    local env_file="${env_example%.example}"
    
    if [ -f "$env_example" ] && [ ! -f "$env_file" ]; then
        cp "$env_example" "$env_file"
        echo -e "${GREEN}✓ Created: $env_file${NC}"
        echo -e "${YELLOW}  ⚠ Please edit this file and add your AWS credentials${NC}"
    fi
}

setup_env_file "$PROJECT_ROOT/services/registry/.env.example"
setup_env_file "$PROJECT_ROOT/services/orchestrator/.env.example"
setup_env_file "$PROJECT_ROOT/services/agents/code_analyzer/.env.example"
setup_env_file "$PROJECT_ROOT/services/agents/data_processor/.env.example"
setup_env_file "$PROJECT_ROOT/services/agents/research_agent/.env.example"
setup_env_file "$PROJECT_ROOT/services/agents/task_executor/.env.example"
setup_env_file "$PROJECT_ROOT/services/agents/observer/.env.example"

# Note: MCP services already have .env files, not .env.example

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                                              ║${NC}"
echo -e "${GREEN}║   Setup Complete! ✅                         ║${NC}"
echo -e "${GREEN}║                                              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo ""
echo -e "1. ${BLUE}Configure AWS credentials:${NC}"
echo -e "   Edit the .env files in each service directory"
echo -e "   Add your AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY"
echo ""
echo -e "2. ${BLUE}Start the A2A system:${NC}"
echo -e "   ${GREEN}./start_services.sh${NC}"
echo ""
echo -e "3. ${BLUE}Start the MCP system:${NC}"
echo -e "   ${GREEN}./start_mcp_services.sh${NC}"
echo ""
echo -e "4. ${BLUE}Test the systems:${NC}"
echo -e "   ${GREEN}python test_distributed_system.py${NC}  (A2A tests)"
echo -e "   ${GREEN}python test_mcp_system.py${NC}          (MCP tests)"
echo ""
echo -e "${YELLOW}Documentation:${NC}"
echo -e "  - DISTRIBUTED_README.md - A2A Agent System guide"
echo -e "  - MCP_README.md - Model Context Protocol guide"
echo -e "  - CURL_EXAMPLES.md - API usage examples"
echo ""
