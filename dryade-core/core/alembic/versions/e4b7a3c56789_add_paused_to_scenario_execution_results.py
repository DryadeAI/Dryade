"""add paused to scenario_execution_results status

Revision ID: e4b7a3c56789
Revises: d5a8e2f01234
Create Date: 2026-03-03 00:00:00.000000

Adds 'paused' to the scenario_execution_results status CHECK constraint so that
approval-node workflows can persist a 'paused' status while awaiting human review.
Previously only: running, completed, failed, cancelled.
Now: running, completed, failed, cancelled, paused.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision = "e4b7a3c56789"
down_revision = "d5a8e2f01234"
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Extend scenario_execution_results.status CHECK constraint to include 'paused'."""
    with op.batch_alter_table("scenario_execution_results") as batch_op:
        # Drop old constraint (running, completed, failed, cancelled)
        batch_op.drop_constraint(
            "ck_scenario_execution_results_status",
            type_="check",
        )
        # Create new constraint with 'paused' added
        batch_op.create_check_constraint(
            "ck_scenario_execution_results_status",
            sa.text("status IN ('running', 'completed', 'failed', 'cancelled', 'paused')"),
        )

def downgrade() -> None:
    """Revert scenario_execution_results.status CHECK constraint — remove 'paused'."""
    with op.batch_alter_table("scenario_execution_results") as batch_op:
        # Drop extended constraint
        batch_op.drop_constraint(
            "ck_scenario_execution_results_status",
            type_="check",
        )
        # Restore original constraint without 'paused'
        batch_op.create_check_constraint(
            "ck_scenario_execution_results_status",
            sa.text("status IN ('running', 'completed', 'failed', 'cancelled')"),
        )
