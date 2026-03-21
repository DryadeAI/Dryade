"""Base abstractions for reasoning/thinking adapters.

This module defines the common interface for provider-specific reasoning adapters
that normalize extended thinking/reasoning APIs across different LLM providers.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    pass  # Future type imports

@dataclass
class ReasoningChunk:
    """Normalized reasoning chunk for all providers.

    Attributes:
        type: Chunk type - "reasoning" for thinking content,
              "content" for response content, "done" for stream completion
        content: The text content of the chunk
        metadata: Optional provider-specific data (e.g., token counts)
    """

    type: Literal["reasoning", "content", "done"]
    content: str
    metadata: dict | None = None

class ReasoningAdapter(ABC):
    """Abstract base class for provider-specific reasoning adapters.

    Reasoning adapters handle the provider-specific implementation of
    extended thinking/reasoning APIs, normalizing the streaming output
    into a unified ReasoningChunk format.

    Each provider has a different API format:
    - Anthropic: thinking parameter with thinking_delta events
    - OpenAI: reasoning parameter with reasoning_summary_text.delta events
    - vLLM: reasoning_content in delta
    - DeepSeek: reasoning_content in delta

    Implementations should handle:
    1. Model capability detection (which models support reasoning)
    2. Request building with provider-specific parameters
    3. Streaming with normalized chunk output
    """

    @abstractmethod
    def supports_reasoning(self, model: str) -> bool:
        """Check if a model supports reasoning/thinking.

        Args:
            model: The model identifier (e.g., "claude-sonnet-4-5-20250929")

        Returns:
            True if the model supports extended reasoning/thinking
        """
        pass

    @abstractmethod
    def build_request(
        self,
        messages: list[dict],
        enable_thinking: bool,
        budget_tokens: int = 10000,
        **kwargs,
    ) -> dict:
        """Build a provider-specific request with reasoning parameters.

        Args:
            messages: List of message dicts with role/content
            enable_thinking: Whether to enable reasoning/thinking
            budget_tokens: Token budget for reasoning (minimum 1024 for Anthropic)
            **kwargs: Provider-specific parameters (model, max_tokens, etc.)

        Returns:
            Provider-specific request dict ready for API call
        """
        pass

    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        enable_thinking: bool,
        **kwargs,
    ) -> AsyncGenerator[ReasoningChunk, None]:
        """Stream response with normalized reasoning chunks.

        Yields ReasoningChunk objects with:
        - type="reasoning" for thinking/reasoning content
        - type="content" for response content
        - type="done" at stream completion

        Args:
            messages: List of message dicts with role/content
            enable_thinking: Whether to enable reasoning/thinking
            **kwargs: Provider-specific parameters (model, max_tokens, etc.)

        Yields:
            ReasoningChunk objects with normalized content
        """
        pass
