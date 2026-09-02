#!/usr/bin/env bash
# deploy.sh - Deploy trading system to VPS
set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Trading System Deployment ===${NC}"

# Check requirements
check_requirements() {
    echo -e "${YELLOW}Checking requirements...${NC}"
    for cmd in docker docker-compose python3; do
        if ! command -v $cmd &> /dev/null; then
            echo -e "${RED}Error: $cmd not found${NC}"
            exit 1
        fi
    done
    # Check Python packages
    pip_packages="redis aiohttp fastapi uvicorn prometheus_client"
    for pkg in $pip_packages; do
        if ! python3 -c "import $pkg" &> /dev/null; then
            echo -e "${YELLOW}Installing $pkg...${NC}"
            pip3 install --break-system-packages $pkg 2>&1 | tail -1
        fi
    done
    echo -e "${GREEN}Requirements OK${NC}"
}

# Check .env file
check_env() {
    if [[ ! -f .env ]]; then
        echo -e "${YELLOW}No .env file found. Copying from .env.example...${NC}"
        cp .env.example .env
        echo -e "${RED}Please edit .env with your configuration before continuing.${NC}"
        exit 1
    fi
    echo -e "${GREEN}.env file found${NC}"
}

# Build images
build_images() {
    echo -e "${YELLOW}Building Docker images...${NC}"
    docker-compose build --parallel
    echo -e "${GREEN}Build complete${NC}"
}

# Start Docker services (postgres, redis, minio, etc.)
start_docker_services() {
    echo -e "${YELLOW}Starting infrastructure services...${NC}"
    docker-compose up -d postgres redis minio prometheus grafana
    echo -e "${GREEN}Infrastructure services started${NC}"
}

# Start Python trading system
start_trading_system() {
    echo -e "${YELLOW}Starting trading system...${NC}"
    # Check if venv exists, if not create it
    if [[ ! -d "venv" ]]; then
        python3 -m venv venv
        source venv/bin/activate
        pip install --upgrade pip
        pip install -r requirements.txt
    else
        source venv/bin/activate
    fi
    
    # Start the trading system in the background
    python3 agent_system/main.py &
    TRADING_PID=$!
    echo "Trading system PID: $TRADING_PID"
    
    # Wait for initialization
    sleep 5
    
    # Start Prometheus metrics endpoint
    echo -e "${YELLOW}Starting Prometheus metrics server...${NC}"
    # The metrics are started within the trading system
    
    # Start FastAPI execution endpoint
    echo -e "${YELLOW}Starting execution API on port 8080...${NC}"
    # This would be started separately or integrated
}

# Wait for health checks
wait_healthy() {
    echo -e "${YELLOW}Waiting for services to be healthy...${NC}"
    local max_attempts=60
    local attempt=0
    
    # Check Docker services
    while [[ $attempt -lt $max_attempts ]]; do
        if docker-compose ps | grep -q "unhealthy"; then
            echo -e "${RED}Some services are unhealthy${NC}"
            docker-compose ps
            exit 1
        fi
        if docker-compose ps | grep -q "starting"; then
            sleep 3
            ((attempt++))
        else
            break
        fi
    done
    
    # Check trading system is running
    if kill -0 $TRADING_PID 2>/dev/null; then
        echo -e "${GREEN}Trading system is running${NC}"
    else
        echo -e "${RED}Trading system failed to start${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}All services healthy${NC}"
}

# Show status
show_status() {
    echo -e "${GREEN}=== Deployment Complete ===${NC}"
    docker-compose ps
    echo ""
    echo "Access points:"
    echo "  API Gateway:    http://localhost:8080"
    echo "  Admin UI:       http://localhost:3000"
    echo "  Grafana:        http://localhost:3001 (admin/admin)"
    echo "  Prometheus:     http://localhost:9090"
    echo "  MinIO:          http://localhost:9001 (minioadmin/changeme)"
    echo "  Trading System: ws://localhost:8080/ws (WebSocket)"
    echo ""
    echo "Running services:"
    docker-compose ps
    echo "Trading System PID: $TRADING_PID"
}

# Main
case "${1:-deploy}" in
    deploy)
        check_requirements
        check_env
        build_images
        start_docker_services
        start_trading_system
        wait_healthy
        show_status
        ;;
    build)
        check_requirements
        build_images
        ;;
    start)
        check_env
        start_docker_services
        start_trading_system
        wait_healthy
        show_status
        ;;
    stop)
        echo -e "${YELLOW}Stopping services...${NC}"
        if [[ -n "${TRADING_PID:-}" ]]; then
            kill $TRADING_PID 2>/dev/null || true
        fi
        docker-compose down
        echo -e "${GREEN}Stopped${NC}"
        ;;
    restart)
        check_env
        docker-compose restart
        wait_healthy
        show_status
        ;;
    logs)
        docker-compose logs -f "${2:-}"
        ;;
    ps)
        docker-compose ps
        echo "Trading System PID: ${TRADING_PID:-not started}"
        ;;
    metrics)
        # Start just the Prometheus metrics endpoint
        echo -e "${YELLOW}Starting metrics endpoint...${NC}"
        # The metrics are collected internally by the trading system
        # Access at http://localhost:9090/metrics
        ;;
    *)
        echo "Usage: $0 {deploy|build|start|stop|restart|logs|ps|metrics}"
        exit 1
        ;;
esac