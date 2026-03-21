"""Local provider connectors for Ollama and vLLM."""

import httpx
import openai

from core.providers.connectors.base import ConnectionTestResult, ProviderConnector


class OllamaConnector(ProviderConnector):
    """Connector for Ollama local inference server.

    Uses httpx to make direct HTTP requests to Ollama's REST API.
    Discovers models via GET /api/tags endpoint.
    """

    async def test_connection(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> ConnectionTestResult:
        """Test connection to Ollama server.

        Args:
            api_key: Not used (Ollama doesn't require authentication)
            base_url: Custom Ollama endpoint (default: http://localhost:11434)
            **kwargs: Additional configuration (unused)

        Returns:
            ConnectionTestResult with success status and discovered models
        """
        endpoint = base_url or "http://localhost:11434"

        try:
            # Attempt to discover models as connection test
            models = await self.discover_models(api_key, base_url, **kwargs)

            return ConnectionTestResult(
                success=True,
                message=f"Connected to Ollama. Found {len(models)} model(s).",
                models=models,
            )
        except httpx.ConnectError:
            return ConnectionTestResult(
                success=False,
                message=f"Cannot connect to Ollama at {endpoint}. Is the server running?",
                error_code="connection_refused",
            )
        except httpx.TimeoutException:
            return ConnectionTestResult(
                success=False,
                message=f"Connection to {endpoint} timed out.",
                error_code="timeout",
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
        """Discover available models from Ollama server.

        Args:
            api_key: Not used (Ollama doesn't require authentication)
            base_url: Custom Ollama endpoint (default: http://localhost:11434)
            **kwargs: Additional configuration (unused)

        Returns:
            List of available model names
        """
        endpoint = base_url or "http://localhost:11434"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{endpoint}/api/tags",
                    timeout=10.0,
                )
                response.raise_for_status()

                data = response.json()
                # Ollama returns {"models": [{"name": "model1"}, ...]}
                return [model["name"] for model in data.get("models", [])]

        except Exception:
            return []

class VLLMConnector(ProviderConnector):
    """Connector for vLLM local inference server.

    vLLM is OpenAI-compatible, so we use the OpenAI SDK with a custom base_url.
    Discovers models via the /v1/models endpoint.
    """

    async def test_connection(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs,
    ) -> ConnectionTestResult:
        """Test connection to vLLM server.

        Args:
            api_key: Not used (vLLM typically doesn't require authentication)
            base_url: Custom vLLM endpoint (default: http://localhost:8000)
            **kwargs: Additional configuration (unused)

        Returns:
            ConnectionTestResult with success status and discovered models
        """
        endpoint = base_url or "http://localhost:8000"

        try:
            # Attempt to discover models as connection test
            models = await self.discover_models(api_key, base_url, **kwargs)

            return ConnectionTestResult(
                success=True,
                message=f"Connected to vLLM. Found {len(models)} model(s).",
                models=models,
            )
        except openai.APIConnectionError as e:
            return ConnectionTestResult(
                success=False,
                message=f"Cannot connect to vLLM at {endpoint}: {str(e)}",
                error_code="connection_refused",
            )
        except openai.APITimeoutError:
            return ConnectionTestResult(
                success=False,
                message=f"Connection to {endpoint} timed out.",
                error_code="timeout",
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
        """Discover available models from vLLM server.

        Args:
            api_key: Optional API key if vLLM is configured with authentication
            base_url: Custom vLLM endpoint (default: http://localhost:8000)
            **kwargs: Additional configuration (unused)

        Returns:
            List of available model IDs
        """
        endpoint = base_url or "http://localhost:8000"

        try:
            # vLLM is OpenAI-compatible, use OpenAI SDK
            client = openai.AsyncOpenAI(
                api_key=api_key or "dummy",  # vLLM may not require real key
                base_url=endpoint + "/v1" if not endpoint.endswith("/v1") else endpoint,
            )

            response = await client.models.list()
            return [model.id for model in response.data]

        except Exception:
            return []
