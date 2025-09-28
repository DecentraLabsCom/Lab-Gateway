#!/bin/bash

# DecentraLabs Gateway - Full Version Deployment Script
# This script deploys the complete blockchain-based authentication system

set -e

echo "🚀 DecentraLabs Gateway - Full Version Deployment"
echo "=================================================="
echo ""

# Check if we're in the correct branch
CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
if [ "$CURRENT_BRANCH" != "full" ]; then
    echo "⚠️  Warning: You're not on the 'full' branch (current: $CURRENT_BRANCH)"
    echo "   To switch to full version: git checkout full"
    echo ""
    read -p "Continue anyway? [y/N]: " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

# Check if docker-compose is available
if ! command -v docker-compose >/dev/null 2>&1; then
    echo "❌ docker-compose is not installed. Please install Docker Compose and try again."
    exit 1
fi

echo "✅ Docker and Docker Compose are available"
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✅ Copied .env.example to .env"
    else
        echo "❌ .env.example template not found. Please create .env manually."
        exit 1
    fi
else
    echo "✅ .env file already exists"
fi

# Check if certificates exist
if [ ! -d "certs" ] || [ ! -f "certs/fullchain.pem" ] || [ ! -f "certs/privkey.pem" ]; then
    echo ""
    echo "⚠️  SSL certificates not found in certs/ directory"
    echo "   You need the following files:"
    echo "   - certs/fullchain.pem (SSL certificate)"
    echo "   - certs/privkey.pem (SSL private key)"
    echo "   - certs/public_key.pem (JWT public key)"
    echo ""
    read -p "Continue without certificates? [y/N]: " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Please add certificates to certs/ directory and try again."
        exit 1
    fi
fi

echo ""
echo "🏗️  Building and starting services..."
echo "   This may take several minutes on first run..."
echo ""

# Build and start services
docker-compose down --remove-orphans
docker-compose build --no-cache
docker-compose up -d

echo ""
echo "⏳ Waiting for services to be ready..."

# Wait for services to be healthy
SERVICES=("mysql" "redis" "auth-service" "guacamole" "openresty")
MAX_WAIT=300  # 5 minutes
WAIT_TIME=0

for service in "${SERVICES[@]}"; do
    echo -n "   Waiting for $service..."
    while [ $WAIT_TIME -lt $MAX_WAIT ]; do
        if docker-compose ps $service | grep -q "healthy\|running"; then
            echo " ✅"
            break
        fi
        sleep 5
        WAIT_TIME=$((WAIT_TIME + 5))
        echo -n "."
    done
    
    if [ $WAIT_TIME -ge $MAX_WAIT ]; then
        echo " ❌ (timeout)"
        echo "Service $service failed to start properly."
        echo "Check logs with: docker-compose logs $service"
        exit 1
    fi
    WAIT_TIME=0
done

echo ""
echo "🎉 Deployment completed successfully!"
echo ""
echo "📋 Service Status:"
docker-compose ps

echo ""
echo "🌐 Access URLs:"
echo "   Homepage: https://$(grep SERVER_NAME .env | cut -d'=' -f2)"
echo "   Guacamole: https://$(grep SERVER_NAME .env | cut -d'=' -f2)/guacamole/"
echo "   Auth Service: https://$(grep SERVER_NAME .env | cut -d'=' -f2)/auth"
echo ""
echo "🔑 Default Guacamole Credentials:"
echo "   Username: $(grep GUAC_ADMIN_USER .env | cut -d'=' -f2)"
echo "   Password: $(grep GUAC_ADMIN_PASS .env | cut -d'=' -f2)"
echo ""
echo "📊 Useful Commands:"
echo "   View logs: docker-compose logs -f [service_name]"
echo "   Restart service: docker-compose restart [service_name]"
echo "   Stop all: docker-compose down"
echo "   Update: docker-compose pull && docker-compose up -d"
echo ""
echo "🔧 Configuration:"
echo "   Environment: .env"
echo "   Certificates: certs/"
echo "   Auth Service Config: auth-service/src/main/resources/"
echo ""

# Show any potential issues
echo "🔍 Health Check Results:"
for service in "${SERVICES[@]}"; do
    status=$(docker-compose ps -q $service | xargs docker inspect --format='{{.State.Health.Status}}' 2>/dev/null || echo "no-healthcheck")
    case $status in
        "healthy")
            echo "   $service: ✅ Healthy"
            ;;
        "unhealthy")
            echo "   $service: ❌ Unhealthy"
            ;;
        "starting")
            echo "   $service: ⏳ Starting"
            ;;
        "no-healthcheck")
            echo "   $service: ℹ️  Running (no health check)"
            ;;
        *)
            echo "   $service: ❓ Unknown status: $status"
            ;;
    esac
done

echo ""
echo "✨ Full version deployment complete!"
echo "   Your blockchain-based authentication system is now running."