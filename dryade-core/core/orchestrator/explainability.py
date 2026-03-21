"""Routing decision explainability for DX polish.

Phase 115.5: Captures the full context of each routing decision
(model tier, strategy, tools filtered, few-shot examples injected)
for debugging, audit, and developer understanding.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

__all__ = [
    "RoutingExplanation",
    "build_routing_explanation",
    "format_explanation_for_log",
]

@dataclass
class RoutingExplanation:
    """Full context of a single routing decision.

    Captures every dimension of the routing pipeline so developers
    and operators can understand exactly why a particular routing
    outcome was chosen.
    """

    model_name: str
    model_tier: str
    strategy_name: str
    tools_total: int
    tools_after_filter: int
    description_variant: str
    few_shot_count: int
    few_shot_categories: list[str] = field(default_factory=list)
    middleware_hooks_fired: list[str] = field(default_factory=list)
    meta_action_hint: bool = False
    feature_flags: dict[str, bool] = field(default_factory=dict)

def build_routing_explanation(
    *,
    model_name: str,
    model_tier: str,
    strategy_name: str,
    tools_total: int,
    tools_after_filter: int,
    description_variant: str,
    few_shot_count: int,
    few_shot_categories: list[str] | None = None,
    middleware_hooks_fired: list[str] | None = None,
    meta_action_hint: bool = False,
    feature_flags: dict[str, bool] | None = None,
) -> RoutingExplanation:
    """Factory function to build a RoutingExplanation.

    Maps keyword arguments to the RoutingExplanation dataclass.
    The actual population happens in ThinkingProvider (Plan 03 wiring).
    """
    return RoutingExplanation(
        model_name=model_name,
        model_tier=model_tier,
        strategy_name=strategy_name,
        tools_total=tools_total,
        tools_after_filter=tools_after_filter,
        description_variant=description_variant,
        few_shot_count=few_shot_count,
        few_shot_categories=few_shot_categories or [],
        middleware_hooks_fired=middleware_hooks_fired or [],
        meta_action_hint=meta_action_hint,
        feature_flags=feature_flags or {},
    )

def format_explanation_for_log(explanation: RoutingExplanation) -> str:
    """Format a RoutingExplanation as a single-line log-friendly summary.

    Returns:
        A string like: "[ROUTING-EXPLAIN] tier=frontier strategy=FrontierStrategy
        tools=50/50 few_shot=0 variant=detailed meta_hint=False"
    """
    return (
        f"[ROUTING-EXPLAIN] tier={explanation.model_tier}"
        f" strategy={explanation.strategy_name}"
        f" tools={explanation.tools_after_filter}/{explanation.tools_total}"
        f" few_shot={explanation.few_shot_count}"
        f" variant={explanation.description_variant}"
        f" meta_hint={explanation.meta_action_hint}"
    )
