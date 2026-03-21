"""Unit tests for reasoning adapters."""

import pytest

from core.providers.reasoning import (
    AnthropicReasoningAdapter,
    LiteLLMReasoningAdapter,
    OpenAIResponsesAdapter,
    ReasoningAdapter,
    ReasoningChunk,
)

class TestReasoningChunk:
    """Tests for ReasoningChunk dataclass."""

    def test_chunk_creation(self):
        """Test basic chunk creation with required fields."""
        chunk = ReasoningChunk(type="reasoning", content="thinking...")
        assert chunk.type == "reasoning"
        assert chunk.content == "thinking..."
        assert chunk.metadata is None

    def test_chunk_with_metadata(self):
        """Test chunk creation with optional metadata."""
        chunk = ReasoningChunk(type="content", content="hello", metadata={"tokens": 10})
        assert chunk.metadata == {"tokens": 10}

    def test_chunk_types(self):
        """Test all valid chunk types."""
        reasoning = ReasoningChunk(type="reasoning", content="thinking")
        content = ReasoningChunk(type="content", content="response")
        done = ReasoningChunk(type="done", content="")

        assert reasoning.type == "reasoning"
        assert content.type == "content"
        assert done.type == "done"

class TestReasoningAdapter:
    """Tests for ReasoningAdapter ABC."""

    def test_is_abstract_class(self):
        """Verify ReasoningAdapter is an abstract base class."""
        with pytest.raises(TypeError):
            ReasoningAdapter()  # type: ignore

class TestAnthropicReasoningAdapter:
    """Tests for AnthropicReasoningAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create adapter instance for tests."""
        return AnthropicReasoningAdapter()

    def test_supports_claude_4_models(self, adapter):
        """Test that Claude 4+ models are recognized as thinking-capable."""
        assert adapter.supports_reasoning("claude-sonnet-4-5")
        assert adapter.supports_reasoning("claude-opus-4-5")
        assert adapter.supports_reasoning("claude-opus-4")
        assert adapter.supports_reasoning("claude-haiku-4-5")
        assert adapter.supports_reasoning("claude-3-7-sonnet")

    def test_supports_versioned_model_names(self, adapter):
        """Test substring matching for versioned model names."""
        assert adapter.supports_reasoning("claude-sonnet-4-5-20250929")
        assert adapter.supports_reasoning("claude-opus-4-5-20250929")
        assert adapter.supports_reasoning("claude-3-7-sonnet-20250929")

    def test_does_not_support_non_thinking_models(self, adapter):
        """Test that non-thinking models are correctly rejected."""
        assert not adapter.supports_reasoning("gpt-4")
        assert not adapter.supports_reasoning("gpt-4-turbo")
        assert not adapter.supports_reasoning("claude-3-5-sonnet")
        assert not adapter.supports_reasoning("llama-3.1-70b")
        assert not adapter.supports_reasoning("mistral-large")

    def test_build_request_with_thinking(self, adapter):
        """Test request building with thinking enabled."""
        messages = [{"role": "user", "content": "test"}]
        request = adapter.build_request(
            messages=messages,
            enable_thinking=True,
            budget_tokens=10000,
            model="claude-sonnet-4-5",
            max_tokens=16000,
        )

        assert request["thinking"]["type"] == "enabled"
        assert request["thinking"]["budget_tokens"] == 10000
        assert request["stream"] is True
        assert request["model"] == "claude-sonnet-4-5"
        assert request["max_tokens"] == 16000
        assert request["messages"] == messages

    def test_build_request_without_thinking(self, adapter):
        """Test request building with thinking disabled."""
        messages = [{"role": "user", "content": "test"}]
        request = adapter.build_request(
            messages=messages,
            enable_thinking=False,
            model="claude-sonnet-4-5",
            max_tokens=4096,
        )

        assert "thinking" not in request
        assert request["stream"] is True
        assert request["model"] == "claude-sonnet-4-5"
        assert request["max_tokens"] == 4096

    def test_budget_tokens_minimum_enforcement(self, adapter):
        """Test that budget_tokens below minimum is enforced to 1024."""
        messages = [{"role": "user", "content": "test"}]
        request = adapter.build_request(
            messages=messages,
            enable_thinking=True,
            budget_tokens=500,  # Below minimum
            model="claude-sonnet-4-5",
            max_tokens=16000,
        )

        # Adapter should enforce minimum of 1024
        assert request["thinking"]["budget_tokens"] >= 1024

    def test_budget_tokens_at_minimum(self, adapter):
        """Test budget_tokens exactly at minimum."""
        messages = [{"role": "user", "content": "test"}]
        request = adapter.build_request(
            messages=messages,
            enable_thinking=True,
            budget_tokens=1024,  # At minimum
            model="claude-sonnet-4-5",
            max_tokens=16000,
        )

        assert request["thinking"]["budget_tokens"] == 1024

    def test_budget_tokens_above_minimum(self, adapter):
        """Test budget_tokens above minimum is preserved."""
        messages = [{"role": "user", "content": "test"}]
        request = adapter.build_request(
            messages=messages,
            enable_thinking=True,
            budget_tokens=32000,
            model="claude-sonnet-4-5",
            max_tokens=64000,
        )

        assert request["thinking"]["budget_tokens"] == 32000

    def test_default_max_tokens(self, adapter):
        """Test that max_tokens defaults to 16000."""
        messages = [{"role": "user", "content": "test"}]
        request = adapter.build_request(
            messages=messages,
            enable_thinking=True,
            budget_tokens=10000,
            model="claude-sonnet-4-5",
        )

        assert request["max_tokens"] == 16000

    def test_default_budget_tokens(self, adapter):
        """Test that budget_tokens defaults to 10000."""
        messages = [{"role": "user", "content": "test"}]
        request = adapter.build_request(
            messages=messages,
            enable_thinking=True,
            model="claude-sonnet-4-5",
            max_tokens=16000,
        )

        assert request["thinking"]["budget_tokens"] == 10000

class TestOpenAIResponsesAdapter:
    """Tests for OpenAIResponsesAdapter (o1/o3/o4 Responses API)."""

    @pytest.fixture
    def adapter(self):
        """Create adapter instance for tests."""
        return OpenAIResponsesAdapter()

    def test_supports_o1_models(self, adapter):
        """Test that o1 models are recognized as reasoning-capable."""
        assert adapter.supports_reasoning("o1")
        assert adapter.supports_reasoning("o1-preview")
        assert adapter.supports_reasoning("o1-2024-12-17")
        assert adapter.supports_reasoning("o1-mini")

    def test_supports_o3_models(self, adapter):
        """Test that o3 models are recognized as reasoning-capable."""
        assert adapter.supports_reasoning("o3")
        assert adapter.supports_reasoning("o3-pro")
        assert adapter.supports_reasoning("o3-mini")

    def test_supports_o4_mini(self, adapter):
        """Test that o4-mini is recognized as reasoning-capable."""
        assert adapter.supports_reasoning("o4-mini")

    def test_supports_future_gpt5(self, adapter):
        """Test that gpt-5 models are recognized as reasoning-capable."""
        assert adapter.supports_reasoning("gpt-5")
        assert adapter.supports_reasoning("gpt-5-turbo")

    def test_does_not_support_chat_models(self, adapter):
        """Test that Chat Completions models are rejected."""
        assert not adapter.supports_reasoning("gpt-4")
        assert not adapter.supports_reasoning("gpt-4-turbo")
        assert not adapter.supports_reasoning("gpt-4o")
        assert not adapter.supports_reasoning("claude-3-5-sonnet")
        assert not adapter.supports_reasoning("llama-3.1-70b")

    def test_budget_to_effort_low(self, adapter):
        """Test budget to effort mapping for low effort."""
        assert adapter._budget_to_effort(1000) == "low"
        assert adapter._budget_to_effort(4000) == "low"
        assert adapter._budget_to_effort(4095) == "low"

    def test_budget_to_effort_medium(self, adapter):
        """Test budget to effort mapping for medium effort."""
        assert adapter._budget_to_effort(4096) == "medium"
        assert adapter._budget_to_effort(10000) == "medium"
        assert adapter._budget_to_effort(16383) == "medium"

    def test_budget_to_effort_high(self, adapter):
        """Test budget to effort mapping for high effort."""
        assert adapter._budget_to_effort(16384) == "high"
        assert adapter._budget_to_effort(32000) == "high"
        assert adapter._budget_to_effort(100000) == "high"

    def test_build_request_with_thinking(self, adapter):
        """Test request building with thinking enabled (Responses API format)."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "test"},
        ]
        request = adapter.build_request(
            messages=messages,
            enable_thinking=True,
            budget_tokens=10000,
            model="o3",
            max_tokens=4096,
        )

        # Responses API uses 'input' not 'messages'
        assert "input" in request
        assert "messages" not in request
        assert len(request["input"]) == 2

        # System becomes developer role
        assert request["input"][0]["role"] == "developer"
        assert request["input"][0]["type"] == "message"

        # User stays user
        assert request["input"][1]["role"] == "user"

        # Reasoning config
        assert request["reasoning"]["effort"] == "medium"
        assert request["reasoning"]["summary"] == "detailed"

        # Other params
        assert request["stream"] is True
        assert request["model"] == "o3"
        assert request["max_output_tokens"] == 4096

    def test_build_request_without_thinking(self, adapter):
        """Test request building with thinking disabled."""
        messages = [{"role": "user", "content": "test"}]
        request = adapter.build_request(
            messages=messages,
            enable_thinking=False,
            model="o3",
        )

        assert "reasoning" not in request
        assert request["stream"] is True
        assert "input" in request

    def test_build_request_message_role_mapping(self, adapter):
        """Test that message roles are correctly mapped to Responses API."""
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "usr"},
            {"role": "assistant", "content": "ast"},
        ]
        request = adapter.build_request(
            messages=messages,
            enable_thinking=False,
            model="o3",
        )

        assert request["input"][0]["role"] == "developer"
        assert request["input"][1]["role"] == "user"
        assert request["input"][2]["role"] == "assistant"

class TestLiteLLMReasoningAdapter:
    """Tests for LiteLLMReasoningAdapter (fallback reasoning)."""

    @pytest.fixture
    def adapter(self):
        """Create adapter instance for tests."""
        return LiteLLMReasoningAdapter()

    def test_supports_deepseek_r1(self, adapter):
        """Test that DeepSeek R1 models are recognized."""
        assert adapter.supports_reasoning("deepseek-r1")
        assert adapter.supports_reasoning("deepseek-r1-lite")
        assert adapter.supports_reasoning("deepseek-reasoner")

    def test_supports_gemini_thinking(self, adapter):
        """Test that Gemini thinking models are recognized."""
        assert adapter.supports_reasoning("gemini-2.5-thinking")
        assert adapter.supports_reasoning("gemini-2.5-pro")
        assert adapter.supports_reasoning("gemini-2.5-flash")
        assert adapter.supports_reasoning("gemini-3.0-ultra")

    def test_supports_qwq(self, adapter):
        """Test that QwQ models are recognized."""
        assert adapter.supports_reasoning("qwq-32b")
        assert adapter.supports_reasoning("qwq-72b")

    def test_supports_ollama_think_suffix(self, adapter):
        """Test that Ollama models with /think suffix are recognized."""
        assert adapter.supports_reasoning("ollama/llama3/think")
        assert adapter.supports_reasoning("qwen:32b/think")

    def test_does_not_support_unknown_models(self, adapter):
        """Test that unknown models are conservatively rejected."""
        assert not adapter.supports_reasoning("gpt-4")
        assert not adapter.supports_reasoning("claude-3-5-sonnet")
        assert not adapter.supports_reasoning("llama-3.1-70b")
        assert not adapter.supports_reasoning("deepseek-v2")  # No r1/reasoner

    def test_budget_to_effort_low(self, adapter):
        """Test budget to effort mapping for low effort."""
        assert adapter._budget_to_effort(1000) == "low"
        assert adapter._budget_to_effort(4000) == "low"
        assert adapter._budget_to_effort(4095) == "low"

    def test_budget_to_effort_medium(self, adapter):
        """Test budget to effort mapping for medium effort."""
        assert adapter._budget_to_effort(4096) == "medium"
        assert adapter._budget_to_effort(10000) == "medium"
        assert adapter._budget_to_effort(16383) == "medium"

    def test_budget_to_effort_high(self, adapter):
        """Test budget to effort mapping for high effort."""
        assert adapter._budget_to_effort(16384) == "high"
        assert adapter._budget_to_effort(32000) == "high"

    def test_build_request_with_thinking(self, adapter):
        """Test request building with thinking enabled (Chat Completions format)."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "test"},
        ]
        request = adapter.build_request(
            messages=messages,
            enable_thinking=True,
            budget_tokens=10000,
            model="deepseek-r1",
            max_tokens=4096,
        )

        # Chat Completions format uses 'messages'
        assert "messages" in request
        assert "input" not in request
        assert request["messages"] == messages

        # reasoning_effort parameter
        assert request["reasoning_effort"] == "medium"

        # Other params
        assert request["stream"] is True
        assert request["model"] == "deepseek-r1"
        assert request["max_tokens"] == 4096

    def test_build_request_without_thinking(self, adapter):
        """Test request building with thinking disabled."""
        messages = [{"role": "user", "content": "test"}]
        request = adapter.build_request(
            messages=messages,
            enable_thinking=False,
            model="deepseek-r1",
        )

        assert "reasoning_effort" not in request
        assert request["stream"] is True
        assert request["messages"] == messages

    def test_build_request_preserves_temperature(self, adapter):
        """Test that temperature is preserved in request."""
        messages = [{"role": "user", "content": "test"}]
        request = adapter.build_request(
            messages=messages,
            enable_thinking=True,
            model="deepseek-r1",
            temperature=0.7,
        )

        assert request["temperature"] == 0.7
