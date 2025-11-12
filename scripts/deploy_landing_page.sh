#!/bin/bash

# Deploy Landing Page to DigitalOcean App Platform
# Usage: ./scripts/deploy_landing_page.sh

set -e

echo "🚀 Deploying AI EA Landing Page to DigitalOcean App Platform..."

# Check if doctl is installed
if ! command -v doctl &> /dev/null; then
    echo "❌ doctl CLI not found. Installing..."
    echo "📦 Installing doctl via Homebrew..."
    brew install doctl
fi

# Check authentication
echo "🔐 Checking DigitalOcean authentication..."
if ! doctl auth list &> /dev/null; then
    echo "⚠️  Not authenticated with DigitalOcean."
    echo "Please run: doctl auth init"
    exit 1
fi

# Create or update the app
echo "📤 Deploying app to DigitalOcean..."

# Check if app already exists
APP_ID=$(doctl apps list --format ID,Spec.Name | grep "ai-ea-landing-page" | awk '{print $1}' || echo "")

if [ -z "$APP_ID" ]; then
    echo "🆕 Creating new app..."
    doctl apps create --spec .do/landing-page/app.yaml
else
    echo "🔄 Updating existing app (ID: $APP_ID)..."
    doctl apps update $APP_ID --spec .do/landing-page/app.yaml
fi

echo ""
echo "✅ Deployment initiated!"
echo ""
echo "📊 Monitor deployment:"
echo "   doctl apps list"
echo ""
echo "🌐 Your site will be available at:"
echo "   https://ai-ea-landing-page.ondigitalocean.app"
echo ""
echo "💡 To add a custom domain:"
echo "   1. Go to DigitalOcean dashboard"
echo "   2. Navigate to your app > Settings > Domains"
echo "   3. Add your custom domain (e.g., landing.yourdomain.com)"
echo ""
