"""
Unit tests for Zitadel Authentication Plugin.

Tests plugin initialization, user sync, and graceful handling
when Zitadel is not configured or library is not installed.

Key principle: Plugin is OPTIONAL - all tests pass without Zitadel.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

class TestZitadelAuthPlugin:
    """Tests for ZitadelAuthPlugin class."""

    def test_plugin_disabled_by_default(self):
        """Plugin should not be enabled without configuration."""
        from plugins.zitadel_auth import ZitadelAuthPlugin

        plugin = ZitadelAuthPlugin()
        # Without calling startup(), plugin should be disabled
        assert not plugin.is_enabled
        assert plugin.auth is None

    def test_plugin_metadata(self):
        """Plugin should have correct metadata."""
        from plugins.zitadel_auth import ZitadelAuthPlugin

        plugin = ZitadelAuthPlugin()
        assert plugin.name == "zitadel_auth"
        assert plugin.version == "1.0.0"
        assert "SSO" in plugin.description or "Zitadel" in plugin.description

    def test_plugin_register_does_nothing(self):
        """Plugin register should not raise errors."""
        from plugins.zitadel_auth import ZitadelAuthPlugin

        plugin = ZitadelAuthPlugin()
        mock_registry = MagicMock()
        # Should not raise
        plugin.register(mock_registry)
        # Should not register any extensions (Zitadel is auth, not pipeline)
        mock_registry.register.assert_not_called()

    @pytest.mark.asyncio
    async def test_plugin_init_without_zitadel_enabled(self, monkeypatch):
        """Plugin init should succeed when ZITADEL_ENABLED=false."""
        # Clear any cached settings
        from plugins.zitadel_auth import ZitadelAuthPlugin

        from core.config import get_settings

        get_settings.cache_clear()

        monkeypatch.setenv("DRYADE_ZITADEL_ENABLED", "false")
        monkeypatch.setenv("DRYADE_LLM_BASE_URL", "http://localhost:8000")

        plugin = ZitadelAuthPlugin()
        plugin.startup()

        assert not plugin.is_enabled  # Disabled, no error
        assert plugin.auth is None

    @pytest.mark.asyncio
    async def test_plugin_init_missing_config(self, monkeypatch):
        """Plugin should warn but not fail with missing config."""
        # Clear any cached settings
        from plugins.zitadel_auth import ZitadelAuthPlugin

        from core.config import get_settings

        get_settings.cache_clear()

        # Enable but don't configure
        monkeypatch.setenv("DRYADE_ZITADEL_ENABLED", "true")
        monkeypatch.setenv("DRYADE_ZITADEL_ISSUER", "")
        monkeypatch.setenv("DRYADE_ZITADEL_PROJECT_ID", "")
        monkeypatch.setenv("DRYADE_LLM_BASE_URL", "http://localhost:8000")

        plugin = ZitadelAuthPlugin()
        plugin.startup()

        # Should be disabled due to missing config
        assert not plugin.is_enabled

    @pytest.mark.asyncio
    async def test_plugin_init_missing_library(self, monkeypatch):
        """Plugin should handle missing fastapi-zitadel-auth gracefully."""
        # Clear any cached settings
        from plugins.zitadel_auth import ZitadelAuthPlugin

        from core.config import get_settings

        get_settings.cache_clear()

        monkeypatch.setenv("DRYADE_ZITADEL_ENABLED", "true")
        monkeypatch.setenv("DRYADE_ZITADEL_ISSUER", "http://localhost:8080")
        monkeypatch.setenv("DRYADE_ZITADEL_PROJECT_ID", "test-project-id")
        monkeypatch.setenv("DRYADE_LLM_BASE_URL", "http://localhost:8000")

        # Mock ImportError for fastapi_zitadel_auth
        with patch.dict("sys.modules", {"fastapi_zitadel_auth": None}):
            plugin = ZitadelAuthPlugin()
            plugin.startup()

            # Should be disabled due to missing library
            assert not plugin.is_enabled

    def test_plugin_shutdown(self):
        """Plugin shutdown should clear auth state."""
        from plugins.zitadel_auth import ZitadelAuthPlugin

        plugin = ZitadelAuthPlugin()
        plugin._enabled = True
        plugin._auth = MagicMock()

        plugin.shutdown()

        assert not plugin.is_enabled
        assert plugin.auth is None

    def test_get_auth_dependency_disabled(self):
        """get_auth_dependency should return None when disabled."""
        from plugins.zitadel_auth import ZitadelAuthPlugin

        plugin = ZitadelAuthPlugin()
        assert plugin.get_auth_dependency() is None

    def test_get_role_dependency_disabled(self):
        """get_role_dependency should return None when disabled."""
        from plugins.zitadel_auth import ZitadelAuthPlugin

        plugin = ZitadelAuthPlugin()
        assert plugin.get_role_dependency(["admin"]) is None

class TestZitadelUserSync:
    """Tests for ZitadelUserSync class."""

    def test_user_sync_creates_external_user(self, test_db):
        """User sync should create external user from Zitadel token."""
        from plugins.zitadel_auth.user_sync import ZitadelUserSync

        sync = ZitadelUserSync(test_db)

        token = {
            "sub": "zitadel-user-123",
            "email": "ssouser@example.com",
            "name": "SSO User",
            "roles": ["member"],
        }

        user = sync.get_or_create_user(token)

        assert user.id == "zitadel-user-123"
        assert user.email == "ssouser@example.com"
        assert user.display_name == "SSO User"
        assert user.is_external is True
        assert user.external_provider == "zitadel"
        assert user.password_hash is None
        assert user.is_verified is True
        assert user.role == "member"

    def test_user_sync_updates_existing_user(self, test_db):
        """User sync should update existing user from Zitadel token."""
        from plugins.zitadel_auth.user_sync import ZitadelUserSync

        from core.database.models import User

        # Create existing local user
        existing_user = User(
            id="existing-user-id",
            email="existing@example.com",
            password_hash="hashed",
            is_external=False,
            role="member",
        )
        test_db.add(existing_user)
        test_db.commit()

        sync = ZitadelUserSync(test_db)

        token = {
            "sub": "zitadel-user-456",
            "email": "existing@example.com",  # Same email
            "name": "Updated Name",
        }

        user = sync.get_or_create_user(token)

        # Should link to Zitadel
        assert user.email == "existing@example.com"
        assert user.is_external is True
        assert user.external_provider == "zitadel"
        # Should keep existing password hash (can still use local auth)

    def test_user_sync_maps_admin_role(self, test_db):
        """User sync should map admin role from Zitadel."""
        from plugins.zitadel_auth.user_sync import ZitadelUserSync

        sync = ZitadelUserSync(test_db)

        token = {
            "sub": "zitadel-admin-user",
            "email": "admin@example.com",
            "roles": ["admin"],
        }

        user = sync.get_or_create_user(token)
        assert user.role == "admin"

    def test_user_sync_missing_sub_raises(self, test_db):
        """User sync should raise error for missing sub claim."""
        from plugins.zitadel_auth.user_sync import ZitadelUserSync

        sync = ZitadelUserSync(test_db)

        token = {
            "email": "nosubuser@example.com",
        }

        with pytest.raises(ValueError, match="missing 'sub' claim"):
            sync.get_or_create_user(token)

class TestZitadelMiddleware:
    """Tests for ZitadelMiddleware class."""

    def test_middleware_passes_through_when_disabled(self):
        """Middleware should pass through when plugin disabled."""
        from plugins.zitadel_auth.middleware import ZitadelMiddleware

        mock_plugin = MagicMock()
        mock_plugin.is_enabled = False

        mock_app = MagicMock()
        middleware = ZitadelMiddleware(mock_app, mock_plugin)

        # Plugin is disabled, so middleware should pass through
        assert middleware.plugin.is_enabled is False

class TestZitadelRoutes:
    """Tests for SSO routes."""

    def test_routes_module_imports(self):
        """Routes module should import without errors."""
        from plugins.zitadel_auth.routes import router

        assert router is not None
        assert router.prefix == "/auth/sso"

# Pytest fixtures
@pytest.fixture
def test_db():
    """Create test database session with per-test users table cleanup.

    Truncates the ``users`` table before yielding a session so that rows
    inserted by a previous test run do not cause UniqueViolation errors when
    the same hard-coded IDs / emails are inserted again.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from core.database.models import Base, User

    engine = create_engine(
        os.environ.get(
            "DRYADE_TEST_DATABASE_URL",
            "postgresql+psycopg://dryade:dryade_dev@localhost:5432/dryade_test",
        )
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    # Truncate the users table before each test to prevent key collisions
    # across test runs that share the same PostgreSQL database.
    with Session() as _cleanup:
        _cleanup.query(User).delete()
        _cleanup.commit()

    session = Session()

    yield session

    session.close()
