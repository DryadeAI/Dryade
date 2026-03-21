"""Tests for core.orchestrator.model_detection -- Phase 115.4.

Covers heuristic classification, caching, tier override, and singleton.
"""

from unittest.mock import MagicMock

from core.orchestrator.model_detection import (
    ModelDetector,
    ModelProfile,
    ModelTier,
    get_model_detector,
)

def _make_llm(model: str, supports_fc: bool | None = None) -> MagicMock:
    """Create a mock LLM with the given model string."""
    llm = MagicMock()
    llm.model = model
    llm.provider = None
    if supports_fc is not None:
        llm.supports_function_calling = MagicMock(return_value=supports_fc)
    else:
        # Remove the attribute so hasattr returns False
        del llm.supports_function_calling
    return llm

class TestHeuristicClassify:
    """Tests for heuristic model classification."""

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

class TestSingleton:
    """Test singleton pattern."""

    def test_singleton(self):
        # Reset singleton for test isolation
        import core.orchestrator.model_detection as mod

        mod._model_detector = None
        d1 = get_model_detector()
        d2 = get_model_detector()
        assert d1 is d2
