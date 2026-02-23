"""
FastAPI Authentication Dependencies

Provides reusable FastAPI dependencies for JWT authentication and authorization.
"""

from fastapi import HTTPException, Header, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
import logging

from .identity_provider import get_identity_provider, UserContext

logger = logging.getLogger(__name__)

# Security scheme for Bearer token
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    authorization: Optional[str] = Header(None)
) -> UserContext:
    """
    FastAPI dependency to extract and validate user from JWT token.
    
    Supports:
    - Bearer token in Authorization header (standard OAuth/OIDC)
    - Token in custom Authorization header
    - Fallback to anonymous user if auth is disabled
    
    Usage in FastAPI endpoints:
        @app.post("/api/endpoint")
        async def endpoint(user: UserContext = Depends(get_current_user)):
            print(f"User: {user.user_id}, Roles: {user.roles}")
    
    Raises:
        HTTPException: 401 if token is invalid or missing (when auth is enabled)
    """
    idp = get_identity_provider()
    
    # If authentication is disabled, return anonymous user
    if not idp.enabled:
        logger.debug("Authentication disabled - returning anonymous user")
        return UserContext(
            user_id="anonymous",
            email="anonymous@local",
            roles=["admin"],  # Dev mode gets admin access
            scopes=["*"]
        )
    
    # Extract token from Bearer authorization
    token = None
    if credentials:
        token = credentials.credentials
    elif authorization:
        # Support custom Authorization header format
        if authorization.startswith("Bearer "):
            token = authorization[7:]
        else:
            token = authorization
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Validate token
    try:
        user_context = await idp.validate_token(token)
        return user_context
    except ValueError as e:
        logger.warning(f"Token validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Unexpected error during token validation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service error"
        )


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[UserContext]:
    """
    FastAPI dependency for optional authentication.
    
    Returns UserContext if token is provided and valid, otherwise None.
    Does not raise exceptions - useful for endpoints that work with or without auth.
    """
    idp = get_identity_provider()
    
    if not idp.enabled:
        return UserContext(
            user_id="anonymous",
            roles=["admin"],
            scopes=["*"]
        )
    
    if not credentials:
        return None
    
    try:
        user_context = await idp.validate_token(credentials.credentials)
        return user_context
    except Exception as e:
        logger.debug(f"Optional auth failed: {e}")
        return None


def require_role(required_role: str):
    """
    Dependency factory for role-based access control.
    
    Usage:
        @app.post("/admin/endpoint")
        async def admin_endpoint(
            user: UserContext = Depends(get_current_user),
            _: None = Depends(require_role("admin"))
        ):
            # Only users with 'admin' role can access
    
    Args:
        required_role: Role name that user must have
        
    Returns:
        FastAPI dependency function
    """
    async def check_role(user: UserContext = Depends(get_current_user)) -> None:
        if not user.has_role(required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {required_role}"
            )
    return check_role


def require_scope(required_scope: str):
    """
    Dependency factory for scope-based access control.
    
    Usage:
        @app.post("/api/sensitive")
        async def sensitive_endpoint(
            user: UserContext = Depends(get_current_user),
            _: None = Depends(require_scope("sensitive.read"))
        ):
            # Only users with 'sensitive.read' scope can access
    
    Args:
        required_scope: Scope that user token must have
        
    Returns:
        FastAPI dependency function
    """
    async def check_scope(user: UserContext = Depends(get_current_user)) -> None:
        if not user.has_scope(required_scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required scope: {required_scope}"
            )
    return check_scope


def require_any_role(*roles: str):
    """
    Dependency factory for checking if user has any of the specified roles.
    
    Usage:
        @app.post("/api/endpoint")
        async def endpoint(
            user: UserContext = Depends(get_current_user),
            _: None = Depends(require_any_role("admin", "operator"))
        ):
            # Users with 'admin' OR 'operator' role can access
    
    Args:
        *roles: One or more role names
        
    Returns:
        FastAPI dependency function
    """
    async def check_roles(user: UserContext = Depends(get_current_user)) -> None:
        if not any(user.has_role(role) for role in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required one of: {', '.join(roles)}"
            )
    return check_roles


async def get_user_headers(user: UserContext = Depends(get_current_user)) -> Dict[str, str]:
    """
    Dependency to convert UserContext to headers for downstream services.
    
    Usage:
        @app.post("/api/workflow")
        async def workflow(
            request: Dict,
            user: UserContext = Depends(get_current_user),
            headers: Dict[str, str] = Depends(get_user_headers)
        ):
            # Forward to another service with user identity
            await downstream_service.call(headers=headers)
    
    Returns:
        Dictionary of identity propagation headers
    """
    return {
        "X-User-ID": user.user_id,
        "X-User-Email": user.email or "",
        "X-User-Name": user.name or "",
        "X-User-Role": user.roles[0] if user.roles else "user",
        "X-User-Roles": ",".join(user.roles),
        "X-Session-ID": user.tenant_id or "",
        "X-Tenant-ID": user.tenant_id or "",
        "X-Auth-Token": user.raw_token or "",
        "X-Scopes": ",".join(user.scopes)
    }
