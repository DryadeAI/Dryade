"""Complexity estimation for goal classification.

Classifies user goals into PlanningMode (REACT / PLAN / DEFER) using
pure regex heuristics -- zero LLM overhead.

Design from 81-03 Section 1.1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from core.adapters.protocol import AgentCard
from core.orchestrator.models import Tier

__all__ = [
    "PlanningMode",
    "PlanningDecision",
    "TierDecision",
    "ComplexityEstimator",
    "META_ACTION_PATTERNS",
]

# Regex patterns for meta-action detection (system infrastructure requests).
# These match requests to create/add/configure/remove agents, tools, servers, etc.
# Checked before SIMPLE tier to prevent agent-name substring matches from
# routing meta-actions away from COMPLEX/REACT orchestration.
META_ACTION_PATTERNS: list[str] = [
    r"(?:create|add|set\s*up|configure|install|enable)\s+(?:a\s+|an\s+|the\s+)?(?:\w+\s+)*(?:agent|tool|server|integration|plugin|capability)",
    r"(?:remove|delete|disable|uninstall)\s+(?:a\s+|an\s+|the\s+)?(?:\w+\s+)*(?:agent|tool|server|integration|plugin)",
]

class PlanningMode(str, Enum):
    """How the orchestrator should handle a goal.

    REACT  -- simple, execute immediately via ReAct loop
    PLAN   -- complex, build an ExecutionPlan DAG first
    DEFER  -- ambiguous, let the LLM decide
    """

    REACT = "react"
    PLAN = "plan"
    DEFER = "defer"

@dataclass
class PlanningDecision:
    """Result of complexity estimation."""

    mode: PlanningMode
    confidence: float  # 0.0 - 1.0
    reason: str
    estimated_steps: int = 1
    agent_hint: str | None = None

@dataclass
class TierDecision:
    """Result of tier classification.

    Returned by ComplexityEstimator.classify(). Contains the tier,
    confidence, and optional dispatch target for SIMPLE tier.
    """

    tier: Tier
    confidence: float  # 0.0 - 1.0
    reason: str
    target_agent: str | None = None  # For SIMPLE: which agent to dispatch to
    target_tool: str | None = None  # For SIMPLE: which tool was matched
    sub_mode: PlanningMode | None = None  # For COMPLEX: REACT/PLAN/DEFER
    meta_action_hint: bool = False  # Hint for self-mod tool injection (not a bypass)

class ComplexityEstimator:
    """Regex-based goal complexity classifier.

    Errs toward REACT -- planning overhead is only justified for
    genuinely complex multi-step goals.
    """

    # Compiled regex patterns (class-level, shared across instances)
    MULTI_STEP_PATTERNS: list[re.Pattern[str]] = [
        re.compile(p, re.IGNORECASE)
        for p in [
            r"and then",
            r"after that",
            r"once .+ is done",
            r"followed by",
            r"next step",
            r"\bfirst\b",
            r"\bsecond\b",
            r"\bthird\b",
            r"\bfinally\b",
            r"step \d+",
            r"create .+ and .+ and",
            r"analyze .+ then .+ then",
        ]
    ]

    CONDITIONAL_PATTERNS: list[re.Pattern[str]] = [
        re.compile(p, re.IGNORECASE)
        for p in [
            r"if .+ then",
            r"depending on",
            r"in case .+ otherwise",
            r"when .+ do",
        ]
    ]

    QUESTION_PATTERNS: list[re.Pattern[str]] = [
        re.compile(p, re.IGNORECASE)
        for p in [
            r"^(what|who|where|when|how|why|is|are|can|does|do|did|will|would|could)\b",
            r"\?$",
        ]
    ]

    # Matches comma-separated verb phrases (e.g., "analyze repo, find issues, fix them")
    _COMMA_ACTION_RE: re.Pattern[str] = re.compile(r"(?:^|,\s*)[a-z]+\s+\w+", re.IGNORECASE)

    SINGLE_ACTION_PATTERNS: list[re.Pattern[str]] = [
        re.compile(p, re.IGNORECASE)
        for p in [
            r"^(list|show|get|find|read|open|search|check|look up|tell me)\b",
            r"^(summarize|translate|explain|describe|compare)\b",
        ]
    ]

    # --- Tier classification patterns (Phase 90) ---

    GREETING_PATTERNS: list[re.Pattern[str]] = [
        re.compile(p, re.IGNORECASE)
        for p in [
            r"^(hi|hello|hey|howdy|good morning|good afternoon|good evening|greetings|bonjour|hola)\b",
        ]
    ]

    META_QUESTION_PATTERNS: list[re.Pattern[str]] = [
        re.compile(p, re.IGNORECASE)
        for p in [
            r"^(what can you|what do you|who are you|how do you|tell me about yourself|what are your)\b",
        ]
    ]

    ACTION_VERBS: set[str] = {
        "list",
        "search",
        "find",
        "create",
        "update",
        "delete",
        "run",
        "execute",
        "open",
        "read",
        "write",
        "analyze",
        "compare",
        "show",
        "get",
        "check",
        "look",
    }

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def classify(
        self,
        message: str,
        available_agents: list[AgentCard],
    ) -> TierDecision:
        """Classify message into INSTANT / SIMPLE / COMPLEX tier.

        Runs BEFORE estimate() -- if tier is INSTANT or SIMPLE, the
        existing estimate() is skipped entirely. If COMPLEX, estimate()
        runs to determine the REACT/PLAN/DEFER sub-mode.

        Uses zero-LLM heuristics: regex patterns, agent/tool name matching.

        Args:
            message: Raw user message.
            available_agents: Currently registered agents from AgentRegistry.

        Returns:
            TierDecision with tier, confidence, reason, and optional
            target_agent/target_tool (for SIMPLE) or sub_mode (for COMPLEX).
        """
        text = message.lower().strip()
        word_count = len(text.split())

        # Build lookup sets from agent registry
        agent_names: set[str] = {a.name.lower() for a in available_agents}
        tool_names: dict[str, str] = {}  # tool_name_lower -> agent_name
        for a in available_agents:
            for cap in a.capabilities or []:
                tool_names[cap.name.lower()] = a.name

        # Check for agent/tool name matches in message
        matched_agent: str | None = None
        matched_tool: str | None = None
        for name in agent_names:
            if name in text:
                matched_agent = name
                break
        for tool, agent in tool_names.items():
            if tool in text:
                matched_tool = tool
                matched_agent = matched_agent or agent
                break

        has_agent_signal = matched_agent is not None or matched_tool is not None

        # --- INSTANT check (all must be true: no agent signal + pattern match + no action verbs) ---
        if not has_agent_signal:
            words = set(text.split())
            has_action_verb = bool(words & self.ACTION_VERBS)

            if self._matches_any(text, self.GREETING_PATTERNS) and not has_action_verb:
                return TierDecision(
                    tier=Tier.INSTANT,
                    confidence=0.95,
                    reason="Greeting detected",
                )
            if self._matches_any(text, self.META_QUESTION_PATTERNS) and not has_action_verb:
                return TierDecision(
                    tier=Tier.INSTANT,
                    confidence=0.90,
                    reason="System meta-question",
                )
            if (
                word_count < 15
                and not has_action_verb
                and self._matches_any(text, self.QUESTION_PATTERNS)
            ):
                return TierDecision(
                    tier=Tier.INSTANT,
                    confidence=0.80,
                    reason="Short factual question",
                )

        # --- META-ACTION check (agent/tool creation/configuration) ---
        # Must run BEFORE SIMPLE check to prevent "create a websearch agent"
        # from matching agent name "websearch" and bypassing orchestration.
        meta_action_detected = False
        if any(re.search(p, text) for p in META_ACTION_PATTERNS):
            meta_action_detected = True
            # Don't return -- let classification continue to COMPLEX path
            # The hint will be passed through to enable self-mod tool injection

        if not meta_action_detected:
            # --- SIMPLE check ---
            if matched_agent and matched_tool:
                return TierDecision(
                    tier=Tier.SIMPLE,
                    confidence=0.95,
                    reason="Agent + tool name match",
                    target_agent=matched_agent,
                    target_tool=matched_tool,
                )
            if matched_agent and word_count < 30:
                return TierDecision(
                    tier=Tier.SIMPLE,
                    confidence=0.85,
                    reason="Agent name match",
                    target_agent=matched_agent,
                )
            if matched_tool and word_count < 30:
                return TierDecision(
                    tier=Tier.SIMPLE,
                    confidence=0.85,
                    reason="Tool name match",
                    target_agent=tool_names[matched_tool],
                    target_tool=matched_tool,
                )
            if (
                self._matches_any(text, self.SINGLE_ACTION_PATTERNS)
                and word_count < 30
                and matched_agent
            ):
                return TierDecision(
                    tier=Tier.SIMPLE,
                    confidence=0.70,
                    reason="Single action + agent hint",
                    target_agent=matched_agent,
                )

        # --- COMPLEX (default) ---
        # Run existing estimate() for REACT/PLAN/DEFER sub-mode
        sub_decision = self.estimate(message, available_agents)
        return TierDecision(
            tier=Tier.COMPLEX,
            confidence=0.90 if meta_action_detected else sub_decision.confidence,
            reason="Meta-action: system infrastructure request"
            if meta_action_detected
            else sub_decision.reason,
            sub_mode=PlanningMode.REACT if meta_action_detected else sub_decision.mode,
            meta_action_hint=meta_action_detected,
        )

    def estimate(
        self,
        goal: str,
        available_agents: list[AgentCard],
    ) -> PlanningDecision:
        """Classify *goal* into a PlanningMode.

        Args:
            goal: Natural language user goal.
            available_agents: Currently registered agents (used for
                multi-agent detection).

        Returns:
            PlanningDecision with mode, confidence, and reason.
        """
        text = goal.lower().strip()
        word_count = len(text.split())

        # Pre-compute complexity signals so REACT checks can yield to PLAN
        multi_step_count = self._count_matches(text, self.MULTI_STEP_PATTERNS)
        conditional_count = self._count_matches(text, self.CONDITIONAL_PATTERNS)
        agent_mentions = self._count_agent_mentions(text, available_agents)
        comma_actions = len(self._COMMA_ACTION_RE.findall(text))
        has_plan_signals = (
            multi_step_count >= 2
            or conditional_count >= 1
            or agent_mentions >= 2
            or word_count >= 100
            or comma_actions >= 3
        )

        # --- REACT signals (checked first, high confidence) ----------- #
        # Single-action / question checks only return REACT when there
        # are no overriding PLAN-level signals in the same goal.

        if self._matches_any(text, self.QUESTION_PATTERNS) and not has_plan_signals:
            return PlanningDecision(
                mode=PlanningMode.REACT,
                confidence=0.9,
                reason="Question syntax detected",
                estimated_steps=1,
            )

        if self._matches_any(text, self.SINGLE_ACTION_PATTERNS) and not has_plan_signals:
            return PlanningDecision(
                mode=PlanningMode.REACT,
                confidence=0.85,
                reason="Single-action verb detected",
                estimated_steps=1,
            )

        # --- PLAN signals --------------------------------------------- #

        if multi_step_count >= 2:
            return PlanningDecision(
                mode=PlanningMode.PLAN,
                confidence=0.9,
                reason=f"{multi_step_count} multi-step signals detected",
                estimated_steps=multi_step_count + 1,
            )

        if conditional_count >= 1:
            return PlanningDecision(
                mode=PlanningMode.PLAN,
                confidence=0.85,
                reason="Conditional logic detected",
                estimated_steps=3,
            )

        if word_count >= 100:
            return PlanningDecision(
                mode=PlanningMode.PLAN,
                confidence=0.8,
                reason=f"Long goal ({word_count} words) suggests complexity",
                estimated_steps=4,
            )

        if comma_actions >= 3:
            return PlanningDecision(
                mode=PlanningMode.PLAN,
                confidence=0.85,
                reason=f"{comma_actions} comma-separated action phrases detected",
                estimated_steps=comma_actions,
            )

        if agent_mentions >= 2:
            return PlanningDecision(
                mode=PlanningMode.PLAN,
                confidence=0.85,
                reason=f"{agent_mentions} agent names mentioned",
                estimated_steps=agent_mentions,
            )

        # --- Short goal with no multi-step signals -> REACT ----------- #

        if word_count < 15 and multi_step_count == 0:
            return PlanningDecision(
                mode=PlanningMode.REACT,
                confidence=0.75,
                reason="Short goal with no multi-step signals",
                estimated_steps=1,
            )

        # --- DEFER: ambiguous ----------------------------------------- #

        if multi_step_count == 1 or 30 <= word_count < 100:
            return PlanningDecision(
                mode=PlanningMode.DEFER,
                confidence=0.5,
                reason="Ambiguous complexity -- single multi-step signal or moderate length",
                estimated_steps=2,
            )

        # --- Default: REACT ------------------------------------------- #

        return PlanningDecision(
            mode=PlanningMode.REACT,
            confidence=0.6,
            reason="No strong complexity signals",
            estimated_steps=1,
        )

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    @staticmethod
    def _matches_any(text: str, patterns: list[re.Pattern[str]]) -> bool:
        return any(p.search(text) for p in patterns)

    @staticmethod
    def _count_matches(text: str, patterns: list[re.Pattern[str]]) -> int:
        return sum(1 for p in patterns if p.search(text))

    @staticmethod
    def _count_agent_mentions(text: str, agents: list[AgentCard]) -> int:
        return sum(1 for a in agents if a.name.lower() in text)
