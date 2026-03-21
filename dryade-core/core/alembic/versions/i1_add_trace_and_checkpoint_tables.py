"""Add trace_events and checkpoints tables.

Revision ID: i1_traces_checkpoints
Revises: h1_loop_engine
Create Date: 2026-03-10 16:00:00.000000

Migrates observability tracing and orchestration checkpoints from raw
sqlite3 to PostgreSQL via SQLAlchemy ORM.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "i1_traces_checkpoints"
down_revision = "h1_loop_engine"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # --- trace_events ---
    op.create_table(
        "trace_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("crew_id", sa.String(256), nullable=True),
        sa.Column("agent_name", sa.String(256), nullable=True),
        sa.Column("task_id", sa.String(256), nullable=True),
        sa.Column("tool_name", sa.String(256), nullable=True),
        sa.Column("data", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Float, nullable=True),
        sa.Column("status", sa.String(64), nullable=True),
    )
    op.create_index("ix_trace_events_timestamp", "trace_events", ["timestamp"])
    op.create_index("ix_trace_events_event_type", "trace_events", ["event_type"])
    op.create_index("ix_trace_events_crew_id", "trace_events", ["crew_id"])

    # --- orchestration_checkpoints ---
    op.create_table(
        "orchestration_checkpoints",
        sa.Column("checkpoint_id", sa.String(64), primary_key=True),
        sa.Column("execution_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(64), nullable=False),
        sa.Column("label", sa.String(256), server_default=""),
        sa.Column("state_json", sa.Text, nullable=False),
    )
    op.create_index(
        "ix_orch_checkpoints_execution_id", "orchestration_checkpoints", ["execution_id"]
    )

def downgrade() -> None:
    op.drop_table("orchestration_checkpoints")
    op.drop_table("trace_events")
