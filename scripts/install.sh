#!/bin/bash
# Dryade Community Edition - Installation Script
#
# Usage: curl -fsSL https://raw.githubusercontent.com/dryade/dryade/main/scripts/install.sh | bash
# Or: ./scripts/install.sh
#
# This script:
#   1. Checks system requirements
#   2. Prompts for required configuration (LLM API key)
#   3. Configures PostgreSQL database connection
#   4. Installs dependencies
#   5. Starts the application

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Version
DRYADE_VERSION="community-v1.0.0"

echo -e "${BLUE}"
echo "=============================================================="
echo "                                                              "
echo "     Dryade Community Edition - Installation Script           "
echo "                                                              "
echo "=============================================================="
echo -e "${NC}"

# =============================================================================
# System Requirements Check
# =============================================================================
check_requirements() {
    echo -e "${BLUE}Checking system requirements...${NC}"

    # Check Python 3.10+
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f1)
        PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f2)
        if [[ $PYTHON_MAJOR -ge 3 && $PYTHON_MINOR -ge 10 ]]; then
            echo -e "${GREEN}  [OK] Python $PYTHON_VERSION${NC}"
        else
            echo -e "${RED}  [FAIL] Python 3.10+ required (found $PYTHON_VERSION)${NC}"
            exit 1
        fi
    else
        echo -e "${RED}  [FAIL] Python 3 not found${NC}"
        exit 1
    fi

    # Check Node.js 18+ (for MCP servers)
    if command -v node &> /dev/null; then
        NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
        if [[ $NODE_VERSION -ge 18 ]]; then
            echo -e "${GREEN}  [OK] Node.js v$(node -v | cut -d'v' -f2)${NC}"
        else
            echo -e "${YELLOW}  [WARN] Node.js 18+ recommended for MCP servers (found v$NODE_VERSION)${NC}"
        fi
    else
        echo -e "${YELLOW}  [WARN] Node.js not found (optional, needed for MCP servers)${NC}"
    fi

    # Check Docker (optional)
    if command -v docker &> /dev/null; then
        echo -e "${GREEN}  [OK] Docker available${NC}"
        DOCKER_AVAILABLE=true
    else
        echo -e "${YELLOW}  [WARN] Docker not found (optional, for containerized deployment)${NC}"
        DOCKER_AVAILABLE=false
    fi

    # Check git
    if command -v git &> /dev/null; then
        echo -e "${GREEN}  [OK] Git available${NC}"
    else
        echo -e "${YELLOW}  [WARN] Git not found (needed for updates)${NC}"
    fi

    # Check openssl (for secret generation)
    if command -v openssl &> /dev/null; then
        echo -e "${GREEN}  [OK] OpenSSL available${NC}"
    else
        echo -e "${RED}  [FAIL] OpenSSL not found (required for secret generation)${NC}"
        exit 1
    fi

    echo ""
}

# =============================================================================
# Configuration
# =============================================================================
configure() {
    echo -e "${BLUE}Configuration${NC}"
    echo "We need a few settings to get started."
    echo ""

    # Check if .env exists
    if [[ -f .env ]]; then
        echo -e "${YELLOW}Existing .env found. Overwrite? (y/N)${NC}"
        read -r OVERWRITE
        if [[ ! $OVERWRITE =~ ^[Yy]$ ]]; then
            echo "Keeping existing configuration."
            return
        fi
    fi

    # Copy example
    if [[ -f .env.example ]]; then
        cp .env.example .env
    else
        echo -e "${RED}Error: .env.example not found. Are you in the Dryade directory?${NC}"
        exit 1
    fi

    # Prompt for LLM API key (REQUIRED)
    echo ""
    echo -e "${YELLOW}Enter your LLM API key (OpenAI, Anthropic, etc.):${NC}"
    echo "  - OpenAI: starts with sk-"
    echo "  - Anthropic: starts with sk-ant-"
    read -r -s LLM_API_KEY
    echo ""

    if [[ -z "$LLM_API_KEY" ]]; then
        echo -e "${RED}LLM API key is required. Exiting.${NC}"
        exit 1
    fi

    # Update .env with API key
    if [[ "$(uname)" == "Darwin" ]]; then
        # macOS sed requires different syntax
        sed -i '' "s|^DRYADE_LLM_API_KEY=.*|DRYADE_LLM_API_KEY=$LLM_API_KEY|" .env
    else
        sed -i "s|^DRYADE_LLM_API_KEY=.*|DRYADE_LLM_API_KEY=$LLM_API_KEY|" .env
    fi

    # Prompt for LLM provider/mode
    echo ""
    echo -e "${YELLOW}Select LLM provider:${NC}"
    echo "  1) OpenAI (default)"
    echo "  2) Anthropic"
    echo "  3) vLLM (local)"
    echo "  4) Ollama (local)"
    read -r -p "Choice [1]: " LLM_CHOICE

    case "${LLM_CHOICE:-1}" in
        1)
            LLM_MODE="openai"
            LLM_MODEL="gpt-4o"
            LLM_BASE_URL="https://api.openai.com/v1"
            ;;
        2)
            LLM_MODE="anthropic"
            LLM_MODEL="claude-sonnet-4-20250514"
            LLM_BASE_URL="https://api.anthropic.com"
            ;;
        3)
            LLM_MODE="vllm"
            LLM_MODEL="local-llm"
            echo -e "${YELLOW}Enter vLLM server URL (e.g., http://localhost:8000/v1):${NC}"
            read -r LLM_BASE_URL
            ;;
        4)
            LLM_MODE="ollama"
            LLM_MODEL="llama2"
            echo -e "${YELLOW}Enter Ollama server URL (default: http://localhost:11434):${NC}"
            read -r LLM_BASE_URL
            LLM_BASE_URL="${LLM_BASE_URL:-http://localhost:11434}"
            ;;
    esac

    # Update LLM settings
    if [[ "$(uname)" == "Darwin" ]]; then
        sed -i '' "s|^DRYADE_LLM_MODE=.*|DRYADE_LLM_MODE=$LLM_MODE|" .env
        sed -i '' "s|^DRYADE_LLM_MODEL=.*|DRYADE_LLM_MODEL=$LLM_MODEL|" .env
        sed -i '' "s|^DRYADE_LLM_BASE_URL=.*|DRYADE_LLM_BASE_URL=$LLM_BASE_URL|" .env
    else
        sed -i "s|^DRYADE_LLM_MODE=.*|DRYADE_LLM_MODE=$LLM_MODE|" .env
        sed -i "s|^DRYADE_LLM_MODEL=.*|DRYADE_LLM_MODEL=$LLM_MODEL|" .env
        sed -i "s|^DRYADE_LLM_BASE_URL=.*|DRYADE_LLM_BASE_URL=$LLM_BASE_URL|" .env
    fi

    # Database connection (PostgreSQL required)
    echo ""
    echo -e "${YELLOW}PostgreSQL connection URL (press Enter for default localhost):${NC}"
    echo -e "  Format: postgresql+psycopg://user:password@host:port/dbname"
    echo -e "  Default: postgresql+psycopg://dryade:dryade_dev@localhost:5432/dryade"
    read -r DB_URL
    if [[ -z "$DB_URL" ]]; then
        DB_URL="postgresql+psycopg://dryade:dryade_dev@localhost:5432/dryade"
    fi
    if [[ "$(uname)" == "Darwin" ]]; then
        sed -i '' "s|^DRYADE_DATABASE_URL=.*|DRYADE_DATABASE_URL=$DB_URL|" .env
    else
        sed -i "s|^DRYADE_DATABASE_URL=.*|DRYADE_DATABASE_URL=$DB_URL|" .env
    fi

    # Generate secret key
    SECRET_KEY=$(openssl rand -hex 32)
    if [[ "$(uname)" == "Darwin" ]]; then
        sed -i '' "s|^DRYADE_JWT_SECRET=.*|DRYADE_JWT_SECRET=$SECRET_KEY|" .env
    else
        sed -i "s|^DRYADE_JWT_SECRET=.*|DRYADE_JWT_SECRET=$SECRET_KEY|" .env
    fi

    echo -e "${GREEN}  [OK] Configuration saved to .env${NC}"
    echo ""
}

# =============================================================================
# Installation
# =============================================================================
install_dependencies() {
    echo -e "${BLUE}Installing dependencies...${NC}"

    # Create virtual environment
    if [[ ! -d ".venv" ]]; then
        echo "  Creating virtual environment..."
        python3 -m venv .venv
    fi

    # Activate venv
    source .venv/bin/activate

    # Upgrade pip
    echo "  Upgrading pip..."
    pip install --upgrade pip -q

    # Install Python dependencies
    echo "  Installing Python packages (this may take a few minutes)..."
    pip install -r requirements.txt -q

    echo -e "${GREEN}  [OK] Dependencies installed${NC}"
    echo ""
}

setup_database() {
    echo -e "${BLUE}Setting up database...${NC}"

    # Create data directory
    mkdir -p data
    mkdir -p logs

    # Activate venv if not already
    source .venv/bin/activate

    # Run migrations
    if command -v alembic &> /dev/null || [[ -f .venv/bin/alembic ]]; then
        echo "  Running database migrations..."
        alembic upgrade head 2>/dev/null || {
            echo -e "${YELLOW}  [WARN] Alembic migrations skipped (may not be configured yet)${NC}"
        }
    else
        echo -e "${YELLOW}  [WARN] Alembic not found, skipping migrations${NC}"
    fi

    echo -e "${GREEN}  [OK] Database initialized${NC}"
    echo ""
}

# =============================================================================
# Start Services
# =============================================================================
start_services() {
    echo -e "${BLUE}Starting Dryade...${NC}"

    # Ask about Docker vs local
    if [[ "$DOCKER_AVAILABLE" == "true" ]]; then
        echo -e "${YELLOW}Start with Docker? (Y/n)${NC}"
        read -r USE_DOCKER
    else
        USE_DOCKER="n"
    fi

    if [[ $USE_DOCKER =~ ^[Nn]$ ]]; then
        # Start without Docker
        source .venv/bin/activate

        # Create logs directory
        mkdir -p logs

        echo "  Starting API server..."
        nohup python -m uvicorn core.api.main:app --host 0.0.0.0 --port 8000 > logs/api.log 2>&1 &
        echo $! > .dryade.pid

        sleep 2

        # Verify it started
        if kill -0 "$(cat .dryade.pid)" 2>/dev/null; then
            echo -e "${GREEN}  [OK] API server started on http://localhost:8000${NC}"
        else
            echo -e "${RED}  [FAIL] API server failed to start. Check logs/api.log${NC}"
            exit 1
        fi
    else
        # Start with Docker
        if [[ -f docker-compose.community.yml ]]; then
            docker compose -f docker-compose.community.yml up -d
            echo -e "${GREEN}  [OK] Dryade started with Docker${NC}"
        else
            echo -e "${RED}  [FAIL] docker-compose.community.yml not found${NC}"
            exit 1
        fi
    fi

    echo ""
}

# =============================================================================
# Main
# =============================================================================
main() {
    check_requirements
    configure
    install_dependencies
    setup_database
    start_services

    echo -e "${GREEN}"
    echo "=============================================================="
    echo "                                                              "
    echo "     Installation Complete!                                   "
    echo "                                                              "
    echo "     API:      http://localhost:8000                          "
    echo "     Docs:     http://localhost:8000/docs                     "
    echo "     Health:   http://localhost:8000/health                   "
    echo "                                                              "
    echo "     Next steps:                                              "
    echo "     - Check health: ./scripts/health-check.sh                "
    echo "     - View logs:    tail -f logs/api.log                     "
    echo "     - Stop:         kill \$(cat .dryade.pid)                  "
    echo "                                                              "
    echo "     Docker commands:                                         "
    echo "     - Logs: docker compose -f docker-compose.community.yml logs"
    echo "     - Stop: docker compose -f docker-compose.community.yml down"
    echo "                                                              "
    echo "     Documentation: https://docs.dryade.ai                   "
    echo "     Support: https://github.com/dryade/dryade/discussions    "
    echo "                                                              "
    echo "=============================================================="
    echo -e "${NC}"
}

main "$@"
