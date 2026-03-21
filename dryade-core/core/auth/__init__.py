"""Dryade Authentication Module.

Provides password-based authentication, JWT tokens, and RBAC.
Works standalone without external dependencies (Zitadel is optional plugin).
"""

from core.auth.dependencies import (
    get_current_user,
    get_current_user_db,
    require_admin,
    require_member,
    require_role,
)
from core.auth.password import hash_password, verify_password
from core.auth.service import AuthService

__all__ = [
    "hash_password",
    "verify_password",
    "AuthService",
    "get_current_user",
    "require_role",
    "require_admin",
    "require_member",
    "get_current_user_db",
]
