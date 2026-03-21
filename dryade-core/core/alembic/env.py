"""Alembic migration environment for Dryade Core.

Sync engine only -- core does not use async SQLAlchemy.
Reads database URL from settings.database_url at runtime.
PostgreSQL only.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from core.config import get_settings
from core.database.models import Base

# Import Loop Engine models so their tables are registered in Base.metadata
from core.loops.models import LoopExecution, ScheduledLoop  # noqa: F401

# Alembic Config object (access to alembic.ini values)
config = context.config

# Only configure logging from alembic.ini when running Alembic CLI directly.
# When called programmatically (command.upgrade from migrate.py), the app
# has already configured logging and fileConfig would clobber it.
if config.config_file_name is not None and not config.attributes.get("skip_logging_config"):
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support
target_metadata = Base.metadata

# Override sqlalchemy.url from application settings
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine.
    Calls to context.execute() emit the given string to the script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        # render_as_batch kept for backward compat with pre-PG migrations; no-op on PostgreSQL
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an Engine and associates a connection with the context.
    Uses NullPool to avoid connection leaks during migration.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            # render_as_batch kept for backward compat with pre-PG migrations; no-op on PostgreSQL
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
