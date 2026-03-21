"""Provider connectors for connection testing and model discovery.

This package provides connector implementations for testing API connectivity
and discovering available models from LLM providers.
"""

from core.providers.connectors.base import ConnectionTestResult, ProviderConnector

__all__ = [
    "ConnectionTestResult",
    "ProviderConnector",
    "get_connector",
]

_CONNECTOR_CACHE: dict[str, ProviderConnector] = {}

def _build_connector(provider_id: str) -> ProviderConnector | None:
    """Create a new connector instance for the given built-in provider."""
    from core.providers.connectors.anthropic_connector import AnthropicConnector
    from core.providers.connectors.bedrock_connector import BedrockConnector
    from core.providers.connectors.cohere_connector import CohereConnector
    from core.providers.connectors.google_connector import GoogleConnector
    from core.providers.connectors.huggingface_connector import HuggingFaceConnector
    from core.providers.connectors.local_connector import OllamaConnector, VLLMConnector
    from core.providers.connectors.mistral_connector import MistralConnector
    from core.providers.connectors.openai_compatible_connector import OpenAICompatibleConnector
    from core.providers.connectors.openai_connector import OpenAIConnector

    _CONNECTOR_MAP: dict[str, type[ProviderConnector] | tuple] = {
        "openai": OpenAIConnector,
        "azure_openai": (OpenAIConnector, {"is_azure": True}),
        "anthropic": AnthropicConnector,
        "google": GoogleConnector,
        "mistral": MistralConnector,
        "cohere": CohereConnector,
        "bedrock": BedrockConnector,
        "ollama": OllamaConnector,
        "vllm": VLLMConnector,
        "huggingface": HuggingFaceConnector,
        "deepseek": (
            OpenAICompatibleConnector,
            {"default_base_url": "https://api.deepseek.com/v1"},
        ),
        "qwen": (
            OpenAICompatibleConnector,
            {"default_base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"},
        ),
        "moonshot": (OpenAICompatibleConnector, {"default_base_url": "https://api.moonshot.ai/v1"}),
        "xai": (OpenAICompatibleConnector, {"default_base_url": "https://api.x.ai/v1"}),
        "together_ai": (
            OpenAICompatibleConnector,
            {"default_base_url": "https://api.together.xyz/v1"},
        ),
        "groq": (OpenAICompatibleConnector, {"default_base_url": "https://api.groq.com/openai/v1"}),
        "litellm_proxy": (
            OpenAICompatibleConnector,
            {"default_base_url": "http://localhost:4000/v1"},
        ),
    }

    entry = _CONNECTOR_MAP.get(provider_id)
    if entry is None:
        return None
    if isinstance(entry, tuple):
        cls, kwargs = entry
        return cls(**kwargs)
    return entry()

def get_connector(provider_id: str, custom_base_url: str | None = None) -> ProviderConnector | None:
    """Get connector instance for a provider.

    Connectors are lazily created and cached per provider_id. Each built-in
    provider is instantiated at most once.

    Args:
        provider_id: Provider identifier (e.g., "openai", "anthropic", "ollama")
        custom_base_url: Base URL for custom (user-defined) providers.
            When provided and provider_id is not a built-in, returns an
            OpenAICompatibleConnector targeting this URL.

    Returns:
        Connector instance if provider is supported, None otherwise
    """
    if provider_id in _CONNECTOR_CACHE:
        return _CONNECTOR_CACHE[provider_id]

    connector = _build_connector(provider_id)
    if connector is not None:
        _CONNECTOR_CACHE[provider_id] = connector
        return connector

    # Dynamic connector for custom (user-defined) providers (not cached —
    # different base_url values yield different connectors)
    if custom_base_url:
        from core.providers.connectors.openai_compatible_connector import OpenAICompatibleConnector

        return OpenAICompatibleConnector(custom_base_url)

    return None

def reset_connectors() -> None:
    """Clear the connector cache. Intended for testing."""
    _CONNECTOR_CACHE.clear()
