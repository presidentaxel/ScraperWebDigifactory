#!/bin/bash
# Helper script to create .env file

echo "Creating .env file from template..."
cat > .env << 'EOF'
# DigiFactory Configuration
BASE_URL=https://entrepreneur.digifactory.fr
LOGIN_URL=https://entrepreneur.digifactory.fr/digi/com/login

# Authentication (Option A: credentials)
USERNAME=your_username
PASSWORD=your_password

# Authentication (Option B: session cookie - fallback)
# SESSION_COOKIE=DigifactoryBO=xxxx

# Scraper Configuration
CONCURRENCY=20
BATCH_SIZE=1000
RATE_PER_DOMAIN=2
TIMEOUT=20
MAX_RETRIES=5

# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE=your_service_role_key
SUPABASE_TABLE=digifactory_sales

# Logging
LOG_LEVEL=INFO
EOF

echo ".env file created. Please edit it with your actual credentials."

