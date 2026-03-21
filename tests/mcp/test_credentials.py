"""Tests for MCP credential management.

Tests the CredentialManager class including keyring storage,
resolution chain (user -> global -> env), and error handling.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from core.mcp.credentials import CredentialManager, get_credential_manager

class TestCredentialManager:
    """Test suite for CredentialManager."""

    @pytest.fixture
    def mock_keyring(self):
        """Fixture to mock keyring for testing."""
        with patch.dict("sys.modules", {"keyring": MagicMock(), "keyring.errors": MagicMock()}):
            import sys

            mock = sys.modules["keyring"]
            mock.get_keyring.return_value = MagicMock()
            mock.errors = sys.modules["keyring.errors"]
            mock.errors.PasswordDeleteError = type("PasswordDeleteError", (Exception,), {})
            yield mock

    @pytest.fixture
    def manager_with_mock(self, mock_keyring):
        """Create a CredentialManager with mocked keyring."""
        # Reset singleton
        import core.mcp.credentials

        core.mcp.credentials._manager = None

        manager = CredentialManager.__new__(CredentialManager)
        manager._keyring_available = True
        return manager, mock_keyring

    def test_get_credentials_user_specific(self, manager_with_mock):
        """Test getting user-specific credentials."""
        manager, mock_keyring = manager_with_mock
        mock_keyring.get_password.return_value = json.dumps({"token": "user-token-123"})

        creds = manager.get_credentials("github", user_id="user123")

        assert creds is not None
        assert creds["token"] == "user-token-123"
        mock_keyring.get_password.assert_called_with("dryade-mcp-github:user123", "credentials")

    def test_get_credentials_global_fallback(self, manager_with_mock):
        """Test falling back to global credentials when user-specific not found."""
        manager, mock_keyring = manager_with_mock
        # First call (user-specific) returns None, second (global) returns data
        mock_keyring.get_password.side_effect = [
            None,  # user-specific
            json.dumps({"token": "global-token"}),  # global
        ]

        creds = manager.get_credentials("github", user_id="user123")

        assert creds is not None
        assert creds["token"] == "global-token"
        assert mock_keyring.get_password.call_count == 2

    def test_get_credentials_env_fallback_api_key(self, manager_with_mock):
        """Test falling back to environment variable for API key."""
        manager, mock_keyring = manager_with_mock
        mock_keyring.get_password.return_value = None

        with patch.dict(os.environ, {"GITHUB_API_KEY": "env-api-key-123"}, clear=False):
            creds = manager.get_credentials("github")

        assert creds is not None
        assert creds["api_key"] == "env-api-key-123"

    def test_get_credentials_env_fallback_token(self, manager_with_mock):
        """Test falling back to environment variable for token."""
        manager, mock_keyring = manager_with_mock
        mock_keyring.get_password.return_value = None

        # Clear any conflicting env vars and set only the token
        env_copy = {k: v for k, v in os.environ.items() if not k.startswith("CONTEXT7")}
        env_copy["CONTEXT7_TOKEN"] = "env-token-456"
        with patch.dict(os.environ, env_copy, clear=True):
            creds = manager.get_credentials("context7")

        assert creds is not None
        assert creds["token"] == "env-token-456"

    def test_get_credentials_none_when_missing(self, manager_with_mock):
        """Test returning None when no credentials found anywhere."""
        manager, mock_keyring = manager_with_mock
        mock_keyring.get_password.return_value = None

        # Clear env vars that could interfere
        env_copy = {k: v for k, v in os.environ.items() if not k.startswith("NONEXISTENT")}
        with patch.dict(os.environ, env_copy, clear=True):
            creds = manager.get_credentials("nonexistent")

        assert creds is None

    def test_set_and_get_credentials(self, manager_with_mock):
        """Test storing and retrieving credentials."""
        manager, mock_keyring = manager_with_mock
        stored_data = {}

        def mock_set(service, key, value):
            stored_data[f"{service}:{key}"] = value

        def mock_get(service, key):
            return stored_data.get(f"{service}:{key}")

        mock_keyring.set_password.side_effect = mock_set
        mock_keyring.get_password.side_effect = mock_get

        # Set credentials
        manager.set_credentials("github", {"token": "test-token"})

        # Get credentials
        creds = manager.get_credentials("github")

        assert creds is not None
        assert creds["token"] == "test-token"

    def test_set_credentials_with_user_id(self, manager_with_mock):
        """Test storing user-specific credentials."""
        manager, mock_keyring = manager_with_mock
        manager.set_credentials("github", {"token": "user-token"}, user_id="user456")

        mock_keyring.set_password.assert_called_once_with(
            "dryade-mcp-github:user456",
            "credentials",
            json.dumps({"token": "user-token"}),
        )

    def test_delete_credentials_success(self, manager_with_mock):
        """Test deleting credentials successfully."""
        manager, mock_keyring = manager_with_mock
        result = manager.delete_credentials("github")

        assert result is True
        mock_keyring.delete_password.assert_called_once_with("dryade-mcp-github", "credentials")

    def test_delete_credentials_not_found(self, manager_with_mock):
        """Test deleting credentials that don't exist."""
        manager, mock_keyring = manager_with_mock
        mock_keyring.delete_password.side_effect = mock_keyring.errors.PasswordDeleteError()

        result = manager.delete_credentials("nonexistent")

        assert result is False

    def test_needs_setup_true_when_missing(self, manager_with_mock):
        """Test needs_setup returns True when no credentials."""
        manager, mock_keyring = manager_with_mock
        mock_keyring.get_password.return_value = None

        # Clear env vars
        env_copy = {k: v for k, v in os.environ.items() if not k.startswith("GITHUB")}
        with patch.dict(os.environ, env_copy, clear=True):
            assert manager.needs_setup("github") is True

    def test_needs_setup_false_when_exists(self, manager_with_mock):
        """Test needs_setup returns False when credentials exist."""
        manager, mock_keyring = manager_with_mock
        mock_keyring.get_password.return_value = json.dumps({"token": "exists"})

        assert manager.needs_setup("github") is False

    def test_credential_resolution_chain(self, manager_with_mock):
        """Test full credential resolution chain: user -> global -> env."""
        manager, mock_keyring = manager_with_mock
        # Set up mock to return different values for different calls
        call_count = [0]

        def mock_get(service, key):
            call_count[0] += 1
            if call_count[0] == 1:
                return None  # user-specific not found
            if call_count[0] == 2:
                return None  # global not found
            return None

        mock_keyring.get_password.side_effect = mock_get

        # Clear env vars and set only our test var
        env_copy = {k: v for k, v in os.environ.items() if not k.startswith("TESTSERVICE")}
        env_copy["TESTSERVICE_API_KEY"] = "env-key"
        with patch.dict(os.environ, env_copy, clear=True):
            creds = manager.get_credentials("testservice", user_id="testuser")

        assert creds is not None
        assert creds["api_key"] == "env-key"
        # Should have tried user-specific (1) and global (2)
        assert call_count[0] == 2

    def test_set_credentials_no_keyring_raises(self):
        """Test that set_credentials raises when no keyring available."""
        manager = CredentialManager.__new__(CredentialManager)
        manager._keyring_available = False

        with pytest.raises(RuntimeError, match="No keyring backend available"):
            manager.set_credentials("github", {"token": "test"})

class TestGetCredentialManager:
    """Test suite for get_credential_manager singleton."""

    def test_singleton_returns_same_instance(self):
        """Test that get_credential_manager returns singleton."""
        # Reset singleton
        import core.mcp.credentials

        core.mcp.credentials._manager = None

        with patch.object(CredentialManager, "_ensure_backend", return_value=True):
            manager1 = get_credential_manager()
            manager2 = get_credential_manager()

        assert manager1 is manager2

    def test_get_credential_manager_creates_instance(self):
        """Test that get_credential_manager creates a valid instance."""
        import core.mcp.credentials

        core.mcp.credentials._manager = None

        with patch.object(CredentialManager, "_ensure_backend", return_value=True):
            manager = get_credential_manager()

        assert isinstance(manager, CredentialManager)

class TestCredentialManagerBackend:
    """Test suite for keyring backend handling."""

    def test_ensure_backend_success(self):
        """Test successful backend initialization."""
        with patch.dict("sys.modules", {"keyring": MagicMock()}):
            import sys

            mock_keyring = sys.modules["keyring"]
            mock_keyring.get_keyring.return_value = MagicMock()

            manager = CredentialManager.__new__(CredentialManager)
            result = manager._ensure_backend()

            assert result is True

    def test_no_backend_uses_env_only(self):
        """Test graceful degradation when no keyring backend available."""
        # Create manager that will fail backend setup
        manager = CredentialManager.__new__(CredentialManager)
        manager._keyring_available = False

        # Should still work with env vars
        env_copy = {k: v for k, v in os.environ.items() if not k.startswith("GITHUB")}
        env_copy["GITHUB_TOKEN"] = "env-only"
        with patch.dict(os.environ, env_copy, clear=True):
            creds = manager.get_credentials("github")

        assert creds is not None
        assert creds["token"] == "env-only"

    def test_service_name_with_user_id(self):
        """Test service name generation with user ID."""
        manager = CredentialManager.__new__(CredentialManager)
        manager._keyring_available = True

        service_name = manager._get_service_name("github", user_id="user123")
        assert service_name == "dryade-mcp-github:user123"

    def test_service_name_without_user_id(self):
        """Test service name generation without user ID."""
        manager = CredentialManager.__new__(CredentialManager)
        manager._keyring_available = True

        service_name = manager._get_service_name("github")
        assert service_name == "dryade-mcp-github"

    def test_env_var_with_hyphenated_service(self):
        """Test env var lookup with hyphenated service name."""
        manager = CredentialManager.__new__(CredentialManager)
        manager._keyring_available = False

        # Test that hyphens are converted to underscores
        env_copy = {k: v for k, v in os.environ.items() if not k.startswith("MY_SERVICE")}
        env_copy["MY_SERVICE_API_KEY"] = "hyphen-test"
        with patch.dict(os.environ, env_copy, clear=True):
            creds = manager.get_credentials("my-service")

        assert creds is not None
        assert creds["api_key"] == "hyphen-test"
