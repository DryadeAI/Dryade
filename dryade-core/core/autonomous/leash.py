"""Configurable autonomy constraints (leash mechanism).

Implements defense-in-depth for autonomous execution:
- Token/cost limits prevent runaway resource consumption
- Time limits prevent infinite loops
- Action limits bound execution scope
- Confidence thresholds trigger human escalation
- Dangerous patterns require explicit approval
"""

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.autonomous.models import ExecutionState

if TYPE_CHECKING:
    from core.orchestrator.action_autonomy import ActionAutonomy, AutonomyLevel

@dataclass
class LeashResult:
    """Result of leash constraint check."""

    exceeded: bool
    reasons: list[str] = field(default_factory=list)
    requires_approval: bool = False
    approval_reason: str | None = None

@dataclass
class LeashConfig:
    """Configurable autonomy constraints.

    User defines pause triggers via any combination.
    Skill can declare its own autonomy level override.

    Attributes:
        max_tokens: Maximum tokens before pause (None = unlimited)
        max_cost_usd: Maximum cost in USD before pause
        max_duration_seconds: Maximum execution time
        max_actions: Maximum skill/tool invocations
        max_tool_calls: Maximum individual tool calls
        confidence_threshold: Minimum confidence to proceed without human
        approval_required_patterns: Regex patterns requiring explicit approval
    """

    # Token/cost limits
    max_tokens: int | None = 50000
    max_cost_usd: float | None = 0.50

    # Time limits
    max_duration_seconds: int | None = 300  # 5 minutes

    # Action limits
    max_actions: int | None = 20
    max_tool_calls: int | None = 50

    # Confidence threshold for escalation (industry standard 80-90%)
    confidence_threshold: float = 0.85

    # Dangerous action patterns requiring approval
    approval_required_patterns: list[str] = field(
        default_factory=lambda: [
            r"rm\s+-rf",
            r"DROP\s+TABLE",
            r"git\s+push\s+--force",
            r"chmod\s+777",
            r"DELETE\s+FROM.*WHERE\s+1\s*=\s*1",
            r"TRUNCATE\s+TABLE",
        ]
    )

    # Per-action autonomy for self-modification tools (Phase 115.3).
    # Optional: when None, caller uses default behavior. When set,
    # provides granular auto/confirm/approve levels per tool.
    action_autonomy: "ActionAutonomy | None" = None

    def exceeded(self, state: ExecutionState) -> LeashResult:
        """Check if any constraint exceeded.

        Args:
            state: Current execution state

        Returns:
            LeashResult with exceeded status and reasons
        """
        reasons = []

        if self.max_tokens and state.tokens_used > self.max_tokens:
            reasons.append(f"tokens: {state.tokens_used}/{self.max_tokens}")

        if self.max_cost_usd and state.cost_usd > self.max_cost_usd:
            reasons.append(f"cost: ${state.cost_usd:.2f}/${self.max_cost_usd}")

        if self.max_duration_seconds and state.duration_seconds > self.max_duration_seconds:
            reasons.append(f"duration: {state.duration_seconds:.0f}s/{self.max_duration_seconds}s")

        if self.max_actions and state.actions_taken > self.max_actions:
            reasons.append(f"actions: {state.actions_taken}/{self.max_actions}")

        if self.max_tool_calls and state.tool_calls > self.max_tool_calls:
            reasons.append(f"tool_calls: {state.tool_calls}/{self.max_tool_calls}")

        return LeashResult(exceeded=bool(reasons), reasons=reasons)

    def check_action(self, action_text: str) -> LeashResult:
        """Check if action requires approval.

        Args:
            action_text: Command or action to check

        Returns:
            LeashResult indicating if approval needed
        """
        for pattern in self.approval_required_patterns:
            if re.search(pattern, action_text, re.IGNORECASE):
                return LeashResult(
                    exceeded=False,
                    requires_approval=True,
                    approval_reason=f"Action matches dangerous pattern: {pattern}",
                )
        return LeashResult(exceeded=False)

    def check_confidence(self, confidence: float) -> LeashResult:
        """Check if confidence is below threshold.

        Args:
            confidence: LLM confidence score (0.0-1.0)

        Returns:
            LeashResult indicating if human review needed
        """
        if confidence < self.confidence_threshold:
            return LeashResult(
                exceeded=False,
                requires_approval=True,
                approval_reason=f"Low confidence: {confidence:.2%} < {self.confidence_threshold:.2%}",
            )
        return LeashResult(exceeded=False)

    def check_action_autonomy(self, tool_name: str) -> "AutonomyLevel | None":
        """Check per-action autonomy level if ActionAutonomy is configured.

        Returns None if no ActionAutonomy set (caller uses default behavior).

        Args:
            tool_name: The self-modification tool name to check.

        Returns:
            AutonomyLevel if ActionAutonomy is configured, None otherwise.
        """
        if self.action_autonomy is None:
            return None
        return self.action_autonomy.check_autonomy(tool_name)

# Default leash configurations for different autonomy levels
LEASH_CONSERVATIVE = LeashConfig(
    max_tokens=10000,
    max_cost_usd=0.10,
    max_duration_seconds=60,
    max_actions=5,
    confidence_threshold=0.95,
)

LEASH_STANDARD = LeashConfig()  # Defaults

LEASH_PERMISSIVE = LeashConfig(
    max_tokens=200000,
    max_cost_usd=2.00,
    max_duration_seconds=600,
    max_actions=50,
    max_tool_calls=200,
    confidence_threshold=0.70,
)
