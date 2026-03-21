"""Provider registry and metadata.

This package provides a centralized registry of LLM providers with their
authentication requirements, capabilities, and model metadata.
"""

from core.providers.capabilities import AuthType, Capability
from core.providers.registry import (
    PROVIDER_REGISTRY,
    ModelMetadata,
    ProviderMetadata,
    get_provider,
)

__all__ = [
    "AuthType",
    "Capability",
    "ModelMetadata",
    "ProviderMetadata",
    "PROVIDER_REGISTRY",
    "get_provider",
]

def validate_provider(provider_id: str) -> bool:
    """Check if a provider exists in the registry.

    Args:
        provider_id: Provider identifier to validate

    Returns:
        True if provider exists, False otherwise
    """
    return provider_id in PROVIDER_REGISTRY
