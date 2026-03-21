"""add DSAR request and consent preference tables

Revision ID: f3_add_dsar_consent_tables
Revises: f2_add_ai_decision_log
Create Date: 2026-03-05 00:00:02.000000

Creates dsar_requests and consent_preferences tables for GDPR compliance.
DSAR requests track data export/erasure workflows with status lifecycle.
Consent preferences store granular user consent choices with audit timestamps.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision = "f3_add_dsar_consent_tables"
down_revision = "f2_add_ai_decision_log"
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Create dsar_requests and consent_preferences tables."""
    op.create_table(
        "dsar_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("request_type", sa.String(32), nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("download_url", sa.Text(), nullable=True),
        sa.Column("download_expires_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_dsar_requests_user_id", "dsar_requests", ["user_id"])
    op.create_index("ix_dsar_requests_status", "dsar_requests", ["status"])
    op.create_index("ix_dsar_requests_created_at", "dsar_requests", ["created_at"])

    op.create_table(
        "consent_preferences",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(64), nullable=False, unique=True),
        sa.Column("essential", sa.Boolean(), server_default="1"),
        sa.Column("analytics", sa.Boolean(), server_default="0"),
        sa.Column("preferences", sa.Boolean(), server_default="0"),
        sa.Column("consent_timestamp", sa.DateTime(), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_consent_preferences_user_id",
        "consent_preferences",
        ["user_id"],
        unique=True,
    )

def downgrade() -> None:
    """Drop consent_preferences and dsar_requests tables."""
    op.drop_index("ix_consent_preferences_user_id", table_name="consent_preferences")
    op.drop_table("consent_preferences")

    op.drop_index("ix_dsar_requests_created_at", table_name="dsar_requests")
    op.drop_index("ix_dsar_requests_status", table_name="dsar_requests")
    op.drop_index("ix_dsar_requests_user_id", table_name="dsar_requests")
    op.drop_table("dsar_requests")
