"""add fallback chain to model config

Revision ID: a1b2c3d4e5f6
Revises: b27c6c14e2e3
Create Date: 2026-03-02 20:00:00.000000

Adds LLM provider fallback chain columns to model_configs table (Phase 146).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "b27c6c14e2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    """Add fallback_chain and fallback_enabled columns to model_configs."""
    op.add_column(
        "model_configs",
        sa.Column("fallback_chain", sa.Text(), nullable=True),
    )
    op.add_column(
        "model_configs",
        sa.Column(
            "fallback_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
    )

def downgrade() -> None:
    """Remove fallback_chain and fallback_enabled columns from model_configs."""
    op.drop_column("model_configs", "fallback_enabled")
    op.drop_column("model_configs", "fallback_chain")
