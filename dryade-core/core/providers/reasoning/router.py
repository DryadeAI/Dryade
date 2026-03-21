"""Reasoning adapter router - selects appropriate adapter based on provider/model.

This module routes reasoning requests to the appropriate provider-specific adapter
based on the provider name and model identifier. It provides a unified entry point
for multi-provider reasoning support.

Router Selection Logic:
1. Anthropic provider -> AnthropicReasoningAdapter
2. OpenAI provider with o1/o3/o4 model -> OpenAIResponsesAdapter
3. OpenAI provider with other models -> LiteLLMReasoningAdapter (no native reasoning)
4. vLLM -> None (use existing VLLMBaseLLM path which handles reasoning_content)
5. Other providers -> LiteLLMReasoningAdapter (uses reasoning_effort)

Usage:
    from core.providers.reasoning import get_reasoning_adapter, stream_with_reasoning

    # Get adapter for provider/model
    adapter = get_reasoning_adapter("anthropic", "claude-sonnet-4-5")
    if adapter is not None:
        async for chunk in stream_with_reasoning(...):
            ...

    # For vLLM, returns None - use VLLMBaseLLM directly
    adapter = get_reasoning_adapter("vllm", "qwen3")
    assert adapter is None
"""

import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from core.providers.reasoning.anthropic import AnthropicReasoningAdapter
from core.providers.reasoning.litellm import LiteLLMReasoningAdapter
from core.providers.reasoning.openai_responses import OpenAIResponsesAdapter

if TYPE_CHECKING:
    from core.providers.reasoning.base import ReasoningAdapter, ReasoningChunk

logger = logging.getLogger(__name__)

# Singleton instances for efficiency
_adapters = {
    "anthropic": AnthropicReasoningAdapter(),
    "openai_responses": OpenAIResponsesAdapter(),
    "litellm": LiteLLMReasoningAdapter(),
}

def get_reasoning_adapter(provider: str, model: str) -> "ReasoningAdapter | None":
    """Get appropriate reasoning adapter for provider/model combination.

    Selection logic:
    1. Anthropic provider -> AnthropicReasoningAdapter
    2. OpenAI provider with o1/o3/o4 model -> OpenAIResponsesAdapter
    3. OpenAI provider with other models -> LiteLLMReasoningAdapter (no native reasoning)
    4. vLLM -> None (signal to use existing VLLMBaseLLM path)
    5. Other providers -> LiteLLMReasoningAdapter (uses reasoning_effort)

    Args:
        provider: Provider name ("anthropic", "openai", "vllm", "ollama", etc.)
        model: Model name/ID

    Returns:
        Appropriate ReasoningAdapter instance, or None for vLLM
        (None signals use existing VLLMBaseLLM path which handles reasoning_content)
    """
    provider_lower = provider.lower() if provider else ""

    # Anthropic always uses Anthropic adapter (for thinking-capable models)
    if provider_lower == "anthropic":
        return _adapters["anthropic"]

    # OpenAI: route o1/o3/o4 to Responses API, others to LiteLLM
    if provider_lower == "openai":
        openai_adapter = _adapters["openai_responses"]
        if openai_adapter.supports_reasoning(model):
            return openai_adapter
        # Non-reasoning OpenAI models don't have thinking but can use LiteLLM fallback
        return _adapters["litellm"]

    # vLLM: Return None to signal use existing VLLMBaseLLM path
    # VLLMBaseLLM already handles reasoning_content correctly
    if provider_lower == "vllm":
        return None  # Signal to use existing path

    # All other providers: LiteLLM fallback
    # This includes ollama, deepseek, gemini, etc.
    return _adapters["litellm"]

def supports_reasoning(provider: str, model: str) -> bool:
    """Check if provider/model combination supports reasoning.

    Returns True if the combination has native reasoning support.

    Args:
        provider: Provider name
        model: Model name/ID

    Returns:
        True if the combination supports reasoning/thinking
    """
    adapter = get_reasoning_adapter(provider, model)

    if adapter is None:
        # vLLM - check model manually for reasoning models
        reasoning_models = ["qwen3", "deepseek", "granite", "ministral", "r1", "qwq"]
        model_lower = model.lower() if model else ""
        return any(rm in model_lower for rm in reasoning_models)

    return adapter.supports_reasoning(model)

async def stream_with_reasoning(
    provider: str,
    model: str,
    messages: list[dict],
    enable_thinking: bool = False,
    api_key: str | None = None,
    base_url: str | None = None,
    budget_tokens: int = 10000,
    **kwargs,
) -> AsyncGenerator["ReasoningChunk", None]:
    """Unified streaming that handles reasoning for any provider.

    Yields ReasoningChunk objects normalized from provider-specific formats.
    For vLLM, raises ValueError - caller should use VLLMBaseLLM directly.

    Args:
        provider: Provider name
        model: Model name
        messages: Chat messages
        enable_thinking: Whether to enable thinking/reasoning
        api_key: Provider API key
        base_url: Provider base URL
        budget_tokens: Thinking budget (Anthropic) or effort mapping (others)
        **kwargs: Additional provider-specific params

    Yields:
        ReasoningChunk with type "reasoning", "content", or "done"

    Raises:
        ValueError: If provider is vLLM (should use VLLMBaseLLM directly)
    """

    adapter = get_reasoning_adapter(provider, model)

    # vLLM uses existing path (return None to signal)
    if adapter is None:
        raise ValueError("vLLM should use VLLMBaseLLM directly, not reasoning adapter")

    # Check if model actually supports reasoning
    if not adapter.supports_reasoning(model):
        # Model doesn't support reasoning - disable it
        enable_thinking = False
        logger.info(f"Model {model} doesn't support reasoning, disabling enable_thinking")

    logger.debug(
        f"[REASONING] Streaming with adapter={type(adapter).__name__}, "
        f"provider={provider}, model={model}, enable_thinking={enable_thinking}"
    )

    async for chunk in adapter.stream(
        messages=messages,
        enable_thinking=enable_thinking,
        model=model,
        api_key=api_key,
        base_url=base_url,
        budget_tokens=budget_tokens,
        **kwargs,
    ):
        yield chunk
