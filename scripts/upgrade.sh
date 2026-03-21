#!/bin/bash
# Dryade Community Edition - Upgrade Script
#
# Usage: ./scripts/upgrade.sh [version]
# Example: ./scripts/upgrade.sh v1.1.0
#
# This script:
#   1. Backs up current state (database and config)
#   2. Pulls latest changes or checks out specific version
#   3. Updates dependencies
#   4. Runs database migrations
#   5. Restarts services

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

VERSION=${1:-"latest"}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo -e "${BLUE}Dryade Community Edition - Upgrade${NC}"
echo "Target version: $VERSION"
echo "Project directory: $PROJECT_DIR"
echo ""

# Change to project directory
cd "$PROJECT_DIR"

# =============================================================================
# Pre-upgrade Checks
# =============================================================================
pre_checks() {
    echo -e "${BLUE}Pre-upgrade checks...${NC}"

    RUNNING_DOCKER=false
    RUNNING_LOCAL=false

    # Check if running in Docker
    if command -v docker &> /dev/null && docker ps 2>/dev/null | grep -q dryade; then
        RUNNING_DOCKER=true
        echo -e "${GREEN}  [OK] Dryade running in Docker${NC}"
    elif [[ -f .dryade.pid ]] && kill -0 "$(cat .dryade.pid)" 2>/dev/null; then
        RUNNING_LOCAL=true
        echo -e "${GREEN}  [OK] Dryade running locally (PID: $(cat .dryade.pid))${NC}"
    else
        echo -e "${YELLOW}  [WARN] Dryade not currently running${NC}"
    fi

    # Check if we're in a git repo
    if [[ ! -d .git ]]; then
        echo -e "${RED}  [FAIL] Not a git repository. Cannot upgrade.${NC}"
        exit 1
    fi

    # Check for uncommitted changes
    if [[ -n "$(git status --porcelain)" ]]; then
        echo -e "${YELLOW}  [WARN] Uncommitted changes detected${NC}"
        echo "  Consider committing or stashing changes before upgrade."
        echo ""
        echo -e "${YELLOW}Continue anyway? (y/N)${NC}"
        read -r CONTINUE
        if [[ ! $CONTINUE =~ ^[Yy]$ ]]; then
            echo "Upgrade cancelled."
            exit 0
        fi
    fi

    echo ""
}

# =============================================================================
# Backup
# =============================================================================
backup() {
    echo -e "${BLUE}Creating backup...${NC}"

    BACKUP_DIR="backups/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"

    # Backup database
    if [[ -f data/dryade.db ]]; then
        cp data/dryade.db "$BACKUP_DIR/dryade.db"
        echo -e "${GREEN}  [OK] Database backed up${NC}"
    elif [[ -d data ]]; then
        # Backup any database files found
        find data -name "*.db" -exec cp {} "$BACKUP_DIR/" \;
        echo -e "${GREEN}  [OK] Database files backed up${NC}"
    else
        echo -e "${YELLOW}  [SKIP] No database files found${NC}"
    fi

    # Backup config
    if [[ -f .env ]]; then
        cp .env "$BACKUP_DIR/.env"
        echo -e "${GREEN}  [OK] Configuration backed up${NC}"
    fi

    # Backup custom configs
    if [[ -f config/mcp_servers.yaml ]]; then
        cp config/mcp_servers.yaml "$BACKUP_DIR/mcp_servers.yaml"
        echo -e "${GREEN}  [OK] MCP config backed up${NC}"
    fi

    # Store current version info
    git rev-parse HEAD > "$BACKUP_DIR/git_commit.txt"
    git describe --tags --always 2>/dev/null > "$BACKUP_DIR/git_version.txt" || echo "unknown" > "$BACKUP_DIR/git_version.txt"

    echo ""
    echo "  Backup location: $BACKUP_DIR"
    echo ""

    # Export for rollback
    export BACKUP_DIR
}

# =============================================================================
# Stop Services
# =============================================================================
stop_services() {
    echo -e "${BLUE}Stopping services...${NC}"

    if [[ $RUNNING_DOCKER == true ]]; then
        if [[ -f docker-compose.community.yml ]]; then
            docker compose -f docker-compose.community.yml down
        else
            docker compose down
        fi
        echo -e "${GREEN}  [OK] Docker services stopped${NC}"
    elif [[ $RUNNING_LOCAL == true ]]; then
        kill "$(cat .dryade.pid)" 2>/dev/null || true
        rm -f .dryade.pid
        echo -e "${GREEN}  [OK] Local service stopped${NC}"
    else
        echo -e "${YELLOW}  [SKIP] No services to stop${NC}"
    fi

    echo ""
}

# =============================================================================
# Update Code
# =============================================================================
update_code() {
    echo -e "${BLUE}Updating code...${NC}"

    # Fetch latest
    git fetch --tags origin

    if [[ "$VERSION" == "latest" ]]; then
        # Get the default branch
        DEFAULT_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo "main")
        echo "  Pulling latest from $DEFAULT_BRANCH..."
        git pull origin "$DEFAULT_BRANCH"
    else
        echo "  Checking out version: $VERSION"
        git checkout "$VERSION"
    fi

    echo -e "${GREEN}  [OK] Code updated${NC}"
    echo ""
}

# =============================================================================
# Update Dependencies
# =============================================================================
update_dependencies() {
    echo -e "${BLUE}Updating dependencies...${NC}"

    if [[ $RUNNING_DOCKER == true ]]; then
        # Pull new Docker images
        if [[ -f docker-compose.community.yml ]]; then
            docker compose -f docker-compose.community.yml pull
        fi
        echo -e "${GREEN}  [OK] Docker images updated${NC}"
    else
        # Update Python dependencies
        if [[ -f .venv/bin/activate ]]; then
            source .venv/bin/activate
        elif [[ -d ".venv" ]]; then
            source .venv/bin/activate
        else
            echo -e "${YELLOW}  [WARN] No virtual environment found, creating one...${NC}"
            python3 -m venv .venv
            source .venv/bin/activate
        fi

        echo "  Upgrading pip..."
        pip install --upgrade pip -q

        echo "  Installing updated packages..."
        pip install -r requirements.txt -q

        echo -e "${GREEN}  [OK] Python dependencies updated${NC}"
    fi

    echo ""
}

# =============================================================================
# Run Migrations
# =============================================================================
run_migrations() {
    echo -e "${BLUE}Running database migrations...${NC}"

    if [[ $RUNNING_DOCKER == true ]]; then
        # Run migrations in Docker container
        if [[ -f docker-compose.community.yml ]]; then
            docker compose -f docker-compose.community.yml run --rm dryade-api alembic upgrade head 2>/dev/null || {
                echo -e "${YELLOW}  [WARN] Docker migration command not available, will run on startup${NC}"
            }
        fi
    else
        # Run migrations locally
        if [[ -f .venv/bin/activate ]]; then
            source .venv/bin/activate
        fi

        if command -v alembic &> /dev/null || [[ -f .venv/bin/alembic ]]; then
            alembic upgrade head 2>/dev/null && {
                echo -e "${GREEN}  [OK] Migrations complete${NC}"
            } || {
                echo -e "${YELLOW}  [WARN] Migrations skipped (may not be configured)${NC}"
            }
        else
            echo -e "${YELLOW}  [WARN] Alembic not found, skipping migrations${NC}"
        fi
    fi

    echo ""
}

# =============================================================================
# Start Services
# =============================================================================
start_services() {
    echo -e "${BLUE}Starting services...${NC}"

    if [[ $RUNNING_DOCKER == true ]]; then
        if [[ -f docker-compose.community.yml ]]; then
            docker compose -f docker-compose.community.yml up -d
        else
            docker compose up -d
        fi
        echo -e "${GREEN}  [OK] Docker services started${NC}"
    elif [[ $RUNNING_LOCAL == true ]]; then
        source .venv/bin/activate
        mkdir -p logs
        nohup python -m uvicorn core.api.main:app --host 0.0.0.0 --port 8000 > logs/api.log 2>&1 &
        echo $! > .dryade.pid
        echo -e "${GREEN}  [OK] Local service started (PID: $(cat .dryade.pid))${NC}"
    else
        echo -e "${YELLOW}  [SKIP] No services were running, skipping start${NC}"
        echo "  To start manually:"
        echo "    Docker: docker compose -f docker-compose.community.yml up -d"
        echo "    Local:  source .venv/bin/activate && uvicorn core.api.main:app --host 0.0.0.0 --port 8000"
    fi

    echo ""
}

# =============================================================================
# Verify
# =============================================================================
verify() {
    echo -e "${BLUE}Verifying upgrade...${NC}"

    # Wait for services to start
    sleep 5

    # Check health endpoint
    HEALTH_URL=${DRYADE_API_URL:-"http://localhost:8000"}
    if curl -sf "$HEALTH_URL/health" > /dev/null 2>&1; then
        echo -e "${GREEN}  [OK] Health check passed${NC}"
    else
        echo -e "${YELLOW}  [WARN] Health check failed or service not ready${NC}"
        echo "  Service may still be starting. Check logs and run:"
        echo "    ./scripts/health-check.sh"
    fi

    # Show new version
    NEW_VERSION=$(git describe --tags --always 2>/dev/null || echo "unknown")
    echo ""
    echo "  New version: $NEW_VERSION"

    echo ""
}

# =============================================================================
# Rollback (if needed)
# =============================================================================
rollback() {
    echo -e "${RED}Rollback initiated...${NC}"

    if [[ -z "$BACKUP_DIR" || ! -d "$BACKUP_DIR" ]]; then
        echo -e "${RED}  [FAIL] No backup directory found${NC}"
        exit 1
    fi

    # Restore database
    if [[ -f "$BACKUP_DIR/dryade.db" ]]; then
        cp "$BACKUP_DIR/dryade.db" data/dryade.db
        echo -e "${GREEN}  [OK] Database restored${NC}"
    fi

    # Restore config
    if [[ -f "$BACKUP_DIR/.env" ]]; then
        cp "$BACKUP_DIR/.env" .env
        echo -e "${GREEN}  [OK] Configuration restored${NC}"
    fi

    # Restore git state
    if [[ -f "$BACKUP_DIR/git_commit.txt" ]]; then
        git checkout "$(cat "$BACKUP_DIR/git_commit.txt")"
        echo -e "${GREEN}  [OK] Code restored${NC}"
    fi

    echo ""
    echo "Rollback complete. Please restart services manually."
}

# =============================================================================
# Main
# =============================================================================
main() {
    # Handle rollback flag
    if [[ "$1" == "--rollback" ]]; then
        BACKUP_DIR="$2"
        rollback
        exit 0
    fi

    pre_checks
    backup
    stop_services
    update_code
    update_dependencies
    run_migrations
    start_services
    verify

    echo -e "${GREEN}Upgrade complete!${NC}"
    echo ""
    echo "If you encounter issues, you can rollback:"
    echo "  ./scripts/upgrade.sh --rollback $BACKUP_DIR"
    echo ""
    echo "Run './scripts/health-check.sh' for detailed status."
}

main "$@"
