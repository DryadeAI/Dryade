"""Generic OpenAI-compatible provider connector implementation.

Supports any LLM provider that implements the OpenAI API specification
(e.g., DeepSeek, Qwen, Moonshot, xAI, Together AI, Groq, LiteLLM).
"""

import logging

import openai

from core.providers.connectors.base import ConnectionTestResult, ProviderConnector

logger = logging.getLogger(__name__)

class OpenAICompatibleConnector(ProviderConnector):
    """Connector for OpenAI-compatible API providers.

    Uses the OpenAI SDK with a configurable base_url to connect to any provider
    that implements the OpenAI API specification. Returns only real models
    from the API — no static fallback.
    """

    def __init__(self, default_base_url: str):
        """Initialize OpenAI-compatible connector.

        Args:
            default_base_url: The provider's default API base URL
                (e.g., "https://api.deepseek.com/v1")
        """
        self.default_base_url = default_base_url.rstrip("/")

    async def test_connection(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> ConnectionTestResult:
        """Test connection to an OpenAI-compatible provider.

        Args:
            api_key: API key for authentication
            base_url: Custom endpoint URL (overrides default)
            **kwargs: Provider-specific configuration

        Returns:
            ConnectionTestResult with success status and discovered models
        """
        if not api_key:
            return ConnectionTestResult(
                success=False,
                message="API key is required",
                error_code="missing_api_key",
            )

        try:
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
        """Discover available models from an OpenAI-compatible provider.

        Args:
            api_key: API key for authentication
            base_url: Custom endpoint URL (overrides default)
            **kwargs: Provider-specific configuration

        Returns:
            List of available model IDs, or empty list on failure.
        """
        if not api_key:
            return []

        effective_url = (base_url or self.default_base_url).rstrip("/")

        try:
            client = openai.AsyncOpenAI(
                api_key=api_key,
                base_url=effective_url,
            )

            response = await client.models.list()
            return [model.id for model in response.data]

        except Exception as e:
            logger.warning("Failed to list models from %s: %s", effective_url, str(e))
            return []
