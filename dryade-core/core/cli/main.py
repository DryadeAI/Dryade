"""Dryade CLI Commands.

Provides command-line interface for database, cache, health, and admin operations.
Target: ~200 LOC
"""

import sys

import click

from .build_plugins import build_plugins, dev_push
from .create_plugin import create_plugin
from .validate_plugin import validate_plugin


@click.group()
@click.version_option(version="1.0.0", prog_name="dryade")
def main():
    """Dryade - AI Orchestration CLI."""
    pass

# Register plugin developer commands
main.add_command(validate_plugin)
main.add_command(create_plugin)

# Plugin build commands
main.add_command(build_plugins)
main.add_command(dev_push)

# =============================================================================
# Database Commands
# =============================================================================

@main.group()
def db():
    """Database management commands."""
    pass

def _import_all_models():
    """Import all models to ensure they're registered with Base.metadata.

    This must be called before init_db() to create all tables.
    """
    import importlib
    from pathlib import Path

    # Core models (26 tables) - imported via __init__ which now imports all
    import core.database  # noqa: F401

    # Dynamically discover and import plugin models
    plugins_dir = Path(__file__).resolve().parent.parent.parent / "plugins"
    if plugins_dir.is_dir():
        for child in sorted(plugins_dir.iterdir()):
            if child.is_dir() and (child / "models.py").exists():
                module_name = f"plugins.{child.name}.models"
                try:
                    importlib.import_module(module_name)
                    click.echo(f"  - {child.name} plugin models loaded")
                except ImportError:
                    pass

@db.command()
def migrate():
    """Run database migrations (create tables)."""
    from core.database.session import init_db

    click.echo("Importing all models...")
    _import_all_models()

    click.echo("Running migrations...")
    created = init_db()

    if created:
        click.echo(f"Created {len(created)} tables:")
        for table in sorted(created):
            click.echo(f"  - {table}")
    else:
        click.echo("All tables already exist.")
    click.echo("Migrations complete.")

@db.command()
@click.confirmation_option(prompt="Are you sure you want to reset the database?")
def reset():
    """Reset database (drop and recreate all tables)."""
    from core.database.session import drop_db, init_db

    click.echo("Importing all models...")
    _import_all_models()

    click.echo("Dropping all tables...")
    drop_db()
    click.echo("Recreating tables...")
    init_db()
    click.echo("Database reset complete.")

@db.command()
def upgrade():
    """Upgrade database schema (add missing columns)."""
    from sqlalchemy import inspect, text

    from core.database.session import get_engine

    _import_all_models()

    engine = get_engine()
    inspector = inspect(engine)

    upgrades_applied = []

    # Define schema upgrades: (table, column, sql)
    schema_upgrades = [
        # conversations.project_id - added for project organization feature
        (
            "conversations",
            "project_id",
            "ALTER TABLE conversations ADD COLUMN project_id VARCHAR(64) REFERENCES projects(id) ON DELETE SET NULL",
        ),
        # Add index for project_id after column exists
        (
            "conversations",
            "ix_conversations_project_id",
            "CREATE INDEX IF NOT EXISTS ix_conversations_project_id ON conversations(project_id)",
        ),
        # model_configs.asr_endpoint - added for configurable ASR endpoint per user
        (
            "model_configs",
            "asr_endpoint",
            "ALTER TABLE model_configs ADD COLUMN asr_endpoint VARCHAR(512)",
        ),
    ]

    with engine.connect() as conn:
        for table, item, sql in schema_upgrades:
            # Check if table exists
            if table not in inspector.get_table_names():
                click.echo(f"Skipping {table}.{item} - table doesn't exist")
                continue

            # Check if column/index already exists
            columns = [col["name"] for col in inspector.get_columns(table)]
            indexes = [idx["name"] for idx in inspector.get_indexes(table)]

            if item in columns or item in indexes:
                click.echo(f"Skipping {table}.{item} - already exists")
                continue

            try:
                click.echo(f"Adding {table}.{item}...")
                conn.execute(text(sql))
                conn.commit()
                upgrades_applied.append(f"{table}.{item}")
            except Exception as e:
                click.echo(f"Error adding {table}.{item}: {e}")

    if upgrades_applied:
        click.echo(f"\nApplied {len(upgrades_applied)} upgrades:")
        for upgrade in upgrades_applied:
            click.echo(f"  - {upgrade}")
    else:
        click.echo("No upgrades needed - schema is up to date.")

@db.command()
def status():
    """Show database status and table information."""
    from sqlalchemy import inspect

    from core.database.session import get_engine

    _import_all_models()

    engine = get_engine()
    inspector = inspect(engine)

    existing_tables = inspector.get_table_names()
    click.echo(f"\nDatabase: {engine.url}")
    click.echo(f"Tables found: {len(existing_tables)}")

    if existing_tables:
        click.echo("\nExisting tables:")
        for table in sorted(existing_tables):
            click.echo(f"  - {table}")

    # Check for missing tables
    from core.database.models import Base

    expected_tables = set(Base.metadata.tables.keys())
    missing_tables = expected_tables - set(existing_tables)

    if missing_tables:
        click.echo(f"\nMissing tables ({len(missing_tables)}):")
        for table in sorted(missing_tables):
            click.echo(f"  - {table}")
        click.echo("\nRun 'dryade db migrate' to create missing tables.")

# =============================================================================
# Cache Commands
# =============================================================================

@main.group()
def cache():
    """Cache management commands."""
    pass

@cache.command()
def clear():
    """Clear all cache entries."""
    from core.database.models import CacheEntry
    from core.database.session import get_session

    with get_session() as session:
        count = session.query(CacheEntry).delete()
        session.commit()
        click.echo(f"Cleared {count} cache entries.")

@cache.command()
def stats():
    """Show cache statistics."""
    from sqlalchemy import func

    from core.database.models import CacheEntry
    from core.database.session import get_session

    with get_session() as session:
        total = session.query(CacheEntry).count()
        total_hits = session.query(func.sum(CacheEntry.hit_count)).scalar() or 0
        click.echo(f"Cache entries: {total}")
        click.echo(f"Total hits: {total_hits}")

# =============================================================================
# Health Commands
# =============================================================================

@main.command()
@click.option("--deep", is_flag=True, help="Run deep health checks")
def health(deep):
    """Check system health."""
    import httpx

    from core.config import get_settings

    settings = get_settings()
    base_url = f"http://{settings.host}:{settings.port}"

    try:
        response = httpx.get(f"{base_url}/health", timeout=5.0)
        if response.status_code == 200:
            click.echo("API: HEALTHY")
        else:
            click.echo(f"API: UNHEALTHY ({response.status_code})")
            sys.exit(1)
    except Exception as e:
        click.echo(f"API: UNREACHABLE ({e})")
        sys.exit(1)

    if deep:
        # Check Redis
        try:
            import redis

            r = redis.from_url(settings.redis_url)
            r.ping()
            click.echo("Redis: HEALTHY")
        except Exception as e:
            click.echo(f"Redis: UNHEALTHY ({e})")

        # Check database
        try:
            from core.database.session import get_engine

            engine = get_engine()
            engine.connect()
            click.echo("Database: HEALTHY")
        except Exception as e:
            click.echo(f"Database: UNHEALTHY ({e})")

# =============================================================================
# Config Commands
# =============================================================================

@main.group()
def config():
    """Configuration commands."""
    pass

@config.command()
def show_config():
    """Show current configuration."""
    from core.config import get_settings

    settings = get_settings()
    for key, value in settings.model_dump().items():
        # Mask sensitive values
        if "secret" in key.lower() or "key" in key.lower() or "password" in key.lower():
            value = "***" if value else None
        click.echo(f"{key}: {value}")

@config.command()
def validate():
    """Validate configuration."""
    try:
        from core.config import get_settings

        settings = get_settings()
        click.echo("Configuration valid.")

        # Warnings
        if not settings.jwt_secret:
            click.echo("WARNING: JWT_SECRET not set")
        if settings.debug and settings.env == "production":
            click.echo("WARNING: Debug enabled in production")

    except Exception as e:
        click.echo(f"Configuration invalid: {e}")
        sys.exit(1)

# =============================================================================
# Trace Commands
# =============================================================================

@main.group()
def trace():
    """Trace management commands."""
    pass

@trace.command()
@click.option("--limit", default=20, help="Number of traces to show")
def list(limit):
    """List recent traces."""
    from core.observability.tracing import get_trace_sink

    sink = get_trace_sink()
    traces = sink.query(limit=limit)

    for t in traces:
        click.echo(
            f"[{t.get('timestamp', 'N/A')}] {t.get('type', 'N/A')}: {t.get('event', 'N/A')[:50]}"
        )

@trace.command()
@click.argument("trace_id")
def show_trace(trace_id):
    """Show trace details."""
    from core.observability.tracing import get_trace_sink

    sink = get_trace_sink()
    traces = sink.query(trace_id=trace_id)

    if not traces:
        click.echo(f"Trace {trace_id} not found.")
        sys.exit(1)

    for t in traces:
        click.echo(f"Type: {t.get('type')}")
        click.echo(f"Timestamp: {t.get('timestamp')}")
        click.echo(f"Event: {t.get('event')}")
        click.echo("---")

@trace.command()
@click.argument("output_file")
@click.option("--trace-id", help="Export specific trace")
def export(output_file, trace_id):
    """Export traces to JSON file."""
    import json

    from core.observability.tracing import get_trace_sink

    sink = get_trace_sink()
    traces = sink.query(trace_id=trace_id) if trace_id else sink.query(limit=1000)

    with open(output_file, "w") as f:
        json.dump(traces, f, indent=2, default=str)

    click.echo(f"Exported {len(traces)} traces to {output_file}")

if __name__ == "__main__":
    main()
