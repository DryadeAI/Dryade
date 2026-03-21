"""add workflow approval tables

Revision ID: d5a8e2f01234
Revises: a7e3f1d90b42
Create Date: 2026-03-02 12:00:00.000000

Creates workflow approval request and audit log tables for HITL workflow nodes
(Phase 150 FP-03):
- workflow_approval_requests: persists paused workflow state, prompt, approver, timeout
- workflow_approval_audit_logs: immutable audit trail for all approval actions (SOC2)
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision = "d5a8e2f01234"
down_revision = "a7e3f1d90b42"
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Create workflow_approval_requests and workflow_approval_audit_logs tables."""

    # 1. workflow_approval_requests
    op.create_table(
        "workflow_approval_requests",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "execution_id",
            sa.Integer,
            sa.ForeignKey("workflow_execution_results.id"),
            nullable=False,
        ),
        sa.Column(
            "workflow_id",
            sa.Integer,
            sa.ForeignKey("workflows.id"),
            nullable=False,
        ),
        sa.Column("node_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), default="pending"),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("approver_type", sa.String(32), nullable=False),
        sa.Column("approver_user_id", sa.String(64), nullable=True),
        sa.Column("display_fields", sa.Text, nullable=True),
        sa.Column("state_snapshot", sa.Text, nullable=False),
        sa.Column("timeout_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timeout_action", sa.String(16), nullable=False),
        sa.Column("resolved_by", sa.String(64), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text, nullable=True),
        sa.Column("modified_fields", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # Indexes for workflow_approval_requests
    op.create_index(
        "ix_approval_requests_execution_id",
        "workflow_approval_requests",
        ["execution_id"],
    )
    op.create_index(
        "ix_approval_requests_status",
        "workflow_approval_requests",
        ["status"],
    )
    op.create_index(
        "ix_approval_requests_workflow_id",
        "workflow_approval_requests",
        ["workflow_id"],
    )

    # 2. workflow_approval_audit_logs
    op.create_table(
        "workflow_approval_audit_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "request_id",
            sa.Integer,
            sa.ForeignKey("workflow_approval_requests.id"),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("action_data", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # Indexes for workflow_approval_audit_logs
    op.create_index(
        "ix_audit_log_request_id",
        "workflow_approval_audit_logs",
        ["request_id"],
    )
    op.create_index(
        "ix_audit_log_created_at",
        "workflow_approval_audit_logs",
        ["created_at"],
    )

def downgrade() -> None:
    """Drop workflow approval tables (audit logs first due to FK dependency)."""
    op.drop_index("ix_audit_log_created_at", table_name="workflow_approval_audit_logs")
    op.drop_index("ix_audit_log_request_id", table_name="workflow_approval_audit_logs")
    op.drop_table("workflow_approval_audit_logs")

    op.drop_index("ix_approval_requests_workflow_id", table_name="workflow_approval_requests")
    op.drop_index("ix_approval_requests_status", table_name="workflow_approval_requests")
    op.drop_index("ix_approval_requests_execution_id", table_name="workflow_approval_requests")
    op.drop_table("workflow_approval_requests")
