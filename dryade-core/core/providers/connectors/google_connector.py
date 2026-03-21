"""Google Gemini connector for connection testing and model discovery."""

from core.providers.connectors.base import ConnectionTestResult, ProviderConnector


class GoogleConnector(ProviderConnector):
    """Google Gemini API connection testing.

    Uses the google-generativeai SDK to list available models.
    API docs: https://ai.google.dev/api/models
    """

    async def test_connection(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> ConnectionTestResult:
        """Test connection to Google Gemini API.

        Args:
            api_key: Google AI API key (starts with "AIza")
            endpoint: Not used for Google (fixed endpoint)

        Returns:
            ConnectionTestResult with success status and available models
        """
        if not api_key:
            return ConnectionTestResult(
                success=False,
                message="API key is required",
                error_code="missing_key",
            )

        # Basic format validation
        if not api_key.startswith("AIza"):
            return ConnectionTestResult(
                success=False,
                message="Invalid Google AI API key format (should start with 'AIza')",
                error_code="invalid_format",
            )

        try:
            import google.generativeai as genai

            genai.configure(api_key=api_key)

            # List available models
            models = []
            for model in genai.list_models():
                # Only include models that support generateContent
                if "generateContent" in model.supported_generation_methods:
                    # Extract model name (e.g., "models/gemini-1.5-pro" -> "gemini-1.5-pro")
                    model_name = model.name.replace("models/", "")
                    models.append(model_name)

            return ConnectionTestResult(
                success=True,
                message=f"Connected successfully. Found {len(models)} models.",
                models=models[:20],  # Limit for display
            )

        except ImportError:
            return ConnectionTestResult(
                success=False,
                message="google-generativeai package not installed. Run: pip install google-generativeai",
                error_code="missing_dependency",
            )
        except Exception as e:
            error_msg = str(e)
            if "API_KEY_INVALID" in error_msg or "401" in error_msg:
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
        """Discover available models from Google Gemini.

        Returns list of model IDs that support text generation.
        """
        result = await self.test_connection(api_key, base_url)
        return result.models or []
