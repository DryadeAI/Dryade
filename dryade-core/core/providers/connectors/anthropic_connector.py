"""Anthropic connector implementation."""

import logging

import anthropic

from core.providers.connectors.base import ConnectionTestResult, ProviderConnector

logger = logging.getLogger(__name__)

def _normalize_base_url(base_url: str | None) -> str | None:
    """Strip trailing /v1 from base_url if present.

    The Anthropic SDK expects the bare origin (e.g. https://api.anthropic.com)
    and appends /v1/... internally. If the registry stores the URL with /v1
    we'd hit /v1/v1/models → 404.
    """
    if not base_url:
        return None
    url = base_url.rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url or None

class AnthropicConnector(ProviderConnector):
    """Connector for Anthropic API.

    Uses the /v1/models endpoint for validation and model discovery.
    """

    async def test_connection(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> ConnectionTestResult:
        """Test connection to Anthropic API.

        Uses /v1/models for both validation AND model discovery.

        Args:
            api_key: API key for authentication (must start with 'sk-ant-')
            base_url: Custom endpoint URL (optional)
            **kwargs: Additional configuration (unused)

        Returns:
            ConnectionTestResult with success status and discovered models
        """
        if not api_key:
            return ConnectionTestResult(
                success=False,
                message="API key is required",
                error_code="missing_api_key",
            )

        # Validate key format
        if not api_key.startswith("sk-ant-"):
            return ConnectionTestResult(
                success=False,
                message="Invalid API key format. Anthropic keys start with 'sk-ant-'",
                error_code="invalid_key_format",
            )

        try:
            client = anthropic.AsyncAnthropic(
                api_key=api_key,
                base_url=_normalize_base_url(base_url),
            )

            models_response = await client.models.list()
            model_ids = [model.id for model in models_response.data]

            return ConnectionTestResult(
                success=True,
                message=f"Connected successfully. Found {len(model_ids)} models.",
                models=model_ids,
            )
        except anthropic.AuthenticationError:
            return ConnectionTestResult(
                success=False,
                message="Authentication failed. Check your API key.",
                error_code="auth_failed",
            )
        except anthropic.APIConnectionError as e:
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
        """Get available models from Anthropic API.

        Uses the /v1/models endpoint for dynamic discovery.

        Args:
            api_key: API key for authentication
            base_url: Custom endpoint URL (optional)
            **kwargs: Additional configuration (unused)

        Returns:
            List of available model IDs from API, or empty list on failure
        """
        if not api_key:
            return []

        try:
            client = anthropic.AsyncAnthropic(
                api_key=api_key,
                base_url=_normalize_base_url(base_url),
            )

            models_response = await client.models.list()
            return [model.id for model in models_response.data]
        except Exception as e:
            logger.warning(f"Anthropic model discovery failed: {e}")
            return []
