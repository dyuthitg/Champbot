#!/bin/bash

# LinkedIn Multi-Agent Automation System Deployment Script
# Usage: ./scripts/deploy.sh [docker|kubernetes|local]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if required commands exist
check_command() {
    if ! command -v $1 &> /dev/null; then
        print_error "$1 is required but not installed"
        exit 1
    fi
}

# Create sample configuration
create_sample_config() {
    print_status "Creating sample configuration..."
    
    mkdir -p config
    
    if [ ! -f config/config.json ]; then
        python src/config/config.py
        print_success "Sample configuration created at config/config.json"
        print_warning "Please edit config/config.json with your settings before proceeding"
    else
        print_status "Configuration already exists at config/config.json"
    fi
}

# Local development deployment
deploy_local() {
    print_status "Starting local development deployment..."
    
    # Check Python version
    python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    print_status "Python version: $python_version"
    
    if ! python3 -c 'import sys; exit(0 if sys.version_info >= (3, 8) else 1)'; then
        print_error "Python 3.8 or higher is required"
        exit 1
    fi
    
    # Install dependencies
    print_status "Installing Python dependencies..."
    pip install -r requirements.txt
    
    # Download NLP models
    print_status "Downloading NLP models..."
    python -m spacy download en_core_web_sm || print_warning "Failed to download spacy model"
    
    # Install Playwright browsers
    print_status "Installing browser dependencies..."
    playwright install chromium
    
    # Check Redis
    if ! redis-cli ping &> /dev/null; then
        print_warning "Redis is not running. Please start Redis first:"
        print_warning "  redis-server"
        exit 1
    fi
    
    # Create configuration
    create_sample_config
    
    # Validate configuration
    print_status "Validating configuration..."
    python main.py --dry-run
    
    print_success "Local deployment ready!"
    print_status "To start the system, run: python main.py --config config/config.json"
}

# Docker deployment
deploy_docker() {
    print_status "Starting Docker deployment..."
    
    check_command docker
    check_command docker-compose
    
    # Check if .env file exists
    if [ ! -f .env ]; then
        print_status "Creating .env file..."
        cat > .env << EOF
OPENAI_API_KEY=your-openai-api-key-here
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
LOG_LEVEL=INFO
LINKEDIN_HEADLESS=true
LINKEDIN_BROWSER_TYPE=playwright
EOF
        print_warning "Please edit .env file with your actual API keys"
    fi
    
    # Create configuration
    create_sample_config
    
    # Build and start services
    print_status "Building Docker images..."
    docker-compose build
    
    print_status "Starting services..."
    docker-compose up -d redis
    
    # Wait for Redis to be ready
    print_status "Waiting for Redis to be ready..."
    sleep 5
    
    # Start application
    docker-compose up -d
    
    print_success "Docker deployment completed!"
    print_status "Services are starting up. Check status with: docker-compose ps"
    print_status "View logs with: docker-compose logs -f"
    
    # Show service URLs
    echo ""
    print_status "Service URLs:"
    print_status "  Web Dashboard: http://localhost:8080"
    print_status "  Redis: localhost:6379"
    
    # Check if monitoring profile was requested
    if [ "$2" = "monitoring" ]; then
        print_status "Starting monitoring services..."
        docker-compose --profile monitoring up -d
        print_status "  Prometheus: http://localhost:9090"
        print_status "  Grafana: http://localhost:3000 (admin/admin)"
    fi
}

# Kubernetes deployment
deploy_kubernetes() {
    print_status "Starting Kubernetes deployment..."
    
    check_command kubectl
    
    # Check cluster connection
    if ! kubectl cluster-info &> /dev/null; then
        print_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    # Get API keys from user
    read -p "Enter your OpenAI API key: " -s OPENAI_API_KEY
    echo
    read -p "Enter an encryption key (or press enter for random): " -s ENCRYPTION_KEY
    echo
    
    if [ -z "$ENCRYPTION_KEY" ]; then
        ENCRYPTION_KEY=$(openssl rand -base64 32)
        print_status "Generated random encryption key"
    fi
    
    # Create namespace
    print_status "Creating namespace..."
    kubectl apply -f deployment/kubernetes/namespace.yaml
    
    # Create secrets
    print_status "Creating secrets..."
    kubectl create secret generic linkedin-secrets \
        --from-literal=openai-api-key="$OPENAI_API_KEY" \
        --from-literal=encryption-key="$ENCRYPTION_KEY" \
        -n linkedin-automation \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # Deploy infrastructure
    print_status "Deploying infrastructure..."
    kubectl apply -f deployment/kubernetes/configmap.yaml
    kubectl apply -f deployment/kubernetes/redis.yaml
    
    # Wait for Redis to be ready
    print_status "Waiting for Redis to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/redis -n linkedin-automation
    
    # Deploy orchestrator and agents
    print_status "Deploying orchestrator and agents..."
    kubectl apply -f deployment/kubernetes/orchestrator.yaml
    kubectl apply -f deployment/kubernetes/agents.yaml
    
    # Wait for deployments
    print_status "Waiting for deployments to be ready..."
    kubectl wait --for=condition=available --timeout=600s deployment/linkedin-orchestrator -n linkedin-automation
    
    print_success "Kubernetes deployment completed!"
    
    # Show status
    print_status "Deployment status:"
    kubectl get pods -n linkedin-automation
    
    # Get service information
    print_status "Service information:"
    kubectl get services -n linkedin-automation
    
    print_status "To access the web dashboard, run:"
    print_status "  kubectl port-forward service/linkedin-orchestrator 8080:80 -n linkedin-automation"
}

# Build Docker image
build_image() {
    print_status "Building Docker image..."
    docker build -t linkedin-automation:latest .
    print_success "Docker image built successfully!"
}

# Clean up deployment
cleanup() {
    print_status "Cleaning up deployment..."
    
    case $1 in
        docker)
            docker-compose down -v
            docker system prune -f
            print_success "Docker cleanup completed"
            ;;
        kubernetes)
            kubectl delete namespace linkedin-automation
            print_success "Kubernetes cleanup completed"
            ;;
        *)
            print_status "Manual cleanup required for local deployment"
            ;;
    esac
}

# Health check
health_check() {
    print_status "Performing health check..."
    
    case $1 in
        docker)
            docker-compose ps
            ;;
        kubernetes)
            kubectl get pods -n linkedin-automation
            kubectl get services -n linkedin-automation
            ;;
        local)
            python -c "
import asyncio
import sys
sys.path.insert(0, 'src')
from src.infrastructure.health_check import health_check
try:
    asyncio.run(health_check())
    print('✅ System is healthy')
except Exception as e:
    print(f'❌ Health check failed: {e}')
    sys.exit(1)
"
            ;;
    esac
}

# Show usage
usage() {
    echo "LinkedIn Multi-Agent Automation System Deployment Script"
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  local                 Deploy for local development"
    echo "  docker [monitoring]   Deploy using Docker Compose"
    echo "  kubernetes           Deploy to Kubernetes cluster"
    echo "  build                Build Docker image"
    echo "  cleanup <type>       Clean up deployment (docker|kubernetes)"
    echo "  health <type>        Check deployment health"
    echo "  config               Create sample configuration"
    echo ""
    echo "Examples:"
    echo "  $0 local"
    echo "  $0 docker monitoring"
    echo "  $0 kubernetes"
    echo "  $0 health docker"
}

# Main script
main() {
    case $1 in
        local)
            deploy_local
            ;;
        docker)
            deploy_docker $@
            ;;
        kubernetes)
            deploy_kubernetes
            ;;
        build)
            build_image
            ;;
        cleanup)
            cleanup $2
            ;;
        health)
            health_check $2
            ;;
        config)
            create_sample_config
            ;;
        *)
            usage
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main $@