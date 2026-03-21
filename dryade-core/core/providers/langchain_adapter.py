"""LangChain LLM Adapter.

Provides LangChain-compatible LLM instances configured from user settings.
Mirrors the pattern of llm_adapter.py but for LangChain instead of CrewAI.

Usage:
    from core.providers.langchain_adapter import get_langchain_llm

    # Get LangChain ChatModel configured from user settings
    llm = get_langchain_llm()

    # Use with LangGraph
    from langgraph.prebuilt import create_react_agent
    agent = create_react_agent(llm, tools)
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

def get_langchain_llm(**overrides) -> Any:
    """Get a LangChain-compatible LLM from user config or environment.

    Uses the same configuration source as CrewAI (user Settings page or env vars),
    but returns a LangChain ChatModel instead of CrewAI LLM.

    Args:
        **overrides: Optional overrides (model, temperature, etc.)

    Returns:
        LangChain BaseChatModel instance (ChatOpenAI, ChatAnthropic, etc.)

    Raises:
        ValueError: If no LLM is configured.
        ImportError: If required LangChain package is not installed.
    """
    from core.providers.llm_adapter import get_llm_config

    config = get_llm_config()

    # Apply overrides
    model = overrides.get("model", config.model)
    temperature = overrides.get("temperature", config.temperature)
    api_key = overrides.get("api_key", config.api_key)
    base_url = overrides.get("base_url", config.base_url)

    return _create_langchain_chat_model(
        provider=config.provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
    )

def _create_langchain_chat_model(
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
    temperature: float,
) -> Any:
    """Create a LangChain ChatModel based on provider.

    Args:
        provider: Provider name (openai, anthropic, ollama, vllm, etc.)
        model: Model name/ID
        api_key: API key (may be None for local providers)
        base_url: Base URL for API (may be None for cloud providers)
        temperature: Temperature setting

    Returns:
        LangChain BaseChatModel instance.
    """
    provider_lower = provider.lower()

    # OpenAI and OpenAI-compatible providers
    if provider_lower in ("openai", "litellm") or model.startswith("gpt"):
        return _create_openai_chat(
            model, api_key, base_url, temperature, is_cloud=provider_lower == "openai"
        )

    # Anthropic
    if provider_lower == "anthropic" or model.startswith("claude"):
        return _create_anthropic_chat(model, api_key, temperature)

    # Local providers (Ollama, vLLM) - use OpenAI-compatible endpoint
    if provider_lower in ("ollama", "vllm"):
        return _create_openai_chat(
            model=model,
            api_key=api_key or "sk-placeholder",
            base_url=base_url,
            temperature=temperature,
            is_cloud=False,
        )

    # Default: try OpenAI-compatible endpoint
    logger.debug(f"Unknown provider '{provider}', trying OpenAI-compatible endpoint")
    return _create_openai_chat(model, api_key, base_url, temperature, is_cloud=False)

def _create_openai_chat(
    model: str,
    api_key: str | None,
    base_url: str | None,
    temperature: float,
    is_cloud: bool = True,
) -> Any:
    """Create ChatOpenAI instance.

    Args:
        model: Model name
        api_key: API key
        base_url: Base URL (ignored for cloud OpenAI)
        temperature: Temperature
        is_cloud: If True, ignore base_url (use OpenAI cloud)

    Returns:
        ChatOpenAI instance.
    """
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        raise ImportError(
            "langchain-openai required for OpenAI models. "
            "Install with: pip install langchain-openai"
        ) from e

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=None if is_cloud else base_url,
        temperature=temperature,
    )

def _create_anthropic_chat(
    model: str,
    api_key: str | None,
    temperature: float,
) -> Any:
    """Create ChatAnthropic instance.

    Falls back to OpenAI-compatible if langchain-anthropic not installed.

    Args:
        model: Model name
        api_key: API key
        temperature: Temperature

    Returns:
        ChatAnthropic instance (or ChatOpenAI fallback).
    """
    try:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model,
            api_key=api_key,
            temperature=temperature,
        )
    except ImportError:
        logger.warning(
            "langchain-anthropic not installed, trying OpenAI-compatible endpoint. "
            "Install with: pip install langchain-anthropic"
        )
        # Fall back to OpenAI-compatible (may not work for Anthropic)
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            api_key=api_key,
            temperature=temperature,
        )

__all__ = ["get_langchain_llm"]
