#!/usr/bin/env python3
"""
Test script for verifying Identity Provider integration
"""

import os
import sys
import json
import httpx
import asyncio
from pathlib import Path
from typing import Optional

# Add shared to path
sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))

from identity_provider import IdentityProvider, UserContext
from config import ConfigManager

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_success(msg: str):
    print(f"{Colors.GREEN}✅ {msg}{Colors.END}")

def print_warning(msg: str):
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.END}")

def print_error(msg: str):
    print(f"{Colors.RED}❌ {msg}{Colors.END}")

def print_info(msg: str):
    print(f"{Colors.BLUE}ℹ️  {msg}{Colors.END}")

async def test_identity_provider():
    """Test identity provider setup"""
    print("\n🔐 Testing Identity Provider Integration")
    print("=" * 50)
    
    # Load configuration
    print("\n1. Loading Configuration...")
    config = ConfigManager()
    
    if not config.auth.enabled:
        print_warning("Authentication is DISABLED (development mode)")
        print_info("Set AUTH_ENABLED=true in .env to enable authentication")
        return True
    
    print_success("Authentication is ENABLED")
    print_info(f"Provider: {config.auth.provider}")
    print_info(f"Issuer: {config.auth.issuer}")
    print_info(f"Audience: {config.auth.audience}")
    
    # Initialize identity provider
    print("\n2. Initializing Identity Provider...")
    try:
        idp = IdentityProvider(config.auth)
        print_success("Identity provider initialized")
    except Exception as e:
        print_error(f"Failed to initialize identity provider: {e}")
        return False
    
    # Test OIDC discovery
    if config.auth.discovery_url:
        print("\n3. Testing OIDC Discovery...")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(config.auth.discovery_url, timeout=10.0)
                if response.status_code == 200:
                    discovery = response.json()
                    print_success("OIDC discovery successful")
                    print_info(f"Issuer: {discovery.get('issuer')}")
                    print_info(f"Token endpoint: {discovery.get('token_endpoint')}")
                    print_info(f"JWKS URI: {discovery.get('jwks_uri')}")
                else:
                    print_error(f"OIDC discovery failed: {response.status_code}")
                    return False
        except Exception as e:
            print_error(f"OIDC discovery error: {e}")
            return False
    else:
        print_warning("OIDC discovery URL not configured, skipping...")
    
    # Test JWKS endpoint
    if config.auth.jwks_uri:
        print("\n4. Testing JWKS Endpoint...")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(config.auth.jwks_uri, timeout=10.0)
                if response.status_code == 200:
                    jwks = response.json()
                    keys = jwks.get('keys', [])
                    print_success(f"JWKS retrieved successfully ({len(keys)} keys)")
                else:
                    print_error(f"JWKS retrieval failed: {response.status_code}")
                    return False
        except Exception as e:
            print_error(f"JWKS retrieval error: {e}")
            return False
    else:
        print_warning("JWKS URI not configured, skipping...")
    
    # Test token validation (if sample token provided)
    print("\n5. Testing Token Validation...")
    sample_token = os.getenv("TEST_JWT_TOKEN")
    if sample_token:
        try:
            user = await idp.validate_token(sample_token)
            print_success("Token validation successful")
            print_info(f"User ID: {user.user_id}")
            print_info(f"Email: {user.email}")
            print_info(f"Roles: {', '.join(user.roles)}")
            print_info(f"Scopes: {', '.join(user.scopes)}")
        except Exception as e:
            print_error(f"Token validation failed: {e}")
            print_info("Make sure TEST_JWT_TOKEN environment variable contains a valid JWT")
            return False
    else:
        print_warning("No TEST_JWT_TOKEN provided, skipping token validation")
        print_info("To test token validation:")
        print_info("  export TEST_JWT_TOKEN='your-jwt-token'")
        print_info("  python scripts/test_identity_provider.py")
    
    # Test client credentials flow (if configured)
    if config.auth.client_id and config.auth.client_secret:
        print("\n6. Testing Client Credentials Flow...")
        try:
            token = await idp.get_client_credentials_token()
            if token:
                print_success("Client credentials token obtained")
                print_info(f"Token type: {token.get('token_type', 'bearer')}")
                print_info(f"Expires in: {token.get('expires_in', 'unknown')} seconds")
            else:
                print_warning("Client credentials token not obtained (provider may not support this flow)")
        except Exception as e:
            print_warning(f"Client credentials flow not available: {e}")
            print_info("This is normal if your IdP doesn't support client credentials")
    else:
        print_warning("Client credentials not configured, skipping...")
    
    print("\n" + "=" * 50)
    print_success("Identity Provider tests completed!")
    return True

async def test_service_endpoints():
    """Test service endpoints with authentication"""
    print("\n🌐 Testing Service Endpoints")
    print("=" * 50)
    
    config = ConfigManager()
    
    # Test orchestrator health
    print("\n1. Testing Orchestrator (port 8100)...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8100/api/health", timeout=5.0)
            if response.status_code == 200:
                print_success("Orchestrator is running")
            else:
                print_error(f"Orchestrator health check failed: {response.status_code}")
    except Exception as e:
        print_error(f"Orchestrator connection failed: {e}")
        print_info("Make sure orchestrator is running: cd services/orchestrator && python app.py")
    
    # Test MCP Gateway health
    print("\n2. Testing MCP Gateway (port 8300)...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8300/api/health", timeout=5.0)
            if response.status_code == 200:
                print_success("MCP Gateway is running")
            else:
                print_error(f"MCP Gateway health check failed: {response.status_code}")
    except Exception as e:
        print_error(f"MCP Gateway connection failed: {e}")
        print_info("Make sure MCP Gateway is running: cd services/mcp_gateway && python app.py")
    
    # Test MCP Registry health
    print("\n3. Testing MCP Registry (port 8200)...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8200/api/health", timeout=5.0)
            if response.status_code == 200:
                print_success("MCP Registry is running")
            else:
                print_error(f"MCP Registry health check failed: {response.status_code}")
    except Exception as e:
        print_error(f"MCP Registry connection failed: {e}")
        print_info("Make sure MCP Registry is running: cd services/mcp_registry && python app.py")
    
    # Test authenticated endpoint if token provided
    sample_token = os.getenv("TEST_JWT_TOKEN")
    if sample_token and config.auth.enabled:
        print("\n4. Testing Authenticated Endpoint...")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8100/api/workflow/execute",
                    json={"task_description": "test authentication"},
                    headers={"Authorization": f"Bearer {sample_token}"},
                    timeout=10.0
                )
                if response.status_code == 200:
                    print_success("Authenticated request successful")
                elif response.status_code == 401:
                    print_error("Authentication failed (401 Unauthorized)")
                    print_info("Check if your TEST_JWT_TOKEN is valid")
                else:
                    print_warning(f"Unexpected response: {response.status_code}")
        except Exception as e:
            print_error(f"Authenticated request failed: {e}")
    else:
        print_warning("No TEST_JWT_TOKEN provided or auth disabled, skipping authenticated endpoint test")
    
    print("\n" + "=" * 50)

def main():
    """Main entry point"""
    print("\n" + "=" * 50)
    print("🔐 Identity Provider Integration Test Suite")
    print("=" * 50)
    
    # Check if .env exists
    if not os.path.exists(".env"):
        print_error(".env file not found")
        print_info("Run: cp .env.example .env")
        print_info("Then configure your identity provider settings")
        sys.exit(1)
    
    # Run tests
    try:
        # Test identity provider
        loop = asyncio.get_event_loop()
        idp_result = loop.run_until_complete(test_identity_provider())
        
        # Test service endpoints
        loop.run_until_complete(test_service_endpoints())
        
        # Summary
        print("\n" + "=" * 50)
        print("📊 Test Summary")
        print("=" * 50)
        
        if idp_result:
            print_success("All tests passed!")
            print_info("\nYour identity provider is configured correctly.")
            print_info("You can now start using authenticated endpoints.")
        else:
            print_error("Some tests failed")
            print_info("\nPlease check the errors above and:")
            print_info("1. Verify your .env configuration")
            print_info("2. Check docs/IDENTITY_PROVIDER_SETUP.md")
            print_info("3. Ensure your IdP is accessible")
            sys.exit(1)
    
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(0)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
