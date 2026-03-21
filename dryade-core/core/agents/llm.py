"""LLM Factory for Dryade Agents.

Provides a unified `get_llm()` function that returns the appropriate LLM
based on configuration (vLLM, LiteLLM, Ollama, etc.)

Supports both environment-based config (LLM_MODE, LLM_MODEL) and
user-specific database config (from Settings page).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from core.config import get_settings

if TYPE_CHECKING:
    from core.providers.user_config import UserLLMConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LiteLLM cost callback — automatically records costs for all LiteLLM calls
# ---------------------------------------------------------------------------
try:
    import litellm
    from litellm.integrations.custom_logger import CustomLogger

    class DryadeCostCallback(CustomLogger):
        """Captures token usage and cost from every LiteLLM completion call."""

        def log_success_event(self, kwargs, response_obj, start_time, end_time):
            try:
                model = kwargs.get("model", "unknown")
                usage = getattr(response_obj, "usage", None)
                if usage is None and isinstance(response_obj, dict):
                    usage = response_obj.get("usage")
                if usage is None:
                    return

                prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(usage, "completion_tokens", 0) or 0

                # Use litellm's built-in pricing for accurate USD cost
                try:
                    _cost = litellm.completion_cost(completion_response=response_obj)
                except Exception:
                    _cost = None  # Will be computed by CostTracker's own pricing

                from core.extensions import record_cost
                from core.providers.cost_context import get_cost_user_id

                record_cost(
                    model=model,
                    input_tokens=prompt_tokens,
                    output_tokens=completion_tokens,
                    agent="litellm_callback",
                    user_id=get_cost_user_id(),
                )
            except Exception:
                # Cost tracking must never break LLM calls
                logger.debug("DryadeCostCallback: failed to record cost", exc_info=True)

    _cost_callback = DryadeCostCallback()
    if _cost_callback not in litellm.callbacks:
        litellm.callbacks.append(_cost_callback)

except Exception:
    logger.debug("LiteLLM cost callback not registered (litellm not available)")

# Cache for default (env-based) LLM instance
_default_llm_cache: Any = None

def get_llm(
    model: str | None = None,
    base_url: str | None = None,
    user_config: UserLLMConfig | None = None,
    **kwargs,
) -> Any:
    """Get configured LLM instance.

    Priority for configuration:
    1. Explicit parameters (model, base_url)
    2. User config from database (if provided and configured)
    3. Environment settings (LLM_MODE, LLM_MODEL, etc.)

    Args:
        model: Optional model name override
        base_url: Optional base URL override
        user_config: Optional user-specific config from database
        **kwargs: Additional LLM configuration

    Returns:
        LLM instance compatible with CrewAI
    """
    global _default_llm_cache
    settings = get_settings()

    # Determine effective configuration
    if user_config and user_config.is_configured():
        # Use user's database configuration - never use cache for user-specific config
        from core.providers.user_config import get_litellm_model_string, map_provider_to_llm_mode

        llm_mode = map_provider_to_llm_mode(user_config.provider)
        llm_model = model or user_config.model
        # Only fall back to env base_url for local providers that need an endpoint.
        # Cloud providers (anthropic, openai, litellm) handle their own URLs.
        if llm_mode in ("openai", "anthropic", "litellm"):
            llm_base_url = base_url or user_config.endpoint  # None = SDK default
        else:
            llm_base_url = base_url or user_config.endpoint or settings.llm_base_url
        llm_api_key = user_config.api_key or settings.llm_api_key

        # For LiteLLM providers, format the model string with prefix
        if llm_mode == "litellm":
            llm_model = get_litellm_model_string(user_config.provider, llm_model)

        logger.debug(f"Using user config: provider={user_config.provider}, model={llm_model}")

        # Log and create fresh LLM for user config
        logger.info(
            f"[LLM] Creating LLM from user config: mode={llm_mode}, model={llm_model}, base_url={llm_base_url}"
        )
        return _create_llm_instance(
            llm_mode=llm_mode,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            settings=settings,
            provider=user_config.provider,
            inference_params=user_config.inference_params,
            **kwargs,
        )

    # Fall back to environment settings
    llm_mode = settings.llm_mode
    llm_model = model or settings.llm_model
    llm_base_url = base_url or settings.llm_base_url
    llm_api_key = settings.llm_api_key

    # Only use cache for env-based config with no overrides AND llm_config_source="env"
    # This prevents stale cache when user config might become available
    use_cache = (
        settings.llm_config_source == "env" and model is None and base_url is None and not kwargs
    )

    if use_cache and _default_llm_cache is not None:
        logger.debug("[LLM] Returning cached env-based LLM")
        return _default_llm_cache

    # Log the LLM configuration being used
    logger.info(
        f"[LLM] Creating LLM from env: mode={llm_mode}, model={llm_model}, base_url={llm_base_url}"
    )

    # Create LLM instance based on mode
    llm = _create_llm_instance(
        llm_mode=llm_mode,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
        llm_api_key=llm_api_key,
        settings=settings,
        provider=llm_mode,
        **kwargs,
    )

    # Cache only for pure env mode
    if use_cache:
        _default_llm_cache = llm

    return llm

# Map provider names to the env var that CrewAI / LiteLLM check at init time.
# The api_key IS passed to litellm.completion(), but some providers also
# validate env vars during LLM construction (confirmed for Anthropic).
_PROVIDER_ENV_VARS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GEMINI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "cohere": "COHERE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "xai": "XAI_API_KEY",
    "together_ai": "TOGETHERAI_API_KEY",
    "groq": "GROQ_API_KEY",
}

def _create_llm_instance(
    llm_mode: str,
    llm_model: str,
    llm_base_url: str | None,
    llm_api_key: str | None,
    settings: Any,
    provider: str | None = None,
    inference_params: dict | None = None,
    **kwargs,
) -> Any:
    """Create an LLM instance based on mode and configuration.

    Parameter resolution chain (lowest to highest priority):
    1. Hardcoded defaults (from inference_params.get_defaults())
    2. Environment settings (settings.llm_temperature, etc.)
    3. User DB params (inference_params from UserLLMConfig)
    4. Explicit kwargs (caller overrides, e.g. planner mode)
    """
    from core.providers.inference_params import filter_params_for_provider, get_defaults

    # Belt-and-suspenders: set the provider-specific env var so that
    # CrewAI / LiteLLM can find the key during construction, not just
    # when calling litellm.completion().
    if llm_api_key:
        import os

        env_var = _PROVIDER_ENV_VARS.get(provider or llm_mode)
        if env_var:
            os.environ[env_var] = llm_api_key

    # === Resolve effective params: hardcoded -> env -> user DB -> explicit kwargs ===
    defaults = get_defaults()
    effective = {**defaults}

    # Layer 2: env settings (only for params that have env equivalents)
    effective["temperature"] = settings.llm_temperature
    effective["max_tokens"] = settings.llm_max_tokens
    effective["timeout"] = settings.llm_timeout
    effective["planner_timeout"] = settings.llm_planner_timeout

    # Layer 3: user DB params (highest persistent priority)
    user_params = inference_params or {}
    effective.update({k: v for k, v in user_params.items() if v is not None})

    # Layer 4: explicit kwargs (caller overrides, e.g. planner mode)
    effective.update({k: v for k, v in kwargs.items() if k in defaults and v is not None})

    # Filter to supported params for this provider
    provider_name = provider or llm_mode
    provider_params = filter_params_for_provider(effective, provider_name)

    # Constructor-level params (passed directly to LLM constructors, NOT in _extra_sampling)
    _CONSTRUCTOR_PARAMS = {"temperature", "max_tokens", "timeout", "planner_timeout", "stop"}

    if llm_mode == "vllm":
        # Direct vLLM connection (core module, not a plugin)
        from core.providers.vllm_llm import VLLMBaseLLM

        instance = VLLMBaseLLM(
            model=llm_model,
            base_url=llm_base_url,
            api_key=llm_api_key or "not-needed",
            temperature=provider_params.get("temperature", settings.llm_temperature),
            max_tokens=provider_params.get("max_tokens", settings.llm_max_tokens),
            timeout=float(provider_params.get("timeout", settings.llm_timeout)),
        )
        # Pass additional sampling params that VLLMBaseLLM._build_payload can use
        instance._extra_sampling = {
            k: v for k, v in provider_params.items() if k not in _CONSTRUCTOR_PARAMS
        }
        instance.dryade_provider = provider_name
        return instance

    else:
        # Use CrewAI's native LLM class (wraps LiteLLM)
        from crewai import LLM

        # Build model string with provider prefix (single source: PROVIDER_PREFIX_MAP)
        from core.providers.user_config import PROVIDER_PREFIX_MAP

        if llm_mode == "litellm":
            model_str = llm_model  # Already prefixed by get_litellm_model_string in get_llm()
        elif llm_mode == "openai":
            model_str = llm_model  # OpenAI SDK handles natively
        else:
            prefix = PROVIDER_PREFIX_MAP.get(llm_mode, "")
            model_str = f"{prefix}{llm_model}" if prefix else llm_model

        # Only pass base_url for providers that need it (local/proxy endpoints)
        # Cloud providers routed via LiteLLM handle their own base_url
        if llm_mode in ("openai", "anthropic", "litellm"):
            effective_base_url = None
        else:
            effective_base_url = llm_base_url
        logger.info(f"[LLM] CrewAI LLM: model_str={model_str}, base_url={effective_base_url}")

        # Extra params beyond constructor defaults (e.g. frequency_penalty, presence_penalty)
        extra_kwargs = {k: v for k, v in provider_params.items() if k not in _CONSTRUCTOR_PARAMS}

        instance = LLM(
            model=model_str,
            base_url=effective_base_url,
            api_key=llm_api_key,
            temperature=provider_params.get("temperature", settings.llm_temperature),
            max_tokens=provider_params.get("max_tokens", settings.llm_max_tokens),
            timeout=provider_params.get("timeout", settings.llm_timeout),
            **extra_kwargs,
        )
        instance.dryade_provider = provider_name
        return instance

def clear_llm_cache():
    """Clear the LLM instance cache (useful for config changes)."""
    global _default_llm_cache
    _default_llm_cache = None
