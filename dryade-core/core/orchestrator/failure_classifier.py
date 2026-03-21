"""Deterministic failure classifier (Tier 1).

Two-tier classification architecture:
  Tier 1 (this module): Deterministic pattern matching on HTTP status codes,
      exception types, and error message strings. Handles ~70% of errors at
      zero LLM cost. Returns ErrorClassification with confidence=1.0 for
      deterministic matches.
  Tier 2 (failure_think in ThinkingProvider): LLM-based semantic analysis
      for errors that Tier 1 cannot classify. Triggered when Tier 1 returns
      category=SEMANTIC with confidence=0.0.

Priority order (first match wins):
  1. HTTP status code
  2. Exception type name
  2.5. External rule sources (plugin-provided, Phase 118.8)
  3. Error message string patterns
  4. Default: SEMANTIC / DEGRADED / ESCALATE (confidence=0.0 -> pass to Tier 2)
"""

import logging
import re
import threading
from typing import Callable, Optional

from core.orchestrator.models import (
    ErrorCategory,
    ErrorClassification,
    ErrorSeverity,
    FailureAction,
    ToolError,
)

# ---------------------------------------------------------------------------
# Compiled regex patterns for Priority 3 (string matching)
# ---------------------------------------------------------------------------

# Rate limiting patterns
RE_RATE_LIMIT = re.compile(
    r"rate limit|too many requests|quota exceeded|throttl",
    re.IGNORECASE,
)

# Authentication patterns
RE_AUTH = re.compile(
    r"unauthorized|unauthenticated|invalid.*token|expired.*token|invalid api key",
    re.IGNORECASE,
)

# Permission patterns
RE_PERMISSION = re.compile(
    r"permission denied|access denied|forbidden|not allowed|path outside allowed",
    re.IGNORECASE,
)

# Agent/tool not found patterns
RE_AGENT_NOT_FOUND = re.compile(
    r"agent.*not found|no suitable agent|no agent available|not found in registry",
    re.IGNORECASE,
)

# Context overflow patterns
RE_CONTEXT_OVERFLOW = re.compile(
    r"context.*overflow|token limit|maximum context length|context length exceeded|too many tokens",
    re.IGNORECASE,
)

# Connection patterns
RE_CONNECTION = re.compile(
    r"connection refused|connection reset|connection timed out|dns resolution|name resolution",
    re.IGNORECASE,
)

# Resource exhaustion patterns
RE_RESOURCE = re.compile(
    r"out of memory|disk full|no space left|gpu memory",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# HTTP status code mapping (Priority 1)
# ---------------------------------------------------------------------------

_HTTP_STATUS_MAP: dict[int, tuple[ErrorCategory, ErrorSeverity, FailureAction]] = {
    429: (ErrorCategory.RATE_LIMIT, ErrorSeverity.RETRIABLE, FailureAction.RETRY),
    401: (ErrorCategory.AUTH, ErrorSeverity.FATAL, FailureAction.ESCALATE),
    403: (ErrorCategory.AUTH, ErrorSeverity.FATAL, FailureAction.ESCALATE),
    404: (ErrorCategory.TOOL_NOT_FOUND, ErrorSeverity.FATAL, FailureAction.ESCALATE),
    500: (ErrorCategory.TRANSIENT, ErrorSeverity.RETRIABLE, FailureAction.RETRY),
    502: (ErrorCategory.TRANSIENT, ErrorSeverity.RETRIABLE, FailureAction.RETRY),
    503: (ErrorCategory.TRANSIENT, ErrorSeverity.RETRIABLE, FailureAction.RETRY),
    400: (ErrorCategory.PERMANENT, ErrorSeverity.FATAL, FailureAction.ESCALATE),
}

# ---------------------------------------------------------------------------
# Exception type mapping (Priority 2)
# Groups of exception type names -> classification
# ---------------------------------------------------------------------------

_EXCEPTION_TYPE_GROUPS: list[tuple[frozenset[str], ErrorCategory, ErrorSeverity, FailureAction]] = [
    # Timeout errors -> TRANSIENT / RETRIABLE / RETRY
    (
        frozenset({"TimeoutError", "asyncio.TimeoutError", "Timeout"}),
        ErrorCategory.TRANSIENT,
        ErrorSeverity.RETRIABLE,
        FailureAction.RETRY,
    ),
    # Connection errors -> CONNECTION / RETRIABLE / RETRY
    (
        frozenset({"ConnectionError", "ConnectError", "ConnectionRefusedError"}),
        ErrorCategory.CONNECTION,
        ErrorSeverity.RETRIABLE,
        FailureAction.RETRY,
    ),
    # Parse errors -> PARSE_ERROR / DEGRADED / RETRY
    (
        frozenset({"JSONDecodeError", "json.decoder.JSONDecodeError"}),
        ErrorCategory.PARSE_ERROR,
        ErrorSeverity.DEGRADED,
        FailureAction.RETRY,
    ),
    # Resource errors -> RESOURCE / FATAL / ABORT
    (
        frozenset({"MemoryError", "OutOfMemoryError"}),
        ErrorCategory.RESOURCE,
        ErrorSeverity.FATAL,
        FailureAction.ABORT,
    ),
    # Permanent programming errors -> PERMANENT / FATAL / ESCALATE
    (
        frozenset({"ValueError", "TypeError", "AttributeError"}),
        ErrorCategory.PERMANENT,
        ErrorSeverity.FATAL,
        FailureAction.ESCALATE,
    ),
    # Permission errors -> PERMISSION / FATAL / ESCALATE
    (
        frozenset({"PermissionError", "PermissionDenied"}),
        ErrorCategory.PERMISSION,
        ErrorSeverity.FATAL,
        FailureAction.ESCALATE,
    ),
]

# ---------------------------------------------------------------------------
# String pattern mapping (Priority 3)
# Ordered list of (compiled_regex, category, severity, action)
# ---------------------------------------------------------------------------

_MESSAGE_PATTERN_RULES: list[
    tuple[re.Pattern[str], ErrorCategory, ErrorSeverity, FailureAction]
] = [
    (RE_RATE_LIMIT, ErrorCategory.RATE_LIMIT, ErrorSeverity.RETRIABLE, FailureAction.RETRY),
    (RE_AUTH, ErrorCategory.AUTH, ErrorSeverity.FATAL, FailureAction.ESCALATE),
    (RE_PERMISSION, ErrorCategory.PERMISSION, ErrorSeverity.FATAL, FailureAction.ESCALATE),
    (RE_AGENT_NOT_FOUND, ErrorCategory.TOOL_NOT_FOUND, ErrorSeverity.FATAL, FailureAction.ESCALATE),
    (
        RE_CONTEXT_OVERFLOW,
        ErrorCategory.CONTEXT_OVERFLOW,
        ErrorSeverity.DEGRADED,
        FailureAction.CONTEXT_REDUCE,
    ),
    (RE_CONNECTION, ErrorCategory.CONNECTION, ErrorSeverity.RETRIABLE, FailureAction.RETRY),
    (RE_RESOURCE, ErrorCategory.RESOURCE, ErrorSeverity.FATAL, FailureAction.ABORT),
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# External rule sources (Priority 2.5, Phase 118.8)
# Plugin-provided classification rules inserted between exception type
# and message pattern checks.
# ---------------------------------------------------------------------------

_external_rule_sources: list[Callable[[ToolError], Optional[ErrorClassification]]] = []
_rule_sources_lock = threading.Lock()

def register_rule_source(
    fn: Callable[[ToolError], Optional[ErrorClassification]],
) -> None:
    """Register an external classification rule source.

    External rules run at Priority 2.5 (after exception type, before message
    patterns).  First non-None result from any source wins.  Errors in
    individual rule sources are caught and logged (best-effort).

    Thread-safe: guarded by ``_rule_sources_lock``.
    """
    with _rule_sources_lock:
        _external_rule_sources.append(fn)

def clear_external_rule_sources() -> None:
    """Remove all external rule sources.  Primarily for testing cleanup."""
    with _rule_sources_lock:
        _external_rule_sources.clear()

class FailureClassifier:
    """Deterministic Tier 1 error classifier.

    Classifies ToolError instances into ErrorClassification using pattern
    matching rules with no LLM calls. Priority order: HTTP status > exception
    type > message patterns > default SEMANTIC fallback.

    When the default SEMANTIC classification is returned (confidence=0.0),
    the caller should invoke Tier 2 (failure_think) for LLM-based analysis.

    Usage:
        classification = FailureClassifier.classify(tool_error)
        if classification.confidence == 0.0:
            # Pass to Tier 2 LLM-based classifier
            ...
    """

    @staticmethod
    def classify(error: ToolError) -> ErrorClassification:
        """Classify a ToolError into an ErrorClassification.

        Applies rules in priority order (first match wins):
          1. HTTP status code
          2. Exception type name
          2.5. External rule sources (plugin-provided)
          3. Error message patterns
          4. Default SEMANTIC fallback (confidence=0.0)

        Args:
            error: The ToolError to classify.

        Returns:
            ErrorClassification with category, severity, suggested_action,
            confidence (1.0 for deterministic, 0.0 for default), and reason.
        """
        return (
            _classify_by_http_status(error)
            or _classify_by_exception_type(error)
            or _classify_by_external_rules(error)
            or _classify_by_message_pattern(error)
            or _default_classification(error)
        )

# ---------------------------------------------------------------------------
# Internal classification functions
# ---------------------------------------------------------------------------

def _classify_by_http_status(error: ToolError) -> Optional[ErrorClassification]:
    """Priority 1: Classify by HTTP status code."""
    if error.http_status is None:
        return None
    mapping = _HTTP_STATUS_MAP.get(error.http_status)
    if mapping is None:
        return None
    category, severity, action = mapping
    return ErrorClassification(
        category=category,
        severity=severity,
        suggested_action=action,
        confidence=1.0,
        reason=f"HTTP {error.http_status}",
    )

def _classify_by_exception_type(error: ToolError) -> Optional[ErrorClassification]:
    """Priority 2: Classify by exception type name."""
    if not error.error_type:
        return None
    for type_set, category, severity, action in _EXCEPTION_TYPE_GROUPS:
        if error.error_type in type_set:
            return ErrorClassification(
                category=category,
                severity=severity,
                suggested_action=action,
                confidence=1.0,
                reason=f"Exception type: {error.error_type}",
            )
    return None

def _classify_by_external_rules(error: ToolError) -> Optional[ErrorClassification]:
    """Priority 2.5: Classify by external (plugin-provided) rule sources.

    Takes a snapshot of the sources list under lock for thread safety.
    First non-None result wins.  Errors in individual sources are caught
    and logged.
    """
    with _rule_sources_lock:
        sources = list(_external_rule_sources)
    for fn in sources:
        try:
            result = fn(error)
            if result is not None:
                return result
        except Exception:
            logger.debug(
                "[FAILURE_CLASSIFIER] External rule source %s failed",
                getattr(fn, "__name__", repr(fn)),
                exc_info=True,
            )
    return None

def _classify_by_message_pattern(error: ToolError) -> Optional[ErrorClassification]:
    """Priority 3: Classify by error message string patterns."""
    msg = error.message_lower
    if not msg:
        return None
    for pattern, category, severity, action in _MESSAGE_PATTERN_RULES:
        if pattern.search(msg):
            return ErrorClassification(
                category=category,
                severity=severity,
                suggested_action=action,
                confidence=1.0,
                reason=f"Message pattern: {pattern.pattern}",
            )
    return None

def _default_classification(error: ToolError) -> ErrorClassification:
    """Priority 4: Default SEMANTIC classification (pass to Tier 2 LLM)."""
    return ErrorClassification(
        category=ErrorCategory.SEMANTIC,
        severity=ErrorSeverity.DEGRADED,
        suggested_action=FailureAction.ESCALATE,
        confidence=0.0,
        reason="No deterministic rule matched; pass to Tier 2 LLM classifier",
    )
