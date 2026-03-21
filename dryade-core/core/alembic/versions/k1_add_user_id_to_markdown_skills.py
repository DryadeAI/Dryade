"""Add user_id FK column to markdown_skills table.

Revision ID: k1_user_id_markdown_skills
Revises: j1_inference_params
Create Date: 2026-03-12 21:15:00.000000

Phase 212.1: Ownership columns for RBAC extension points.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "k1_user_id_markdown_skills"
down_revision = "j1_inference_params"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column(
        "markdown_skills",
        sa.Column(
            "user_id",
            sa.String(64),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_markdown_skills_user_id", "markdown_skills", ["user_id"])

def downgrade() -> None:
    op.drop_index("ix_markdown_skills_user_id", table_name="markdown_skills")
    op.drop_column("markdown_skills", "user_id")
