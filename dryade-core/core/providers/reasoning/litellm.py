"""LiteLLM fallback adapter for reasoning models.

This adapter provides reasoning support for models via LiteLLM's unified interface.
LiteLLM handles provider-specific translation of the reasoning_effort parameter
to native formats (e.g., DeepSeek's reasoning_content, Gemini's thinking mode).

Supported providers via LiteLLM:
- DeepSeek: Models with "r1" (e.g., deepseek-r1, deepseek-reasoner)
- Google Gemini: Models with "thinking" or 2.5+ (e.g., gemini-2.5-pro-thinking)
- Ollama: Local models with /think suffix convention

Reference: https://docs.litellm.ai/docs/reasoning_content
"""

import logging
from collections.abc import AsyncGenerator

from core.providers.reasoning.base import ReasoningAdapter, ReasoningChunk

logger = logging.getLogger(__name__)

# Token budget to effort level mapping
# These thresholds align with typical provider behavior
EFFORT_TO_BUDGET_THRESHOLDS = {
    "low": 4096,  # Under 4k tokens
    "medium": 16384,  # 4k-16k tokens
    "high": float("inf"),  # 16k+ tokens
}

class LiteLLMReasoningAdapter(ReasoningAdapter):
    """Fallback adapter for reasoning via LiteLLM's unified interface.

    LiteLLM translates the `reasoning_effort` parameter to provider-specific
    formats, allowing reasoning support across multiple providers without
    direct API implementation.

    Supported model patterns:
    - DeepSeek: "deepseek" + "r1" or "reasoner" (deepseek-r1, deepseek-reasoner)
    - Gemini: "gemini" + ("thinking" or "2.5" or "3") for thinking-capable models
    - Ollama: Models with "/think" suffix (e.g., qwen:32b/think)

    Example:
        adapter = LiteLLMReasoningAdapter()
        if adapter.supports_reasoning("deepseek-r1"):
            async for chunk in adapter.stream(messages, enable_thinking=True):
                if chunk.type == "reasoning":
                    print(f"Thinking: {chunk.content}")
    """

    def supports_reasoning(self, model: str) -> bool:
        """Check if a model supports reasoning via LiteLLM.

        Uses conservative pattern matching - only returns True for models
        known to support reasoning content.

        Args:
            model: The model identifier (e.g., "deepseek-r1", "gemini-2.5-thinking")

        Returns:
            True if the model is known to support reasoning via LiteLLM
        """
        model_lower = model.lower()

        # DeepSeek reasoning models
        if "deepseek" in model_lower and ("r1" in model_lower or "reasoner" in model_lower):
            return True

        # Google Gemini thinking/reasoning models
        if "gemini" in model_lower:
            # Gemini 2.5+ or explicit thinking models
            if "thinking" in model_lower:
                return True
            if "2.5" in model_lower or "3." in model_lower:
                # Gemini 2.5+ supports thinking mode
                return True

        # Ollama models with /think suffix (convention for reasoning)
        if "/think" in model_lower:
            return True

        # QwQ and other known reasoning models
        if "qwq" in model_lower:
            return True

        # Conservative: don't claim support for unknown models
        return False

    def _budget_to_effort(self, budget_tokens: int) -> str:
        """Convert token budget to reasoning effort level.

        LiteLLM uses "low"/"medium"/"high" effort levels which are
        translated to provider-specific parameters.

        Args:
            budget_tokens: Token budget for reasoning

        Returns:
            Effort level string ("low", "medium", or "high")
        """
        if budget_tokens < EFFORT_TO_BUDGET_THRESHOLDS["low"]:
            return "low"
        elif budget_tokens < EFFORT_TO_BUDGET_THRESHOLDS["medium"]:
            return "medium"
        else:
            return "high"

    def build_request(
        self,
        messages: list[dict],
        enable_thinking: bool,
        budget_tokens: int = 10000,
        **kwargs,
    ) -> dict:
        """Build a Chat Completions request with reasoning_effort parameter.

        LiteLLM uses standard Chat Completions format with an additional
        `reasoning_effort` parameter that it translates to provider-specific
        configurations.

        Args:
            messages: List of message dicts with role/content
            enable_thinking: Whether to enable reasoning
            budget_tokens: Token budget for reasoning (maps to effort level)
            **kwargs: Additional parameters (model, max_tokens, etc.)

        Returns:
            Request dict for LiteLLM acompletion
        """
        request = {
            "messages": messages,
            "stream": True,
        }

        # Add model if provided
        if "model" in kwargs:
            request["model"] = kwargs["model"]

        # Add max_tokens if provided
        if "max_tokens" in kwargs:
            request["max_tokens"] = kwargs["max_tokens"]

        # Add temperature if provided (some reasoning models ignore this)
        if "temperature" in kwargs:
            request["temperature"] = kwargs["temperature"]

        # Add reasoning_effort when thinking is enabled
        if enable_thinking:
            effort = self._budget_to_effort(budget_tokens)
            request["reasoning_effort"] = effort

        return request

    async def stream(
        self,
        messages: list[dict],
        enable_thinking: bool,
        **kwargs,
    ) -> AsyncGenerator[ReasoningChunk, None]:
        """Stream response from LiteLLM with normalized reasoning chunks.

        LiteLLM provides reasoning content via `delta.reasoning_content`
        or `delta.reasoning` fields, depending on the underlying provider.

        Args:
            messages: List of message dicts with role/content
            enable_thinking: Whether to enable reasoning
            **kwargs: Additional parameters (model, api_key, budget_tokens, etc.)

        Yields:
            ReasoningChunk objects with normalized content
        """
        try:
            import litellm
        except ImportError:
            logger.error("litellm package not installed")
            yield ReasoningChunk(
                type="done", content="", metadata={"error": "litellm package not installed"}
            )
            return

        # Extract budget_tokens before building request
        budget_tokens = kwargs.pop("budget_tokens", 10000)

        # Build the request
        request = self.build_request(
            messages=messages,
            enable_thinking=enable_thinking,
            budget_tokens=budget_tokens,
            **kwargs,
        )

        # Extract API configuration for litellm
        api_key = kwargs.get("api_key")
        api_base = kwargs.get("base_url") or kwargs.get("api_base")

        if api_key:
            request["api_key"] = api_key
        if api_base:
            request["api_base"] = api_base

        try:
            # Use litellm.acompletion for async streaming
            response = await litellm.acompletion(**request)

            # Iterate over streaming chunks
            async for chunk in response:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # Check for reasoning content (provider-specific field names)
                reasoning_content = None
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    reasoning_content = delta.reasoning_content
                elif hasattr(delta, "reasoning") and delta.reasoning:
                    reasoning_content = delta.reasoning
                elif hasattr(delta, "thinking") and delta.thinking:
                    # Some providers use "thinking" field
                    reasoning_content = delta.thinking

                if reasoning_content:
                    yield ReasoningChunk(
                        type="reasoning",
                        content=reasoning_content,
                    )

                # Check for regular content
                if hasattr(delta, "content") and delta.content:
                    yield ReasoningChunk(
                        type="content",
                        content=delta.content,
                    )

                # Check for finish reason
                if chunk.choices[0].finish_reason:
                    # Extract usage info if available
                    metadata = {}
                    if hasattr(chunk, "usage") and chunk.usage:
                        metadata["usage"] = {
                            "prompt_tokens": getattr(chunk.usage, "prompt_tokens", 0),
                            "completion_tokens": getattr(chunk.usage, "completion_tokens", 0),
                        }
                        # Some providers include reasoning tokens
                        if hasattr(chunk.usage, "reasoning_tokens"):
                            metadata["usage"]["reasoning_tokens"] = chunk.usage.reasoning_tokens

                    yield ReasoningChunk(
                        type="done",
                        content="",
                        metadata=metadata or None,
                    )
                    return

            # If we exit without finish_reason, yield done anyway
            yield ReasoningChunk(type="done", content="")

        except litellm.APIError as e:
            logger.error(f"LiteLLM API error: {e}")
            yield ReasoningChunk(
                type="done",
                content="",
                metadata={"error": str(e), "error_type": type(e).__name__},
            )
        except Exception as e:
            logger.error(f"Unexpected error in LiteLLM stream: {e}")
            yield ReasoningChunk(
                type="done",
                content="",
                metadata={"error": str(e), "error_type": type(e).__name__},
            )
