"""DSPy-inspired BootstrapFewShot optimizer for routing.

Phase 115.5: Reads routing metrics, identifies successful tool calls,
validates against quality thresholds, and bootstraps passing examples
into the FewShotLibrary. Uses synthetic example generation (not message
reconstruction) to preserve privacy.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

__all__ = [
    "OptimizationResult",
    "RoutingOptimizer",
    "get_routing_optimizer",
]

@dataclass
class OptimizationResult:
    """Result of a single BootstrapFewShot optimization cycle."""

    examples_added: int = 0
    examples_rejected: int = 0
    examples_evicted: int = 0
    metric_window_start: datetime = field(default_factory=lambda: datetime.now(UTC))
    metric_window_end: datetime = field(default_factory=lambda: datetime.now(UTC))
    quality_threshold: float = 0.7
    total_metrics_analyzed: int = 0
    candidate_count: int = 0

# ---- Synthetic message generation ------------------------------------------------
# NEVER reconstruct from message hashes. Always use synthetic templates.

_SYNTHETIC_TEMPLATES: dict[str, list[str]] = {
    # Phase 167: "create" replaces "self_improve", "create_agent", "create_tool"
    "create": [
        "Create a {type} agent for {purpose}",
        "Set up a {type} MCP server",
        "Add a new {capability} to the system",
        "Create a {type} tool that can {capability}",
        "Build a {purpose} utility tool",
    ],
    "modify_config": [
        "Change the {key} setting to {value}",
        "Update the {key} configuration",
    ],
}

_CATEGORY_MAP: dict[str, str] = {
    # Phase 167: "create" replaces "self_improve" and "create_tool"
    "create": "agent_creation",
    "modify_config": "config",
}

# Deterministic fill terms for synthetic placeholders
_FILL_TERMS: dict[str, list[str]] = {
    "type": ["specialized", "custom", "enhanced", "automated", "intelligent"],
    "purpose": ["data processing", "monitoring", "analysis", "integration", "automation"],
    "capability": [
        "advanced search",
        "real-time sync",
        "pattern detection",
        "reporting",
        "transformation",
    ],
    "key": ["timeout", "max_retries", "threshold", "interval", "batch_size"],
    "value": ["optimized", "increased", "adjusted", "tuned", "updated"],
}

def _synthesize_message(tool_called: str, arguments_hash: str) -> str:
    """Generate a synthetic user message for a tool call.

    Uses deterministic selection based on the arguments hash to ensure
    reproducibility. Never attempts to reverse message hashes.

    Args:
        tool_called: Name of the tool that was called.
        arguments_hash: sha256[:16] hash of the tool arguments.

    Returns:
        A synthetic natural-language message.
    """
    templates = _SYNTHETIC_TEMPLATES.get(tool_called)
    if not templates:
        return f"Perform a {tool_called} operation"

    # Use md5 of arguments_hash for deterministic selection
    digest = hashlib.md5(arguments_hash.encode()).hexdigest()[:8]
    seed = int(digest, 16)

    template = templates[seed % len(templates)]

    # Fill placeholders deterministically
    result = template
    for placeholder, terms in _FILL_TERMS.items():
        tag = "{" + placeholder + "}"
        if tag in result:
            term_idx = (seed // (len(templates) + 1)) % len(terms)
            result = result.replace(tag, terms[term_idx], 1)
            seed = seed >> 2  # shift for next placeholder

    return result

class RoutingOptimizer:
    """DSPy-inspired BootstrapFewShot optimizer for routing.

    Reads routing metrics from the database, identifies successful
    tool-calling patterns, and bootstraps them as few-shot examples
    into the FewShotLibrary. This makes routing self-improving over time.

    The algorithm:
    1. Query recent routing metrics from DB
    2. Filter to candidates where a hint fired and a tool was called
    3. Score each candidate on quality signals
    4. Deduplicate by tool_arguments_hash
    5. Synthesize privacy-safe messages for passing candidates
    6. Add examples to FewShotLibrary
    7. Evict excess examples if over budget
    """

    def __init__(
        self,
        max_bootstrapped_demos: int = 4,
        max_total_demos: int = 20,
        metric_threshold: float = 0.7,
    ):
        self._max_bootstrapped = max_bootstrapped_demos
        self._max_total = max_total_demos
        self._threshold = metric_threshold

    def _query_recent_metrics(self, since: datetime, limit: int = 500) -> list:
        """Query RoutingMetric records from DB since the given timestamp.

        Best-effort: returns empty list on any failure.

        Args:
            since: Start of the time window.
            limit: Maximum number of records to return.

        Returns:
            List of RoutingMetric ORM objects, or empty list on failure.
        """
        try:
            from core.database.models import RoutingMetric
            from core.database.session import get_session

            with get_session() as session:
                rows = (
                    session.query(RoutingMetric)
                    .filter(RoutingMetric.timestamp >= since)
                    .order_by(RoutingMetric.timestamp.asc())
                    .limit(limit)
                    .all()
                )
                # Detach from session so they survive after close
                session.expunge_all()
                return rows
        except Exception:
            logger.debug("[OPTIMIZER] Failed to query metrics from DB", exc_info=True)
            return []

    @staticmethod
    def _score(metric) -> float:
        """Score a routing metric on quality signals.

        Scoring rules:
        - 1.0: hint fired, tool called, no fallback, user approved, success
        - 0.8: hint fired, tool called, no fallback, success unknown
        - 0.5: success_outcome is False
        - 0.0: fallback activated

        Args:
            metric: A RoutingMetric ORM object or RoutingMetricRecord.

        Returns:
            Quality score between 0.0 and 1.0.
        """
        if getattr(metric, "fallback_activated", False):
            return 0.0

        hint = getattr(metric, "hint_fired", False)
        tool = getattr(metric, "llm_tool_called", None)
        approved = getattr(metric, "user_approved", None)
        success = getattr(metric, "success_outcome", None)

        if hint and tool and not getattr(metric, "fallback_activated", False):
            if approved is True and success is True:
                return 1.0
            if success is None:
                return 0.8
            if success is False:
                return 0.5

        return 0.0

    @staticmethod
    def _count_bootstrapped(library) -> int:
        """Count bootstrapped (non-curated) examples in the library.

        The first 8 examples are curated; anything beyond that is bootstrapped.

        Args:
            library: A FewShotLibrary instance.

        Returns:
            Number of bootstrapped examples (min 0).
        """
        return max(len(library._examples) - 8, 0)

    def optimize(
        self,
        since: datetime,
        until: datetime | None = None,
    ) -> OptimizationResult:
        """Run a BootstrapFewShot optimization cycle.

        1. Query metrics from DB in [since, until]
        2. Filter candidates (hint_fired=True, llm_tool_called not null)
        3. Score each, keep those >= threshold
        4. Deduplicate by tool_arguments_hash
        5. Synthesize messages, bootstrap into FewShotLibrary
        6. Evict excess if over max_total_demos

        Args:
            since: Start of the metric window.
            until: End of the metric window (defaults to now).

        Returns:
            OptimizationResult with counts.
        """
        from core.orchestrator.few_shot_library import get_few_shot_library

        end_time = until or datetime.now(UTC)
        result = OptimizationResult(
            metric_window_start=since,
            metric_window_end=end_time,
            quality_threshold=self._threshold,
        )

        # 1. Query metrics
        metrics = self._query_recent_metrics(since)
        # Filter to time window
        metrics = [m for m in metrics if m.timestamp <= end_time]
        result.total_metrics_analyzed = len(metrics)

        if not metrics:
            return result

        # 2. Filter candidates: hint fired and tool called
        candidates = [
            m
            for m in metrics
            if getattr(m, "hint_fired", False) and getattr(m, "llm_tool_called", None)
        ]
        result.candidate_count = len(candidates)

        # 3. Score and filter by threshold
        scored = []
        for m in candidates:
            score = self._score(m)
            if score >= self._threshold:
                scored.append(m)
            else:
                result.examples_rejected += 1

        # 4. Deduplicate by tool_arguments_hash (keep first occurrence)
        seen_hashes: set[str] = set()
        unique: list = []
        for m in scored:
            h = getattr(m, "tool_arguments_hash", None) or ""
            if h and h in seen_hashes:
                result.examples_rejected += 1
                continue
            if h:
                seen_hashes.add(h)
            unique.append(m)

        # 5. Bootstrap into FewShotLibrary
        library = get_few_shot_library()
        current_bootstrapped = self._count_bootstrapped(library)
        budget = max(self._max_bootstrapped - current_bootstrapped, 0)

        for m in unique[:budget]:
            tool_called = m.llm_tool_called
            args_hash = getattr(m, "tool_arguments_hash", "") or "unknown"
            message = _synthesize_message(tool_called, args_hash)
            category = _CATEGORY_MAP.get(tool_called, "config")

            library.add_from_metric(
                user_message=message,
                tool_called=tool_called,
                arguments={},
                category=category,
            )
            result.examples_added += 1

        # Remaining scored examples beyond budget
        if len(unique) > budget:
            result.examples_rejected += len(unique) - budget

        # 6. Evict excess if total exceeds max_total_demos
        total = len(library._examples)
        if total > self._max_total:
            evict_count = total - self._max_total
            # Evict oldest bootstrapped examples (index 8 onwards)
            for _ in range(evict_count):
                if len(library._examples) > 8:
                    library._examples.pop(8)
                    result.examples_evicted += 1

        logger.info(
            "[OPTIMIZER] Cycle complete: added=%d rejected=%d evicted=%d analyzed=%d",
            result.examples_added,
            result.examples_rejected,
            result.examples_evicted,
            result.total_metrics_analyzed,
        )

        return result

# ---- Singleton with double-checked locking ----------------------------------------

_optimizer: RoutingOptimizer | None = None
_optimizer_lock = threading.Lock()

def get_routing_optimizer() -> RoutingOptimizer:
    """Get or create the singleton RoutingOptimizer instance."""
    global _optimizer
    if _optimizer is None:
        with _optimizer_lock:
            if _optimizer is None:
                _optimizer = RoutingOptimizer()
    return _optimizer
