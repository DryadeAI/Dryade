"""Database session management for Dryade.

Target: ~50 LOC

Exception Handling Strategy:
- Catches specific SQLAlchemy exceptions for database operations
- Logs all errors with operation context before re-raising
- Ensures proper rollback on any error
- All exceptions propagate to caller for handling at API boundary

Database: PostgreSQL only. No SQLite code paths.
"""

from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.exc import (
    DatabaseError,  # General database errors
    DataError,  # Data type/value issues
    IntegrityError,  # Constraint violations (unique, foreign key, etc.)
    OperationalError,  # Database connection/operation issues
)
from sqlalchemy.orm import Session, sessionmaker

from core.config import get_settings
from core.database.models import Base
from core.logs import get_logger

logger = get_logger(__name__)

@lru_cache
def get_engine(database_url: str | None = None):
    """Get or create the PostgreSQL database engine.

    Args:
        database_url: Optional database URL override

    Returns:
        SQLAlchemy engine configured with connection pooling and SSL
    """
    settings = get_settings()
    url = database_url or settings.database_url

    # Append sslmode to URL if configured and not already present
    ssl_mode = settings.database_ssl_mode
    if ssl_mode and ssl_mode != "disable" and "sslmode=" not in url:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}sslmode={ssl_mode}"

    engine = create_engine(
        url,
        echo=settings.debug,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
        pool_pre_ping=True,
        pool_recycle=3600,
    )

    # Run Alembic migrations at startup (auto-stamps existing databases).
    try:
        from core.database.migrate import run_migrations

        run_migrations(engine=engine)
    except Exception as e:  # pragma: no cover - should never block startup
        logger.warning(
            f"Failed to apply migrations: {e}",
            extra={"error_type": type(e).__name__, "operation": "alembic_migration"},
        )

    # Register RLS session events (idempotent -- guarded by internal flag)
    from core.database.rls import register_rls_events

    register_rls_events()

    # Reset RLS context on connection reuse from pool to prevent leaking
    if "postgresql" in url:

        @event.listens_for(engine, "checkout")
        def _reset_rls_on_checkout(dbapi_conn, connection_record, connection_proxy):
            cursor = dbapi_conn.cursor()
            cursor.execute("RESET ALL")
            cursor.close()

    return engine

def get_session_factory(engine=None):
    """Get session factory."""
    if engine is None:
        engine = get_engine()
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Get a database session with automatic transaction management.

    Yields:
        SQLAlchemy session

    Usage:
        with get_session() as session:
            session.query(...)

    Raises:
        IntegrityError: For constraint violations (unique, foreign key)
        OperationalError: For database connection/operation issues
        DataError: For data type/value issues
        DatabaseError: For other database errors
    """
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except IntegrityError as e:
        session.rollback()
        logger.error(
            f"Database integrity error during commit: {e}",
            extra={"error_type": "IntegrityError", "operation": "session_commit"},
        )
        raise
    except OperationalError as e:
        session.rollback()
        logger.error(
            f"Database operational error during commit: {e}",
            extra={"error_type": "OperationalError", "operation": "session_commit"},
        )
        raise
    except DataError as e:
        session.rollback()
        logger.error(
            f"Database data error during commit: {e}",
            extra={"error_type": "DataError", "operation": "session_commit"},
        )
        raise
    except DatabaseError as e:
        session.rollback()
        logger.error(
            f"Database error during commit: {e}",
            extra={"error_type": "DatabaseError", "operation": "session_commit"},
        )
        raise
    except Exception as e:
        # Catch-all for non-database errors (e.g., application logic errors)
        session.rollback()
        logger.error(
            f"Unexpected error during database session: {e}",
            extra={"error_type": type(e).__name__, "operation": "session_commit"},
            exc_info=True,
        )
        raise
    finally:
        session.close()

def init_db(engine=None):
    """Initialize the database schema.

    Creates all tables if they don't exist. Only creates missing tables
    to avoid conflicts with existing indexes.

    Args:
        engine: Optional engine override

    Returns:
        List of created table names
    """
    from sqlalchemy import inspect

    if engine is None:
        engine = get_engine()

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    expected_tables = set(Base.metadata.tables.keys())

    missing_tables = expected_tables - existing_tables

    if not missing_tables:
        logger.info("All tables already exist, nothing to create")
        return []

    # Only create missing tables
    tables_to_create = [Base.metadata.tables[name] for name in missing_tables]

    logger.info(f"Creating {len(tables_to_create)} missing tables: {sorted(missing_tables)}")

    # Create only the missing tables
    Base.metadata.create_all(bind=engine, tables=tables_to_create, checkfirst=True)

    return list(missing_tables)

def drop_db(engine=None):
    """Drop all database tables.

    WARNING: This deletes all data!

    Args:
        engine: Optional engine override
    """
    if engine is None:
        engine = get_engine()
    Base.metadata.drop_all(bind=engine)
