#!/bin/bash
# Quick start script for Identity Provider integration

set -e

echo "🔐 Identity Provider Integration - Quick Start"
echo "=============================================="
echo ""

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file from .env.example..."
    cp .env.example .env
    echo "✅ .env file created"
    echo "⚠️  Please edit .env and configure your identity provider settings"
    echo ""
fi

# Install dependencies
echo "📦 Installing dependencies..."
echo ""

# Root dependencies
echo "Installing root dependencies..."
pip install -r requirements.txt

# Service dependencies
echo "Installing orchestrator dependencies..."
pip install -r services/orchestrator/requirements.txt

echo "Installing MCP Gateway dependencies..."
pip install -r services/mcp_gateway/requirements.txt

echo "Installing MCP Registry dependencies..."
pip install -r services/mcp_registry/requirements.txt

echo ""
echo "✅ All dependencies installed"
echo ""

# Check AUTH_ENABLED in .env
AUTH_ENABLED=$(grep -E "^AUTH_ENABLED=" .env | cut -d'=' -f2 | tr -d ' ')

if [ "$AUTH_ENABLED" = "false" ]; then
    echo "🔓 Authentication is DISABLED (development mode)"
    echo "   To enable authentication:"
    echo "   1. Set AUTH_ENABLED=true in .env"
    echo "   2. Configure your identity provider settings"
    echo ""
elif [ "$AUTH_ENABLED" = "true" ]; then
    echo "🔒 Authentication is ENABLED (production mode)"
    echo "   Make sure you have configured your identity provider in .env"
    echo ""
    
    # Check if essential auth settings are configured
    AUTH_PROVIDER=$(grep -E "^AUTH_PROVIDER=" .env | cut -d'=' -f2 | tr -d ' ')
    if [ -z "$AUTH_PROVIDER" ] || [ "$AUTH_PROVIDER" = "azure_ad" ]; then
        echo "⚠️  Warning: AUTH_PROVIDER not configured or still set to default"
        echo "   Please configure the following in .env:"
        echo "   - AUTH_PROVIDER"
        echo "   - AUTH_ISSUER"
        echo "   - AUTH_AUDIENCE"
        echo "   - AUTH_CLIENT_ID"
        echo "   - AUTH_CLIENT_SECRET"
        echo ""
    fi
else
    echo "⚠️  AUTH_ENABLED not set in .env (defaulting to disabled)"
    echo ""
fi

# Display next steps
echo "📚 Next Steps:"
echo "=============="
echo ""
echo "1. Configure Identity Provider:"
echo "   - Edit .env file with your IdP settings"
echo "   - See .env.example for examples of:"
echo "     * Azure AD (Microsoft Entra ID)"
echo "     * Okta"
echo "     * Auth0"
echo "     * AWS Cognito"
echo "     * Keycloak"
echo ""
echo "2. Review Documentation:"
echo "   - Setup Guide: docs/IDENTITY_PROVIDER_SETUP.md"
echo "   - Architecture: docs/IDENTITY_INTEGRATION_SUMMARY.md"
echo ""
echo "3. Start Services:"
echo "   - Development: ./scripts/start_services.sh"
echo "   - Docker: docker-compose up -d"
echo ""
echo "4. Test Authentication:"
echo "   # Development mode (no auth)"
echo "   curl http://localhost:8100/api/health"
echo ""
echo "   # Production mode (with JWT)"
echo "   TOKEN=\"your-jwt-token\""
echo "   curl -H \"Authorization: Bearer \$TOKEN\" \\"
echo "        http://localhost:8100/api/workflow/execute \\"
echo "        -X POST -H \"Content-Type: application/json\" \\"
echo "        -d '{\"task_description\": \"test task\"}'"
echo ""
echo "5. Optional: Test with Sample JWT"
echo "   # Get a test token from your IdP"
echo "   # Example for Azure AD:"
echo "   az account get-access-token --resource api://your-api-client-id"
echo ""

echo "✅ Setup complete!"
echo ""
echo "For more information, see:"
echo "  - docs/IDENTITY_PROVIDER_SETUP.md"
echo "  - docs/IDENTITY_INTEGRATION_SUMMARY.md"
