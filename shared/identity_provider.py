"""
Enterprise Identity Provider Module

Provides pluggable identity provider integration supporting:
- JWT token validation (RS256, HS256)
- OAuth 2.0 / OIDC flows
- On-Behalf-Of (OBO) token exchange
- Multiple IdP providers (Azure AD, Okta, Auth0, AWS Cognito, Generic OIDC)
- Token caching for performance
- Scope-based token retrieval

Configuration is externalized via environment variables and config files.
"""

import os
import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import httpx
from functools import lru_cache

logger = logging.getLogger(__name__)

# Optional JWT libraries - gracefully degrade if not available
try:
    import jwt
    from jwt import PyJWKClient
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    logger.warning("PyJWT not installed. Token validation will be disabled. Install: pip install PyJWT[crypto] cryptography")


class IdPProvider(Enum):
    """Supported Identity Provider types"""
    AZURE_AD = "azure_ad"
    OKTA = "okta"
    AUTH0 = "auth0"
    AWS_COGNITO = "aws_cognito"
    KEYCLOAK = "keycloak"
    GENERIC_OIDC = "generic_oidc"
    NONE = "none"  # Bypass authentication (development only)


class TokenType(Enum):
    """Token types for different use cases"""
    USER_ACCESS = "user_access"           # User authentication token
    SERVICE_ACCESS = "service_access"     # Service-to-service token
    TOOL_ACCESS = "tool_access"           # Tool-specific access token
    REFRESH_TOKEN = "refresh"             # Refresh token


@dataclass
class TokenInfo:
    """Token information and metadata"""
    token: str
    token_type: TokenType
    expires_at: datetime
    scopes: List[str] = field(default_factory=list)
    claims: Dict[str, Any] = field(default_factory=dict)
    
    def is_expired(self) -> bool:
        """Check if token is expired (with 5 minute buffer)"""
        return datetime.utcnow() >= (self.expires_at - timedelta(minutes=5))


@dataclass
class UserContext:
    """Authenticated user context"""
    user_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    tenant_id: Optional[str] = None
    scopes: List[str] = field(default_factory=list)
    raw_token: Optional[str] = None
    claims: Dict[str, Any] = field(default_factory=dict)
    
    def has_role(self, role: str) -> bool:
        """Check if user has a specific role"""
        return role in self.roles
    
    def has_scope(self, scope: str) -> bool:
        """Check if user has a specific scope"""
        return scope in self.scopes


@dataclass
class ToolAuthRequirement:
    """Authentication requirements for a specific tool/MCP server"""
    tool_name: str
    auth_type: str  # "oauth", "api_key", "basic", "none"
    required_scopes: List[str] = field(default_factory=list)
    token_endpoint: Optional[str] = None
    additional_params: Dict[str, Any] = field(default_factory=dict)


class TokenCache:
    """Simple in-memory token cache with expiration"""
    
    def __init__(self):
        self._cache: Dict[str, TokenInfo] = {}
    
    def get(self, key: str) -> Optional[TokenInfo]:
        """Get token from cache if not expired"""
        if key in self._cache:
            token_info = self._cache[key]
            if not token_info.is_expired():
                return token_info
            else:
                del self._cache[key]
        return None
    
    def set(self, key: str, token_info: TokenInfo):
        """Store token in cache"""
        self._cache[key] = token_info
    
    def clear(self):
        """Clear all cached tokens"""
        self._cache.clear()


class IdentityProvider:
    """
    Enterprise Identity Provider Manager
    
    Supports multiple IdP providers with pluggable configuration.
    All settings are externalized via environment variables.
    """
    
    def __init__(self):
        self.enabled = os.getenv("AUTH_ENABLED", "false").lower() == "true"
        self.provider = IdPProvider(os.getenv("AUTH_PROVIDER", "none"))
        
        # Core OIDC/OAuth configuration
        self.issuer = os.getenv("AUTH_ISSUER", "")
        self.audience = os.getenv("AUTH_AUDIENCE", "")
        self.client_id = os.getenv("AUTH_CLIENT_ID", "")
        self.client_secret = os.getenv("AUTH_CLIENT_SECRET", "")
        
        # JWKS and well-known endpoints
        self.jwks_uri = os.getenv("AUTH_JWKS_URI", "")
        self.token_endpoint = os.getenv("AUTH_TOKEN_ENDPOINT", "")
        self.authorize_endpoint = os.getenv("AUTH_AUTHORIZE_ENDPOINT", "")
        
        # Auto-discover endpoints from well-known config
        self.discovery_url = os.getenv("AUTH_DISCOVERY_URL", "")
        if self.discovery_url and not self.jwks_uri:
            self._discover_endpoints()
        
        # Token validation settings
        self.validate_signature = os.getenv("AUTH_VALIDATE_SIGNATURE", "true").lower() == "true"
        self.validate_expiry = os.getenv("AUTH_VALIDATE_EXPIRY", "true").lower() == "true"
        self.algorithms = os.getenv("AUTH_ALGORITHMS", "RS256").split(",")
        
        # Scopes and claims
        self.default_scopes = os.getenv("AUTH_DEFAULT_SCOPES", "openid profile email").split()
        self.role_claim = os.getenv("AUTH_ROLE_CLAIM", "roles")
        self.tenant_claim = os.getenv("AUTH_TENANT_CLAIM", "tenant_id")
        
        # Token cache
        self._token_cache = TokenCache()
        
        # HTTP client for token operations
        self._http_client = httpx.AsyncClient(timeout=30.0)
        
        # JWT client (if available)
        self._jwks_client = None
        if JWT_AVAILABLE and self.jwks_uri and self.validate_signature:
            try:
                self._jwks_client = PyJWKClient(self.jwks_uri)
                logger.info(f"✓ JWT validation enabled with JWKS from {self.jwks_uri}")
            except Exception as e:
                logger.warning(f"Failed to initialize JWKS client: {e}")
        
        logger.info(f"Identity Provider initialized: {self.provider.value} (enabled={self.enabled})")
    
    def _discover_endpoints(self):
        """Auto-discover OIDC endpoints from well-known configuration"""
        try:
            import httpx
            response = httpx.get(self.discovery_url, timeout=10.0)
            if response.status_code == 200:
                config = response.json()
                self.jwks_uri = self.jwks_uri or config.get("jwks_uri", "")
                self.token_endpoint = self.token_endpoint or config.get("token_endpoint", "")
                self.authorize_endpoint = self.authorize_endpoint or config.get("authorization_endpoint", "")
                self.issuer = self.issuer or config.get("issuer", "")
                logger.info(f"✓ Auto-discovered OIDC endpoints from {self.discovery_url}")
        except Exception as e:
            logger.warning(f"Failed to auto-discover OIDC endpoints: {e}")
    
    async def validate_token(self, token: str) -> UserContext:
        """
        Validate JWT token and extract user context
        
        Args:
            token: JWT access token
            
        Returns:
            UserContext with user information
            
        Raises:
            ValueError: If token is invalid
        """
        if not self.enabled:
            # Return anonymous user for development
            logger.debug("Authentication disabled - returning anonymous user")
            return UserContext(
                user_id="anonymous",
                roles=["admin"],  # Dev mode has admin access
                scopes=["*"]
            )
        
        if not JWT_AVAILABLE:
            raise ValueError("JWT validation not available. Install: pip install PyJWT[crypto] cryptography")
        
        try:
            # Decode without verification first to check if we need to validate
            unverified_claims = jwt.decode(token, options={"verify_signature": False})
            
            # Full validation
            if self.validate_signature and self._jwks_client:
                signing_key = self._jwks_client.get_signing_key_from_jwt(token)
                claims = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=self.algorithms,
                    audience=self.audience if self.audience else None,
                    issuer=self.issuer if self.issuer else None,
                    options={
                        "verify_signature": True,
                        "verify_exp": self.validate_expiry,
                        "verify_aud": bool(self.audience),
                        "verify_iss": bool(self.issuer)
                    }
                )
            else:
                claims = unverified_claims
                logger.warning("Token validation without signature verification (not recommended for production)")
            
            # Extract user context from claims
            user_context = self._extract_user_context(token, claims)
            
            logger.debug(f"Token validated successfully for user: {user_context.user_id}")
            return user_context
            
        except jwt.ExpiredSignatureError:
            raise ValueError("Token has expired")
        except jwt.InvalidAudienceError:
            raise ValueError(f"Invalid audience. Expected: {self.audience}")
        except jwt.InvalidIssuerError:
            raise ValueError(f"Invalid issuer. Expected: {self.issuer}")
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Invalid token: {str(e)}")
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            raise ValueError(f"Token validation failed: {str(e)}")
    
    def _extract_user_context(self, token: str, claims: Dict[str, Any]) -> UserContext:
        """Extract user context from JWT claims"""
        
        # Standard OIDC claims
        user_id = claims.get("sub") or claims.get("oid") or claims.get("user_id", "unknown")
        email = claims.get("email") or claims.get("preferred_username")
        name = claims.get("name") or claims.get("given_name", "")
        
        # Roles can be in different claim paths depending on IdP
        roles = []
        if self.role_claim in claims:
            role_claim = claims[self.role_claim]
            if isinstance(role_claim, list):
                roles = role_claim
            elif isinstance(role_claim, str):
                roles = [role_claim]
        
        # Extract roles from other common locations
        if not roles:
            roles = claims.get("roles", claims.get("groups", []))
        
        # Scopes
        scopes = []
        scope_claim = claims.get("scp") or claims.get("scope", "")
        if isinstance(scope_claim, str):
            scopes = scope_claim.split()
        elif isinstance(scope_claim, list):
            scopes = scope_claim
        
        # Tenant ID (for multi-tenant scenarios)
        tenant_id = claims.get(self.tenant_claim) or claims.get("tid") or claims.get("tenant_id")
        
        return UserContext(
            user_id=user_id,
            email=email,
            name=name,
            roles=roles,
            tenant_id=tenant_id,
            scopes=scopes,
            raw_token=token,
            claims=claims
        )
    
    async def get_token_for_scope(
        self, 
        user_context: UserContext, 
        required_scopes: List[str],
        resource: Optional[str] = None
    ) -> str:
        """
        Get access token with specific scopes using On-Behalf-Of (OBO) flow
        
        Args:
            user_context: Current user context
            required_scopes: List of required scopes for the target resource
            resource: Target resource identifier
            
        Returns:
            Access token with requested scopes
        """
        if not self.enabled:
            return "dev-token-no-auth"
        
        # Check cache first
        cache_key = f"obo:{user_context.user_id}:{':'.join(sorted(required_scopes))}"
        cached_token = self._token_cache.get(cache_key)
        if cached_token:
            logger.debug(f"Using cached OBO token for scopes: {required_scopes}")
            return cached_token.token
        
        # Perform OBO token exchange based on provider
        try:
            if self.provider == IdPProvider.AZURE_AD:
                token = await self._azure_obo_flow(user_context.raw_token, required_scopes, resource)
            elif self.provider == IdPProvider.OKTA:
                token = await self._okta_token_exchange(user_context.raw_token, required_scopes)
            elif self.provider == IdPProvider.GENERIC_OIDC:
                token = await self._generic_token_exchange(user_context.raw_token, required_scopes)
            else:
                logger.warning(f"OBO flow not implemented for {self.provider.value}, using original token")
                token = user_context.raw_token
            
            # Cache the token
            if token and JWT_AVAILABLE:
                try:
                    claims = jwt.decode(token, options={"verify_signature": False})
                    exp = claims.get("exp", time.time() + 3600)
                    expires_at = datetime.fromtimestamp(exp)
                    
                    token_info = TokenInfo(
                        token=token,
                        token_type=TokenType.TOOL_ACCESS,
                        expires_at=expires_at,
                        scopes=required_scopes,
                        claims=claims
                    )
                    self._token_cache.set(cache_key, token_info)
                except:
                    pass  # Ignore cache errors
            
            return token
            
        except Exception as e:
            logger.error(f"Failed to get token for scopes {required_scopes}: {e}")
            # Fallback to original token
            return user_context.raw_token
    
    async def _azure_obo_flow(
        self, 
        user_token: str, 
        scopes: List[str],
        resource: Optional[str] = None
    ) -> str:
        """Azure AD On-Behalf-Of token flow"""
        if not self.token_endpoint:
            raise ValueError("Token endpoint not configured for Azure AD OBO flow")
        
        scope_str = " ".join(scopes) if scopes else self.audience
        
        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "assertion": user_token,
            "scope": scope_str,
            "requested_token_use": "on_behalf_of"
        }
        
        if resource:
            data["resource"] = resource
        
        response = await self._http_client.post(self.token_endpoint, data=data)
        response.raise_for_status()
        
        result = response.json()
        return result.get("access_token")
    
    async def _okta_token_exchange(self, user_token: str, scopes: List[str]) -> str:
        """Okta token exchange flow"""
        if not self.token_endpoint:
            raise ValueError("Token endpoint not configured for Okta token exchange")
        
        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "subject_token": user_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "scope": " ".join(scopes)
        }
        
        response = await self._http_client.post(self.token_endpoint, data=data)
        response.raise_for_status()
        
        result = response.json()
        return result.get("access_token")
    
    async def _generic_token_exchange(self, user_token: str, scopes: List[str]) -> str:
        """Generic OIDC token exchange (RFC 8693)"""
        if not self.token_endpoint:
            raise ValueError("Token endpoint not configured")
        
        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": user_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "scope": " ".join(scopes)
        }
        
        # Include client credentials if available
        if self.client_id and self.client_secret:
            data["client_id"] = self.client_id
            data["client_secret"] = self.client_secret
        
        response = await self._http_client.post(self.token_endpoint, data=data)
        response.raise_for_status()
        
        result = response.json()
        return result.get("access_token")
    
    async def get_client_credentials_token(self, scopes: List[str]) -> str:
        """
        Get access token using client credentials flow (service-to-service)
        
        Args:
            scopes: Required scopes
            
        Returns:
            Access token
        """
        if not self.enabled:
            return "dev-service-token"
        
        cache_key = f"client_creds:{':'.join(sorted(scopes))}"
        cached_token = self._token_cache.get(cache_key)
        if cached_token:
            return cached_token.token
        
        if not self.token_endpoint:
            raise ValueError("Token endpoint not configured for client credentials flow")
        
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": " ".join(scopes)
        }
        
        response = await self._http_client.post(self.token_endpoint, data=data)
        response.raise_for_status()
        
        result = response.json()
        token = result.get("access_token")
        
        # Cache token
        expires_in = result.get("expires_in", 3600)
        token_info = TokenInfo(
            token=token,
            token_type=TokenType.SERVICE_ACCESS,
            expires_at=datetime.utcnow() + timedelta(seconds=expires_in),
            scopes=scopes
        )
        self._token_cache.set(cache_key, token_info)
        
        return token
    
    async def close(self):
        """Clean up resources"""
        await self._http_client.aclose()
        self._token_cache.clear()


# Singleton instance
_identity_provider: Optional[IdentityProvider] = None

def get_identity_provider() -> IdentityProvider:
    """Get or create singleton IdentityProvider instance"""
    global _identity_provider
    if _identity_provider is None:
        _identity_provider = IdentityProvider()
    return _identity_provider
