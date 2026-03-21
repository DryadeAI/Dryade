"""Integration tests for multi-provider reasoning support.

These tests validate the reasoning adapter system works correctly across
all supported providers. Tests are split into:
- Unit-level tests (no API keys needed): adapter selection, filtering
- E2E tests (skipped if API keys missing): actual provider calls

Environment variables for E2E tests:
- ANTHROPIC_API_KEY: Required for Anthropic Extended Thinking tests
- OPENAI_API_KEY: Required for OpenAI Responses API tests
- VLLM_BASE_URL: Required for vLLM reasoning tests
"""

import os

import pytest

class TestReasoningAdapterSelection:
    """Test that correct adapters are selected for each provider/model combination."""

    def test_anthropic_adapter_selected_for_claude_4(self):
        """Test Anthropic adapter selected for Claude 4+ models."""
        from core.providers.reasoning import AnthropicReasoningAdapter, get_reasoning_adapter

        adapter = get_reasoning_adapter("anthropic", "claude-sonnet-4-5")
        assert isinstance(adapter, AnthropicReasoningAdapter)

    def test_anthropic_adapter_selected_for_claude_3_7(self):
        """Test Anthropic adapter selected for Claude 3.7 models."""
        from core.providers.reasoning import AnthropicReasoningAdapter, get_reasoning_adapter

        adapter = get_reasoning_adapter("anthropic", "claude-3-7-sonnet")
        assert isinstance(adapter, AnthropicReasoningAdapter)

    def test_anthropic_non_thinking_model_still_returns_adapter(self):
        """Test that non-thinking Anthropic models still return adapter.

        The adapter is returned for the provider, but supports_reasoning() will
        return False for non-thinking models. This allows graceful fallback.
        """
        from core.providers.reasoning import AnthropicReasoningAdapter, get_reasoning_adapter

        adapter = get_reasoning_adapter("anthropic", "claude-3-5-sonnet")
        # Adapter is returned (for provider), but model doesn't support reasoning
        assert isinstance(adapter, AnthropicReasoningAdapter)
        assert not adapter.supports_reasoning("claude-3-5-sonnet")

    def test_openai_responses_adapter_selected_for_o1(self):
        """Test OpenAI Responses adapter selected for o1 models."""
        from core.providers.reasoning import OpenAIResponsesAdapter, get_reasoning_adapter

        adapter = get_reasoning_adapter("openai", "o1")
        assert isinstance(adapter, OpenAIResponsesAdapter)

    def test_openai_responses_adapter_selected_for_o3(self):
        """Test OpenAI Responses adapter selected for o3 models."""
        from core.providers.reasoning import OpenAIResponsesAdapter, get_reasoning_adapter

        adapter = get_reasoning_adapter("openai", "o3-pro")
        assert isinstance(adapter, OpenAIResponsesAdapter)

    def test_openai_gpt_uses_litellm_fallback(self):
        """Test that GPT models use LiteLLM fallback adapter."""
        from core.providers.reasoning import LiteLLMReasoningAdapter, get_reasoning_adapter

        adapter = get_reasoning_adapter("openai", "gpt-4-turbo")
        assert isinstance(adapter, LiteLLMReasoningAdapter)

    def test_litellm_adapter_for_deepseek_r1(self):
        """Test LiteLLM adapter selected for DeepSeek R1."""
        from core.providers.reasoning import LiteLLMReasoningAdapter, get_reasoning_adapter

        adapter = get_reasoning_adapter("litellm", "deepseek-r1")
        assert isinstance(adapter, LiteLLMReasoningAdapter)

    def test_litellm_adapter_for_gemini_thinking(self):
        """Test LiteLLM adapter selected for Gemini thinking models."""
        from core.providers.reasoning import LiteLLMReasoningAdapter, get_reasoning_adapter

        adapter = get_reasoning_adapter("litellm", "gemini-2.5-thinking")
        assert isinstance(adapter, LiteLLMReasoningAdapter)

    def test_vllm_returns_none(self):
        """Test that vLLM provider returns None (uses native VLLMBaseLLM path)."""
        from core.providers.reasoning import get_reasoning_adapter

        adapter = get_reasoning_adapter("vllm", "qwen3")
        assert adapter is None  # Signals use VLLMBaseLLM path

    def test_ollama_uses_litellm_fallback(self):
        """Test that Ollama provider uses LiteLLM fallback adapter."""
        from core.providers.reasoning import LiteLLMReasoningAdapter, get_reasoning_adapter

        adapter = get_reasoning_adapter("ollama", "llama3:70b")
        # Ollama routes to LiteLLM fallback (not None)
        assert isinstance(adapter, LiteLLMReasoningAdapter)

class TestSemanticCacheFiltering:
    """Test that semantic cache correctly handles reasoning kwargs."""

    def test_enable_thinking_not_filtered_for_anthropic(self):
        """Test enable_thinking preserved for Anthropic provider."""
        wrapper = pytest.importorskip(
            "plugins.semantic_cache.wrapper", reason="semantic_cache plugin not available"
        )
        REASONING_CAPABLE_PROVIDERS = wrapper.REASONING_CAPABLE_PROVIDERS

        assert "anthropic" in REASONING_CAPABLE_PROVIDERS

    def test_enable_thinking_not_filtered_for_openai(self):
        """Test enable_thinking preserved for OpenAI provider."""
        wrapper = pytest.importorskip(
            "plugins.semantic_cache.wrapper", reason="semantic_cache plugin not available"
        )
        REASONING_CAPABLE_PROVIDERS = wrapper.REASONING_CAPABLE_PROVIDERS

        assert "openai" in REASONING_CAPABLE_PROVIDERS

    def test_enable_thinking_not_filtered_for_vllm(self):
        """Test enable_thinking preserved for vLLM provider."""
        wrapper = pytest.importorskip(
            "plugins.semantic_cache.wrapper", reason="semantic_cache plugin not available"
        )
        REASONING_CAPABLE_PROVIDERS = wrapper.REASONING_CAPABLE_PROVIDERS

        assert "vllm" in REASONING_CAPABLE_PROVIDERS

    def test_enable_thinking_not_filtered_for_litellm(self):
        """Test enable_thinking preserved for LiteLLM provider."""
        wrapper = pytest.importorskip(
            "plugins.semantic_cache.wrapper", reason="semantic_cache plugin not available"
        )
        REASONING_CAPABLE_PROVIDERS = wrapper.REASONING_CAPABLE_PROVIDERS

        assert "litellm" in REASONING_CAPABLE_PROVIDERS

    def test_enable_thinking_not_filtered_for_ollama(self):
        """Test enable_thinking preserved for Ollama provider."""
        wrapper = pytest.importorskip(
            "plugins.semantic_cache.wrapper", reason="semantic_cache plugin not available"
        )
        REASONING_CAPABLE_PROVIDERS = wrapper.REASONING_CAPABLE_PROVIDERS

        assert "ollama" in REASONING_CAPABLE_PROVIDERS

    def test_vllm_only_kwargs_excludes_enable_thinking(self):
        """Test that enable_thinking is NOT in vLLM-only kwargs list."""
        wrapper = pytest.importorskip(
            "plugins.semantic_cache.wrapper", reason="semantic_cache plugin not available"
        )
        _VLLM_ONLY_KWARGS = wrapper._VLLM_ONLY_KWARGS

        assert "enable_thinking" not in _VLLM_ONLY_KWARGS

    def test_vllm_only_kwargs_includes_correct_params(self):
        """Test that vLLM-only kwargs contains expected parameters."""
        wrapper = pytest.importorskip(
            "plugins.semantic_cache.wrapper", reason="semantic_cache plugin not available"
        )
        _VLLM_ONLY_KWARGS = wrapper._VLLM_ONLY_KWARGS

        # These are vLLM-specific parameters that should be filtered
        assert "add_generation_prompt" in _VLLM_ONLY_KWARGS
        assert "continue_final_message" in _VLLM_ONLY_KWARGS

class TestReasoningAdapterBuildRequest:
    """Test that adapters build correct request formats."""

    def test_anthropic_builds_thinking_config(self):
        """Test Anthropic adapter builds correct thinking config."""
        from core.providers.reasoning import AnthropicReasoningAdapter

        adapter = AnthropicReasoningAdapter()
        request = adapter.build_request(
            messages=[{"role": "user", "content": "test"}],
            enable_thinking=True,
            model="claude-sonnet-4-5",
            budget_tokens=10000,
            max_tokens=16000,
        )

        assert "thinking" in request
        assert request["thinking"]["type"] == "enabled"
        assert request["thinking"]["budget_tokens"] == 10000
        assert request["stream"] is True

    def test_anthropic_no_thinking_when_disabled(self):
        """Test Anthropic adapter omits thinking when disabled."""
        from core.providers.reasoning import AnthropicReasoningAdapter

        adapter = AnthropicReasoningAdapter()
        request = adapter.build_request(
            messages=[{"role": "user", "content": "test"}],
            enable_thinking=False,
            model="claude-sonnet-4-5",
            max_tokens=4096,
        )

        assert "thinking" not in request

    def test_openai_builds_responses_api_format(self):
        """Test OpenAI adapter builds Responses API format."""
        from core.providers.reasoning import OpenAIResponsesAdapter

        adapter = OpenAIResponsesAdapter()
        request = adapter.build_request(
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "test"},
            ],
            enable_thinking=True,
            model="o3",
            budget_tokens=10000,
        )

        # Responses API uses 'input' not 'messages'
        assert "input" in request
        assert "messages" not in request

        # System role becomes developer
        assert request["input"][0]["role"] == "developer"

        # Has reasoning config
        assert "reasoning" in request
        assert request["reasoning"]["effort"] == "medium"

    def test_litellm_builds_chat_completions_format(self):
        """Test LiteLLM adapter builds Chat Completions format."""
        from core.providers.reasoning import LiteLLMReasoningAdapter

        adapter = LiteLLMReasoningAdapter()
        request = adapter.build_request(
            messages=[{"role": "user", "content": "test"}],
            enable_thinking=True,
            model="deepseek-r1",
            budget_tokens=10000,
        )

        # Chat Completions format uses 'messages'
        assert "messages" in request
        assert "input" not in request

        # Has reasoning_effort
        assert request["reasoning_effort"] == "medium"

class TestSupportsReasoningFunction:
    """Test the supports_reasoning helper function."""

    def test_supports_reasoning_anthropic_thinking_model(self):
        """Test supports_reasoning returns True for Anthropic thinking models."""
        from core.providers.reasoning import supports_reasoning

        assert supports_reasoning("anthropic", "claude-sonnet-4-5") is True
        assert supports_reasoning("anthropic", "claude-3-7-sonnet") is True

    def test_supports_reasoning_anthropic_non_thinking_model(self):
        """Test supports_reasoning returns False for non-thinking models."""
        from core.providers.reasoning import supports_reasoning

        assert supports_reasoning("anthropic", "claude-3-5-sonnet") is False

    def test_supports_reasoning_openai_o_models(self):
        """Test supports_reasoning returns True for OpenAI o-series."""
        from core.providers.reasoning import supports_reasoning

        assert supports_reasoning("openai", "o1") is True
        assert supports_reasoning("openai", "o3-pro") is True

    def test_supports_reasoning_openai_gpt_models(self):
        """Test supports_reasoning returns False for GPT models."""
        from core.providers.reasoning import supports_reasoning

        # GPT models via OpenAI don't support native reasoning
        assert supports_reasoning("openai", "gpt-4-turbo") is False

    def test_supports_reasoning_vllm_reasoning_models(self):
        """Test supports_reasoning returns True for vLLM reasoning models."""
        from core.providers.reasoning import supports_reasoning

        # vLLM reasoning models are detected by model name
        assert supports_reasoning("vllm", "qwen3") is True
        assert supports_reasoning("vllm", "deepseek-r1") is True

    def test_supports_reasoning_vllm_non_reasoning_models(self):
        """Test supports_reasoning returns False for vLLM non-reasoning models."""
        from core.providers.reasoning import supports_reasoning

        # Regular vLLM models don't support reasoning
        assert supports_reasoning("vllm", "llama-3.1-70b") is False

# E2E Tests - skipped if API keys not configured

@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY", "").startswith("sk-ant-"),
    reason="ANTHROPIC_API_KEY not configured",
)
class TestAnthropicReasoningE2E:
    """End-to-end tests for Anthropic Extended Thinking.

    These tests make actual API calls and require ANTHROPIC_API_KEY.
    """

    @pytest.mark.asyncio
    async def test_anthropic_thinking_stream(self):
        """Test that Anthropic extended thinking produces reasoning chunks."""
        from core.providers.reasoning import AnthropicReasoningAdapter

        adapter = AnthropicReasoningAdapter()

        # Skip if model not available
        if not adapter.supports_reasoning("claude-sonnet-4-5"):
            pytest.skip("Claude Sonnet 4.5 not available")

        messages = [{"role": "user", "content": "What is 2+2? Think step by step."}]

        reasoning_chunks = []
        content_chunks = []

        try:
            async for chunk in adapter.stream(
                messages=messages,
                enable_thinking=True,
                model="claude-sonnet-4-5",
                max_tokens=4096,
                budget_tokens=2000,
            ):
                if chunk.type == "reasoning":
                    reasoning_chunks.append(chunk.content)
                elif chunk.type == "content":
                    content_chunks.append(chunk.content)
        except Exception as e:
            if "rate" in str(e).lower() or "quota" in str(e).lower():
                pytest.skip(f"Rate limited or quota exceeded: {e}")
            raise

        # Should have both reasoning and content (or at least content)
        assert len(reasoning_chunks) > 0 or len(content_chunks) > 0

        # Content should mention the answer
        full_content = "".join(content_chunks)
        assert "4" in full_content

@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY", "").startswith("sk-"),
    reason="OPENAI_API_KEY not configured",
)
class TestOpenAIReasoningE2E:
    """End-to-end tests for OpenAI Responses API reasoning.

    These tests make actual API calls and require OPENAI_API_KEY.
    Note: o1/o3 models may not be available to all accounts.
    """

    @pytest.mark.asyncio
    async def test_openai_o1_reasoning_stream(self):
        """Test that OpenAI o1 reasoning produces reasoning chunks."""
        from core.providers.reasoning import OpenAIResponsesAdapter

        adapter = OpenAIResponsesAdapter()

        # o1 models may not be available to all users
        if not adapter.supports_reasoning("o1"):
            pytest.skip("o1 model not supported by adapter")

        messages = [{"role": "user", "content": "What is 15 * 17?"}]

        reasoning_chunks = []
        content_chunks = []

        try:
            async for chunk in adapter.stream(
                messages=messages,
                enable_thinking=True,
                model="o1-preview",
            ):
                if chunk.type == "reasoning":
                    reasoning_chunks.append(chunk.content)
                elif chunk.type == "content":
                    content_chunks.append(chunk.content)
        except Exception as e:
            # May fail if o1 access is limited
            error_msg = str(e).lower()
            if any(
                x in error_msg for x in ["access", "not available", "not found", "rate", "quota"]
            ):
                pytest.skip(f"o1 model access limited: {e}")
            raise

        # Content should have the answer
        full_content = "".join(content_chunks)
        assert "255" in full_content

@pytest.mark.skipif(
    not os.environ.get("VLLM_BASE_URL"),
    reason="VLLM_BASE_URL not configured",
)
class TestVLLMReasoningE2E:
    """End-to-end tests for vLLM reasoning (existing path).

    These tests validate the native VLLMBaseLLM reasoning path still works.
    Requires VLLM_BASE_URL and a reasoning-capable model.
    """

    @pytest.mark.asyncio
    async def test_vllm_reasoning_still_works(self):
        """Test that vLLM reasoning path still works correctly."""
        from plugins.vllm.llm import VLLMBaseLLM

        llm = VLLMBaseLLM()

        # Only test if a reasoning model is configured
        model = os.environ.get("VLLM_MODEL", "")
        reasoning_models = ["qwen3", "deepseek", "granite", "ministral"]
        if not any(rm in model.lower() for rm in reasoning_models):
            pytest.skip("No vLLM reasoning model configured")

        messages = [{"role": "user", "content": "What is 5+5? Think step by step."}]

        chunks = []
        try:
            async for chunk in llm.astream(messages, enable_thinking=True):
                chunks.append(chunk)
        except Exception as e:
            error_msg = str(e).lower()
            if "connection" in error_msg or "timeout" in error_msg:
                pytest.skip(f"vLLM not reachable: {e}")
            raise

        # Should have some chunks
        assert len(chunks) > 0

        # Check for content (reasoning may or may not appear separately)
        has_content = any(
            (isinstance(c, dict) and c.get("type") == "content")
            or (isinstance(c, dict) and c.get("content"))
            or isinstance(c, str)
            for c in chunks
        )
        assert has_content, "Expected some content chunks from vLLM"
