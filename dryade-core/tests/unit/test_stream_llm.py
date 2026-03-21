"""Tests for OrchestrationThinkingProvider._stream_llm().

Covers VLLMBaseLLM path, LiteLLM path, fallback to _call_llm,
cancel_event, and reasoning_content routing.
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure a mock litellm module is available for patching
# (litellm may not be installed in the test environment)
if "litellm" not in sys.modules:
    _mock_litellm = MagicMock()
    _mock_litellm.acompletion = AsyncMock()
    sys.modules["litellm"] = _mock_litellm

from core.orchestrator.thinking import OrchestrationThinkingProvider

@pytest.fixture
def thinking():
    return OrchestrationThinkingProvider()

class TestStreamLlmVLLM:
    """VLLMBaseLLM path (has astream)."""

    @pytest.mark.asyncio
    async def test_streams_content_tokens(self, thinking):
        """Content tokens are accumulated and delivered via on_token."""
        mock_llm = MagicMock()

        async def mock_astream(messages, enable_thinking=False):
            yield {"type": "content", "content": "Hello"}
            yield {"type": "content", "content": " world"}

        mock_llm.astream = mock_astream

        tokens = []
        with patch.object(thinking, "_get_llm", return_value=mock_llm):
            content, reasoning, est = await thinking._stream_llm(
                messages=[{"role": "user", "content": "hi"}],
                on_token=lambda t: tokens.append(t),
            )

        assert content == "Hello world"
        assert reasoning == ""
        assert tokens == ["Hello", " world"]
        assert est > 0

    @pytest.mark.asyncio
    async def test_routes_reasoning_to_on_thinking(self, thinking):
        """reasoning_content tokens go to on_thinking, not on_token."""
        mock_llm = MagicMock()

        async def mock_astream(messages, enable_thinking=False):
            yield {"type": "reasoning", "content": "Let me think..."}
            yield {"type": "content", "content": "Answer"}

        mock_llm.astream = mock_astream

        tokens = []
        thinking_tokens = []
        with patch.object(thinking, "_get_llm", return_value=mock_llm):
            content, reasoning, _ = await thinking._stream_llm(
                messages=[{"role": "user", "content": "hi"}],
                on_token=lambda t: tokens.append(t),
                on_thinking=lambda t: thinking_tokens.append(t),
            )

        assert content == "Answer"
        assert reasoning == "Let me think..."
        assert tokens == ["Answer"]
        assert thinking_tokens == ["Let me think..."]

    @pytest.mark.asyncio
    async def test_handles_string_chunks(self, thinking):
        """Plain string chunks (backward compat) are treated as content."""
        mock_llm = MagicMock()

        async def mock_astream(messages, enable_thinking=False):
            yield "token1"
            yield "token2"

        mock_llm.astream = mock_astream

        tokens = []
        with patch.object(thinking, "_get_llm", return_value=mock_llm):
            content, _reasoning, _ = await thinking._stream_llm(
                messages=[{"role": "user", "content": "hi"}],
                on_token=lambda t: tokens.append(t),
            )

        assert content == "token1token2"
        assert tokens == ["token1", "token2"]

    @pytest.mark.asyncio
    async def test_cancel_event_stops_streaming(self, thinking):
        """Setting cancel_event breaks out of the streaming loop."""
        mock_llm = MagicMock()
        cancel = asyncio.Event()

        async def mock_astream(messages, enable_thinking=False):
            yield {"type": "content", "content": "first"}
            cancel.set()  # Cancel after first chunk
            yield {"type": "content", "content": "second"}

        mock_llm.astream = mock_astream

        tokens = []
        with patch.object(thinking, "_get_llm", return_value=mock_llm):
            content, _reasoning, _ = await thinking._stream_llm(
                messages=[{"role": "user", "content": "hi"}],
                on_token=lambda t: tokens.append(t),
                cancel_event=cancel,
            )

        assert content == "first"
        assert tokens == ["first"]

class TestStreamLlmLiteLLM:
    """LiteLLM path (no astream attribute)."""

    @pytest.mark.asyncio
    async def test_streams_via_litellm(self, thinking):
        """Falls back to litellm.acompletion when no astream."""
        mock_llm = MagicMock(spec=[])  # No astream
        mock_llm.model = "gpt-4"
        mock_llm.api_key = "test-key"
        mock_llm.base_url = None
        mock_llm.api_base = None

        # Create mock chunks
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock()]
        chunk1.choices[0].delta.content = "Hello"
        chunk1.choices[0].delta.reasoning_content = None

        chunk2 = MagicMock()
        chunk2.choices = [MagicMock()]
        chunk2.choices[0].delta.content = " there"
        chunk2.choices[0].delta.reasoning_content = None

        async def mock_response():
            yield chunk1
            yield chunk2

        tokens = []
        with patch.object(thinking, "_get_llm", return_value=mock_llm):
            with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response()):
                content, _reasoning, _ = await thinking._stream_llm(
                    messages=[{"role": "user", "content": "hi"}],
                    on_token=lambda t: tokens.append(t),
                )

        assert content == "Hello there"
        assert tokens == ["Hello", " there"]

class TestStreamLlmFallback:
    """Fallback to _call_llm on streaming failure."""

    @pytest.mark.asyncio
    async def test_fallback_on_exception(self, thinking):
        """When streaming raises, falls back to _call_llm_inner."""
        mock_llm = MagicMock(spec=[])
        mock_llm.model = "gpt-4"
        mock_llm.api_key = None
        mock_llm.base_url = None
        mock_llm.api_base = None

        tokens = []
        with patch.object(thinking, "_get_llm", return_value=mock_llm):
            with patch("litellm.acompletion", side_effect=Exception("stream failed")):
                with patch.object(
                    thinking,
                    "_call_llm_inner",
                    new_callable=AsyncMock,
                    return_value=("fallback response", "reasoning"),
                ):
                    content, _reasoning, _ = await thinking._stream_llm(
                        messages=[{"role": "user", "content": "hi"}],
                        on_token=lambda t: tokens.append(t),
                        on_thinking=lambda t: None,
                    )

        assert content == "fallback response"
        assert tokens == ["fallback response"]

    @pytest.mark.asyncio
    async def test_empty_content_returns_zero_tokens(self, thinking):
        """Empty streaming returns ('', 0)."""
        mock_llm = MagicMock()

        async def mock_astream(messages, enable_thinking=False):
            return
            yield  # make it an async generator

        mock_llm.astream = mock_astream

        with patch.object(thinking, "_get_llm", return_value=mock_llm):
            content, _reasoning, est = await thinking._stream_llm(
                messages=[{"role": "user", "content": "hi"}],
            )

        assert content == ""
        assert est == 0

class TestMergeThinking:
    """Tests for merge_thinking=True (INSTANT tier display fix)."""

    @pytest.mark.asyncio
    async def test_vllm_reasoning_merged_to_content(self, thinking):
        """With merge_thinking, reasoning tokens are routed to on_token."""
        mock_llm = MagicMock()

        async def mock_astream(messages, enable_thinking=False):
            yield {"type": "reasoning", "content": "Hello"}
            yield {"type": "reasoning", "content": " there!"}

        mock_llm.astream = mock_astream

        tokens = []
        thinking_tokens = []
        with patch.object(thinking, "_get_llm", return_value=mock_llm):
            content, _reasoning, est = await thinking._stream_llm(
                messages=[{"role": "user", "content": "hi"}],
                on_token=lambda t: tokens.append(t),
                on_thinking=lambda t: thinking_tokens.append(t),
                merge_thinking=True,
            )

        assert content == "Hello there!"
        assert _reasoning == ""
        assert tokens == ["Hello", " there!"]
        assert thinking_tokens == []  # Nothing goes to on_thinking
        assert est > 0

    @pytest.mark.asyncio
    async def test_vllm_mixed_reasoning_and_content_merged(self, thinking):
        """merge_thinking merges reasoning; content still routes to on_token."""
        mock_llm = MagicMock()

        async def mock_astream(messages, enable_thinking=False):
            yield {"type": "reasoning", "content": "Thinking..."}
            yield {"type": "content", "content": "Answer"}

        mock_llm.astream = mock_astream

        tokens = []
        with patch.object(thinking, "_get_llm", return_value=mock_llm):
            content, _reasoning, _ = await thinking._stream_llm(
                messages=[{"role": "user", "content": "hi"}],
                on_token=lambda t: tokens.append(t),
                merge_thinking=True,
            )

        assert content == "Thinking...Answer"
        assert tokens == ["Thinking...", "Answer"]

    @pytest.mark.asyncio
    async def test_fallback_merge_thinking(self, thinking):
        """Fallback path merges reasoning into content with merge_thinking."""
        mock_llm = MagicMock(spec=[])
        mock_llm.model = "gpt-4"
        mock_llm.api_key = None
        mock_llm.base_url = None
        mock_llm.api_base = None

        tokens = []
        with patch.object(thinking, "_get_llm", return_value=mock_llm):
            with patch("litellm.acompletion", side_effect=Exception("fail")):
                with patch.object(
                    thinking,
                    "_call_llm_inner",
                    new_callable=AsyncMock,
                    return_value=("", "reasoning answer"),
                ):
                    content, _reasoning, _ = await thinking._stream_llm(
                        messages=[{"role": "user", "content": "hi"}],
                        on_token=lambda t: tokens.append(t),
                        on_thinking=lambda t: None,
                        merge_thinking=True,
                    )

        assert content == "reasoning answer"
        assert "reasoning answer" in tokens

class TestReasoningAccumulation:
    """Tests for reasoning accumulation in the 3-tuple return (Phase 99.2)."""

    @pytest.mark.asyncio
    async def test_reasoning_accumulated_when_merge_false(self, thinking):
        """With merge_thinking=False, reasoning tokens accumulate in return value."""
        mock_llm = MagicMock()

        async def mock_astream(messages, enable_thinking=False):
            yield {"type": "reasoning", "content": "Step 1. "}
            yield {"type": "reasoning", "content": "Step 2. "}
            yield {"type": "content", "content": "Answer"}

        mock_llm.astream = mock_astream

        tokens = []
        thinking_tokens = []
        with patch.object(thinking, "_get_llm", return_value=mock_llm):
            content, reasoning, est = await thinking._stream_llm(
                messages=[{"role": "user", "content": "hi"}],
                on_token=lambda t: tokens.append(t),
                on_thinking=lambda t: thinking_tokens.append(t),
                merge_thinking=False,
            )

        assert content == "Answer"
        assert reasoning == "Step 1. Step 2. "
        assert tokens == ["Answer"]
        assert thinking_tokens == ["Step 1. ", "Step 2. "]

    @pytest.mark.asyncio
    async def test_reasoning_empty_when_merge_true(self, thinking):
        """With merge_thinking=True, reasoning goes to content, not to reasoning return."""
        mock_llm = MagicMock()

        async def mock_astream(messages, enable_thinking=False):
            yield {"type": "reasoning", "content": "Thinking..."}
            yield {"type": "content", "content": "Answer"}

        mock_llm.astream = mock_astream

        with patch.object(thinking, "_get_llm", return_value=mock_llm):
            content, reasoning, est = await thinking._stream_llm(
                messages=[{"role": "user", "content": "hi"}],
                on_token=lambda t: None,
                merge_thinking=True,
            )

        assert content == "Thinking...Answer"
        assert reasoning == ""

    @pytest.mark.asyncio
    async def test_reasoning_only_stream_returns_reasoning(self, thinking):
        """When model produces ONLY reasoning tokens (no content), reasoning is accumulated."""
        mock_llm = MagicMock()

        async def mock_astream(messages, enable_thinking=False):
            yield {"type": "reasoning", "content": "The answer is 42."}

        mock_llm.astream = mock_astream

        with patch.object(thinking, "_get_llm", return_value=mock_llm):
            content, reasoning, est = await thinking._stream_llm(
                messages=[{"role": "user", "content": "hi"}],
                on_token=lambda t: None,
                on_thinking=lambda t: None,
                merge_thinking=False,
            )

        assert content == ""
        assert reasoning == "The answer is 42."
