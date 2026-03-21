"""Unit tests for core.factory.relevance.

Covers: get_factory_config(), check_existing_capabilities(),
detect_gaps(), get_proactive_suggestions(), name normalization,
Jaccard similarity.
"""

from unittest.mock import AsyncMock, patch

import pytest

from core.factory.models import FactoryConfig
from core.factory.relevance import (
    _name_jaccard,
    _normalize_name,
    get_factory_config,
)

# ---------------------------------------------------------------------------
# get_factory_config singleton
# ---------------------------------------------------------------------------

class TestGetFactoryConfig:
    """FactoryConfig singleton creation."""

    def test_returns_factory_config(self):
        """Returns a FactoryConfig instance."""
        # Reset the singleton for testing
        import core.factory.relevance as relevance_mod

        old_config = relevance_mod._config
        relevance_mod._config = None
        try:
            config = get_factory_config()
            assert isinstance(config, FactoryConfig)
        finally:
            relevance_mod._config = old_config

    def test_returns_same_instance(self):
        """Singleton returns the same object on repeated calls."""
        config1 = get_factory_config()
        config2 = get_factory_config()
        assert config1 is config2

    def test_config_has_expected_fields(self):
        config = get_factory_config()
        assert hasattr(config, "proactive_detection_enabled")
        assert hasattr(config, "proactive_max_suggestions_per_day")
        assert hasattr(config, "deduplication_name_jaccard_threshold")

    def test_env_override_proactive_enabled(self):
        """Environment variable overrides proactive_detection_enabled."""
        import core.factory.relevance as relevance_mod

        old_config = relevance_mod._config
        relevance_mod._config = None
        try:
            with patch.dict("os.environ", {"DRYADE_FACTORY_PROACTIVE_ENABLED": "true"}):
                config = get_factory_config()
                assert config.proactive_detection_enabled is True
        finally:
            relevance_mod._config = old_config

# ---------------------------------------------------------------------------
# Name normalization and Jaccard similarity
# ---------------------------------------------------------------------------

class TestNameNormalization:
    """Name normalization for comparison."""

    def test_lowercase(self):
        result = _normalize_name("WebSearch_Agent")
        assert result == result.lower()

    def test_strips_agent_suffix(self):
        result = _normalize_name("websearch agent")
        assert "agent" not in result

    def test_strips_tool_suffix(self):
        result = _normalize_name("json_parser tool")
        assert "tool" not in result

    def test_replaces_separators(self):
        result = _normalize_name("web-search_helper")
        assert "-" not in result
        assert "_" not in result

    def test_sorted_tokens(self):
        """Tokens are sorted alphabetically for order-independent comparison."""
        result = _normalize_name("data web search")
        tokens = result.split()
        assert tokens == sorted(tokens)

class TestNameJaccard:
    """Token-level Jaccard similarity."""

    def test_identical_names(self):
        score = _name_jaccard("websearch", "websearch")
        assert score == 1.0

    def test_completely_different(self):
        score = _name_jaccard("abc", "xyz")
        assert score == 0.0

    def test_partial_overlap(self):
        """Names sharing some but not all tokens have 0 < Jaccard < 1."""
        score = _name_jaccard("web_search_data", "web_search_image")
        assert 0.0 < score < 1.0

    def test_empty_name(self):
        score = _name_jaccard("", "something")
        assert score == 0.0

    def test_symmetric(self):
        """Jaccard is symmetric: J(a,b) == J(b,a)."""
        s1 = _name_jaccard("web search", "search web helper")
        s2 = _name_jaccard("search web helper", "web search")
        assert abs(s1 - s2) < 1e-9

# ---------------------------------------------------------------------------
# check_existing_capabilities
# ---------------------------------------------------------------------------

class TestCheckExistingCapabilities:
    """Three-stage dedup: name Jaccard -> embedding -> LLM."""

    @pytest.mark.asyncio
    async def test_empty_capabilities_returns_empty(self):
        """No registered capabilities means no warnings."""
        from core.factory.relevance import check_existing_capabilities

        with patch(
            "core.factory.relevance._get_all_capability_names",
            return_value=[],
        ):
            warnings = await check_existing_capabilities("new_agent", "test goal")
            assert warnings == []

    @pytest.mark.asyncio
    async def test_name_match_produces_warning(self):
        """A capability with high Jaccard name similarity produces a warning."""
        from core.factory.relevance import check_existing_capabilities

        with (
            patch(
                "core.factory.relevance._get_all_capability_names",
                return_value=["websearch_agent", "data_analyzer"],
            ),
            patch(
                "core.factory.relevance.get_factory_config",
                return_value=FactoryConfig(deduplication_name_jaccard_threshold=0.3),
            ),
        ):
            warnings = await check_existing_capabilities("websearch", "web search agent")
            # Should find the websearch_agent match
            assert any("websearch" in w.lower() for w in warnings)

# ---------------------------------------------------------------------------
# detect_gaps
# ---------------------------------------------------------------------------

class TestDetectGaps:
    """Gap detection from routing failures and escalation patterns."""

    @pytest.mark.asyncio
    async def test_no_failures_returns_empty(self):
        """No routing failures or escalations means no gaps."""
        from core.factory.relevance import detect_gaps

        with (
            patch(
                "core.factory.relevance._detect_routing_failure_gaps",
                return_value=[],
            ),
            patch(
                "core.factory.relevance._detect_escalation_gaps",
                return_value=[],
            ),
        ):
            gaps = await detect_gaps()
            assert gaps == []

# ---------------------------------------------------------------------------
# get_proactive_suggestions: rate limiting
# ---------------------------------------------------------------------------

class TestProactiveSuggestions:
    """Proactive suggestion pipeline with rate limiting."""

    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self):
        """When proactive_detection_enabled=False, returns empty list."""
        from core.factory.relevance import get_proactive_suggestions

        disabled_config = FactoryConfig(proactive_detection_enabled=False)
        with (
            patch(
                "core.factory.relevance.get_factory_config",
                return_value=disabled_config,
            ),
            patch(
                "core.factory.relevance.detect_gaps",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            suggestions = await get_proactive_suggestions()
            assert suggestions == []

    @pytest.mark.asyncio
    async def test_no_signals_returns_empty(self):
        """No signals means no suggestions regardless of config."""
        from core.factory.relevance import get_proactive_suggestions

        with patch(
            "core.factory.relevance.detect_gaps",
            new_callable=AsyncMock,
            return_value=[],
        ):
            suggestions = await get_proactive_suggestions()
            assert suggestions == []
