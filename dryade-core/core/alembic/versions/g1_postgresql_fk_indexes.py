"""PostgreSQL-only: Add FK constraints and composite indexes.

Revision ID: g1_postgresql_fk_indexes
Revises: f3_add_dsar_consent_tables
Create Date: 2026-03-06 00:10:00.000000

Adds ForeignKey constraints to all ~20 user_id columns that previously lacked them,
plus 5 composite indexes for high-traffic query patterns. Orphan data is cleaned
before FK creation to avoid constraint violations.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision = "g1_postgresql_fk_indexes"
down_revision = "f3_add_dsar_consent_tables"
branch_labels = None
depends_on = None

# --------------------------------------------------------------------------
# Tables with NOT NULL user_id -> DELETE orphans, then CASCADE FK
# --------------------------------------------------------------------------
NOT_NULL_TABLES = [
    ("projects", "user_id"),
    ("resource_shares", "user_id"),
    ("workflow_approval_audit_logs", "actor_user_id"),
    ("dsar_requests", "user_id"),
    ("training_jobs", "user_id"),
    ("trained_models", "user_id"),
    ("dataset_generations", "user_id"),
    ("model_configs", "user_id"),
    ("provider_api_keys", "user_id"),
    ("custom_providers", "user_id"),
    ("user_notifications", "user_id"),
]

# --------------------------------------------------------------------------
# Tables with nullable user_id -> SET NULL orphans, then SET NULL FK
# --------------------------------------------------------------------------
NULLABLE_TABLES = [
    ("conversations", "user_id"),
    ("cost_records", "user_id"),
    ("execution_plans", "user_id"),
    ("workflows", "user_id"),
    ("workflow_execution_results", "user_id"),
    ("workflow_approval_requests", "approver_user_id"),
    ("audit_logs", "user_id"),
    ("scenario_execution_results", "user_id"),
]

# --------------------------------------------------------------------------
# Composite indexes for high-traffic query patterns
# --------------------------------------------------------------------------
COMPOSITE_INDEXES = [
    ("ix_conversations_user_created", "conversations", ["user_id", sa.text("created_at DESC")]),
    ("ix_messages_conversation_created", "messages", ["conversation_id", "created_at"]),
    ("ix_cost_records_user_timestamp", "cost_records", ["user_id", "timestamp"]),
    ("ix_workflows_user_created", "workflows", ["user_id", sa.text("created_at DESC")]),
    (
        "ix_extension_timeline_request_created",
        "extension_timeline",
        ["request_id", "created_at"],
    ),
]

def upgrade() -> None:
    """Clean orphan references, add FK constraints, create composite indexes."""
    conn = op.get_bind()

    # ── Phase 1: Clean orphan references ──────────────────────────────────
    # NOT NULL columns: delete orphan rows (can't set to NULL)
    for table, column in NOT_NULL_TABLES:
        conn.execute(
            sa.text(
                f"DELETE FROM {table} "
                f"WHERE {column} IS NOT NULL "
                f"AND {column} NOT IN (SELECT id FROM users)"
            )
        )

    # Nullable columns: set orphan references to NULL
    for table, column in NULLABLE_TABLES:
        conn.execute(
            sa.text(
                f"UPDATE {table} SET {column} = NULL "
                f"WHERE {column} IS NOT NULL "
                f"AND {column} NOT IN (SELECT id FROM users)"
            )
        )

    # ── Phase 2: Add FK constraints ───────────────────────────────────────
    for table, column in NOT_NULL_TABLES:
        op.create_foreign_key(
            f"fk_{table}_{column}",
            table,
            "users",
            [column],
            ["id"],
            ondelete="CASCADE",
        )

    for table, column in NULLABLE_TABLES:
        op.create_foreign_key(
            f"fk_{table}_{column}",
            table,
            "users",
            [column],
            ["id"],
            ondelete="SET NULL",
        )

    # ── Phase 3: Add composite indexes ────────────────────────────────────
    for idx_name, table, columns in COMPOSITE_INDEXES:
        op.create_index(idx_name, table, columns)

def downgrade() -> None:
    """Drop composite indexes and FK constraints (reverse order)."""
    # Drop composite indexes first
    for idx_name, table, _columns in reversed(COMPOSITE_INDEXES):
        op.drop_index(idx_name, table_name=table)

    # Drop FK constraints (nullable tables)
    for table, column in reversed(NULLABLE_TABLES):
        op.drop_constraint(f"fk_{table}_{column}", table, type_="foreignkey")

    # Drop FK constraints (NOT NULL tables)
    for table, column in reversed(NOT_NULL_TABLES):
        op.drop_constraint(f"fk_{table}_{column}", table, type_="foreignkey")
