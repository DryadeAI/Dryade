"""Enable PostgreSQL Row-Level Security on user-owned tables.

Revision ID: g2_enable_rls
Revises: g1_postgresql_fk_indexes
Create Date: 2026-03-06 08:55:00.000000

Adds RLS policies on all user-owned tables for defense-in-depth isolation.
Two policies per table:
  - user_isolation: user sees only rows where user_id matches app.current_user_id
  - admin_bypass: admin context (app.is_admin='true') sees all rows

If neither setting is set, NEITHER policy matches -> zero rows returned (safe default).
"""

from alembic import op

# revision identifiers, used by Alembic
revision = "g2_enable_rls"
down_revision = "g1_postgresql_fk_indexes"
branch_labels = None
depends_on = None

# Tables with a user_id column that should be RLS-protected.
# Excluded: audit_logs, security_events (admin/system-level),
#   routing_metrics, optimization_cycles, prompt_versions (system-level),
#   model_pricing, cache (shared resources),
#   workflow_approval_requests, workflow_approval_audit_logs (cross-user),
#   mfa_recovery_codes (already FK-constrained, no user_id isolation needed),
#   resource_shares (complex sharing logic handled in app layer),
#   memory_blocks (scoped by agent_id, not user_id),
#   markdown_skills (no user_id column -- scoped by plugin_id).
RLS_TABLES = [
    "projects",
    "conversations",
    "execution_plans",
    "workflows",
    "cost_records",
    "training_jobs",
    "trained_models",
    "dataset_generations",
    "model_configs",
    "provider_api_keys",
    "custom_providers",
    "user_notifications",
    "dsar_requests",
]

def upgrade():
    """Enable RLS + create user_isolation and admin_bypass policies on each table."""
    for table in RLS_TABLES:
        # Enable RLS and force it even for table owner role
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

        # User isolation policy: user sees only their own rows.
        # current_setting('app.current_user_id', true) returns NULL if not set (no error).
        # Cast to text for comparison with the user_id column.
        op.execute(
            f"CREATE POLICY user_isolation_{table} ON {table} "
            f"USING (user_id = current_setting('app.current_user_id', true)::text)"
        )

        # Admin bypass policy: admin sees all rows.
        # PostgreSQL ORs multiple policies -- if either matches, access is granted.
        op.execute(
            f"CREATE POLICY admin_bypass_{table} ON {table} "
            f"USING (current_setting('app.is_admin', true) = 'true')"
        )

def downgrade():
    """Remove RLS policies and disable RLS on each table."""
    for table in reversed(RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS admin_bypass_{table} ON {table}")
        op.execute(f"DROP POLICY IF EXISTS user_isolation_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
