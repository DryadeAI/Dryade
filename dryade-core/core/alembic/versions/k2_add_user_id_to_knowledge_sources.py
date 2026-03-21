"""Add user_id FK column to knowledge_sources table.

Revision ID: k2_user_id_knowledge_sources
Revises: k1_user_id_markdown_skills
Create Date: 2026-03-12 21:15:00.000000

Phase 212.1: Ownership columns for RBAC extension points.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "k2_user_id_knowledge_sources"
down_revision = "k1_user_id_markdown_skills"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column(
        "knowledge_sources",
        sa.Column(
            "user_id",
            sa.String(64),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_knowledge_sources_user_id", "knowledge_sources", ["user_id"])

def downgrade() -> None:
    op.drop_index("ix_knowledge_sources_user_id", table_name="knowledge_sources")
    op.drop_column("knowledge_sources", "user_id")
