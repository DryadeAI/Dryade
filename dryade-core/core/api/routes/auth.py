"""Authentication API Routes.

Endpoints for user registration, login, and token management.
Provides self-contained auth that works without external dependencies.

Target: ~80 LOC
"""

import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_user, get_db
from core.auth.events import get_client_ip, log_auth_event
from core.auth.service import AuthService
from core.logs import get_logger

logger = get_logger(__name__)
router = APIRouter()

class RegisterRequest(BaseModel):
    """User registration request."""

    email: EmailStr
    password: str = Field(..., min_length=8)
    display_name: str | None = Field(default=None, max_length=100)

class LoginRequest(BaseModel):
    """User login request."""

    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    """Token response for auth endpoints."""

    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int

class RefreshRequest(BaseModel):
    """Token refresh request."""

    refresh_token: str

class LogoutResponse(BaseModel):
    """Logout response."""

    message: str

@router.post("/register", response_model=TokenResponse)
async def register(
    request: RegisterRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    db: Session = Depends(get_db),
):
    """Register a new user.

    Creates a new user account with email and password,
    returning access and refresh tokens on success.
    """
    auth = AuthService(db)
    user = auth.register(request.email, request.password, request.display_name)
    logger.info(f"User registered: {user.email}")
    background_tasks.add_task(log_auth_event, db, user.id, "user_registered", get_client_ip(req))
    return auth.create_tokens(user)

@router.post("/login")
async def login(
    request: LoginRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    db: Session = Depends(get_db),
):
    """Authenticate user. Returns tokens or MFA challenge.

    Normal response: {access_token, refresh_token, token_type, expires_in}
    MFA challenge:   {mfa_required: true, mfa_user_id: str, message: str}

    Note: response_model is intentionally removed so FastAPI does not strip
    the mfa_required/mfa_user_id fields from MFA challenge responses.
    """
    auth = AuthService(db)
    try:
        result = auth.authenticate_with_mfa_check(request.email, request.password)
    except Exception:
        background_tasks.add_task(
            log_auth_event,
            db,
            request.email,
            "login_fail",
            get_client_ip(req),
            {"reason": "invalid_credentials"},
            "warning",
        )
        raise
    if isinstance(result, dict) and result.get("mfa_required"):
        # MFA step needed — return challenge, not tokens
        return result
    # Normal login (no MFA) — result is a User object
    logger.info(f"User logged in: {result.email}")
    background_tasks.add_task(log_auth_event, db, result.id, "login_success", get_client_ip(req))
    return auth.create_tokens(result)

@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: RefreshRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    db: Session = Depends(get_db),
):
    """Refresh access token.

    Exchanges a valid refresh token for new access and refresh tokens.
    """
    auth = AuthService(db)
    tokens = auth.refresh_access_token(request.refresh_token)
    # Extract user_id from the new access token for audit logging
    # (refresh_access_token already validated the refresh token)
    try:
        payload = jwt.decode(
            tokens["access_token"],
            options={"verify_signature": False},
        )
        uid = payload.get("sub", "unknown")
    except Exception:
        uid = "unknown"
    background_tasks.add_task(log_auth_event, db, uid, "token_refresh", get_client_ip(req))
    return tokens

@router.post("/logout", response_model=LogoutResponse)
async def logout(
    background_tasks: BackgroundTasks,
    req: Request,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Logout current user.

    Logs the logout event. Client is responsible for clearing tokens.
    Returns 200 on successful logout.
    """
    logger.info(f"User logged out: {user.get('email', user.get('sub', 'unknown'))}")
    background_tasks.add_task(
        log_auth_event, db, user.get("sub", "unknown"), "user_logout", get_client_ip(req)
    )
    return {"message": "Successfully logged out"}

@router.post("/setup", response_model=TokenResponse)
async def setup_admin(
    request: RegisterRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    db: Session = Depends(get_db),
):
    """Create first admin user.

    Only works when no users exist in the system.
    Used for initial system setup.
    """
    auth = AuthService(db)
    user = auth.create_first_admin(request.email, request.password)
    logger.info(f"First admin created: {user.email}")
    background_tasks.add_task(
        log_auth_event, db, user.id, "admin_setup", get_client_ip(req), severity="critical"
    )
    return auth.create_tokens(user)
