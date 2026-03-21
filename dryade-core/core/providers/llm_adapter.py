"""Unified LLM Configuration Adapter.

Single entry point for all LLM call sites to get configuration.
Respects llm_config_source toggle and automatically selects between:
- Database config (from contextvars, set by middleware)
- Environment variables (from Settings)

Usage:
    # Get config dict (for passing to external APIs)
    config = get_llm_config()
    # config = {"provider": "openai", "model": "gpt-4", "api_key": "...", ...}

    # Get configured LLM instance (for CrewAI agents)
    llm = get_configured_llm()
"""

import logging
from dataclasses import dataclass
from typing import Any

from core.config import get_settings

logger = logging.getLogger(__name__)

@dataclass
class LLMConfig:
    """Normalized LLM configuration from any source."""

    provider: str  # "openai", "anthropic", "vllm", "ollama", etc.
    model: str  # Model name/ID
    base_url: str | None  # API endpoint (for local providers)
    api_key: str | None  # API key (None for local providers)
    temperature: float
    max_tokens: int
    timeout: int
    source: str  # "database" or "env" - for debugging

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for external APIs."""
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
        }

def get_llm_config() -> LLMConfig:
    """Get LLM configuration based on llm_config_source toggle.

    Priority based on llm_config_source setting:
    - "env": Always use environment variables
    - "database": Always use database config (error if not configured)
    - "auto": Try database first, fall back to env

    Returns:
        LLMConfig with normalized configuration

    Raises:
        ValueError: If llm_config_source="database" but user has no config
    """
    settings = get_settings()
    config_source = settings.llm_config_source

    # "env" mode: always use environment variables
    if config_source == "env":
        logger.debug("Using env config (llm_config_source=env)")
        return _config_from_env(settings)

    # Get user config from contextvars (set by middleware)
    from core.providers.llm_context import get_user_llm_context

    user_config = get_user_llm_context()

    # "database" mode: require database config
    if config_source == "database":
        if user_config and user_config.is_configured():
            logger.debug("Using database config (llm_config_source=database)")
            return _config_from_user(user_config, settings)
        else:
            raise ValueError(
                "llm_config_source='database' but user has no LLM configuration. "
                "Please configure LLM settings in the Settings page."
            )

    # "auto" mode: try database first, fall back to env
    if user_config and user_config.is_configured():
        logger.debug("Using database config (llm_config_source=auto, user configured)")
        return _config_from_user(user_config, settings)
    else:
        logger.debug("Using env config (llm_config_source=auto, no user config)")
        return _config_from_env(settings)

def _config_from_env(settings) -> LLMConfig:
    """Create LLMConfig from environment variables."""
    return LLMConfig(
        provider=settings.llm_mode,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout=settings.llm_timeout,
        source="env",
    )

def _config_from_user(user_config, settings) -> LLMConfig:
    """Create LLMConfig from user's database configuration.

    Uses settings for defaults (temperature, max_tokens, timeout)
    since those aren't stored in user config.
    """
    from core.providers.user_config import map_provider_to_llm_mode

    provider_mode = map_provider_to_llm_mode(user_config.provider)

    # Only fall back to env base_url for local providers that need an endpoint.
    # Cloud providers handle their own URLs via their SDKs.
    if provider_mode in ("openai", "anthropic", "litellm"):
        base_url = user_config.endpoint  # None = SDK default
    else:
        base_url = user_config.endpoint or settings.llm_base_url

    return LLMConfig(
        provider=provider_mode,
        model=user_config.model,
        base_url=base_url,
        api_key=user_config.api_key or settings.llm_api_key,
        temperature=settings.llm_temperature,  # Use env default
        max_tokens=settings.llm_max_tokens,  # Use env default
        timeout=settings.llm_timeout,  # Use env default
        source="database",
    )

def get_configured_llm(**overrides) -> Any:
    """Get a configured LLM instance ready for use.

    This is the primary entry point for code that needs an LLM instance.
    It respects the config toggle and returns an appropriate LLM.

    Args:
        **overrides: Optional overrides (model, temperature, timeout, etc.)

    Returns:
        LLM instance compatible with CrewAI (VLLMBaseLLM or CrewAI LLM)
    """
    import logging

    from core.agents.llm import get_llm
    from core.providers.llm_context import get_user_llm_context

    logger = logging.getLogger(__name__)
    settings = get_settings()
    config_source = settings.llm_config_source

    # In "env" mode, use get_llm without user_config
    if config_source == "env":
        logger.debug("[LLM_ADAPTER] config_source=env, using environment settings")
        return get_llm(**overrides)

    # Get user config from contextvars
    user_config = get_user_llm_context()

    # Log what we found
    if user_config:
        logger.info(
            f"[LLM_ADAPTER] User config from context: provider={user_config.provider}, "
            f"model={user_config.model}, endpoint={user_config.endpoint}, "
            f"is_configured={user_config.is_configured()}"
        )
    else:
        logger.warning("[LLM_ADAPTER] No user config in context (middleware may not have set it)")

    # In "database" mode, require user config
    if config_source == "database" and not (user_config and user_config.is_configured()):
        raise ValueError(
            "llm_config_source='database' but user has no LLM configuration. "
            "Please configure LLM settings in the Settings page."
        )

    # In "auto" mode or "database" mode with valid config
    return get_llm(user_config=user_config, **overrides)

async def get_configured_llm_with_fallback(
    user_id: str,
    db,
    cancel_event=None,
    on_failover=None,
    **overrides,
):
    """Get a configured LLM instance with automatic provider fallback.

    Falls back to ``get_configured_llm()`` if no fallback chain is configured
    (backward-compatible with all existing call sites).

    Args:
        user_id: The user's ID (from JWT sub claim).
        db: Database session (sync or async).
        cancel_event: Optional asyncio.Event to cancel mid-chain fallback.
        on_failover: Optional callback(from_provider, to_provider, reason).
        **overrides: Passed through to get_configured_llm() in no-fallback path.

    Returns:
        LLM instance (same type as get_configured_llm()).
    """

    from core.providers.resilience.failover_engine import execute_with_fallback
    from core.providers.resilience.fallback_chain import (
        get_fallback_chain,
        resolve_chain_configs,
    )

    chain = get_fallback_chain(user_id, db)

    if chain is None or not chain.entries:
        # No fallback configured — use existing behavior unchanged
        return get_configured_llm(**overrides)

    # Resolve chain entries to LLMConfig objects (filtering unconfigured providers)

    def _user_config_fn(provider: str):
        """Resolve API key + endpoint for a given provider from the user's stored config."""
        # Load user config, then look up the provider-specific API key
        from core.crypto import decrypt_key
        from core.database.models import ProviderApiKey

        try:
            key_record = (
                db.query(ProviderApiKey)
                .filter(
                    ProviderApiKey.user_id == user_id,
                    ProviderApiKey.provider == provider,
                    ProviderApiKey.is_global == True,  # noqa: E712
                )
                .first()
            )
            api_key = None
            if key_record:
                try:
                    api_key = decrypt_key(key_record.key_encrypted)
                except Exception:
                    pass

            from core.database.models import CustomProvider

            custom = db.query(CustomProvider).filter(CustomProvider.provider_id == provider).first()
            endpoint = custom.base_url if custom else None

            class _ProviderInfo:
                pass

            info = _ProviderInfo()
            info.api_key = api_key
            info.endpoint = endpoint
            return info
        except Exception:

            class _ProviderInfo:
                api_key = None
                endpoint = None

            return _ProviderInfo()

    chain_configs = resolve_chain_configs(chain, _user_config_fn)

    if not chain_configs:
        # All entries filtered out (no API keys) — fall back to default
        logger.warning("[LLM_ADAPTER] Fallback chain empty after resolving keys — using default")
        return get_configured_llm(**overrides)

    # Build call_fn that initialises an LLM for a given LLMConfig
    def _make_call_fn():
        async def call_fn(config) -> object:
            """Initialise and return an LLM instance for the given config."""
            from core.agents.llm import get_llm

            class _FakeUserConfig:
                """Minimal user config shim for get_llm()."""

                provider = config.provider
                model = config.model
                endpoint = config.base_url
                api_key = config.api_key

                def is_configured(self):
                    return True

            return get_llm(user_config=_FakeUserConfig(), **overrides)

        return call_fn

    result = await execute_with_fallback(
        chain=chain_configs,
        call_fn=_make_call_fn(),
        cancel_event=cancel_event,
        on_failover=on_failover,
    )
    return result

__all__ = [
    "LLMConfig",
    "get_llm_config",
    "get_configured_llm",
    "get_configured_llm_with_fallback",
]
