"""add factory and failure history tables

Revision ID: b27c6c14e2e3
Revises: 2ea81be64492
Create Date: 2026-02-20 00:12:22.213907

Adds 6 tables for factory registry (Phase 120-04):
- factory_artifacts (main artifact table)
- artifact_versions (version snapshots)
- relevance_signals (gap detection signals)
- escalation_history (factory escalation log)
- suggestion_log (proactive suggestion log)
- failure_history (tool failure records)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b27c6c14e2e3"
down_revision: Union[str, None] = "2ea81be64492"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # --- factory_artifacts (parent table, must be created first) ---
    op.create_table(
        "factory_artifacts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("artifact_type", sa.String(length=32), nullable=False),
        sa.Column("framework", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_prompt", sa.Text(), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("artifact_path", sa.String(length=512), nullable=False),
        sa.Column("test_result", sa.Text(), nullable=True),
        sa.Column("test_passed", sa.Integer(), nullable=False),
        sa.Column("test_iterations", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(length=64), nullable=False),
        sa.Column("tags", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    with op.batch_alter_table("factory_artifacts", schema=None) as batch_op:
        batch_op.create_index("ix_factory_artifacts_created", ["created_at"], unique=False)
        batch_op.create_index("ix_factory_artifacts_name", ["name"], unique=False)
        batch_op.create_index("ix_factory_artifacts_status", ["status"], unique=False)
        batch_op.create_index("ix_factory_artifacts_type", ["artifact_type"], unique=False)

    # --- artifact_versions (FK to factory_artifacts) ---
    op.create_table(
        "artifact_versions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("artifact_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("files_snapshot", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("rollback_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["artifact_id"], ["factory_artifacts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_id", "version", name="uq_artifact_version"),
    )
    with op.batch_alter_table("artifact_versions", schema=None) as batch_op:
        batch_op.create_index("ix_artifact_versions_artifact", ["artifact_id"], unique=False)

    # --- relevance_signals (FK to factory_artifacts) ---
    op.create_table(
        "relevance_signals",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("pattern", sa.String(length=512), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("example_queries", sa.Text(), nullable=False),
        sa.Column("suggested_type", sa.String(length=32), nullable=True),
        sa.Column("urgency", sa.String(length=32), nullable=False),
        sa.Column("first_seen", sa.String(length=64), nullable=False),
        sa.Column("last_seen", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("resolved_artifact_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["resolved_artifact_id"], ["factory_artifacts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("signal_type", "pattern", name="uq_signal_type_pattern"),
    )
    with op.batch_alter_table("relevance_signals", schema=None) as batch_op:
        batch_op.create_index("ix_relevance_signals_pattern", ["pattern"], unique=False)
        batch_op.create_index("ix_relevance_signals_status", ["status"], unique=False)
        batch_op.create_index("ix_relevance_signals_type", ["signal_type"], unique=False)

    # --- escalation_history ---
    op.create_table(
        "escalation_history",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("conversation_id", sa.String(length=64), nullable=False),
        sa.Column("suggested_name", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("escalation_history", schema=None) as batch_op:
        batch_op.create_index("ix_escalation_history_created", ["created_at"], unique=False)

    # --- suggestion_log ---
    op.create_table(
        "suggestion_log",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("suggestion_log", schema=None) as batch_op:
        batch_op.create_index("ix_suggestion_log_created", ["created_at"], unique=False)

    # --- failure_history ---
    op.create_table(
        "failure_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.String(length=64), nullable=False),
        sa.Column("tool_name", sa.String(length=256), nullable=False),
        sa.Column("server_name", sa.String(length=256), nullable=False),
        sa.Column("error_category", sa.String(length=64), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("action_taken", sa.String(length=64), nullable=False),
        sa.Column("recovery_success", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=True),
        sa.Column("model_used", sa.String(length=128), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("failure_history", schema=None) as batch_op:
        batch_op.create_index("ix_failure_history_server", ["server_name"], unique=False)
        batch_op.create_index("ix_failure_history_timestamp", ["timestamp"], unique=False)
        batch_op.create_index("ix_failure_history_tool", ["tool_name"], unique=False)
        batch_op.create_index(
            "ix_failure_history_tool_category", ["tool_name", "error_category"], unique=False
        )

def downgrade() -> None:
    # Drop in reverse order (child tables with FKs first)
    with op.batch_alter_table("failure_history", schema=None) as batch_op:
        batch_op.drop_index("ix_failure_history_tool_category")
        batch_op.drop_index("ix_failure_history_tool")
        batch_op.drop_index("ix_failure_history_timestamp")
        batch_op.drop_index("ix_failure_history_server")

    op.drop_table("failure_history")

    with op.batch_alter_table("suggestion_log", schema=None) as batch_op:
        batch_op.drop_index("ix_suggestion_log_created")

    op.drop_table("suggestion_log")

    with op.batch_alter_table("escalation_history", schema=None) as batch_op:
        batch_op.drop_index("ix_escalation_history_created")

    op.drop_table("escalation_history")

    with op.batch_alter_table("relevance_signals", schema=None) as batch_op:
        batch_op.drop_index("ix_relevance_signals_type")
        batch_op.drop_index("ix_relevance_signals_status")
        batch_op.drop_index("ix_relevance_signals_pattern")

    op.drop_table("relevance_signals")

    with op.batch_alter_table("artifact_versions", schema=None) as batch_op:
        batch_op.drop_index("ix_artifact_versions_artifact")

    op.drop_table("artifact_versions")

    with op.batch_alter_table("factory_artifacts", schema=None) as batch_op:
        batch_op.drop_index("ix_factory_artifacts_type")
        batch_op.drop_index("ix_factory_artifacts_status")
        batch_op.drop_index("ix_factory_artifacts_name")
        batch_op.drop_index("ix_factory_artifacts_created")

    op.drop_table("factory_artifacts")
