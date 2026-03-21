"""Anthropic Extended Thinking adapter.

This adapter implements Anthropic's Extended Thinking API for Claude 4+ models,
normalizing the streaming output to the unified ReasoningChunk format.

Anthropic API format:
- Request: thinking: {type: "enabled", budget_tokens: N}
- Stream events: content_block_delta with thinking_delta or text_delta type

Reference: https://platform.claude.com/docs/en/docs/build-with-claude/extended-thinking
"""

import logging
from collections.abc import AsyncGenerator

from core.providers.reasoning.base import ReasoningAdapter, ReasoningChunk

logger = logging.getLogger(__name__)

# Claude models that support extended thinking
# Use substring matching to handle version suffixes like "-20250929"
THINKING_MODELS = {
    "claude-sonnet-4-5",
    "claude-sonnet-4",
    "claude-opus-4-5",
    "claude-opus-4",
    "claude-haiku-4-5",
    "claude-3-7-sonnet",
}

# Minimum budget tokens required by Anthropic API
MIN_BUDGET_TOKENS = 1024

class AnthropicReasoningAdapter(ReasoningAdapter):
    """Anthropic Extended Thinking implementation.

    Handles the thinking parameter and thinking_delta streaming events
    for Claude 4+ models that support extended thinking.

    Usage:
        adapter = AnthropicReasoningAdapter()
        if adapter.supports_reasoning("claude-sonnet-4-5"):
            async for chunk in adapter.stream(messages, enable_thinking=True):
                if chunk.type == "reasoning":
                    print(f"Thinking: {chunk.content}")
    """

    def supports_reasoning(self, model: str) -> bool:
        """Check if a model supports extended thinking.

        Uses substring matching to handle versioned model names
        like "claude-sonnet-4-5-20250929".

        Args:
            model: The model identifier

        Returns:
            True if the model supports extended thinking
        """
        return any(thinking_model in model for thinking_model in THINKING_MODELS)

    def build_request(
        self,
        messages: list[dict],
        enable_thinking: bool,
        budget_tokens: int = 10000,
        **kwargs,
    ) -> dict:
        """Build Anthropic-specific request with thinking parameters.

        Args:
            messages: List of message dicts with role/content
            enable_thinking: Whether to enable extended thinking
            budget_tokens: Token budget for thinking (minimum 1024)
            **kwargs: Additional parameters including:
                - model: Model identifier (required)
                - max_tokens: Maximum response tokens (required, must be > budget_tokens)

        Returns:
            Request dict for Anthropic API
        """
        model = kwargs.get("model")
        max_tokens = kwargs.get("max_tokens", 16000)

        request = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": True,
        }

        if enable_thinking:
            # Enforce minimum budget tokens (Anthropic requirement)
            effective_budget = max(budget_tokens, MIN_BUDGET_TOKENS)

            if effective_budget != budget_tokens:
                logger.warning(
                    f"budget_tokens {budget_tokens} below minimum, using {MIN_BUDGET_TOKENS}"
                )

            request["thinking"] = {
                "type": "enabled",
                "budget_tokens": effective_budget,
            }

            logger.debug(f"Extended thinking enabled with budget_tokens={effective_budget}")

        return request

    async def stream(
        self,
        messages: list[dict],
        enable_thinking: bool,
        **kwargs,
    ) -> AsyncGenerator[ReasoningChunk, None]:
        """Stream response with normalized reasoning chunks.

        Uses Anthropic's async client with the messages.stream() context manager.
        Handles thinking_delta and text_delta events.

        Args:
            messages: List of message dicts with role/content
            enable_thinking: Whether to enable extended thinking
            **kwargs: Additional parameters including:
                - model: Model identifier (required)
                - max_tokens: Maximum response tokens
                - budget_tokens: Token budget for thinking

        Yields:
            ReasoningChunk objects with normalized content
        """
        try:
            import anthropic
        except ImportError as e:
            logger.error("anthropic SDK not installed: pip install anthropic")
            raise ImportError("anthropic SDK required for AnthropicReasoningAdapter") from e

        budget_tokens = kwargs.pop("budget_tokens", 10000)
        request = self.build_request(
            messages=messages,
            enable_thinking=enable_thinking,
            budget_tokens=budget_tokens,
            **kwargs,
        )

        client = anthropic.AsyncAnthropic()

        try:
            logger.debug(f"Starting Anthropic stream with model={request.get('model')}")

            async with client.messages.stream(**request) as stream:
                async for event in stream:
                    if event.type == "content_block_delta":
                        delta = event.delta

                        if delta.type == "thinking_delta":
                            # Extended thinking content
                            yield ReasoningChunk(
                                type="reasoning",
                                content=delta.thinking,
                            )
                        elif delta.type == "text_delta":
                            # Regular response content
                            yield ReasoningChunk(
                                type="content",
                                content=delta.text,
                            )

                # Extract usage from the final message (still inside async with)
                metadata = {}
                try:
                    final_message = await stream.get_final_message()
                    if hasattr(final_message, "usage") and final_message.usage:
                        metadata["usage"] = {
                            "input_tokens": final_message.usage.input_tokens,
                            "output_tokens": final_message.usage.output_tokens,
                        }
                except Exception as e:
                    logger.debug(f"Could not extract usage from stream: {e}")

            # Signal stream completion with usage metadata
            yield ReasoningChunk(type="done", content="", metadata=metadata or None)

        except anthropic.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during Anthropic stream: {e}")
            raise
