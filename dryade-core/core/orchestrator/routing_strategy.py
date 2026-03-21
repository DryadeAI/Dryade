"""Adaptive routing strategies for model-tier-aware tool selection.

Phase 115.4: Each model tier gets a distinct strategy controlling:
- Tool filtering (how many tools to expose)
- Description variant (short vs detailed)
- Few-shot example count
- Fallback behavior (force fallback for weak models)
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.orchestrator.model_detection import ModelTier

__all__ = [
    "RoutingStrategy",
    "FrontierStrategy",
    "StrongStrategy",
    "ModerateStrategy",
    "WeakStrategy",
    "get_strategy_for_tier",
]

class RoutingStrategy(ABC):
    """Abstract routing strategy that adapts behavior to model capabilities."""

    @abstractmethod
    def select_tools(self, all_tools: list[dict], meta_hint: bool) -> list[dict]:
        """Filter and select tools appropriate for this model tier.

        Args:
            all_tools: All available tools in OpenAI function-calling format.
            meta_hint: Whether the current message has a meta-action hint.

        Returns:
            Filtered list of tools.
        """

    @abstractmethod
    def get_tool_description_variant(self) -> str:
        """Return the description variant to use.

        Returns:
            "short" for compact descriptions, "detailed" for full descriptions.
        """

    @abstractmethod
    def get_few_shot_count(self) -> int:
        """Return the number of few-shot examples to inject.

        Returns:
            Number of examples (0 = none).
        """

    @abstractmethod
    def should_force_fallback(self) -> bool:
        """Whether to force the programmatic fallback path.

        Returns:
            True if the model is too weak for reliable tool calling.
        """

class FrontierStrategy(RoutingStrategy):
    """Strategy for frontier models (GPT-4, Claude, Gemini Pro).

    Frontier models handle large tool sets and detailed descriptions
    without guidance. No few-shot needed, no fallback.
    """

    def select_tools(self, all_tools: list[dict], meta_hint: bool) -> list[dict]:
        return all_tools

    def get_tool_description_variant(self) -> str:
        return "detailed"

    def get_few_shot_count(self) -> int:
        return 0

    def should_force_fallback(self) -> bool:
        return False

class StrongStrategy(RoutingStrategy):
    """Strategy for strong models (GPT-3.5, DeepSeek, vLLM with tools).

    Strong models handle tools well but benefit from a few examples.
    Capped at 50 base tools to avoid overwhelming smaller models.
    """

    def select_tools(self, all_tools: list[dict], meta_hint: bool) -> list[dict]:
        return all_tools[:50]

    def get_tool_description_variant(self) -> str:
        return "detailed"

    def get_few_shot_count(self) -> int:
        return 2

    def should_force_fallback(self) -> bool:
        return False

class ModerateStrategy(RoutingStrategy):
    """Strategy for moderate models (unknown or vLLM without tools).

    Moderate models need tool count capping to avoid confusion.
    Meta-action hints get a higher cap (self-mod tools added separately).
    """

    def select_tools(self, all_tools: list[dict], meta_hint: bool) -> list[dict]:
        if meta_hint:
            # Higher cap for meta-actions; self-mod tools (~12) added on top
            return all_tools[:30]
        return all_tools[:20]

    def get_tool_description_variant(self) -> str:
        return "detailed"

    def get_few_shot_count(self) -> int:
        return 3

    def should_force_fallback(self) -> bool:
        return False

class WeakStrategy(RoutingStrategy):
    """Strategy for weak models (Ollama local models).

    Weak models can barely handle tool calling. Severely limit tools,
    use short descriptions, inject maximum examples, force fallback.
    Phase 167: should_force_fallback() returns True -> self-mod tools are NOT
    injected for weak models (they can't handle the full tool set).
    """

    def select_tools(self, all_tools: list[dict], meta_hint: bool) -> list[dict]:
        if meta_hint:
            # Phase 167: Expose the unified `create` tool for meta-actions
            # (replaces old self_improve-only restriction)
            return [
                t
                for t in all_tools
                if t.get("function", {}).get("name") in ("factory_create", "create")
            ]
        return all_tools[:5]

    def get_tool_description_variant(self) -> str:
        return "short"

    def get_few_shot_count(self) -> int:
        return 5

    def should_force_fallback(self) -> bool:
        return True

# Strategy singletons mapped by tier
_STRATEGY_MAP: dict[ModelTier, RoutingStrategy] = {
    ModelTier.FRONTIER: FrontierStrategy(),
    ModelTier.STRONG: StrongStrategy(),
    ModelTier.MODERATE: ModerateStrategy(),
    ModelTier.WEAK: WeakStrategy(),
}

def get_strategy_for_tier(tier: ModelTier) -> RoutingStrategy:
    """Get the routing strategy for a given model tier.

    Args:
        tier: The detected model tier.

    Returns:
        RoutingStrategy instance for the tier.
    """
    return _STRATEGY_MAP[tier]
