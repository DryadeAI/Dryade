"""OpenAI Responses API adapter for reasoning models.

This adapter handles the OpenAI Responses API used by o1/o3/o4 and future
reasoning models. These models use a different API format than Chat Completions,
with `input` instead of `messages` and reasoning configuration via the
`reasoning` parameter.

Reference: https://platform.openai.com/docs/guides/reasoning
"""

import logging
from collections.abc import AsyncGenerator

from core.providers.reasoning.base import ReasoningAdapter, ReasoningChunk

logger = logging.getLogger(__name__)

# Models that support reasoning via the Responses API
# These are checked via substring matching to handle version suffixes
REASONING_MODELS = frozenset(
    {
        "o1",  # o1, o1-preview, o1-2024-12-17, etc.
        "o3",  # o3, o3-pro, o3-mini, etc.
        "o4-mini",  # o4-mini
        "gpt-5",  # Future gpt-5 models
    }
)

class OpenAIResponsesAdapter(ReasoningAdapter):
    """Adapter for OpenAI Responses API (o1/o3/o4 reasoning models).

    The Responses API uses a different format than Chat Completions:
    - Uses `input` instead of `messages`
    - Configures reasoning via `reasoning` parameter with `effort` and `summary`
    - Streams `response.reasoning_summary_text.delta` for thinking content
    - Streams `response.output_text.delta` for response content

    Example:
        adapter = OpenAIResponsesAdapter()
        if adapter.supports_reasoning("o3"):
            async for chunk in adapter.stream(messages, enable_thinking=True):
                if chunk.type == "reasoning":
                    print(f"Thinking: {chunk.content}")
    """

    def supports_reasoning(self, model: str) -> bool:
        """Check if a model supports reasoning via the Responses API.

        Args:
            model: The model identifier (e.g., "o1", "o3-pro", "gpt-4")

        Returns:
            True if the model is a Responses API reasoning model
        """
        model_lower = model.lower()
        return any(reasoning_model in model_lower for reasoning_model in REASONING_MODELS)

    def _budget_to_effort(self, budget_tokens: int) -> str:
        """Convert token budget to reasoning effort level.

        The Responses API uses "low"/"medium"/"high" effort levels
        instead of explicit token budgets.

        Args:
            budget_tokens: Token budget for reasoning

        Returns:
            Effort level string ("low", "medium", or "high")
        """
        if budget_tokens < 4096:
            return "low"
        elif budget_tokens < 16384:
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
        """Build a Responses API request with reasoning parameters.

        The Responses API uses a different format:
        - `input` instead of `messages`
        - `reasoning` parameter with `effort` and `summary` keys

        Args:
            messages: List of message dicts with role/content
            enable_thinking: Whether to enable reasoning
            budget_tokens: Token budget for reasoning (maps to effort level)
            **kwargs: Additional parameters (model, max_tokens, etc.)

        Returns:
            Request dict for the Responses API
        """
        # Convert messages to Responses API input format
        # The Responses API accepts a list of input items
        input_items = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            # Map roles to Responses API format
            if role == "system":
                # System messages become developer instructions
                input_items.append(
                    {
                        "type": "message",
                        "role": "developer",
                        "content": content,
                    }
                )
            elif role == "assistant":
                input_items.append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": content,
                    }
                )
            else:
                # User messages
                input_items.append(
                    {
                        "type": "message",
                        "role": "user",
                        "content": content,
                    }
                )

        request = {
            "input": input_items,
            "stream": True,
        }

        # Add model if provided
        if "model" in kwargs:
            request["model"] = kwargs["model"]

        # Add max_tokens if provided (Responses API calls it max_output_tokens)
        if "max_tokens" in kwargs:
            request["max_output_tokens"] = kwargs["max_tokens"]

        # Add reasoning configuration when thinking is enabled
        if enable_thinking:
            effort = self._budget_to_effort(budget_tokens)
            request["reasoning"] = {
                "effort": effort,
                "summary": "detailed",  # Get detailed reasoning summaries
            }

        return request

    async def stream(
        self,
        messages: list[dict],
        enable_thinking: bool,
        **kwargs,
    ) -> AsyncGenerator[ReasoningChunk, None]:
        """Stream response from OpenAI Responses API with normalized chunks.

        Uses the `client.responses.stream()` context manager to handle
        the streaming events.

        Args:
            messages: List of message dicts with role/content
            enable_thinking: Whether to enable reasoning
            **kwargs: Additional parameters (model, api_key, budget_tokens, etc.)

        Yields:
            ReasoningChunk objects with normalized content
        """
        try:
            import openai
        except ImportError:
            logger.error("openai package not installed")
            yield ReasoningChunk(
                type="done", content="", metadata={"error": "openai package not installed"}
            )
            return

        # Extract API configuration
        api_key = kwargs.pop("api_key", None)
        base_url = kwargs.pop("base_url", None)
        budget_tokens = kwargs.pop("budget_tokens", 10000)

        # Build the request
        request = self.build_request(
            messages=messages,
            enable_thinking=enable_thinking,
            budget_tokens=budget_tokens,
            **kwargs,
        )

        # Create async client
        client_kwargs = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if base_url:
            client_kwargs["base_url"] = base_url

        try:
            client = openai.AsyncOpenAI(**client_kwargs)

            # Use the Responses API stream context manager
            async with client.responses.stream(**request) as stream:
                async for event in stream:
                    # Handle reasoning summary text deltas
                    if hasattr(event, "type"):
                        if event.type == "response.reasoning_summary_text.delta":
                            delta = getattr(event, "delta", "")
                            if delta:
                                yield ReasoningChunk(
                                    type="reasoning",
                                    content=delta,
                                )
                        elif event.type == "response.output_text.delta":
                            delta = getattr(event, "delta", "")
                            if delta:
                                yield ReasoningChunk(
                                    type="content",
                                    content=delta,
                                )
                        elif event.type == "response.done":
                            # Extract usage info if available
                            metadata = {}
                            if hasattr(event, "response") and hasattr(event.response, "usage"):
                                usage = event.response.usage
                                metadata["usage"] = {
                                    "input_tokens": getattr(usage, "input_tokens", 0),
                                    "output_tokens": getattr(usage, "output_tokens", 0),
                                    "reasoning_tokens": getattr(usage, "reasoning_tokens", 0),
                                }
                            yield ReasoningChunk(type="done", content="", metadata=metadata or None)
                            return

            # If we exit the stream without a done event, yield done anyway
            yield ReasoningChunk(type="done", content="")

        except openai.APIError as e:
            logger.error(f"OpenAI Responses API error: {e}")
            yield ReasoningChunk(
                type="done",
                content="",
                metadata={"error": str(e), "error_type": type(e).__name__},
            )
        except Exception as e:
            logger.error(f"Unexpected error in OpenAI Responses API stream: {e}")
            yield ReasoningChunk(
                type="done",
                content="",
                metadata={"error": str(e), "error_type": type(e).__name__},
            )
