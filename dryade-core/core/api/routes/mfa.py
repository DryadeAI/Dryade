"""MFA (Multi-Factor Authentication) API Routes.

TOTP-based MFA with recovery codes.

Endpoints:
- POST /setup    — begin MFA setup (returns QR + secret + recovery codes)
- POST /verify   — confirm setup by validating a TOTP code
- POST /validate — validate TOTP code during login (second factor)
- POST /recovery — use recovery code during login
- POST /disable  — disable MFA (requires password confirmation)
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.auth.dependencies import get_current_user, get_db
from core.auth.events import get_client_ip, log_auth_event
from core.auth.service import AuthService

router = APIRouter()

# =============================================================================
# Request / Response Models
# =============================================================================

class MFASetupResponse(BaseModel):
    """Response for MFA setup — shown once, save recovery codes."""

    qr_code: str  # SVG string for QR code
    secret: str  # Base32 secret for manual entry
    recovery_codes: list[str]  # 8 one-time recovery codes (shown once)

class MFAVerifyRequest(BaseModel):
    """Confirm MFA setup with a code from the authenticator app."""

    code: str  # 6-digit TOTP code

class MFAValidateRequest(BaseModel):
    """Validate TOTP code during login (second factor)."""

    user_id: str  # From login mfa_required response
    code: str  # 6-digit TOTP code

class MFARecoveryRequest(BaseModel):
    """Use a recovery code during login."""

    user_id: str  # From login mfa_required response
    recovery_code: str  # Recovery code (XXXX-XXXX-XXXX-XXXX)

class MFADisableRequest(BaseModel):
    """Disable MFA — requires password confirmation."""

    password: str  # Current password

class MFARecoveryCodesResponse(BaseModel):
    """Regenerated recovery codes — shown once."""

    recovery_codes: list[str]

class TokenResponse(BaseModel):
    """Token response for auth endpoints."""

    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int

# =============================================================================
# Endpoints
# =============================================================================

@router.post("/setup", response_model=MFASetupResponse)
async def mfa_setup(
    background_tasks: BackgroundTasks,
    req: Request,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Begin MFA setup — returns QR code, secret, and 8 recovery codes.

    Call this once. Show QR code to user (they scan with authenticator app).
    Show recovery codes once — user must save them securely.
    Then call /verify with a code from their authenticator to confirm setup.
    """
    auth = AuthService(db)
    try:
        result = auth.setup_mfa(user["sub"])
        background_tasks.add_task(
            log_auth_event, db, user["sub"], "mfa_setup_initiated", get_client_ip(req)
        )
        return MFASetupResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/verify", response_model=TokenResponse)
async def mfa_verify_setup(
    request: MFAVerifyRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Confirm MFA setup by verifying a TOTP code from authenticator app.

    After this succeeds, MFA is active. Future logins require TOTP.
    Returns full tokens — user is now authenticated.
    """
    auth = AuthService(db)
    try:
        tokens = auth.verify_mfa_setup(user["sub"], request.code)
        background_tasks.add_task(
            log_auth_event, db, user["sub"], "mfa_enabled", get_client_ip(req)
        )
        return TokenResponse(**tokens)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/validate", response_model=TokenResponse)
async def mfa_validate(
    request: MFAValidateRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    db: Session = Depends(get_db),
):
    """Validate TOTP code during login (second factor).

    Called after login returns mfa_required=true. No auth header needed —
    user_id from the login mfa_required response is used instead.
    Returns full tokens on success.
    """
    auth = AuthService(db)
    try:
        tokens = auth.verify_mfa(request.user_id, request.code)
        background_tasks.add_task(
            log_auth_event, db, request.user_id, "mfa_validated", get_client_ip(req)
        )
        return TokenResponse(**tokens)
    except ValueError as e:
        background_tasks.add_task(
            log_auth_event,
            db,
            request.user_id,
            "mfa_validation_failed",
            get_client_ip(req),
            {"reason": str(e)},
            "warning",
        )
        raise HTTPException(status_code=401, detail=str(e))

@router.post("/recovery", response_model=TokenResponse)
async def mfa_recovery(
    request: MFARecoveryRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    db: Session = Depends(get_db),
):
    """Use a recovery code as MFA fallback (when authenticator device is lost).

    Each recovery code is single-use. After all 8 are consumed, user must
    disable+re-enable MFA to generate new codes.
    """
    auth = AuthService(db)
    try:
        tokens = auth.use_recovery_code(request.user_id, request.recovery_code)
        background_tasks.add_task(
            log_auth_event,
            db,
            request.user_id,
            "mfa_recovery_used",
            get_client_ip(req),
            severity="warning",
        )
        return TokenResponse(**tokens)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

@router.post("/disable")
async def mfa_disable(
    request: MFADisableRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Disable MFA — requires password re-confirmation.

    Clears TOTP secret and deletes all recovery codes.
    """
    auth = AuthService(db)
    try:
        auth.disable_mfa(user["sub"], request.password)
        background_tasks.add_task(
            log_auth_event,
            db,
            user["sub"],
            "mfa_disabled",
            get_client_ip(req),
            severity="warning",
        )
        return {"detail": "MFA disabled successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/recovery-codes", response_model=MFARecoveryCodesResponse)
async def mfa_regenerate_recovery_codes(
    background_tasks: BackgroundTasks,
    req: Request,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Regenerate MFA recovery codes.

    Replaces all existing recovery codes with 8 new ones.
    Only works when MFA is enabled.
    """
    auth = AuthService(db)
    try:
        codes = auth.regenerate_recovery_codes(user["sub"])
        background_tasks.add_task(
            log_auth_event, db, user["sub"], "mfa_recovery_regenerated", get_client_ip(req)
        )
        return MFARecoveryCodesResponse(recovery_codes=codes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
