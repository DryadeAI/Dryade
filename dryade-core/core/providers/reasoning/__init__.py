"""Reasoning/Thinking adapter module for multi-provider support.

This module provides a unified interface for LLM reasoning/thinking APIs
across different providers. Each provider has its own API format for
extended thinking, and the adapters normalize these to a common interface.

Supported providers:
- Anthropic: Extended Thinking (thinking parameter, thinking_delta events)
- OpenAI: Responses API (reasoning parameter, reasoning_summary_text.delta)
- vLLM: reasoning_content in delta (already handled in VLLMBaseLLM)
- LiteLLM: Fallback for other providers via reasoning_effort

Usage:
    from core.providers.reasoning import (
        ReasoningChunk,
        ReasoningAdapter,
        AnthropicReasoningAdapter,
        OpenAIResponsesAdapter,
        LiteLLMReasoningAdapter,
    )

    # Anthropic Extended Thinking
    adapter = AnthropicReasoningAdapter()
    if adapter.supports_reasoning("claude-sonnet-4-5"):
        async for chunk in adapter.stream(messages, enable_thinking=True):
            if chunk.type == "reasoning":
                print(f"Thinking: {chunk.content}")
            elif chunk.type == "content":
                print(f"Response: {chunk.content}")

    # OpenAI Responses API (o1/o3/o4)
    openai_adapter = OpenAIResponsesAdapter()
    if openai_adapter.supports_reasoning("o3"):
        async for chunk in openai_adapter.stream(messages, enable_thinking=True):
            ...

    # LiteLLM fallback (DeepSeek, Gemini, etc.)
    litellm_adapter = LiteLLMReasoningAdapter()
    if litellm_adapter.supports_reasoning("deepseek-r1"):
        async for chunk in litellm_adapter.stream(messages, enable_thinking=True):
            ...
"""

from core.providers.reasoning.anthropic import AnthropicReasoningAdapter
from core.providers.reasoning.base import ReasoningAdapter, ReasoningChunk
from core.providers.reasoning.litellm import LiteLLMReasoningAdapter
from core.providers.reasoning.openai_responses import OpenAIResponsesAdapter
from core.providers.reasoning.router import (
    get_reasoning_adapter,
    stream_with_reasoning,
    supports_reasoning,
)

__all__ = [
    "ReasoningChunk",
    "ReasoningAdapter",
    "AnthropicReasoningAdapter",
    "LiteLLMReasoningAdapter",
    "OpenAIResponsesAdapter",
    # Router functions
    "get_reasoning_adapter",
    "stream_with_reasoning",
    "supports_reasoning",
]
