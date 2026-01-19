#!/bin/bash
# Deployment script for DigitalOcean Droplet

set -e

echo "Deploying DigiFactory Scraper..."

# Build and start containers
docker-compose -f docker-compose.prod.yml up -d --build

# Show logs
docker-compose -f docker-compose.prod.yml logs -f

