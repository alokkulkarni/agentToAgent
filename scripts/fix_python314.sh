#!/bin/bash

# Quick fix for Python 3.14 compatibility
# This script removes the existing venv and recreates it with Python 3.13
# or uses the PyO3 forward compatibility flag

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$PROJECT_ROOT/venv"

echo ""
echo -e "${YELLOW}╔══════════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║   Python 3.14 Compatibility Fix             ║${NC}"
echo -e "${YELLOW}╚══════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BLUE}Option 1: Install Python 3.13 (Recommended)${NC}"
echo ""
echo "  macOS:"
echo "    brew install python@3.13"
echo ""
echo "  Ubuntu/Debian:"
echo "    sudo apt-get install python3.13"
echo ""
echo "  Then run: ./setup.sh"
echo ""

echo -e "${BLUE}Option 2: Use Python 3.14 with compatibility flag${NC}"
echo ""
echo -e "${YELLOW}⚠ Warning: This uses experimental forward compatibility${NC}"
echo ""

read -p "Use Python 3.14 with compatibility flag? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo -e "${YELLOW}Removing existing venv...${NC}"
    rm -rf "$VENV_PATH"
    
    echo -e "${YELLOW}Creating venv with Python 3.14...${NC}"
    python3.14 -m venv "$VENV_PATH"
    
    echo -e "${YELLOW}Activating venv...${NC}"
    source "$VENV_PATH/bin/activate"
    
    echo -e "${YELLOW}Setting PyO3 compatibility flag...${NC}"
    export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
    
    echo -e "${YELLOW}Upgrading pip...${NC}"
    pip install --upgrade pip
    
    echo -e "${YELLOW}Installing dependencies (this may take a while)...${NC}"
    
    # Function to install with retry
    install_with_retry() {
        local service_path=$1
        local service_name=$2
        local max_retries=3
        local retry=0
        
        while [ $retry -lt $max_retries ]; do
            echo -e "${BLUE}Installing dependencies for $service_name (attempt $((retry+1)))...${NC}"
            
            if PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 pip install -r "$service_path/requirements.txt" 2>&1 | grep -v "WARNING"; then
                echo -e "${GREEN}✓ Dependencies installed for $service_name${NC}"
                return 0
            fi
            
            retry=$((retry+1))
            if [ $retry -lt $max_retries ]; then
                echo -e "${YELLOW}Retrying...${NC}"
                sleep 2
            fi
        done
        
        echo -e "${RED}✗ Failed to install dependencies for $service_name after $max_retries attempts${NC}"
        return 1
    }
    
    # Install for all services
    install_with_retry "$PROJECT_ROOT/services/registry" "Registry"
    install_with_retry "$PROJECT_ROOT/services/orchestrator" "Orchestrator"
    install_with_retry "$PROJECT_ROOT/services/agents/code_analyzer" "Code Analyzer"
    install_with_retry "$PROJECT_ROOT/services/agents/data_processor" "Data Processor"
    install_with_retry "$PROJECT_ROOT/services/agents/research_agent" "Research Agent"
    install_with_retry "$PROJECT_ROOT/services/agents/task_executor" "Task Executor"
    install_with_retry "$PROJECT_ROOT/services/agents/observer" "Observer"
    
    # Add the flag to start script
    echo ""
    echo -e "${YELLOW}Creating environment file with compatibility flag...${NC}"
    echo "export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1" > "$PROJECT_ROOT/.env.python314"
    
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   Setup Complete!                            ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}Note: You're using Python 3.14 with forward compatibility${NC}"
    echo -e "${YELLOW}This may have some limitations. Python 3.13 is recommended.${NC}"
    echo ""
    echo -e "${BLUE}To start services:${NC}"
    echo "  source .env.python314"
    echo "  ./start_services.sh"
    echo ""
else
    echo ""
    echo -e "${YELLOW}Cancelled. Please install Python 3.13 and run ./setup.sh${NC}"
    echo ""
fi
