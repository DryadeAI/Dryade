"""OpenAI and Azure OpenAI connector implementation."""

import openai

from core.providers.connectors.base import ConnectionTestResult, ProviderConnector


class OpenAIConnector(ProviderConnector):
    """Connector for OpenAI and Azure OpenAI providers.

    Supports both standard OpenAI API and Azure OpenAI deployments via is_azure flag.
    Uses the OpenAI SDK's models.list() endpoint for connection testing and model discovery.
    """

    def __init__(self, is_azure: bool = False):
        """Initialize OpenAI connector.

        Args:
            is_azure: If True, configure for Azure OpenAI; if False, for standard OpenAI
        """
        self.is_azure = is_azure

    async def test_connection(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> ConnectionTestResult:
        """Test connection to OpenAI or Azure OpenAI.

        Args:
            api_key: API key for authentication
            base_url: Custom endpoint URL (required for Azure)
            **kwargs: Azure-specific config (azure_deployment, api_version)

        Returns:
            ConnectionTestResult with success status and discovered models
        """
        if not api_key:
            return ConnectionTestResult(
                success=False,
                message="API key is required",
                error_code="missing_api_key",
            )

        if self.is_azure and not base_url:
            return ConnectionTestResult(
                success=False,
                message="Base URL is required for Azure OpenAI",
                error_code="missing_base_url",
            )

        try:
            # Attempt to discover models as connection test
            models = await self.discover_models(api_key, base_url, **kwargs)

            return ConnectionTestResult(
                success=True,
                message=f"Connected successfully. Found {len(models)} model(s).",
                models=models,
            )
        except openai.AuthenticationError:
            return ConnectionTestResult(
                success=False,
                message="Authentication failed. Check your API key.",
                error_code="auth_failed",
            )
        except openai.APIConnectionError as e:
            return ConnectionTestResult(
                success=False,
                message=f"Connection failed: {str(e)}",
                error_code="network_error",
            )
        except Exception as e:
            return ConnectionTestResult(
                success=False,
                message=f"Unexpected error: {str(e)}",
                error_code="unknown_error",
            )

    async def discover_models(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> list[str]:
        """Discover available models from OpenAI or Azure OpenAI.

        Args:
            api_key: API key for authentication
            base_url: Custom endpoint URL (required for Azure)
            **kwargs: Azure-specific config (api_version)

        Returns:
            List of available model IDs

        Raises:
            openai.AuthenticationError: If the API key is invalid
            openai.APIConnectionError: If the endpoint is unreachable
        """
        if not api_key:
            return []

        try:
            # Configure client based on provider type
            if self.is_azure:
                api_version = kwargs.get("api_version", "2024-02-01")
                client = openai.AsyncAzureOpenAI(
                    api_key=api_key,
                    azure_endpoint=base_url or "",
                    api_version=api_version,
                )
            else:
                client = openai.AsyncOpenAI(
                    api_key=api_key,
                    base_url=base_url,
                )

            # List available models
            response = await client.models.list()
            return [model.id for model in response.data]

        except (openai.AuthenticationError, openai.APIConnectionError):
            # Re-raise auth and connection errors so test_connection can handle them
            raise
        except Exception:
            return []
