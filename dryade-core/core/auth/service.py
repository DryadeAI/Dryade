"""Authentication Service for Dryade.

Provides user registration, authentication, and JWT token management.
Works standalone without external auth providers.

Target: ~120 LOC
"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.auth import mfa as mfa_helpers
from core.auth.password import hash_password, verify_password
from core.config import get_settings
from core.database.models import MFARecoveryCode, User
from core.ee.allowlist_ee import get_allowlist_path

class AuthService:
    """Authentication service for local user management."""

    def __init__(self, db: Session):
        """Initialize auth service with database session.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self.settings = get_settings()

    def register(self, email: str, password: str, display_name: str = None) -> User:
        """Register a new user with password.

        Args:
            email: User's email address
            password: Plain text password
            display_name: Optional display name

        Returns:
            Created User instance

        Raises:
            HTTPException: 400 if email already registered
        """
        if len(password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        if display_name and len(display_name) > 100:
            raise HTTPException(
                status_code=400, detail="Display name must be at most 100 characters"
            )
        # Check email exists
        existing = self.db.query(User).filter(User.email == email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Enforce max_users from signed allowlist
        from core.ee.allowlist_ee import get_tier_metadata

        tier_meta = get_tier_metadata()
        if tier_meta and tier_meta.max_users > 0:
            active_count = self.db.query(User).filter(User.is_active == True).count()  # noqa: E712
            if active_count >= tier_meta.max_users:
                raise HTTPException(
                    status_code=403,
                    detail="User limit reached for your license tier",
                )

        # Community auto-admin: first user gets admin if no allowlist
        role = "member"
        if self.db.query(User).count() == 0:
            try:
                if not get_allowlist_path().exists():
                    role = "admin"
            except ImportError:
                # EE module not available -- community build, promote to admin
                role = "admin"

        user = User(
            id=str(uuid.uuid4()),
            email=email,
            password_hash=hash_password(password),
            display_name=display_name,
            role=role,
            is_external=False,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def authenticate(self, email: str, password: str) -> User:
        """Authenticate user with email/password.

        Args:
            email: User's email address
            password: Plain text password

        Returns:
            Authenticated User instance

        Raises:
            HTTPException: 401 for invalid credentials, 400 for external auth, 403 for disabled
        """
        user = self.db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if user.is_external:
            raise HTTPException(status_code=400, detail="Use external login for this account")

        if not user.password_hash or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account disabled")

        # Update last_seen
        user.last_seen = datetime.now(UTC)
        self.db.commit()
        return user

    def authenticate_with_mfa_check(self, email: str, password: str) -> dict | User:
        """Authenticate user with MFA challenge support.

        Wraps authenticate() and returns MFA challenge dict if user has MFA enabled.

        Args:
            email: User's email address
            password: Plain text password

        Returns:
            User instance (no MFA) or {mfa_required: True, mfa_user_id: str, message: str}

        Raises:
            HTTPException: 401 for invalid credentials, 400 for external auth, 403 for disabled
        """
        user = self.authenticate(email, password)
        if user.mfa_enabled:
            return {
                "mfa_required": True,
                "mfa_user_id": user.id,
                "message": "MFA verification required",
            }
        return user

    def create_tokens(self, user: User) -> dict:
        """Create access and refresh tokens for a user.

        Args:
            user: User instance

        Returns:
            Dict with access_token, refresh_token, token_type, expires_in
        """
        access_token = self._create_token(
            user_id=user.id,
            role=user.role,
            email=user.email,
            token_type="access",
            expires_minutes=30,
        )
        refresh_token = self._create_token(
            user_id=user.id,
            role=user.role,
            email=user.email,
            token_type="refresh",
            expires_minutes=60 * 24 * 7,  # 7 days
        )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": 30 * 60,
        }

    def refresh_access_token(self, refresh_token: str) -> dict:
        """Create new tokens from refresh token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            New token dict

        Raises:
            HTTPException: 401 for invalid/expired tokens
        """
        try:
            payload = jwt.decode(refresh_token, self.settings.jwt_secret, algorithms=["HS256"])
            if payload.get("type") != "refresh":
                raise HTTPException(status_code=401, detail="Invalid token type")

            user = self.db.query(User).filter(User.id == payload["sub"]).first()
            if not user or not user.is_active:
                raise HTTPException(status_code=401, detail="User not found or inactive")

            # Prevent pre-MFA refresh tokens from bypassing MFA (Pitfall 3)
            if user.mfa_enabled and user.mfa_enabled_at:
                token_iat = payload.get("iat", 0)
                # Ensure mfa_enabled_at is timezone-aware before converting to timestamp
                mfa_at = user.mfa_enabled_at
                if mfa_at.tzinfo is None:
                    # Normalize naive datetimes to UTC
                    from datetime import timezone

                    mfa_at = mfa_at.replace(tzinfo=timezone.utc)
                mfa_enabled_ts = mfa_at.timestamp()
                if token_iat < mfa_enabled_ts:
                    raise HTTPException(
                        status_code=401,
                        detail="Refresh token issued before MFA was enabled — re-login required",
                    )

            return self.create_tokens(user)
        except jwt.ExpiredSignatureError as e:
            raise HTTPException(status_code=401, detail="Refresh token expired") from e
        except jwt.InvalidTokenError as e:
            raise HTTPException(status_code=401, detail="Invalid refresh token") from e

    def _create_token(
        self, user_id: str, role: str, email: str, token_type: str, expires_minutes: int
    ) -> str:
        """Create a JWT token with given claims."""
        payload = {
            "sub": user_id,
            "role": role,
            "email": email,
            "type": token_type,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=expires_minutes),
        }
        return jwt.encode(payload, self.settings.jwt_secret, algorithm="HS256")

    def get_user_by_id(self, user_id: str) -> User | None:
        """Get user by ID."""
        return self.db.query(User).filter(User.id == user_id).first()

    # -------------------------------------------------------------------------
    # MFA Methods (Phase 147)
    # -------------------------------------------------------------------------

    def setup_mfa(self, user_id: str) -> dict:
        """Begin MFA setup for a user.

        Generates a TOTP secret, QR code, and 8 recovery codes.
        MFA is NOT enabled yet — user must call verify_mfa_setup() to confirm.

        Args:
            user_id: User's ID

        Returns:
            Dict with qr_code (SVG), secret (base32), recovery_codes (list)

        Raises:
            ValueError: If MFA is already enabled
            HTTPException: 404 if user not found
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user.mfa_enabled:
            raise ValueError("MFA is already enabled. Disable it first to reconfigure.")

        # Generate TOTP secret and QR code
        secret = mfa_helpers.generate_totp_secret()
        provisioning_uri = mfa_helpers.generate_provisioning_uri(user.email, secret)
        qr_svg = mfa_helpers.generate_qr_svg(provisioning_uri)

        # Store secret (not yet enabled — confirmed in verify_mfa_setup)
        user.totp_secret = secret
        self.db.commit()

        # Generate and store recovery codes (delete any existing unused codes first)
        self.db.query(MFARecoveryCode).filter(
            MFARecoveryCode.user_id == user_id,
            MFARecoveryCode.used_at.is_(None),
        ).delete(synchronize_session=False)

        plaintext_codes = mfa_helpers.generate_recovery_codes(8)
        for code in plaintext_codes:
            recovery_code = MFARecoveryCode(
                user_id=user_id,
                code_hash=mfa_helpers.hash_recovery_code(code),
            )
            self.db.add(recovery_code)
        self.db.commit()

        return {
            "qr_code": qr_svg,
            "secret": secret,
            "recovery_codes": plaintext_codes,
        }

    def verify_mfa_setup(self, user_id: str, code: str) -> dict:
        """Confirm MFA setup by verifying a TOTP code from the authenticator app.

        After this succeeds, MFA is active. Future logins require TOTP.

        Args:
            user_id: User's ID
            code: 6-digit TOTP code from authenticator app

        Returns:
            Token dict (access_token, refresh_token, token_type, expires_in)

        Raises:
            ValueError: If code is invalid or user has no TOTP secret
            HTTPException: 404 if user not found
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if not user.totp_secret:
            raise ValueError("MFA setup not initiated. Call setup_mfa first.")

        if not mfa_helpers.verify_totp(user.totp_secret, code):
            raise ValueError("invalid_totp_code")

        # Enable MFA
        user.mfa_enabled = True
        user.mfa_enabled_at = datetime.now(UTC)
        self.db.commit()

        return self.create_tokens(user)

    def verify_mfa(self, user_id: str, code: str) -> dict:
        """Verify TOTP code during login (second factor).

        Called after login returns mfa_required=True.

        Args:
            user_id: User's ID (from login mfa_required response)
            code: 6-digit TOTP code from authenticator app

        Returns:
            Token dict (access_token, refresh_token, token_type, expires_in)

        Raises:
            ValueError: If code is invalid
            HTTPException: 404 if user not found
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if not user.totp_secret or not mfa_helpers.verify_totp(user.totp_secret, code):
            raise ValueError("invalid_totp_code")

        return self.create_tokens(user)

    def use_recovery_code(self, user_id: str, recovery_code: str) -> dict:
        """Use a recovery code as MFA fallback (when authenticator device is lost).

        Each recovery code is single-use. Atomic mark-as-used prevents replay.

        Args:
            user_id: User's ID (from login mfa_required response)
            recovery_code: Plaintext recovery code

        Returns:
            Token dict (access_token, refresh_token, token_type, expires_in)

        Raises:
            ValueError: If recovery code is invalid or already used
            HTTPException: 404 if user not found
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Find unused recovery codes for this user
        unused_codes = (
            self.db.query(MFARecoveryCode)
            .filter(
                MFARecoveryCode.user_id == user_id,
                MFARecoveryCode.used_at.is_(None),
            )
            .all()
        )

        # O(n) verify loop over unused codes (max 8 — negligible)
        matched = None
        for stored in unused_codes:
            if mfa_helpers.verify_recovery_code(recovery_code, stored.code_hash):
                matched = stored
                break

        if not matched:
            raise ValueError("invalid_recovery_code")

        # Atomically mark as used
        matched.used_at = datetime.now(UTC)
        self.db.commit()

        return self.create_tokens(user)

    def disable_mfa(self, user_id: str, password: str) -> None:
        """Disable MFA — requires password re-confirmation.

        Clears TOTP secret and deletes all recovery codes.

        Args:
            user_id: User's ID
            password: Current password for re-confirmation

        Raises:
            ValueError: If password is wrong
            HTTPException: 404 if user not found
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Require password confirmation
        if not user.password_hash or not verify_password(password, user.password_hash):
            raise ValueError("invalid_password")

        # Clear MFA
        user.totp_secret = None
        user.mfa_enabled = False
        user.mfa_enabled_at = None
        user.mfa_grace_deadline = None

        # Delete all recovery codes
        self.db.query(MFARecoveryCode).filter(MFARecoveryCode.user_id == user_id).delete(
            synchronize_session=False
        )

        self.db.commit()

    def regenerate_recovery_codes(self, user_id: str) -> list[str]:
        """Regenerate recovery codes for a user with MFA enabled.

        Args:
            user_id: User's ID

        Returns:
            List of 8 new plaintext recovery codes

        Raises:
            ValueError: If MFA is not enabled
            HTTPException: 404 if user not found
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if not user.mfa_enabled:
            raise ValueError("MFA is not enabled. Enable MFA before regenerating codes.")

        # Delete all existing recovery codes
        self.db.query(MFARecoveryCode).filter(MFARecoveryCode.user_id == user_id).delete(
            synchronize_session=False
        )

        # Generate new codes
        plaintext_codes = mfa_helpers.generate_recovery_codes(8)
        for code in plaintext_codes:
            recovery_code = MFARecoveryCode(
                user_id=user_id,
                code_hash=mfa_helpers.hash_recovery_code(code),
            )
            self.db.add(recovery_code)
        self.db.commit()

        return plaintext_codes

    def create_first_admin(self, email: str, password: str) -> User:
        """Create first admin user if no users exist.

        Args:
            email: Admin email address
            password: Admin password

        Returns:
            Created admin User

        Raises:
            HTTPException: 400 if users already exist
        """
        if self.db.query(User).count() > 0:
            raise HTTPException(status_code=400, detail="Users already exist")

        user = User(
            id=str(uuid.uuid4()),
            email=email,
            password_hash=hash_password(password),
            role="admin",
            is_verified=True,
            is_external=False,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
