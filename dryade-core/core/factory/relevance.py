"""Relevance detection engine for the Agent Factory.

Three-stage deduplication, dual-signal gap detection, and proactive
suggestion generation with rate limiting.
"""

import logging
import os
import threading
from collections import Counter
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

__all__ = [
    "check_existing_capabilities",
    "detect_gaps",
    "get_proactive_suggestions",
    "get_factory_config",
    "_extract_verb_object",
]

# ---------------------------------------------------------------------------
# Section 1: FactoryConfig singleton
# ---------------------------------------------------------------------------

_config: "FactoryConfig | None" = None
_config_lock = threading.Lock()

def get_factory_config():
    """Get or create the global FactoryConfig singleton.

    Reads overrides from environment variables:
    - DRYADE_FACTORY_PROACTIVE_ENABLED (bool, default False)
    - DRYADE_FACTORY_MAX_SUGGESTIONS_PER_DAY (int, default 3)
    - DRYADE_FACTORY_MAX_SUGGESTIONS_PER_SESSION (int, default 1)
    """
    global _config
    if _config is None:
        with _config_lock:
            if _config is None:
                from core.factory.models import FactoryConfig

                overrides = {}
                env_val = os.environ.get("DRYADE_FACTORY_PROACTIVE_ENABLED")
                if env_val is not None:
                    overrides["proactive_detection_enabled"] = env_val.lower() in (
                        "1",
                        "true",
                        "yes",
                    )
                env_val = os.environ.get("DRYADE_FACTORY_MAX_SUGGESTIONS_PER_DAY")
                if env_val is not None:
                    try:
                        overrides["proactive_max_suggestions_per_day"] = int(env_val)
                    except ValueError:
                        pass
                env_val = os.environ.get("DRYADE_FACTORY_MAX_SUGGESTIONS_PER_SESSION")
                if env_val is not None:
                    try:
                        overrides["proactive_max_suggestions_per_session"] = int(env_val)
                    except ValueError:
                        pass
                _config = FactoryConfig(**overrides)
    return _config

# ---------------------------------------------------------------------------
# Section 2: Name normalization and Jaccard similarity
# ---------------------------------------------------------------------------

def _normalize_name(name: str) -> str:
    """Normalize capability name for comparison.

    Lowercases, replaces hyphens/underscores with spaces, strips common
    suffixes (agent, tool, skill, helper, service, server), then sorts
    tokens alphabetically for order-independent comparison.
    """
    n = name.lower().replace("-", " ").replace("_", " ")
    for suffix in (
        " agent",
        " tool",
        " skill",
        " helper",
        " service",
        " server",
    ):
        if n.endswith(suffix):
            n = n[: -len(suffix)]
    return " ".join(sorted(n.split()))

def _name_jaccard(a: str, b: str) -> float:
    """Token-level Jaccard similarity after normalization."""
    tokens_a = set(_normalize_name(a).split())
    tokens_b = set(_normalize_name(b).split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)

def _extract_verb_object(message: str) -> str:
    """Normalize a user message to a verb+object pattern for semantic grouping.

    Strips articles, prepositions, and modifiers to extract the core intent.
    Examples:
        "search the web for Python tutorials" -> "search web"
        "find information about climate change" -> "find information"
        "create a new spreadsheet for Q4 budget" -> "create spreadsheet"
        "analyze my sales data from last quarter" -> "analyze data"

    Args:
        message: Raw user message text.

    Returns:
        Normalized verb+object string (lowercased, max 2 significant words).
        Falls back to first 2 significant words if no verb detected.
    """
    if not message:
        return ""

    _VERBS = frozenset(
        {
            "search",
            "find",
            "get",
            "fetch",
            "look",
            "query",
            "browse",
            "create",
            "make",
            "build",
            "generate",
            "write",
            "compose",
            "analyze",
            "check",
            "review",
            "examine",
            "inspect",
            "audit",
            "update",
            "edit",
            "modify",
            "change",
            "fix",
            "patch",
            "delete",
            "remove",
            "clean",
            "clear",
            "drop",
            "purge",
            "send",
            "post",
            "submit",
            "push",
            "deploy",
            "publish",
            "read",
            "open",
            "load",
            "view",
            "show",
            "display",
            "list",
            "run",
            "execute",
            "start",
            "launch",
            "trigger",
            "invoke",
            "convert",
            "transform",
            "translate",
            "format",
            "parse",
            "download",
            "upload",
            "import",
            "export",
            "backup",
            "connect",
            "link",
            "sync",
            "integrate",
            "attach",
            "summarize",
            "explain",
            "describe",
            "document",
            "schedule",
            "plan",
            "organize",
            "sort",
            "filter",
            "monitor",
            "track",
            "watch",
            "log",
            "measure",
            "help",
            "assist",
            "support",
            "debug",
            "diagnose",
        }
    )
    _STOP = frozenset(
        {
            "a",
            "an",
            "the",
            "to",
            "for",
            "of",
            "in",
            "on",
            "at",
            "by",
            "with",
            "and",
            "or",
            "is",
            "it",
            "that",
            "this",
            "be",
            "do",
            "my",
            "your",
            "our",
            "their",
            "its",
            "me",
            "you",
            "us",
            "them",
            "from",
            "about",
            "into",
            "some",
            "any",
            "all",
            "new",
            "last",
            "please",
            "can",
            "could",
            "would",
            "should",
            "will",
            "i",
        }
    )

    import re

    words = re.findall(r"[a-z]+", message.lower())
    significant = [w for w in words if w not in _STOP and len(w) > 1]

    if not significant:
        return ""

    # Find the verb (first significant word that is a known verb)
    verb = None
    remaining = []
    for w in significant:
        if verb is None and w in _VERBS:
            verb = w
        elif verb is not None:
            remaining.append(w)
        else:
            remaining.append(w)

    if verb and remaining:
        return f"{verb} {remaining[0]}"
    elif verb:
        return verb
    else:
        # No verb found -- return first 2 significant words
        return " ".join(significant[:2])

# ---------------------------------------------------------------------------
# Section 3: Capability listing helper
# ---------------------------------------------------------------------------

def _get_all_capability_names() -> list[str]:
    """Get all registered capability names from CapabilityRegistry + FactoryRegistry."""
    names: list[str] = []
    try:
        from core.orchestrator.capability_registry import get_capability_registry

        cap_reg = get_capability_registry()
        names.extend(e.name for e in cap_reg.list_all())
    except Exception:
        logger.debug("CapabilityRegistry unavailable for dedup", exc_info=True)
    try:
        from core.factory.registry import get_factory_registry

        fact_reg = get_factory_registry()
        names.extend(a.name for a in fact_reg.list_all())
    except Exception:
        logger.debug("FactoryRegistry unavailable for dedup", exc_info=True)
    return names

# ---------------------------------------------------------------------------
# Section 4: LLM dedup helper
# ---------------------------------------------------------------------------

async def _llm_dedup_check(name_a: str, goal_a: str, name_b: str, desc_b: str) -> bool:
    """Use LLM to determine if two capabilities are duplicates.

    Called for the ambiguous embedding similarity band (0.7-0.85).
    Returns True if LLM confirms duplication, False otherwise.
    On any failure, returns False (prefer false negatives for dedup).
    """
    try:
        from core.factory._llm import call_llm_json

        prompt = (
            "Determine if these two capabilities are duplicates or substantially "
            'overlapping. Respond with JSON: {"is_duplicate": true/false, "reason": "..."}\n\n'
            f"Capability A: name='{name_a}', goal='{goal_a}'\n"
            f"Capability B: name='{name_b}', description='{desc_b}'\n"
        )
        result = await call_llm_json(
            prompt,
            system="You are a capability deduplication checker. Be conservative -- "
            "only mark as duplicate if they serve the same core purpose.",
        )
        return result.get("is_duplicate", False)
    except Exception:
        logger.debug("LLM dedup check failed, treating as non-duplicate", exc_info=True)
        return False

# ---------------------------------------------------------------------------
# Section 5: check_existing_capabilities (public API #1)
# ---------------------------------------------------------------------------

async def check_existing_capabilities(name: str, goal: str) -> list[str]:
    """Three-stage dedup: name Jaccard -> embedding cosine -> LLM for ambiguous band.

    Returns list of warning strings for similar capabilities.
    Called from FactoryPipeline.create() step 1 (deduplication).

    Stage 1: Name Jaccard >= threshold (fast, no I/O)
    Stage 2: Embedding similarity >= threshold (Qdrant query, graceful degradation)
    Stage 3: LLM confirmation for 0.7-0.85 band (optional, graceful degradation)
    """
    config = get_factory_config()
    warnings: list[str] = []

    # Stage 1: Name Jaccard (fast, no I/O)
    capabilities = _get_all_capability_names()
    jaccard_threshold = config.deduplication_name_jaccard_threshold
    name_matches = [
        (c, _name_jaccard(name, c))
        for c in capabilities
        if _name_jaccard(name, c) >= jaccard_threshold
    ]
    for cap_name, score in name_matches:
        warnings.append(
            f"Name similarity: '{name}' matches existing '{cap_name}' (jaccard={score:.2f})"
        )

    # Stage 2: Embedding similarity (graceful degradation if Qdrant unavailable)
    embedding_threshold = config.deduplication_embedding_threshold
    try:
        from core.mcp.embeddings import get_tool_embedding_store

        store = get_tool_embedding_store()
        if store.available:
            results = store.search_tools(goal, top_k=5)
            for r in results:
                if r.score >= embedding_threshold:
                    warnings.append(
                        f"Similar capability exists: {r.name} (embedding={r.score:.2f})"
                    )
                elif 0.7 <= r.score < embedding_threshold:
                    # Stage 3: LLM confirmation for ambiguous band
                    is_dup = await _llm_dedup_check(
                        name,
                        goal,
                        r.name,
                        r.payload.get("description", "") if r.payload else "",
                    )
                    if is_dup:
                        warnings.append(
                            f"Possibly similar: {r.name} (LLM confirmed, embedding={r.score:.2f})"
                        )
    except Exception:
        logger.debug("Embedding dedup stage skipped", exc_info=True)

    return warnings

# ---------------------------------------------------------------------------
# Section 6: Signal 1 - Routing failure detection
# ---------------------------------------------------------------------------

def _detect_routing_failure_gaps(
    window_hours: int = 24,
    min_count: int = 3,
) -> list["RelevanceSignal"]:
    """Detect gaps from routing failure patterns in RoutingMetric DB.

    Uses fallback_activated=True or success_outcome=False as failure signals.
    Groups by message_hash for pattern detection (privacy-safe, not reversible).

    Also checks in-memory RoutingMetricsTracker.records for example queries
    (the original message text IS available in-memory but NOT in DB).
    """
    from core.factory.models import RelevanceSignal

    signals: list[RelevanceSignal] = []
    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)

    # Read from SQLAlchemy DB
    try:
        from core.database.models import RoutingMetric
        from core.database.session import get_session

        with get_session() as session:
            from sqlalchemy import or_

            failures = (
                session.query(RoutingMetric)
                .filter(
                    RoutingMetric.timestamp >= cutoff,
                    or_(
                        RoutingMetric.fallback_activated == True,  # noqa: E712
                        RoutingMetric.success_outcome == False,  # noqa: E712
                    ),
                )
                .all()
            )
            # Detach from session before closing
            failure_data = [
                {"message_hash": f.message_hash, "timestamp": f.timestamp} for f in failures
            ]
    except Exception:
        logger.debug("RoutingMetric query failed, skipping Signal 1", exc_info=True)
        return signals

    if not failure_data:
        return signals

    # Group by message_hash
    hash_counts = Counter(f["message_hash"] for f in failure_data)

    for msg_hash, count in hash_counts.items():
        if count >= min_count:
            hash_failures = [f for f in failure_data if f["message_hash"] == msg_hash]
            timestamps = [f["timestamp"] for f in hash_failures]

            signals.append(
                RelevanceSignal(
                    signal_type="routing_failure",
                    pattern=msg_hash,
                    count=count,
                    confidence=min(1.0, count / (min_count * 2)),
                    urgency="immediate" if count >= min_count * 2 else "batch",
                    first_seen=min(timestamps),
                    last_seen=max(timestamps),
                )
            )

    # Secondary grouping: normalize llm_tool_called from in-memory records
    # This catches semantically similar failures across different message hashes
    # (e.g., "search_web" and "web_search" both normalize to "search web")
    try:
        from core.orchestrator.routing_metrics import get_routing_metrics_tracker

        tracker = get_routing_metrics_tracker()

        # Map message_hash -> normalized verb+object from llm_tool_called
        hash_to_vo: dict[str, str] = {}
        for rec in tracker.records:
            if rec.timestamp >= cutoff and (rec.fallback_activated or not rec.success_outcome):
                tool_name = rec.llm_tool_called or ""
                if tool_name:
                    # Normalize: "search_web" -> "search web" -> _extract_verb_object
                    vo = _extract_verb_object(tool_name.replace("_", " "))
                    if vo:
                        hash_to_vo[rec.message_hash] = vo

        # Re-group DB failures by verb+object where mapping exists
        vo_counts: dict[str, int] = {}
        vo_timestamps: dict[str, list] = {}
        for fd in failure_data:
            h = fd["message_hash"]
            vo = hash_to_vo.get(h)
            if vo:
                vo_counts[vo] = vo_counts.get(vo, 0) + 1
                if vo not in vo_timestamps:
                    vo_timestamps[vo] = []
                vo_timestamps[vo].append(fd["timestamp"])

        # Add verb+object signals that weren't already captured by hash grouping
        existing_patterns = {s.pattern for s in signals}
        for vo, count in vo_counts.items():
            if count >= min_count and vo not in existing_patterns:
                ts_list = vo_timestamps[vo]
                signals.append(
                    RelevanceSignal(
                        signal_type="routing_failure",
                        pattern=f"vo:{vo}",
                        count=count,
                        confidence=min(1.0, count / (min_count * 2)),
                        urgency="immediate" if count >= min_count * 2 else "batch",
                        first_seen=min(ts_list),
                        last_seen=max(ts_list),
                    )
                )
    except Exception:
        logger.debug("Verb+object grouping failed, hash-only signals used", exc_info=True)

    return signals

# ---------------------------------------------------------------------------
# Section 7: Signal 2 - Escalation pattern detection
# ---------------------------------------------------------------------------

def _detect_escalation_gaps(
    window_hours: int = 72,
    min_count: int = 2,
) -> list["RelevanceSignal"]:
    """Detect gaps from escalation patterns in escalation_history table.

    Groups by action_type for pattern detection. Threshold: 2 creation-type
    escalations in 72 hours suggests a capability gap.
    """
    from core.factory.models import RelevanceSignal

    signals: list[RelevanceSignal] = []

    try:
        from core.factory.registry import get_factory_registry

        registry = get_factory_registry()
        history = registry.get_escalation_history(since_hours=window_hours)
    except Exception:
        logger.debug("Escalation history query failed, skipping Signal 2", exc_info=True)
        return signals

    if not history:
        return signals

    # Group by action_type
    type_groups: dict[str, list[dict]] = {}
    for entry in history:
        action_type = entry.get("action_type", "unknown")
        if action_type not in type_groups:
            type_groups[action_type] = []
        type_groups[action_type].append(entry)

    # Pre-filter: exclude action_types matching rejected suggestion categories
    rejected_categories: set[str] = set()
    try:
        from core.factory.registry import get_factory_registry as _get_reg

        reg = _get_reg()
        # Use the public last_rejection() method to check each action_type
        # rather than accessing _get_conn() private method directly.
        # We check all type_groups and pre-filter those with rejections.
        for action_type in list(type_groups.keys()):
            category = f"escalation_pattern:{action_type}"
            if reg.last_rejection(category=category):
                rejected_categories.add(action_type)
    except Exception:
        logger.debug("Failed to load rejected categories, no filtering applied", exc_info=True)

    for action_type, entries in type_groups.items():
        # Skip categories the user has already rejected
        if action_type in rejected_categories:
            logger.debug("Skipping rejected escalation category: %s", action_type)
            continue

        if len(entries) >= min_count:
            timestamps = [
                datetime.fromisoformat(e["created_at"]) for e in entries if e.get("created_at")
            ]
            example_names = [
                e.get("suggested_name", "") for e in entries if e.get("suggested_name")
            ][:5]  # Limit examples

            signals.append(
                RelevanceSignal(
                    signal_type="escalation_pattern",
                    pattern=action_type,
                    count=len(entries),
                    confidence=min(1.0, len(entries) / (min_count * 2)),
                    example_queries=example_names,
                    urgency="batch",
                    first_seen=min(timestamps) if timestamps else None,
                    last_seen=max(timestamps) if timestamps else None,
                )
            )

    return signals

# ---------------------------------------------------------------------------
# Section 8: Signal merging
# ---------------------------------------------------------------------------

def _merge_signals(
    routing_signals: list["RelevanceSignal"],
    escalation_signals: list["RelevanceSignal"],
    weight_routing: float = 0.6,
    weight_escalation: float = 0.4,
) -> list["RelevanceSignal"]:
    """Merge and weight signals from both sources.

    Routing failures (Signal 1) have weight 0.6, escalation patterns
    (Signal 2) have weight 0.4. Confidence is scaled by weight
    (e.g. confidence=1.0 with weight_routing=0.6 -> 0.6,
    confidence=0.0 -> 0.0). No floor boosting -- zero-confidence
    signals remain zero after weighting.
    """
    merged: list["RelevanceSignal"] = []

    for s in routing_signals:
        merged.append(
            s.model_copy(
                update={
                    "confidence": s.confidence * weight_routing,
                }
            )
        )

    for s in escalation_signals:
        merged.append(
            s.model_copy(
                update={
                    "confidence": s.confidence * weight_escalation,
                }
            )
        )

    # Sort by confidence descending
    merged.sort(key=lambda s: s.confidence, reverse=True)
    return merged

# ---------------------------------------------------------------------------
# Section 9: Rate limit checks
# ---------------------------------------------------------------------------

def _check_rate_limits(
    config: "FactoryConfig",
    category: str,
    session_id: str | None = None,
) -> tuple[bool, str]:
    """Check 6 rate limits. Returns (allowed, reason).

    Rate limits enforced here:
    1. Global kill switch (proactive_detection_enabled)
    2. Per-session limit (proactive_max_suggestions_per_session)
    3. Per-day limit (proactive_max_suggestions_per_day)
    4. Per-category/24h limit (1 per category per 24h)
    5. 72h rejection cooldown
    6. 24h creation cooldown (after any artifact creation)

    Note: The minimum failure count threshold (proactive_min_failure_count)
    is enforced upstream in _detect_routing_failure_gaps(min_count=...) at
    detection time, not here. Signals that don't meet the threshold are
    never emitted, so _check_rate_limits only sees already-qualified signals.
    """
    # 1. Global kill switch
    if not config.proactive_detection_enabled:
        return False, "proactive detection disabled"

    from core.factory.registry import get_factory_registry

    registry = get_factory_registry()

    # 2. Per-session limit
    if session_id:
        session_count = registry.count_suggestions(session_id=session_id)
        if session_count >= config.proactive_max_suggestions_per_session:
            return (
                False,
                f"session limit ({config.proactive_max_suggestions_per_session})",
            )

    # 3. Per-day limit
    day_count = registry.count_suggestions(since_hours=24)
    if day_count >= config.proactive_max_suggestions_per_day:
        return False, f"daily limit ({config.proactive_max_suggestions_per_day})"

    # 4. Per-category/24h limit
    cat_count = registry.count_suggestions(category=category, since_hours=24)
    if cat_count >= 1:
        return False, f"category limit for '{category}'"

    # 5. 72h rejection cooldown
    last_rej = registry.last_rejection(category=category)
    if last_rej:
        hours_since = (datetime.now(UTC) - last_rej).total_seconds() / 3600
        if hours_since < config.proactive_cooldown_after_rejection_hours:
            return (
                False,
                f"rejection cooldown ({hours_since:.0f}h < "
                f"{config.proactive_cooldown_after_rejection_hours}h)",
            )

    # 6. 24h creation cooldown
    last_creation = registry.last_artifact_creation()
    if last_creation:
        hours_since = (datetime.now(UTC) - last_creation).total_seconds() / 3600
        if hours_since < 24:
            return False, f"creation cooldown ({hours_since:.0f}h < 24h)"

    return True, "allowed"

# ---------------------------------------------------------------------------
# Section 10: Suggestion builder
# ---------------------------------------------------------------------------

def _build_suggestion(signals: list["RelevanceSignal"]) -> "ProactiveSuggestion":
    """Build a ProactiveSuggestion from merged signals."""
    from core.factory.models import ProactiveSuggestion

    combined_confidence = sum(s.confidence for s in signals) / len(signals) if signals else 0.0

    # Build reasoning from signal descriptions
    reasoning_parts: list[str] = []
    for s in signals:
        if s.signal_type == "routing_failure":
            reasoning_parts.append(
                f"Routing failures detected: {s.count} failures for pattern '{s.pattern}'"
            )
        elif s.signal_type == "escalation_pattern":
            reasoning_parts.append(f"Escalation pattern: {s.count} '{s.pattern}' requests")

    # Derive suggested goal from signals
    if signals and signals[0].example_queries:
        suggested_goal = f"Create capability to handle: {', '.join(signals[0].example_queries[:3])}"
    else:
        suggested_goal = (
            f"Create capability to address detected gap (confidence={combined_confidence:.2f})"
        )

    return ProactiveSuggestion(
        signals=signals,
        combined_confidence=min(1.0, combined_confidence),
        suggested_goal=suggested_goal,
        suggested_type=signals[0].suggested_type if signals else None,
        reasoning=(" | ".join(reasoning_parts) if reasoning_parts else "Gap detected from signals"),
    )

# ---------------------------------------------------------------------------
# Section 11: detect_gaps (public API #2)
# ---------------------------------------------------------------------------

async def detect_gaps() -> list["RelevanceSignal"]:
    """Detect capability gaps from routing failures and escalation patterns.

    Merges signals with weights: routing=0.6, escalation=0.4.
    Persists discovered signals to the relevance_signals table via upsert.

    Returns:
        List of RelevanceSignal objects representing detected gaps.
    """
    config = get_factory_config()

    # Signal 1: Routing failures
    routing_signals = _detect_routing_failure_gaps(
        window_hours=config.routing_failure_window_hours,
        min_count=config.proactive_min_failure_count,
    )

    # Signal 2: Escalation patterns
    escalation_signals = _detect_escalation_gaps(
        window_hours=config.escalation_pattern_window_hours,
        min_count=2,  # Hardcoded per spec: 2 in 72h
    )

    # Merge with weights
    merged = _merge_signals(routing_signals, escalation_signals)

    # Persist to registry
    try:
        from core.factory.registry import get_factory_registry

        registry = get_factory_registry()
        for signal in merged:
            registry.upsert_signal(signal)
    except Exception:
        logger.debug("Failed to persist signals to registry", exc_info=True)

    return merged

# ---------------------------------------------------------------------------
# Section 12: get_proactive_suggestions (public API #3)
# ---------------------------------------------------------------------------

async def get_proactive_suggestions(
    session_id: str | None = None,
) -> list["ProactiveSuggestion"]:
    """Full proactive suggestion pipeline: detect gaps, check rate limits, build suggestions.

    Args:
        session_id: Optional session identifier for per-session rate limiting.

    Returns:
        List of ProactiveSuggestion objects (typically 0-1 per call).
    """
    config = get_factory_config()

    # Detect gaps
    signals = await detect_gaps()

    if not signals:
        return []

    suggestions: list["ProactiveSuggestion"] = []

    # Group signals by type for category-based rate limiting
    for signal in signals:
        category = f"{signal.signal_type}:{signal.pattern}"

        # Check rate limits
        allowed, reason = _check_rate_limits(config, category, session_id)
        if not allowed:
            logger.debug("Rate limit blocked suggestion: %s", reason)
            continue

        suggestion = _build_suggestion([signal])
        suggestions.append(suggestion)

        # Log the suggestion for rate limit tracking
        try:
            from core.factory.registry import get_factory_registry

            registry = get_factory_registry()
            registry.record_suggestion(
                category=category,
                status="pending",
                session_id=session_id or "",
            )
        except Exception:
            logger.debug("Failed to log suggestion", exc_info=True)

        # Only return first valid suggestion (per-call limit)
        break

    return suggestions
