#!/bin/bash

# WebChat Deployment Script for ProxMox LXC
# Run this script inside your LXC container after copying the project files

set -e  # Exit on any error

echo "🚀 Starting WebChat deployment..."

# Update system
echo "📦 Updating system packages..."
apt update && apt upgrade -y

# Install Docker
echo "🐳 Installing Docker..."
apt install -y docker.io docker-compose-v2 curl git

# Enable Docker service
systemctl enable docker
systemctl start docker

# Add user to docker group
usermod -aG docker $USER

echo "✅ Docker installed successfully"

# Check if .env exists, if not create from template
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.template .env
    echo "⚠️  IMPORTANT: Edit .env file with your actual API keys!"
    echo "⚠️  Run: nano .env"
else
    echo "✅ .env file already exists"
fi

# Create data directories
echo "📁 Creating data directories..."
mkdir -p ./chats ./data

# Build and start services
echo "🏗️  Building and starting containers..."
docker compose up -d --build

# Wait a moment for services to start
sleep 10

# Check if services are running
echo "🔍 Checking service status..."
docker compose ps

# Show logs
echo "📋 Recent logs:"
docker compose logs --tail=20

echo ""
echo "🎉 Deployment complete!"
echo ""
echo "📡 Access your webapp at:"
echo "   http://$(hostname -I | awk '{print $1}'):5000"
echo ""
echo "🔧 Useful commands:"
echo "   docker compose logs -f          # View live logs"
echo "   docker compose restart          # Restart services"
echo "   docker compose down             # Stop services"
echo "   docker compose pull && docker compose up -d  # Update services"
echo ""
echo "📝 Next steps:"
echo "1. Edit .env with your API keys: nano .env"
echo "2. Restart services: docker compose restart"
echo "3. Test from another device on your network"