"""User Model Configuration - Loads user's LLM preferences from database.

Bridges the Settings page (database) with the LLM factory.
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

@dataclass
class UserLLMConfig:
    """User's LLM configuration loaded from database."""

    provider: str | None = None
    model: str | None = None
    endpoint: str | None = None
    api_key: str | None = None  # Decrypted API key (if stored)
    inference_params: dict | None = None  # Phase 211: per-capability inference params from DB

    def is_configured(self) -> bool:
        """Check if user has configured an LLM."""
        return bool(self.provider and self.model)

def get_user_llm_config(user_id: str, db: "Session") -> UserLLMConfig:
    """Load user's LLM configuration from database.

    Args:
        user_id: The user's ID (from JWT sub claim)
        db: Database session

    Returns:
        UserLLMConfig with user's preferences, or empty config if not set
    """
    from core.crypto import decrypt_key
    from core.database.models import ModelConfig, ProviderApiKey

    config = UserLLMConfig()

    try:
        # Get user's model configuration
        model_config = db.query(ModelConfig).filter(ModelConfig.user_id == user_id).first()

        if model_config:
            config.provider = model_config.llm_provider
            config.model = model_config.llm_model
            config.endpoint = model_config.llm_endpoint
            config.inference_params = model_config.llm_inference_params  # JSON column, may be None

        # Get user's API key for the provider (if stored)
        if config.provider:
            api_key_record = (
                db.query(ProviderApiKey)
                .filter(
                    ProviderApiKey.user_id == user_id,
                    ProviderApiKey.provider == config.provider,
                    ProviderApiKey.is_global == True,  # noqa: E712
                )
                .first()
            )
            if api_key_record:
                try:
                    config.api_key = decrypt_key(api_key_record.key_encrypted)
                except Exception as e:
                    logger.warning(f"Failed to decrypt API key for {config.provider}: {e}")

    except Exception as e:
        logger.error(f"Failed to load user LLM config: {e}")

    return config

@dataclass
class UserEmbeddingConfig:
    """User's embedding configuration loaded from database."""

    provider: str | None = None
    model: str | None = None
    endpoint: str | None = None

    def is_configured(self) -> bool:
        """Check if user has configured an embedding provider."""
        return bool(self.provider and self.model)

def get_user_embedding_config(user_id: str, db: "Session") -> UserEmbeddingConfig:
    """Load user's embedding configuration from database.

    Args:
        user_id: The user's ID (from JWT sub claim)
        db: Database session

    Returns:
        UserEmbeddingConfig with user's preferences, or empty config if not set
    """
    from core.database.models import ModelConfig

    config = UserEmbeddingConfig()

    try:
        model_config = db.query(ModelConfig).filter(ModelConfig.user_id == user_id).first()

        if model_config:
            config.provider = model_config.embedding_provider
            config.model = model_config.embedding_model
            config.endpoint = getattr(model_config, "embedding_endpoint", None)

    except Exception as e:
        logger.error(f"Failed to load user embedding config: {e}")

    return config

def map_provider_to_llm_mode(provider: str) -> str:
    """Map provider name to LLM_MODE setting.

    Args:
        provider: Provider name from registry (e.g., 'openai', 'vllm', 'ollama')
            or a custom provider slug (e.g., 'my-llama-server')

    Returns:
        LLM mode string for get_llm() (e.g., 'openai', 'vllm', 'ollama', 'litellm')
    """
    # Direct mappings - providers with native SDK support
    direct_modes = {"openai", "anthropic", "ollama", "vllm"}
    if provider in direct_modes:
        return provider

    # Custom endpoint providers - use as OpenAI-compatible with user's base_url
    if provider == "litellm_proxy":
        return provider

    # Known cloud providers in the registry route through LiteLLM
    from core.providers import PROVIDER_REGISTRY

    if provider in PROVIDER_REGISTRY:
        return "litellm"

    # Unknown provider = custom (user-defined), treat as OpenAI-compatible
    return "litellm_proxy"

# Single source of truth for provider -> LiteLLM model string prefix.
# Used by get_litellm_model_string() and _create_llm_instance() in llm.py.
PROVIDER_PREFIX_MAP: dict[str, str] = {
    "ollama": "ollama/",
    "anthropic": "anthropic/",
    "litellm_proxy": "openai/",
    "google": "gemini/",
    "mistral": "mistral/",
    "cohere": "cohere/",
    "bedrock": "bedrock/",
    "azure_openai": "azure/",
    "deepseek": "deepseek/",
    "xai": "xai/",
    "together_ai": "together_ai/",
    "groq": "groq/",
    "qwen": "openai/",
    "moonshot": "openai/",
}

def get_litellm_model_string(provider: str, model: str) -> str:
    """Get the LiteLLM model string for a provider/model combination.

    LiteLLM uses provider prefixes for routing.
    See: https://docs.litellm.ai/docs/providers

    Args:
        provider: Provider name from registry
        model: Model name/ID

    Returns:
        Model string with appropriate prefix for LiteLLM
    """
    prefix = PROVIDER_PREFIX_MAP.get(provider, "")
    return f"{prefix}{model}"
