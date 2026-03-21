"""Mistral AI connector for connection testing and model discovery."""

from core.providers.connectors.base import ConnectionTestResult, ProviderConnector


class MistralConnector(ProviderConnector):
    """Mistral AI API connection testing.

    Uses the mistralai SDK to list available models.
    API docs: https://docs.mistral.ai/api/endpoint/models
    """

    async def test_connection(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> ConnectionTestResult:
        """Test connection to Mistral AI API.

        Args:
            api_key: Mistral API key
            endpoint: Not used for Mistral (fixed endpoint)

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
            from mistralai import Mistral

            client = Mistral(api_key=api_key)

            # List available models
            response = client.models.list()
            models = [model.id for model in response.data]

            return ConnectionTestResult(
                success=True,
                message=f"Connected successfully. Found {len(models)} models.",
                models=models,
            )

        except ImportError:
            return ConnectionTestResult(
                success=False,
                message="mistralai package not installed. Run: pip install mistralai",
                error_code="missing_dependency",
            )
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg:
                return ConnectionTestResult(
                    success=False,
                    message="Invalid API key",
                    error_code="invalid_key",
                )
            if "403" in error_msg or "payment" in error_msg.lower():
                return ConnectionTestResult(
                    success=False,
                    message="API key valid but account requires payment setup",
                    error_code="payment_required",
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
        """Discover available models from Mistral AI.

        Returns list of model IDs.
        """
        result = await self.test_connection(api_key, base_url)
        return result.models or []
