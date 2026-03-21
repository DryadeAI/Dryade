"""MCP Server Credential Management.

Provides secure credential storage and retrieval for MCP servers
using the system keyring with fallbacks for headless environments.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

class CredentialManager:
    """Manages MCP server credentials with keyring storage.

    Resolution chain: user-specific -> global -> environment.
    Uses keyring for secure storage, falls back to cryptfile on headless.

    Attributes:
        SERVICE_PREFIX: Prefix for all Dryade MCP credential services.

    Example:
        >>> manager = CredentialManager()
        >>> manager.set_credentials("github", {"token": "ghp_..."})
        >>> creds = manager.get_credentials("github")
        >>> creds["token"]
        'ghp_...'
    """

    SERVICE_PREFIX = "dryade-mcp-"

    def __init__(self) -> None:
        """Initialize the credential manager and ensure backend is available."""
        self._keyring_available = self._ensure_backend()

    def _ensure_backend(self) -> bool:
        """Ensure keyring backend is available, configure fallback.

        Returns:
            True if a keyring backend is available, False otherwise.
        """
        try:
            import keyring

            # Test if backend works by getting the current keyring
            backend = keyring.get_keyring()
            logger.debug("Using keyring backend: %s", type(backend).__name__)
            return True
        except Exception as e:
            # Try to configure cryptfile fallback for headless
            try:
                import keyring
                from keyrings.cryptfile.cryptfile import CryptFileKeyring

                keyring.set_keyring(CryptFileKeyring())
                logger.info("Using CryptFileKeyring fallback for headless environment")
                return True
            except ImportError:
                logger.warning("No keyring backend available, using env vars only: %s", e)
                return False

    def _get_service_name(self, service: str, user_id: str | None = None) -> str:
        """Build the full service name for keyring storage.

        Args:
            service: The base service name (e.g., "github", "context7").
            user_id: Optional user ID for user-specific credentials.

        Returns:
            Full service name with prefix and optional user ID.
        """
        if user_id:
            return f"{self.SERVICE_PREFIX}{service}:{user_id}"
        return f"{self.SERVICE_PREFIX}{service}"

    def get_credentials(self, service: str, user_id: str | None = None) -> dict[str, Any] | None:
        """Get credentials for an MCP service.

        Resolution chain:
        1. User-specific credentials (if user_id provided)
        2. Global credentials (no user_id)
        3. Environment variables ({SERVICE}_API_KEY or {SERVICE}_TOKEN)

        Args:
            service: The service name (e.g., "github", "context7").
            user_id: Optional user ID for user-specific credentials.

        Returns:
            Credentials dictionary or None if not found.

        Example:
            >>> manager = CredentialManager()
            >>> creds = manager.get_credentials("github", user_id="user123")
            >>> if creds:
            ...     token = creds.get("token")
        """
        # Try keyring storage if available
        if self._keyring_available:
            import keyring

            # Try user-specific first
            if user_id:
                service_name = self._get_service_name(service, user_id)
                try:
                    stored = keyring.get_password(service_name, "credentials")
                    if stored:
                        return json.loads(stored)
                except Exception as e:
                    logger.debug("Failed to get user-specific credentials: %s", e)

            # Try global
            service_name = self._get_service_name(service)
            try:
                stored = keyring.get_password(service_name, "credentials")
                if stored:
                    return json.loads(stored)
            except Exception as e:
                logger.debug("Failed to get global credentials: %s", e)

        # Fall back to environment variables
        return self._get_credentials_from_env(service)

    def _get_credentials_from_env(self, service: str) -> dict[str, Any] | None:
        """Get credentials from environment variables.

        Checks for {SERVICE}_API_KEY and {SERVICE}_TOKEN.

        Args:
            service: The service name.

        Returns:
            Credentials dictionary or None if not found.
        """
        env_prefix = service.upper().replace("-", "_")

        # Check for API key
        api_key = os.environ.get(f"{env_prefix}_API_KEY")
        if api_key:
            return {"api_key": api_key}

        # Check for token
        token = os.environ.get(f"{env_prefix}_TOKEN")
        if token:
            return {"token": token}

        return None

    def set_credentials(
        self,
        service: str,
        credentials: dict[str, Any],
        user_id: str | None = None,
    ) -> None:
        """Store credentials for an MCP service.

        Args:
            service: The service name (e.g., "github", "context7").
            credentials: Dictionary of credentials to store.
            user_id: Optional user ID for user-specific credentials.

        Raises:
            RuntimeError: If no keyring backend is available.

        Example:
            >>> manager = CredentialManager()
            >>> manager.set_credentials("github", {"token": "ghp_..."})
        """
        if not self._keyring_available:
            raise RuntimeError(
                "No keyring backend available. "
                "Install keyring or keyrings.cryptfile for credential storage."
            )

        import keyring

        service_name = self._get_service_name(service, user_id)
        try:
            keyring.set_password(service_name, "credentials", json.dumps(credentials))
            logger.debug("Stored credentials for service: %s", service_name)
        except Exception as e:
            logger.error("Failed to store credentials for %s: %s", service_name, e)
            raise

    def delete_credentials(self, service: str, user_id: str | None = None) -> bool:
        """Delete credentials for an MCP service.

        Args:
            service: The service name (e.g., "github", "context7").
            user_id: Optional user ID for user-specific credentials.

        Returns:
            True if credentials were deleted, False if not found.

        Example:
            >>> manager = CredentialManager()
            >>> deleted = manager.delete_credentials("github")
        """
        if not self._keyring_available:
            return False

        import keyring

        service_name = self._get_service_name(service, user_id)
        try:
            keyring.delete_password(service_name, "credentials")
            logger.debug("Deleted credentials for service: %s", service_name)
            return True
        except keyring.errors.PasswordDeleteError:
            logger.debug("No credentials found to delete for: %s", service_name)
            return False
        except Exception as e:
            logger.warning("Failed to delete credentials for %s: %s", service_name, e)
            return False

    def needs_setup(self, service: str, user_id: str | None = None) -> bool:
        """Check if credentials need to be set up for a service.

        Args:
            service: The service name (e.g., "github", "context7").
            user_id: Optional user ID for user-specific credentials.

        Returns:
            True if no credentials found, False if credentials exist.

        Example:
            >>> manager = CredentialManager()
            >>> if manager.needs_setup("github"):
            ...     print("Please configure GitHub credentials")
        """
        return self.get_credentials(service, user_id) is None

# Singleton instance
_manager: CredentialManager | None = None

def get_credential_manager() -> CredentialManager:
    """Get the singleton CredentialManager instance.

    Returns:
        The global CredentialManager instance.

    Example:
        >>> manager = get_credential_manager()
        >>> creds = manager.get_credentials("github")
    """
    global _manager
    if _manager is None:
        _manager = CredentialManager()
    return _manager
