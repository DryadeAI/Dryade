"""add ai_decision_log table

Revision ID: f2_add_ai_decision_log
Revises: f1_add_audit_immutability
Create Date: 2026-03-05 00:00:01.000000

Creates the ai_decision_log table for EU AI Act Article 12 transparency logging.
Tracks model decisions, confidence, human overrides, and risk levels. Hash chain
columns enable tamper detection. PostgreSQL RULEs enforce immutability.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision = "f2_add_ai_decision_log"
down_revision = "f1_add_audit_immutability"
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Create ai_decision_log table with indexes and immutability RULEs."""
    op.create_table(
        "ai_decision_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("orchestration_mode", sa.String(32), nullable=True),
        sa.Column("prompt_category", sa.String(32), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("alternatives_considered", sa.JSON(), default=[]),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("human_review_required", sa.Boolean(), server_default="0"),
        sa.Column("human_reviewer_id", sa.String(64), nullable=True),
        sa.Column("human_override", sa.Boolean(), server_default="0"),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "risk_level",
            sa.String(16),
            nullable=True,
            server_default="limited",
        ),
        sa.Column("prev_hash", sa.String(64), nullable=True),
        sa.Column("entry_hash", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_ai_decision_log_model_id", "ai_decision_log", ["model_id"])
    op.create_index("ix_ai_decision_log_provider", "ai_decision_log", ["provider"])
    op.create_index("ix_ai_decision_log_created_at", "ai_decision_log", ["created_at"])
    op.create_index("ix_ai_decision_log_risk_level", "ai_decision_log", ["risk_level"])

    # PostgreSQL-only: immutability RULEs
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE RULE ai_decision_no_update AS ON UPDATE TO ai_decision_log DO INSTEAD NOTHING;"
        )
        op.execute(
            "CREATE RULE ai_decision_no_delete AS ON DELETE TO ai_decision_log DO INSTEAD NOTHING;"
        )

def downgrade() -> None:
    """Drop ai_decision_log table and associated RULEs."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP RULE IF EXISTS ai_decision_no_delete ON ai_decision_log;")
        op.execute("DROP RULE IF EXISTS ai_decision_no_update ON ai_decision_log;")

    op.drop_index("ix_ai_decision_log_risk_level", table_name="ai_decision_log")
    op.drop_index("ix_ai_decision_log_created_at", table_name="ai_decision_log")
    op.drop_index("ix_ai_decision_log_provider", table_name="ai_decision_log")
    op.drop_index("ix_ai_decision_log_model_id", table_name="ai_decision_log")
    op.drop_table("ai_decision_log")
