"""Tests for core.orchestrator.explainability -- Phase 115.5.

Covers RoutingExplanation creation and formatting.
"""

from core.orchestrator.explainability import (
    RoutingExplanation,
    build_routing_explanation,
    format_explanation_for_log,
)

# ---- Build routing explanation -----------------------------------------------

class TestBuildRoutingExplanation:
    def test_returns_populated_explanation(self):
        exp = build_routing_explanation(
            model_name="gpt-4o",
            model_tier="frontier",
            strategy_name="FrontierStrategy",
            tools_total=50,
            tools_after_filter=10,
            description_variant="detailed",
            few_shot_count=3,
            few_shot_categories=["agent_creation", "config"],
            middleware_hooks_fired=["pre_routing", "post_routing"],
            meta_action_hint=True,
            feature_flags={"adaptive_routing_enabled": True},
        )
        assert isinstance(exp, RoutingExplanation)
        assert exp.model_name == "gpt-4o"
        assert exp.model_tier == "frontier"
        assert exp.strategy_name == "FrontierStrategy"
        assert exp.tools_total == 50
        assert exp.tools_after_filter == 10
        assert exp.description_variant == "detailed"
        assert exp.few_shot_count == 3
        assert exp.few_shot_categories == ["agent_creation", "config"]
        assert exp.middleware_hooks_fired == ["pre_routing", "post_routing"]
        assert exp.meta_action_hint is True
        assert exp.feature_flags == {"adaptive_routing_enabled": True}

# ---- Format for log ---------------------------------------------------------

class TestFormatExplanationForLog:
    def test_contains_key_fields(self):
        exp = build_routing_explanation(
            model_name="gpt-4o",
            model_tier="frontier",
            strategy_name="FrontierStrategy",
            tools_total=50,
            tools_after_filter=10,
            description_variant="detailed",
            few_shot_count=3,
        )
        formatted = format_explanation_for_log(exp)
        assert "tier=frontier" in formatted
        assert "strategy=FrontierStrategy" in formatted
        assert "tools=10/50" in formatted
        assert "few_shot=3" in formatted
        assert "variant=detailed" in formatted
        assert "meta_hint=False" in formatted
        assert "[ROUTING-EXPLAIN]" in formatted

    def test_with_empty_lists(self):
        exp = build_routing_explanation(
            model_name="gpt-3.5",
            model_tier="weak",
            strategy_name="WeakStrategy",
            tools_total=20,
            tools_after_filter=20,
            description_variant="short",
            few_shot_count=0,
            few_shot_categories=[],
            middleware_hooks_fired=[],
        )
        assert exp.few_shot_categories == []
        assert exp.middleware_hooks_fired == []
        formatted = format_explanation_for_log(exp)
        assert "tier=weak" in formatted

    def test_with_meta_action_hint_true(self):
        exp = build_routing_explanation(
            model_name="gpt-4",
            model_tier="strong",
            strategy_name="StrongStrategy",
            tools_total=30,
            tools_after_filter=15,
            description_variant="detailed",
            few_shot_count=2,
            meta_action_hint=True,
        )
        formatted = format_explanation_for_log(exp)
        assert "meta_hint=True" in formatted

    def test_with_feature_flags(self):
        flags = {
            "adaptive_routing_enabled": True,
            "few_shot_enabled": False,
        }
        exp = build_routing_explanation(
            model_name="claude-3",
            model_tier="frontier",
            strategy_name="FrontierStrategy",
            tools_total=40,
            tools_after_filter=8,
            description_variant="detailed",
            few_shot_count=0,
            feature_flags=flags,
        )
        assert exp.feature_flags == flags
        assert exp.feature_flags["adaptive_routing_enabled"] is True
        assert exp.feature_flags["few_shot_enabled"] is False

    def test_defaults_for_optional_fields(self):
        """Build with None for optional lists -- should default to empty."""
        exp = build_routing_explanation(
            model_name="test",
            model_tier="moderate",
            strategy_name="ModerateStrategy",
            tools_total=10,
            tools_after_filter=5,
            description_variant="short",
            few_shot_count=1,
            few_shot_categories=None,
            middleware_hooks_fired=None,
            feature_flags=None,
        )
        assert exp.few_shot_categories == []
        assert exp.middleware_hooks_fired == []
        assert exp.feature_flags == {}
