"""Add inference parameter JSON columns to model_configs.

Revision ID: j1_inference_params
Revises: i1_traces_checkpoints
Create Date: 2026-03-12 15:00:00.000000

Phase 211: Per-capability inference parameters and vLLM server params.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "j1_inference_params"
down_revision = "i1_traces_checkpoints"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("model_configs", sa.Column("llm_inference_params", sa.JSON(), nullable=True))
    op.add_column("model_configs", sa.Column("vision_inference_params", sa.JSON(), nullable=True))
    op.add_column("model_configs", sa.Column("audio_inference_params", sa.JSON(), nullable=True))
    op.add_column(
        "model_configs", sa.Column("embedding_inference_params", sa.JSON(), nullable=True)
    )
    op.add_column("model_configs", sa.Column("vllm_server_params", sa.JSON(), nullable=True))

def downgrade() -> None:
    op.drop_column("model_configs", "vllm_server_params")
    op.drop_column("model_configs", "embedding_inference_params")
    op.drop_column("model_configs", "audio_inference_params")
    op.drop_column("model_configs", "vision_inference_params")
    op.drop_column("model_configs", "llm_inference_params")
