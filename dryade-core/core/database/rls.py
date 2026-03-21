"""Row-Level Security context management for PostgreSQL.

Uses contextvars to thread user identity from FastAPI request handlers
into SQLAlchemy session events. Every transaction automatically executes
SET LOCAL app.current_user_id before any queries.

Usage:
    # In FastAPI dependency or middleware:
    set_rls_context(user_id="abc-123")

    # In background tasks or system operations:
    set_rls_context(user_id=None, is_admin=True)
"""

import contextvars

from sqlalchemy import event, text
from sqlalchemy.orm import Session

_current_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "db_current_user_id", default=None
)
_is_admin: contextvars.ContextVar[bool] = contextvars.ContextVar("db_is_admin", default=False)

_rls_events_registered = False

def set_rls_context(user_id: str | None = None, is_admin: bool = False):
    """Set RLS context for the current async task/thread.

    Args:
        user_id: The authenticated user's ID (sets app.current_user_id)
        is_admin: If True, sets app.is_admin='true' for admin bypass policy
    """
    _current_user_id.set(user_id)
    _is_admin.set(is_admin)

def clear_rls_context():
    """Clear RLS context (e.g., after request completes)."""
    _current_user_id.set(None)
    _is_admin.set(False)

def register_rls_events():
    """Register SQLAlchemy session event to apply RLS settings at transaction start.

    Safe to call multiple times -- guarded by module-level flag.
    """
    global _rls_events_registered
    if _rls_events_registered:
        return
    _rls_events_registered = True

    @event.listens_for(Session, "after_begin")
    def _apply_rls_settings(session, transaction, connection):
        """Inject RLS context as SET LOCAL at the start of each transaction.

        SET LOCAL is transaction-scoped -- automatically reset on COMMIT/ROLLBACK.
        This prevents context leaking across requests sharing a pooled connection.
        Only runs on PostgreSQL (SET LOCAL is PG-specific).
        """
        if connection.dialect.name != "postgresql":
            return

        user_id = _current_user_id.get(None)
        is_admin = _is_admin.get(False)

        if is_admin:
            # Admin bypass: policies check current_setting('app.is_admin', true) = 'true'
            connection.execute(text("SET LOCAL app.is_admin = 'true'"))
        elif user_id:
            # User isolation: policies check user_id = current_setting('app.current_user_id', true)
            # SET LOCAL requires a literal value, not a parameterized bind.
            # We use set_config() which accepts parameters safely.
            connection.execute(
                text("SELECT set_config('app.current_user_id', :uid, true)"),
                {"uid": user_id},
            )
        # If neither admin nor user_id set, RLS policies will block all rows (safe default)
