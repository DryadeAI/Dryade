"""JWT Authentication Middleware.

Simple, stateless JWT verification.
JWT_SECRET environment variable is required for authentication to work.
If JWT_SECRET is not configured, authentication will fail with a 500 error.

Target: ~60 LOC
"""

from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from core.config import get_settings
from core.logs import get_logger
from core.utils.time import utcnow

logger = get_logger(__name__)

# MFA-related and auth paths exempt from grace period enforcement
_MFA_EXEMPT_PREFIXES = (
    "/api/auth/mfa",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/refresh",
    "/api/auth/setup",
)

class AuthMiddleware(BaseHTTPMiddleware):
    """JWT authentication middleware."""

    def __init__(self, app, exclude: list[str] | None = None):
        """Initialize auth middleware.

        Args:
            app: FastAPI application
            exclude: List of path prefixes to exclude from authentication
        """
        super().__init__(app)
        self.exclude = exclude or [
            "/health",
            "/api/health",
            "/api/health/detailed",
            "/api/health/metrics",
            "/api/ready",
            "/api/live",
            "/ready",
            "/live",
            "/metrics",
            "/docs",
            "/openapi.json",
        ]
        self.settings = get_settings()

    async def dispatch(self, request: Request, call_next):
        """Process request and verify JWT token.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            HTTP response
        """
        # WebSocket connections handle their own auth (via ?token= query param)
        if request.scope.get("type") == "websocket":
            return await call_next(request)

        # Skip excluded paths
        path = request.url.path
        if any(path.startswith(p) for p in self.exclude):
            return await call_next(request)

        # Skip if auth is disabled
        if not self.settings.auth_enabled:
            return await call_next(request)

        # Extract token
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return JSONResponse(status_code=401, content={"detail": "Missing authorization header"})

        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401, content={"detail": "Invalid authorization header format"}
            )

        token = auth_header.split(" ")[1]

        # JWT_SECRET is required - no bypass
        if not self.settings.jwt_secret:
            logger.error("JWT_SECRET not configured")
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Authentication not configured. Set JWT_SECRET environment variable."
                },
            )

        # Verify token
        try:
            payload = jwt.decode(
                token,
                self.settings.jwt_secret,
                algorithms=["HS256"],
            )
            request.state.user = payload
        except jwt.ExpiredSignatureError:
            return JSONResponse(status_code=401, content={"detail": "Token expired"})
        except jwt.InvalidTokenError as e:
            return JSONResponse(status_code=401, content={"detail": f"Invalid token: {str(e)}"})

        # MFA grace period enforcement (Phase 147)
        mfa_block = await self._check_mfa_enforcement(request, payload)
        if mfa_block is not None:
            return mfa_block

        return await call_next(request)

    async def _check_mfa_enforcement(self, request: Request, user_payload: dict):
        """Return 403 if MFA enforcement is active and user hasn't enrolled.

        Returns None if check passes, JSONResponse(403) if user must enroll.
        Exemptions:
          - MFA-related routes (/api/auth/mfa/*) — prevent redirect loop
          - Login/register/refresh routes
          - External/SSO users (is_external=True) — MFA managed by their IdP
          - Users with mfa_enabled=True — already enrolled
          - Grace period not yet expired
          - Enforcement not enabled (DRYADE_MFA_ENFORCEMENT_ENABLED=false)
        """
        # Skip if enforcement not enabled
        if not self.settings.mfa_enforcement_enabled:
            return None

        # Skip MFA-related and auth routes (prevent redirect loop)
        path = request.url.path
        if any(path.startswith(p) for p in _MFA_EXEMPT_PREFIXES):
            return None

        user_id = user_payload.get("sub")
        if not user_id:
            return None

        # DB lookup — lazy import to avoid circular imports
        try:
            from core.database.models import User
            from core.database.session import get_session

            with get_session() as db:
                user = db.query(User).filter(User.id == user_id).first()
                if not user:
                    return None

                # Exempt external/SSO users — MFA is managed by their IdP
                if user.is_external:
                    return None

                # Already enrolled — pass through
                if user.mfa_enabled:
                    return None

                now = datetime.now(UTC)

                # If no grace deadline set, set it now (14-day grace)
                if not user.mfa_grace_deadline:
                    user.mfa_grace_deadline = now + timedelta(days=14)
                    db.commit()
                    return None  # Just set the deadline — user gets 14 days

                # Normalize grace_deadline to UTC-aware for comparison
                # Normalize to UTC-aware for comparison
                grace_deadline = user.mfa_grace_deadline
                if grace_deadline.tzinfo is None:
                    grace_deadline = grace_deadline.replace(tzinfo=UTC)

                # Still within grace period
                if now < grace_deadline:
                    return None

                # Grace period expired, MFA not enrolled — block
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "mfa_required",
                        "message": "MFA enrollment required. Your grace period has expired.",
                    },
                )
        except Exception as e:
            logger.warning(f"MFA enforcement check failed: {e}")
            return None  # Fail open on DB errors to avoid locking users out

def create_token(user_id: str, role: str = "user", expires_hours: int = 24) -> str:
    """Create a JWT token for a user."""
    from datetime import timedelta

    settings = get_settings()
    if not settings.jwt_secret:
        raise ValueError("JWT_SECRET not configured")

    payload = {
        "sub": user_id,
        "role": role,
        "iat": utcnow(),
        "exp": utcnow() + timedelta(hours=expires_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

def get_current_user(request: Request) -> dict:
    """Get current user from request state."""
    return getattr(request.state, "user", None)
