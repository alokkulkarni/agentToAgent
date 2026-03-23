# Identity Provider Integration - Requirements

## Python Dependencies

Add these to your `requirements.txt`:

```
PyJWT[crypto]>=2.8.0
cryptography>=41.0.0
httpx>=0.24.1
```

Install with:
```bash
pip install PyJWT[crypto] cryptography httpx
```

## Environment Configuration

See `.env.example` for all available authentication configuration options.

### Quick Start - Development Mode (No Auth)

```bash
AUTH_ENABLED=false
```

### Quick Start - Azure AD

```bash
AUTH_ENABLED=true
AUTH_PROVIDER=azure_ad
AUTH_ISSUER=https://login.microsoftonline.com/{tenant-id}/v2.0
AUTH_AUDIENCE=api://{your-api-client-id}
AUTH_CLIENT_ID={your-client-id}
AUTH_CLIENT_SECRET={your-client-secret}
AUTH_DISCOVERY_URL=https://login.microsoftonline.com/{tenant-id}/v2.0/.well-known/openid-configuration
```

### Quick Start - Okta

```bash
AUTH_ENABLED=true
AUTH_PROVIDER=okta
AUTH_ISSUER=https://{your-domain}.okta.com/oauth2/default
AUTH_AUDIENCE=api://{your-api-identifier}
AUTH_CLIENT_ID={your-client-id}
AUTH_CLIENT_SECRET={your-client-secret}
AUTH_DISCOVERY_URL=https://{your-domain}.okta.com/.well-known/openid-configuration
```

## Usage

### In API Requests

Include JWT token in Authorization header:

```bash
curl -X POST http://localhost:8100/api/workflow/execute \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"task_description": "Your task"}'
```

### Testing Without Authentication

Set `AUTH_ENABLED=false` to bypass authentication for development/testing.

## Features

- ✅ **JWT Token Validation** (RS256, HS256)
- ✅  **Multiple IdP Support** (Azure AD, Okta, Auth0, Cognito, Keycloak, Generic OIDC)
- ✅ **On-Behalf-Of (OBO) Token Flow** for tool-specific authentication
- ✅ **Auto-discovery** from OIDC .well-known endpoints
- ✅ **Token Caching** for performance
- ✅ **Scope-based Access Control**
- ✅ **Role-based Access Control (RBAC)**
- ✅ **MCP Tool Authentication** - tools declare their auth requirements

## Architecture

```
┌─────────────┐
│   Client    │
│ (with JWT)  │
└──────┬──────┘
       │ Bearer Token
       ▼
┌─────────────────────┐
│   Orchestrator      │
│  (validates JWT)    │────► Identity Provider
└──────┬──────────────┘      (Azure AD/Okta/etc)
       │ User Context
       │ + User Token
       ▼
┌─────────────────────┐
│   MCP Gateway       │
│ (validates JWT)     │
└──────┬──────────────┘
       │ Gets tool auth requirements
       │ from Registry
       ▼
┌─────────────────────┐
│   MCP Registry      │
│ (stores tool auth   │
│   schemas)          │
└──────┬──────────────┘
       │ Tool requires scopes: ["api.read", "api.execute"]
       ▼
┌─────────────────────┐
│   Identity Provider │ ◄─── OBO Token Exchange
│  (gets tool token)  │
└──────┬──────────────┘
       │ Tool-specific Token
       ▼
┌─────────────────────┐
│    MCP Server/      │
│    Tool             │
│ (validates token)   │
└─────────────────────┘
```

## MCP Server Auth Schema Registration

When registering an MCP server with tools that require authentication:

```python
from pydantic import BaseModel
from typing import List

class ToolAuthSchema(BaseModel):
    auth_type: str  # "oauth", "api_key", "bearer", "basic", "none"
    required_scopes: List[str] = []
    token_endpoint: str = None
    audience: str = None

# Register tool with auth requirements
tool_with_auth = {
    "name": "database_query",
    "description": "Query the database",
    "parameters": {...},
    "auth_schema": {
        "auth_type": "oauth",
        "required_scopes": ["database.read", "database.query"],
        "audience": "api://database-service"
    }
}
```

## Security Best Practices

1. **Always enable AUTH_ENABLED=true in production**
2. **Use HTTPS/TLS in production** (set `use_ssl: true` in config)
3. **Rotate client secrets regularly**
4. **Use narrow scopes** - only request what's needed
5. **Validate token signatures** (AUTH_VALIDATE_SIGNATURE=true)
6. **Check token expiry** (AUTH_VALIDATE_EXPIRY=true)
7. **Store secrets in secure vaults** (Azure Key Vault, AWS Secrets Manager, etc.)
8. **Use service-to-service authentication** for backend components

## Troubleshooting

### Token validation fails

- Check AUTH_ISSUER matches the token's `iss` claim
- Check AUTH_AUDIENCE matches the token's `aud` claim
- Verify JWKS_URI is accessible
- Check clock skew between systems

### OBO token exchange fails

- Verify CLIENT_SECRET is correct
- Check TOKEN_ENDPOINT is accessible
- Ensure user's token has necessary permissions for OBO
- Verify target scopes are valid

### MCP Tool auth fails

- Check tool's auth_schema is registered in MCP Registry
- Verify tool's required_scopes match what IdP can issue
- Check MCP server can validate the tool-specific token
