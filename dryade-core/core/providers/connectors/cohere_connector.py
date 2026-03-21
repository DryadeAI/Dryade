"""Cohere connector for connection testing and model discovery."""

from core.providers.connectors.base import ConnectionTestResult, ProviderConnector


class CohereConnector(ProviderConnector):
    """Cohere API connection testing.

    Uses the cohere SDK to list available models.
    API docs: https://docs.cohere.com/reference/list-models
    """

    async def test_connection(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> ConnectionTestResult:
        """Test connection to Cohere API.

        Args:
            api_key: Cohere API key
            endpoint: Not used for Cohere (fixed endpoint)

        Returns:
            ConnectionTestResult with success status and available models
        """
        if not api_key:
            return ConnectionTestResult(
                success=False,
                message="API key is required",
                error_code="missing_key",
            )

        try:
            import cohere

            # Use v2 client
            client = cohere.ClientV2(api_key=api_key)

            # List available models
            response = client.models.list()
            models = [model.name for model in response.models]

            return ConnectionTestResult(
                success=True,
                message=f"Connected successfully. Found {len(models)} models.",
                models=models,
            )

        except ImportError:
            return ConnectionTestResult(
                success=False,
                message="cohere package not installed. Run: pip install cohere",
                error_code="missing_dependency",
            )
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "invalid" in error_msg.lower():
                return ConnectionTestResult(
                    success=False,
                    message="Invalid API key",
                    error_code="invalid_key",
                )
            return ConnectionTestResult(
                success=False,
                message=f"Connection failed: {error_msg}",
                error_code="connection_error",
            )

    async def discover_models(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> list[str]:
        """Discover available models from Cohere.

        Returns list of model names.
        """
        result = await self.test_connection(api_key, base_url)
        return result.models or []
