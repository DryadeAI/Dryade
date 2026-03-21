"""Add user_id FK column to factory_artifacts table.

Revision ID: k3_user_id_factory_artifacts
Revises: k2_user_id_knowledge_sources
Create Date: 2026-03-12 21:15:00.000000

Phase 212.1: Ownership columns for RBAC extension points.
Includes data migration to copy created_by -> user_id where valid.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "k3_user_id_factory_artifacts"
down_revision = "k2_user_id_knowledge_sources"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column(
        "factory_artifacts",
        sa.Column(
            "user_id",
            sa.String(64),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_factory_artifacts_user_id", "factory_artifacts", ["user_id"])

    # Data migration: copy created_by to user_id where it matches a valid user
    op.execute(
        """
        UPDATE factory_artifacts
        SET user_id = created_by
        WHERE created_by IN (SELECT id FROM users)
    """
    )

def downgrade() -> None:
    op.drop_index("ix_factory_artifacts_user_id", table_name="factory_artifacts")
    op.drop_column("factory_artifacts", "user_id")
