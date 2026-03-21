"""Add scheduled_loops and loop_executions tables.

Revision ID: h1_loop_engine
Revises: g2_enable_rls
Create Date: 2026-03-10 09:15:00.000000

Loop Engine core tables for scheduling and tracking execution of
workflows, agents, skills, and orchestrator tasks.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "h1_loop_engine"
down_revision = "g2_enable_rls"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # --- scheduled_loops ---
    op.create_table(
        "scheduled_loops",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column(
            "target_type",
            sa.String(32),
            nullable=False,
        ),
        sa.Column("target_id", sa.String(255), nullable=False),
        sa.Column(
            "trigger_type",
            sa.String(32),
            nullable=False,
        ),
        sa.Column("schedule", sa.String(255), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_scheduled_loops_name", "scheduled_loops", ["name"])

    # --- loop_executions ---
    op.create_table(
        "loop_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "loop_id",
            sa.String(36),
            sa.ForeignKey("scheduled_loops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("trigger_source", sa.String(32), nullable=False, server_default="schedule"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_loop_executions_loop_id", "loop_executions", ["loop_id"])
    op.create_index("ix_loop_executions_started_at", "loop_executions", ["started_at"])
    op.create_index(
        "ix_loop_executions_loop_started",
        "loop_executions",
        ["loop_id", sa.text("started_at DESC")],
    )

def downgrade() -> None:
    op.drop_table("loop_executions")
    op.drop_table("scheduled_loops")
