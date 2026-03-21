"""Tests for core.orchestrator.model_detection -- Phase 115.4 + Phase 181.

Covers heuristic classification, provider-based tier resolution,
litellm enrichment, caching, tier override, and singleton.
"""

from unittest.mock import MagicMock, patch

from core.orchestrator.model_detection import (
    ModelDetector,
    ModelProfile,
    ModelTier,
    get_model_detector,
)

def _make_llm(
    model: str, supports_fc: bool | None = None, provider: str | None = None
) -> MagicMock:
    """Create a mock LLM with the given model string."""
    llm = MagicMock()
    llm.model = model
    if provider is not None:
        llm.provider = provider
    else:
        del llm.provider
    if supports_fc is not None:
        llm.supports_function_calling = MagicMock(return_value=supports_fc)
    else:
        # Remove the attribute so hasattr returns False
        del llm.supports_function_calling
    return llm

class TestHeuristicClassify:
    """Tests for heuristic model classification (no provider_hint -- backward compat)."""

    def test_ollama_weak(self):
        detector = ModelDetector()
        llm = _make_llm("ollama/llama3")
        profile = detector.get_model_tier(llm)
        assert profile.tier == ModelTier.WEAK
        assert not profile.supports_tools

    def test_openai_frontier(self):
        detector = ModelDetector()
        llm = _make_llm("openai/gpt-4o")
        profile = detector.get_model_tier(llm)
        assert profile.tier == ModelTier.FRONTIER
        assert profile.supports_tools
        assert profile.supports_structured_output

    def test_anthropic_frontier(self):
        detector = ModelDetector()
        llm = _make_llm("anthropic/claude-3-opus")
        profile = detector.get_model_tier(llm)
        assert profile.tier == ModelTier.FRONTIER

    def test_vllm_known_strong_family(self):
        """vLLM with known model family (qwen, mistral, etc.) -> STRONG."""
        detector = ModelDetector()
        for name in ["vllm/qwen3-8b", "vllm/ministral-8b", "vllm/llama-3.3-70b"]:
            detector.clear_cache()
            llm = _make_llm(name, supports_fc=True)
            profile = detector.get_model_tier(llm)
            assert profile.tier == ModelTier.STRONG, f"{name} should be STRONG"

    def test_vllm_gpt_oss_moderate(self):
        """vLLM with gpt-oss (broken tool calling) -> MODERATE."""
        detector = ModelDetector()
        llm = _make_llm("vllm/gpt-oss-20b", supports_fc=True)
        profile = detector.get_model_tier(llm)
        assert profile.tier == ModelTier.MODERATE

    def test_vllm_unknown_moderate(self):
        """vLLM with unknown model name -> MODERATE (safe default)."""
        detector = ModelDetector()
        llm = _make_llm("vllm/my-custom-finetune")
        profile = detector.get_model_tier(llm)
        assert profile.tier == ModelTier.MODERATE

    def test_unknown_moderate(self):
        detector = ModelDetector()
        llm = _make_llm("custom/my-model")
        profile = detector.get_model_tier(llm)
        assert profile.tier == ModelTier.MODERATE

    def test_vllm_class_generic_name_moderate(self):
        """VLLMBaseLLM with generic --served-model-name -> MODERATE."""
        detector = ModelDetector()
        llm = MagicMock(spec_set=["model", "supports_function_calling"])
        llm.model = "local-llm"
        llm.supports_function_calling = MagicMock(return_value=True)
        type(llm).__name__ = "VLLMBaseLLM"
        profile = detector.get_model_tier(llm)
        assert profile.tier == ModelTier.MODERATE

    def test_vllm_class_descriptive_name_strong(self):
        """VLLMBaseLLM with descriptive --served-model-name -> STRONG."""
        detector = ModelDetector()
        llm = MagicMock(spec_set=["model", "supports_function_calling"])
        llm.model = "qwen3-8b"
        llm.supports_function_calling = MagicMock(return_value=True)
        type(llm).__name__ = "VLLMBaseLLM"
        profile = detector.get_model_tier(llm)
        assert profile.tier == ModelTier.STRONG

class TestProviderBasedClassify:
    """Tests for provider-based tier resolution (provider_hint parameter)."""

    def test_anthropic_frontier(self):
        detector = ModelDetector()
        llm = _make_llm("claude-3-opus")
        profile = detector.get_model_tier(llm, provider_hint="anthropic")
        assert profile.tier == ModelTier.FRONTIER

    def test_openai_frontier(self):
        detector = ModelDetector()
        llm = _make_llm("gpt-4o")
        profile = detector.get_model_tier(llm, provider_hint="openai")
        assert profile.tier == ModelTier.FRONTIER

    def test_google_frontier(self):
        detector = ModelDetector()
        llm = _make_llm("gemini-2.0-flash")
        profile = detector.get_model_tier(llm, provider_hint="google")
        assert profile.tier == ModelTier.FRONTIER

    def test_mistral_strong(self):
        detector = ModelDetector()
        llm = _make_llm("mistral-large-latest")
        profile = detector.get_model_tier(llm, provider_hint="mistral")
        assert profile.tier == ModelTier.STRONG

    def test_cohere_strong(self):
        detector = ModelDetector()
        llm = _make_llm("command-r-plus")
        profile = detector.get_model_tier(llm, provider_hint="cohere")
        assert profile.tier == ModelTier.STRONG

    def test_deepseek_strong(self):
        detector = ModelDetector()
        llm = _make_llm("deepseek-chat")
        profile = detector.get_model_tier(llm, provider_hint="deepseek")
        assert profile.tier == ModelTier.STRONG

    def test_groq_strong(self):
        detector = ModelDetector()
        llm = _make_llm("llama-3.3-70b")
        profile = detector.get_model_tier(llm, provider_hint="groq")
        assert profile.tier == ModelTier.STRONG

    def test_together_ai_strong(self):
        detector = ModelDetector()
        llm = _make_llm("meta-llama/Llama-3-70b")
        profile = detector.get_model_tier(llm, provider_hint="together_ai")
        assert profile.tier == ModelTier.STRONG

    def test_xai_frontier(self):
        detector = ModelDetector()
        llm = _make_llm("grok-2")
        profile = detector.get_model_tier(llm, provider_hint="xai")
        assert profile.tier == ModelTier.FRONTIER

    def test_bedrock_frontier(self):
        detector = ModelDetector()
        llm = _make_llm("anthropic.claude-3-sonnet")
        profile = detector.get_model_tier(llm, provider_hint="bedrock")
        assert profile.tier == ModelTier.FRONTIER

    def test_vllm_qwen_strong(self):
        """vLLM with provider_hint still uses family sub-classification."""
        detector = ModelDetector()
        llm = _make_llm("qwen3-8b")
        profile = detector.get_model_tier(llm, provider_hint="vllm")
        assert profile.tier == ModelTier.STRONG

    def test_vllm_unknown_moderate(self):
        """vLLM with unknown model name -> MODERATE."""
        detector = ModelDetector()
        llm = _make_llm("local-llm")
        profile = detector.get_model_tier(llm, provider_hint="vllm")
        assert profile.tier == ModelTier.MODERATE

    def test_ollama_weak(self):
        detector = ModelDetector()
        llm = _make_llm("llama3")
        profile = detector.get_model_tier(llm, provider_hint="ollama")
        assert profile.tier == ModelTier.WEAK

    def test_no_hint_backward_compat(self):
        """No provider_hint falls back to _build_key heuristic."""
        detector = ModelDetector()
        llm = _make_llm("openai/gpt-4o")
        profile = detector.get_model_tier(llm, provider_hint=None)
        assert profile.tier == ModelTier.FRONTIER

    def test_unknown_provider_moderate(self):
        """Unknown provider defaults to MODERATE (fail-safe)."""
        detector = ModelDetector()
        llm = _make_llm("some-model")
        profile = detector.get_model_tier(llm, provider_hint="some_new_provider")
        assert profile.tier == ModelTier.MODERATE

    def test_provider_hint_overrides_model_string(self):
        """Provider hint takes priority -- model string doesn't matter for cloud."""
        detector = ModelDetector()
        # Model string looks like nothing recognizable, but provider says anthropic
        llm = _make_llm("my-fine-tuned-model-v2")
        profile = detector.get_model_tier(llm, provider_hint="anthropic")
        assert profile.tier == ModelTier.FRONTIER

class TestLiteLLMEnrichment:
    """Tests for litellm.get_model_info() enrichment on cloud providers."""

    def test_enrichment_sets_supports_tools(self):
        """litellm enrichment populates supports_tools and max_tokens."""
        detector = ModelDetector()
        llm = _make_llm("gpt-4o")
        mock_info = {
            "supports_function_calling": True,
            "max_output_tokens": 16384,
        }
        with patch("litellm.get_model_info", return_value=mock_info):
            profile = detector.get_model_tier(llm, provider_hint="openai")
        assert profile.supports_tools is True
        assert profile.max_tokens == 16384

    def test_enrichment_exception_fallback(self):
        """litellm throws -> fall back to static map defaults (no crash)."""
        detector = ModelDetector()
        llm = _make_llm("gpt-4o")
        with patch("litellm.get_model_info", side_effect=Exception("unknown model")):
            profile = detector.get_model_tier(llm, provider_hint="openai")
        assert profile.tier == ModelTier.FRONTIER
        assert profile.supports_tools is True  # cloud default
        assert profile.max_tokens is None

    def test_enrichment_supports_tools_false(self):
        """litellm says supports_function_calling=False -> honor it."""
        detector = ModelDetector()
        llm = _make_llm("some-embedding-model")
        mock_info = {
            "supports_function_calling": False,
            "max_output_tokens": 4096,
        }
        with patch("litellm.get_model_info", return_value=mock_info):
            profile = detector.get_model_tier(llm, provider_hint="openai")
        assert profile.supports_tools is False
        assert profile.max_tokens == 4096

    def test_enrichment_supports_tools_none_defaults_true(self):
        """litellm returns None for supports_function_calling -> default True for cloud."""
        detector = ModelDetector()
        llm = _make_llm("gpt-4o")
        mock_info = {
            "supports_function_calling": None,
            "max_output_tokens": None,
        }
        with patch("litellm.get_model_info", return_value=mock_info):
            profile = detector.get_model_tier(llm, provider_hint="openai")
        assert profile.supports_tools is True  # cloud default when None

class TestCacheKeyWithProvider:
    """Tests that cache key incorporates provider_hint."""

    def test_same_model_different_provider(self):
        """Same model string with different provider_hint -> different cache entries."""
        detector = ModelDetector()
        llm = _make_llm("llama-3.3-70b")
        p1 = detector.get_model_tier(llm, provider_hint="groq")
        p2 = detector.get_model_tier(llm, provider_hint="vllm")
        assert p1.tier == ModelTier.STRONG  # groq = cloud STRONG
        assert p2.tier == ModelTier.STRONG  # vllm + llama family = STRONG
        # But they must be separate cache entries
        assert "groq:llama-3.3-70b" in detector._cache
        assert "vllm:llama-3.3-70b" in detector._cache

    def test_no_hint_uses_model_key_only(self):
        """No provider_hint -> cache key is just the model key."""
        detector = ModelDetector()
        llm = _make_llm("openai/gpt-4o")
        detector.get_model_tier(llm)
        assert "openai/gpt-4o" in detector._cache

class TestCaching:
    """Tests for model profile caching."""

    def test_cache_hit(self):
        detector = ModelDetector()
        llm = _make_llm("openai/gpt-4o")
        p1 = detector.get_model_tier(llm)
        p2 = detector.get_model_tier(llm)
        assert p1 is p2
        assert "openai/gpt-4o" in detector._cache

    def test_clear_cache(self):
        detector = ModelDetector()
        llm = _make_llm("openai/gpt-4o")
        detector.get_model_tier(llm)
        assert len(detector._cache) > 0
        detector.clear_cache()
        assert len(detector._cache) == 0

class TestTierOverride:
    """Test tier override via ModelTier enum construction."""

    def test_tier_override_construction(self):
        """Verify the code path used when config.model_tier_override is set."""
        override_tier = ModelTier("weak")
        detector = ModelDetector()
        profile = ModelProfile(
            tier=override_tier,
            supports_tools=override_tier != ModelTier.WEAK,
            supports_structured_output=override_tier in (ModelTier.STRONG, ModelTier.FRONTIER),
            calibration_score=detector._tier_to_score(override_tier),
            model_key="override/weak",
        )
        assert profile.tier == ModelTier.WEAK
        assert not profile.supports_tools
        assert not profile.supports_structured_output
        assert profile.calibration_score == 0.2

class TestTierDowngrade:
    """Tests for ModelDetector.downgrade_tier() static method."""

    def test_downgrade_frontier_to_strong(self):
        assert ModelDetector.downgrade_tier(ModelTier.FRONTIER) == ModelTier.STRONG

    def test_downgrade_strong_to_moderate(self):
        assert ModelDetector.downgrade_tier(ModelTier.STRONG) == ModelTier.MODERATE

    def test_downgrade_moderate_to_weak(self):
        assert ModelDetector.downgrade_tier(ModelTier.MODERATE) == ModelTier.WEAK

    def test_downgrade_weak_stays_weak(self):
        """WEAK is the floor -- can't go lower."""
        assert ModelDetector.downgrade_tier(ModelTier.WEAK) == ModelTier.WEAK

class TestSingleton:
    """Test singleton pattern."""

    def test_singleton(self):
        # Reset singleton for test isolation
        import core.orchestrator.model_detection as mod

        mod._model_detector = None
        d1 = get_model_detector()
        d2 = get_model_detector()
        assert d1 is d2
