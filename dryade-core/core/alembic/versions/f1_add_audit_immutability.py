"""add audit immutability columns and PostgreSQL RULE

Revision ID: f1_add_audit_immutability
Revises: e4b7a3c56789
Create Date: 2026-03-05 00:00:00.000000

Extends audit_logs with hash chain columns (prev_hash, entry_hash) for tamper
detection and event_severity for compliance filtering. Creates PostgreSQL RULEs
to enforce append-only immutability.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision = "f1_add_audit_immutability"
down_revision = "e4b7a3c56789"
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Add hash chain and severity columns to audit_logs; create immutability RULEs on PostgreSQL."""
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.add_column(sa.Column("prev_hash", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("entry_hash", sa.String(64), nullable=True))
        batch_op.add_column(
            sa.Column(
                "event_severity",
                sa.String(16),
                nullable=True,
                server_default="info",
            )
        )
        batch_op.create_index("ix_audit_logs_event_severity", ["event_severity"])

    # Create RULEs to block UPDATE and DELETE on audit_logs
    op.execute("CREATE RULE audit_no_update AS ON UPDATE TO audit_logs DO INSTEAD NOTHING;")
    op.execute("CREATE RULE audit_no_delete AS ON DELETE TO audit_logs DO INSTEAD NOTHING;")

def downgrade() -> None:
    """Remove hash chain columns, severity column, and immutability RULEs."""
    op.execute("DROP RULE IF EXISTS audit_no_delete ON audit_logs;")
    op.execute("DROP RULE IF EXISTS audit_no_update ON audit_logs;")

    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.drop_index("ix_audit_logs_event_severity")
        batch_op.drop_column("event_severity")
        batch_op.drop_column("entry_hash")
        batch_op.drop_column("prev_hash")
