"""Base connector interface for provider connectivity testing."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class ConnectionTestResult:
    """Result of a connection test to a provider.

    Attributes:
        success: Whether the connection test succeeded
        message: Human-readable message describing the result
        models: List of available model IDs (if discovery succeeded)
        error_code: Optional error code for debugging (e.g., "auth_failed", "network_error")
    """

    success: bool
    message: str
    models: list[str] | None = None
    error_code: str | None = None

class ProviderConnector(ABC):
    """Abstract base class for provider connectors.

    Connectors handle connection testing and model discovery for specific providers.
    Each connector implements provider-specific authentication and API interaction logic.
    """

    @abstractmethod
    async def test_connection(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> ConnectionTestResult:
        """Test connection to the provider.

        Args:
            api_key: API key for authentication (None for local providers)
            base_url: Custom endpoint URL (overrides default)
            **kwargs: Provider-specific configuration (e.g., azure_deployment)

        Returns:
            ConnectionTestResult with success status and optional model list
        """
        pass

    @abstractmethod
    async def discover_models(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> list[str]:
        """Discover available models from the provider.

        Args:
            api_key: API key for authentication (None for local providers)
            base_url: Custom endpoint URL (overrides default)
            **kwargs: Provider-specific configuration

        Returns:
            List of available model IDs
        """
        pass
