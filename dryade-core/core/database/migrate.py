"""Alembic migration runner for application startup (PostgreSQL only).

Handles three scenarios:
1. Fresh database (no tables): run upgrade to create everything
2. Existing database (tables but no alembic_version): stamp + upgrade
3. Migrated database (has alembic_version): just upgrade
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from core.config import get_settings

logger = logging.getLogger(__name__)

def get_alembic_config() -> Config:
    """Get Alembic config pointing to core/alembic.ini."""
    ini_path = Path(__file__).parent.parent / "alembic.ini"
    if not ini_path.exists():
        raise FileNotFoundError(f"Alembic config not found at {ini_path}")
    cfg = Config(str(ini_path))
    # Override script_location to absolute path so it works regardless of cwd
    alembic_dir = Path(__file__).parent.parent / "alembic"
    cfg.set_main_option("script_location", str(alembic_dir))
    # Override URL from settings (same source as engine)
    settings = get_settings()
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    # Prevent env.py from calling fileConfig() which clobbers app logging
    cfg.attributes["skip_logging_config"] = True
    return cfg

def run_migrations(engine=None) -> None:
    """Run Alembic upgrade to head at startup.

    Automatically stamps existing databases that predate Alembic.
    Raises on failure -- migration errors must not be silently swallowed.
    """
    from core.database.session import get_engine as _get_engine

    if engine is None:
        engine = _get_engine()

    cfg = get_alembic_config()

    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())

    has_alembic = "alembic_version" in existing_tables
    has_data_tables = bool(existing_tables - {"alembic_version"})

    if has_data_tables and not has_alembic:
        # Scenario 2: existing DB without Alembic tracking
        logger.info(
            "Existing database detected without alembic_version. Stamping at head to adopt Alembic."
        )
        command.stamp(cfg, "head")

    # Scenarios 1 & 3: run upgrade to head
    command.upgrade(cfg, "head")
    logger.info("Database migrations applied successfully")

def stamp_current() -> None:
    """Stamp existing database as current (for first-time Alembic adoption)."""
    cfg = get_alembic_config()
    command.stamp(cfg, "head")
    logger.info("Database stamped at head")
