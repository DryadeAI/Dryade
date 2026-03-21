"""Tests for database concurrency fixes (C-1 from Phase 102 audit).

Tests cover:
- PostgreSQL pool configuration

Note: Schema migration serialization is now handled by Alembic (Phase 120).
SQLite-specific WAL/busy_timeout tests removed — session.py is PostgreSQL-only now.
"""

from unittest.mock import MagicMock, patch

import pytest

@pytest.fixture(autouse=True)
def _clear_engine_cache():
    """Clear the lru_cache on get_engine before each test."""
    from core.database.session import get_engine

    get_engine.cache_clear()
    yield
    get_engine.cache_clear()

class TestPoolConfiguration:
    """Test connection pool configuration (C-1)."""

    def test_postgresql_pool_config(self):
        """PostgreSQL engines should have pool_size, max_overflow, pool_timeout, pool_pre_ping."""
        captured_kwargs = {}

        def mock_create_engine(url, **kwargs):
            captured_kwargs.update(kwargs)
            mock_engine = MagicMock()
            return mock_engine

        with (
            patch("core.database.session.create_engine", side_effect=mock_create_engine),
            patch("core.database.migrate.run_migrations"),
            patch("core.database.rls.register_rls_events"),
            patch("core.database.session.event"),
        ):
            from core.database.session import get_engine

            get_engine("postgresql://user:pass@localhost/db")

        assert captured_kwargs.get("pool_size") == 10
        assert captured_kwargs.get("max_overflow") == 20
        assert captured_kwargs.get("pool_timeout") == 30
        assert captured_kwargs.get("pool_pre_ping") is True
        assert captured_kwargs.get("pool_recycle") == 3600
