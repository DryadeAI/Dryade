"""
Unit tests for model_selection_enhanced plugin.

Tests cover:
1. Plugin protocol implementation
2. Config module (UseCase, Provider, ModelSpec, MODELS catalog)
3. Model lookup by ID, use-case, provider
4. Recommendation engine (fast/quality/cheap)
5. Pricing retrieval
6. Model listing and summary
"""

import pytest

@pytest.mark.unit
class TestModelSelectionEnhancedPlugin:
    """Tests for ModelSelectionEnhancedPlugin protocol implementation."""

    def test_plugin_protocol_attributes(self):
        """Test plugin has required protocol attributes."""
        from plugins.model_selection_enhanced.plugin import ModelSelectionEnhancedPlugin

        plugin = ModelSelectionEnhancedPlugin()
        assert plugin.name == "model_selection_enhanced"
        assert plugin.version == "1.0.0"
        assert hasattr(plugin, "register")
        assert hasattr(plugin, "startup")
        assert hasattr(plugin, "shutdown")

    def test_plugin_cost_tracker_initially_unavailable(self):
        """Test cost tracker not available before startup."""
        from plugins.model_selection_enhanced.plugin import ModelSelectionEnhancedPlugin

        plugin = ModelSelectionEnhancedPlugin()
        assert plugin._cost_tracker_available is False

    def test_plugin_shutdown_clears_cost_tracker(self):
        """Test shutdown clears cost tracker reference."""
        from plugins.model_selection_enhanced.plugin import ModelSelectionEnhancedPlugin

        plugin = ModelSelectionEnhancedPlugin()
        plugin._cost_tracker_available = True
        plugin._cost_tracker = "fake"
        plugin.shutdown()
        assert plugin._cost_tracker is None
        assert plugin._cost_tracker_available is False

@pytest.mark.unit
class TestModelSelectionConfig:
    """Tests for config module enums and data classes."""

    def test_use_case_enum_values(self):
        """Test UseCase enum has expected values."""
        from plugins.model_selection_enhanced.config import UseCase

        assert UseCase.FAST.value == "fast"
        assert UseCase.QUALITY.value == "quality"
        assert UseCase.CHEAP.value == "cheap"

    def test_provider_enum_values(self):
        """Test Provider enum has expected values."""
        from plugins.model_selection_enhanced.config import Provider

        assert Provider.OPENAI.value == "openai"
        assert Provider.ANTHROPIC.value == "anthropic"
        assert Provider.GOOGLE.value == "google"
        assert Provider.GROQ.value == "groq"
        assert Provider.OLLAMA.value == "ollama"

    def test_model_catalog_populated(self):
        """Test MODELS catalog has entries."""
        from plugins.model_selection_enhanced.config import MODELS

        assert len(MODELS) >= 10  # At least 10 models defined

    def test_model_spec_fields(self):
        """Test ModelSpec has all required fields."""
        from plugins.model_selection_enhanced.config import MODELS, ModelCosts, Provider, UseCase

        model = MODELS["gpt-4o"]
        assert model.id == "gpt-4o"
        assert model.provider == Provider.OPENAI
        assert model.use_case == UseCase.QUALITY
        assert model.context_window == 128000
        assert model.supports_vision is True
        assert isinstance(model.costs, ModelCosts)

@pytest.mark.unit
class TestModelLookup:
    """Tests for model lookup functions."""

    def test_get_model_existing(self):
        """Test get_model returns correct model."""
        from plugins.model_selection_enhanced.config import get_model

        model = get_model("gpt-4o")
        assert model is not None
        assert model.id == "gpt-4o"

    def test_get_model_nonexistent(self):
        """Test get_model returns None for unknown model."""
        from plugins.model_selection_enhanced.config import get_model

        assert get_model("nonexistent-model") is None

    def test_get_models_by_use_case_fast(self):
        """Test filtering by FAST use case."""
        from plugins.model_selection_enhanced.config import UseCase, get_models_by_use_case

        fast_models = get_models_by_use_case(UseCase.FAST)
        assert len(fast_models) >= 1
        for m in fast_models:
            assert m.use_case == UseCase.FAST

    def test_get_models_by_use_case_quality(self):
        """Test filtering by QUALITY use case."""
        from plugins.model_selection_enhanced.config import UseCase, get_models_by_use_case

        quality_models = get_models_by_use_case(UseCase.QUALITY)
        assert len(quality_models) >= 1
        for m in quality_models:
            assert m.use_case == UseCase.QUALITY

    def test_get_models_by_provider(self):
        """Test filtering by provider."""
        from plugins.model_selection_enhanced.config import Provider, get_models_by_provider

        openai_models = get_models_by_provider(Provider.OPENAI)
        assert len(openai_models) >= 1
        for m in openai_models:
            assert m.provider == Provider.OPENAI

    def test_get_models_by_provider_ollama(self):
        """Test Ollama models are all cheap."""
        from plugins.model_selection_enhanced.config import (
            Provider,
            UseCase,
            get_models_by_provider,
        )

        ollama_models = get_models_by_provider(Provider.OLLAMA)
        assert len(ollama_models) >= 1
        for m in ollama_models:
            assert m.use_case == UseCase.CHEAP
            assert m.costs.input == 0.0

@pytest.mark.unit
class TestModelRecommendation:
    """Tests for recommendation functions."""

    def test_get_cheapest_model(self):
        """Test cheapest model selection."""
        from plugins.model_selection_enhanced.config import get_cheapest_model

        cheapest = get_cheapest_model()
        assert cheapest is not None
        # Should be an Ollama model (free) or cheapest priced
        assert cheapest.costs is not None
        assert (cheapest.costs.input + cheapest.costs.output) >= 0.0

    def test_get_fastest_model(self):
        """Test fastest model selection."""
        from plugins.model_selection_enhanced.config import UseCase, get_fastest_model

        fastest = get_fastest_model()
        assert fastest is not None
        assert fastest.use_case == UseCase.FAST

    def test_get_quality_model(self):
        """Test quality model selection."""
        from plugins.model_selection_enhanced.config import UseCase, get_quality_model

        quality = get_quality_model()
        assert quality is not None
        assert quality.use_case == UseCase.QUALITY

    def test_get_fastest_model_by_provider(self):
        """Test fastest model filtered by provider."""
        from plugins.model_selection_enhanced.config import Provider, UseCase, get_fastest_model

        fastest_groq = get_fastest_model(Provider.GROQ)
        assert fastest_groq is not None
        assert fastest_groq.provider == Provider.GROQ
        assert fastest_groq.use_case == UseCase.FAST

    def test_get_quality_model_by_provider(self):
        """Test quality model filtered by provider."""
        from plugins.model_selection_enhanced.config import Provider, get_quality_model

        quality_anthropic = get_quality_model(Provider.ANTHROPIC)
        assert quality_anthropic is not None
        assert quality_anthropic.provider == Provider.ANTHROPIC

    def test_recommend_model_via_plugin(self):
        """Test recommend_model method on plugin."""
        from plugins.model_selection_enhanced.plugin import ModelSelectionEnhancedPlugin

        plugin = ModelSelectionEnhancedPlugin()
        model = plugin.recommend_model(preference="fast")
        assert model is not None

    def test_recommend_model_quality_default(self):
        """Test recommend_model defaults to quality."""
        from plugins.model_selection_enhanced.plugin import ModelSelectionEnhancedPlugin

        plugin = ModelSelectionEnhancedPlugin()
        model = plugin.recommend_model()  # default="quality"
        assert model is not None

@pytest.mark.unit
class TestModelListing:
    """Tests for model listing and summary."""

    def test_list_all_models(self):
        """Test list_all_models returns dicts with expected fields."""
        from plugins.model_selection_enhanced.config import list_all_models

        models = list_all_models()
        assert len(models) >= 10
        for m in models:
            assert "id" in m
            assert "provider" in m
            assert "use_case" in m
            assert "context_window" in m

    def test_get_models_summary(self):
        """Test get_models_summary returns counts."""
        from plugins.model_selection_enhanced.plugin import ModelSelectionEnhancedPlugin

        plugin = ModelSelectionEnhancedPlugin()
        summary = plugin.get_models_summary()
        assert "total" in summary
        assert "by_use_case" in summary
        assert "by_provider" in summary
        assert summary["total"] >= 10
        assert "fast" in summary["by_use_case"]
        assert "quality" in summary["by_use_case"]
        assert "cheap" in summary["by_use_case"]

    def test_get_pricing_builtin(self):
        """Test get_pricing falls back to built-in costs."""
        from plugins.model_selection_enhanced.plugin import ModelSelectionEnhancedPlugin

        plugin = ModelSelectionEnhancedPlugin()
        pricing = plugin.get_pricing("gpt-4o")
        assert pricing is not None
        assert "input" in pricing
        assert "output" in pricing
        assert pricing["input"] == 2.50
        assert pricing["output"] == 10.00

    def test_get_pricing_unknown_returns_none(self):
        """Test get_pricing returns None for unknown model."""
        from plugins.model_selection_enhanced.plugin import ModelSelectionEnhancedPlugin

        plugin = ModelSelectionEnhancedPlugin()
        assert plugin.get_pricing("nonexistent-model") is None
