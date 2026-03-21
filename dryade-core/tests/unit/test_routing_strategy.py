"""Tests for core.orchestrator.routing_strategy -- Phase 115.4.

Covers all 4 strategies and the factory function.
"""

from core.orchestrator.model_detection import ModelTier
from core.orchestrator.routing_strategy import (
    FrontierStrategy,
    ModerateStrategy,
    StrongStrategy,
    WeakStrategy,
    get_strategy_for_tier,
)

def _make_tools(n: int) -> list[dict]:
    """Create N dummy tools in OpenAI format."""
    return [
        {
            "type": "function",
            "function": {
                "name": f"tool_{i}",
                "description": f"Tool number {i}",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        for i in range(n)
    ]

class TestFrontierStrategy:
    def test_no_filtering(self):
        s = FrontierStrategy()
        tools = _make_tools(50)
        result = s.select_tools(tools, meta_hint=False)
        assert len(result) == 50

    def test_no_fewshot(self):
        s = FrontierStrategy()
        assert s.get_few_shot_count() == 0

    def test_detailed_variant(self):
        s = FrontierStrategy()
        assert s.get_tool_description_variant() == "detailed"

    def test_no_fallback(self):
        s = FrontierStrategy()
        assert not s.should_force_fallback()

class TestStrongStrategy:
    def test_caps_at_50(self):
        s = StrongStrategy()
        tools = _make_tools(80)
        assert len(s.select_tools(tools, meta_hint=False)) == 50

    def test_passthrough_under_cap(self):
        s = StrongStrategy()
        tools = _make_tools(30)
        assert len(s.select_tools(tools, meta_hint=False)) == 30

    def test_fewshot_2(self):
        s = StrongStrategy()
        assert s.get_few_shot_count() == 2

class TestModerateStrategy:
    def test_caps_at_20(self):
        s = ModerateStrategy()
        tools = _make_tools(40)
        result = s.select_tools(tools, meta_hint=False)
        assert len(result) == 20

    def test_caps_at_30_on_meta(self):
        s = ModerateStrategy()
        tools = _make_tools(50)
        result = s.select_tools(tools, meta_hint=True)
        assert len(result) == 30

    def test_passthrough_under_meta_cap(self):
        s = ModerateStrategy()
        tools = _make_tools(15)
        result = s.select_tools(tools, meta_hint=True)
        assert len(result) == 15

class TestWeakStrategy:
    def test_caps_at_5(self):
        s = WeakStrategy()
        tools = _make_tools(20)
        result = s.select_tools(tools, meta_hint=False)
        assert len(result) == 5

    def test_short_variant(self):
        s = WeakStrategy()
        assert s.get_tool_description_variant() == "short"

    def test_force_fallback(self):
        s = WeakStrategy()
        assert s.should_force_fallback()

    def test_meta_hint_create_only(self):
        # Phase 167: WeakStrategy exposes `create` for meta-actions (was self_improve)
        s = WeakStrategy()
        tools = _make_tools(10)
        # Add the unified `create` tool
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "create",
                    "description": "Create agents/tools/skills",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        )
        result = s.select_tools(tools, meta_hint=True)
        assert len(result) == 1
        assert result[0]["function"]["name"] == "create"

class TestFactory:
    def test_frontier(self):
        s = get_strategy_for_tier(ModelTier.FRONTIER)
        assert isinstance(s, FrontierStrategy)

    def test_strong(self):
        s = get_strategy_for_tier(ModelTier.STRONG)
        assert isinstance(s, StrongStrategy)

    def test_moderate(self):
        s = get_strategy_for_tier(ModelTier.MODERATE)
        assert isinstance(s, ModerateStrategy)

    def test_weak(self):
        s = get_strategy_for_tier(ModelTier.WEAK)
        assert isinstance(s, WeakStrategy)
