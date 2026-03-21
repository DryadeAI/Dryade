"""add mfa columns and recovery codes

Revision ID: a7e3f1d90b42
Revises: a1b2c3d4e5f6
Create Date: 2026-02-27 12:00:00.000000

Adds TOTP MFA support (Phase 147 SEC-01):
- 4 nullable columns on users table: totp_secret, mfa_enabled, mfa_grace_deadline, mfa_enabled_at
- New mfa_recovery_codes table with user_id FK, code_hash, used_at, created_at
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7e3f1d90b42"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Add MFA columns to users table (all nullable for backward compat)
    op.add_column("users", sa.Column("totp_secret", sa.String(64), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "mfa_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column("users", sa.Column("mfa_grace_deadline", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("mfa_enabled_at", sa.DateTime(), nullable=True))

    # Create mfa_recovery_codes table
    op.create_table(
        "mfa_recovery_codes",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("code_hash", sa.String(255), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_mfa_recovery_user", "mfa_recovery_codes", ["user_id"])

def downgrade() -> None:
    op.drop_index("ix_mfa_recovery_user", table_name="mfa_recovery_codes")
    op.drop_table("mfa_recovery_codes")
    op.drop_column("users", "mfa_enabled_at")
    op.drop_column("users", "mfa_grace_deadline")
    op.drop_column("users", "mfa_enabled")
    op.drop_column("users", "totp_secret")
