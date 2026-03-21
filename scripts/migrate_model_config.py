#!/usr/bin/env python
"""Migration script for model configuration tables.

Creates ModelConfig and ProviderApiKey tables using SQLAlchemy metadata.
Safe to run multiple times - create_all() is idempotent.

Usage:
    python scripts/migrate_model_config.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database.models import Base, ModelConfig, ProviderApiKey
from core.database.session import get_engine
from core.logs import get_logger

logger = get_logger(__name__)

def migrate():
    """Create model configuration tables."""
    logger.info("Creating model configuration tables...")

    engine = get_engine()

    # Create only the new tables (idempotent - won't recreate existing)
    Base.metadata.create_all(bind=engine, tables=[ModelConfig.__table__, ProviderApiKey.__table__])

    logger.info("Migration complete.")

    # Verify tables exist
    from sqlalchemy import inspect

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if "model_configs" in tables:
        logger.info("  - model_configs table: OK")
    else:
        logger.error("  - model_configs table: MISSING")
        return False

    if "provider_api_keys" in tables:
        logger.info("  - provider_api_keys table: OK")
    else:
        logger.error("  - provider_api_keys table: MISSING")
        return False

    return True

if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
