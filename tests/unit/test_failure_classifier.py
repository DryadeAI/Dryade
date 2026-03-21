"""Tests for FailureClassifier - deterministic error classification (Tier 1).

Covers all priority-ordered classification paths:
  Priority 1: HTTP status codes
  Priority 2: Exception types
  Priority 3: String patterns in message
  Priority 4: Default SEMANTIC fallback

Plan: 118.1-03
"""

from core.orchestrator.failure_classifier import FailureClassifier
from core.orchestrator.models import (
    ErrorCategory,
    ErrorClassification,
    ErrorSeverity,
    FailureAction,
    ToolError,
)

def _make_error(
    *,
    http_status: int | None = None,
    error_type: str = "",
    message: str = "",
    tool_name: str = "test-tool",
    server_name: str = "test-server",
) -> ToolError:
    """Helper to build ToolError with sensible defaults."""
    return ToolError(
        tool_name=tool_name,
        server_name=server_name,
        error_type=error_type,
        message=message,
        http_status=http_status,
    )

# ---- Priority 1: HTTP status code rules ----

class TestHTTPStatusClassification:
    """HTTP status code takes highest priority."""

    def test_429_rate_limit(self):
        result = FailureClassifier.classify(_make_error(http_status=429))
        assert result.category == ErrorCategory.RATE_LIMIT
        assert result.severity == ErrorSeverity.RETRIABLE
        assert result.suggested_action == FailureAction.RETRY
        assert result.confidence == 1.0

    def test_401_auth(self):
        result = FailureClassifier.classify(_make_error(http_status=401))
        assert result.category == ErrorCategory.AUTH
        assert result.severity == ErrorSeverity.FATAL
        assert result.suggested_action == FailureAction.ESCALATE

    def test_403_auth(self):
        result = FailureClassifier.classify(_make_error(http_status=403))
        assert result.category == ErrorCategory.AUTH
        assert result.severity == ErrorSeverity.FATAL
        assert result.suggested_action == FailureAction.ESCALATE

    def test_404_tool_not_found(self):
        result = FailureClassifier.classify(_make_error(http_status=404))
        assert result.category == ErrorCategory.TOOL_NOT_FOUND
        assert result.severity == ErrorSeverity.FATAL
        assert result.suggested_action == FailureAction.ESCALATE

    def test_500_transient(self):
        result = FailureClassifier.classify(_make_error(http_status=500))
        assert result.category == ErrorCategory.TRANSIENT
        assert result.severity == ErrorSeverity.RETRIABLE
        assert result.suggested_action == FailureAction.RETRY

    def test_502_transient(self):
        result = FailureClassifier.classify(_make_error(http_status=502))
        assert result.category == ErrorCategory.TRANSIENT
        assert result.severity == ErrorSeverity.RETRIABLE
        assert result.suggested_action == FailureAction.RETRY

    def test_503_transient(self):
        result = FailureClassifier.classify(_make_error(http_status=503))
        assert result.category == ErrorCategory.TRANSIENT
        assert result.severity == ErrorSeverity.RETRIABLE
        assert result.suggested_action == FailureAction.RETRY

    def test_400_permanent(self):
        result = FailureClassifier.classify(_make_error(http_status=400))
        assert result.category == ErrorCategory.PERMANENT
        assert result.severity == ErrorSeverity.FATAL
        assert result.suggested_action == FailureAction.ESCALATE

# ---- Priority 2: Exception type rules ----

class TestExceptionTypeClassification:
    """Exception type classification when no HTTP status matches."""

    def test_timeout_error(self):
        result = FailureClassifier.classify(_make_error(error_type="TimeoutError"))
        assert result.category == ErrorCategory.TRANSIENT
        assert result.severity == ErrorSeverity.RETRIABLE
        assert result.suggested_action == FailureAction.RETRY

    def test_asyncio_timeout_error(self):
        result = FailureClassifier.classify(_make_error(error_type="asyncio.TimeoutError"))
        assert result.category == ErrorCategory.TRANSIENT
        assert result.severity == ErrorSeverity.RETRIABLE
        assert result.suggested_action == FailureAction.RETRY

    def test_timeout_keyword(self):
        result = FailureClassifier.classify(_make_error(error_type="Timeout"))
        assert result.category == ErrorCategory.TRANSIENT
        assert result.severity == ErrorSeverity.RETRIABLE
        assert result.suggested_action == FailureAction.RETRY

    def test_connection_error(self):
        result = FailureClassifier.classify(_make_error(error_type="ConnectionError"))
        assert result.category == ErrorCategory.CONNECTION
        assert result.severity == ErrorSeverity.RETRIABLE
        assert result.suggested_action == FailureAction.RETRY

    def test_connect_error(self):
        result = FailureClassifier.classify(_make_error(error_type="ConnectError"))
        assert result.category == ErrorCategory.CONNECTION
        assert result.severity == ErrorSeverity.RETRIABLE
        assert result.suggested_action == FailureAction.RETRY

    def test_connection_refused_error(self):
        result = FailureClassifier.classify(_make_error(error_type="ConnectionRefusedError"))
        assert result.category == ErrorCategory.CONNECTION
        assert result.severity == ErrorSeverity.RETRIABLE
        assert result.suggested_action == FailureAction.RETRY

    def test_json_decode_error(self):
        result = FailureClassifier.classify(_make_error(error_type="JSONDecodeError"))
        assert result.category == ErrorCategory.PARSE_ERROR
        assert result.severity == ErrorSeverity.DEGRADED
        assert result.suggested_action == FailureAction.RETRY

    def test_json_decoder_full_path(self):
        result = FailureClassifier.classify(_make_error(error_type="json.decoder.JSONDecodeError"))
        assert result.category == ErrorCategory.PARSE_ERROR
        assert result.severity == ErrorSeverity.DEGRADED
        assert result.suggested_action == FailureAction.RETRY

    def test_memory_error(self):
        result = FailureClassifier.classify(_make_error(error_type="MemoryError"))
        assert result.category == ErrorCategory.RESOURCE
        assert result.severity == ErrorSeverity.FATAL
        assert result.suggested_action == FailureAction.ABORT

    def test_out_of_memory_error(self):
        result = FailureClassifier.classify(_make_error(error_type="OutOfMemoryError"))
        assert result.category == ErrorCategory.RESOURCE
        assert result.severity == ErrorSeverity.FATAL
        assert result.suggested_action == FailureAction.ABORT

    def test_value_error(self):
        result = FailureClassifier.classify(_make_error(error_type="ValueError"))
        assert result.category == ErrorCategory.PERMANENT
        assert result.severity == ErrorSeverity.FATAL
        assert result.suggested_action == FailureAction.ESCALATE

    def test_type_error(self):
        result = FailureClassifier.classify(_make_error(error_type="TypeError"))
        assert result.category == ErrorCategory.PERMANENT
        assert result.severity == ErrorSeverity.FATAL
        assert result.suggested_action == FailureAction.ESCALATE

    def test_attribute_error(self):
        result = FailureClassifier.classify(_make_error(error_type="AttributeError"))
        assert result.category == ErrorCategory.PERMANENT
        assert result.severity == ErrorSeverity.FATAL
        assert result.suggested_action == FailureAction.ESCALATE

    def test_permission_error_type(self):
        result = FailureClassifier.classify(_make_error(error_type="PermissionError"))
        assert result.category == ErrorCategory.PERMISSION
        assert result.severity == ErrorSeverity.FATAL
        assert result.suggested_action == FailureAction.ESCALATE

    def test_permission_denied_type(self):
        result = FailureClassifier.classify(_make_error(error_type="PermissionDenied"))
        assert result.category == ErrorCategory.PERMISSION
        assert result.severity == ErrorSeverity.FATAL
        assert result.suggested_action == FailureAction.ESCALATE

# ---- Priority 3: String pattern rules ----

class TestStringPatternClassification:
    """Message pattern classification when no HTTP status or exception type matches."""

    def test_rate_limit_message(self):
        result = FailureClassifier.classify(
            _make_error(message="Rate limit exceeded for this endpoint")
        )
        assert result.category == ErrorCategory.RATE_LIMIT
        assert result.severity == ErrorSeverity.RETRIABLE
        assert result.suggested_action == FailureAction.RETRY

    def test_too_many_requests_message(self):
        result = FailureClassifier.classify(
            _make_error(message="Too many requests, please slow down")
        )
        assert result.category == ErrorCategory.RATE_LIMIT
        assert result.suggested_action == FailureAction.RETRY

    def test_quota_exceeded_message(self):
        result = FailureClassifier.classify(_make_error(message="API quota exceeded for project"))
        assert result.category == ErrorCategory.RATE_LIMIT

    def test_throttled_message(self):
        result = FailureClassifier.classify(_make_error(message="Request was throttled"))
        assert result.category == ErrorCategory.RATE_LIMIT

    def test_unauthorized_message(self):
        result = FailureClassifier.classify(_make_error(message="unauthorized access to resource"))
        assert result.category == ErrorCategory.AUTH
        assert result.severity == ErrorSeverity.FATAL
        assert result.suggested_action == FailureAction.ESCALATE

    def test_invalid_token_message(self):
        result = FailureClassifier.classify(_make_error(message="invalid bearer token provided"))
        assert result.category == ErrorCategory.AUTH

    def test_expired_token_message(self):
        result = FailureClassifier.classify(_make_error(message="expired session token"))
        assert result.category == ErrorCategory.AUTH

    def test_invalid_api_key_message(self):
        result = FailureClassifier.classify(_make_error(message="invalid api key"))
        assert result.category == ErrorCategory.AUTH

    def test_permission_denied_message(self):
        result = FailureClassifier.classify(
            _make_error(message="permission denied for file /etc/shadow")
        )
        assert result.category == ErrorCategory.PERMISSION
        assert result.severity == ErrorSeverity.FATAL
        assert result.suggested_action == FailureAction.ESCALATE

    def test_access_denied_message(self):
        result = FailureClassifier.classify(
            _make_error(message="access denied to bucket s3://private")
        )
        assert result.category == ErrorCategory.PERMISSION

    def test_forbidden_message(self):
        result = FailureClassifier.classify(_make_error(message="This action is forbidden"))
        assert result.category == ErrorCategory.PERMISSION

    def test_not_allowed_message(self):
        result = FailureClassifier.classify(
            _make_error(message="Operation not allowed in this context")
        )
        assert result.category == ErrorCategory.PERMISSION

    def test_path_outside_allowed_message(self):
        result = FailureClassifier.classify(_make_error(message="path outside allowed directory"))
        assert result.category == ErrorCategory.PERMISSION

    def test_agent_not_found_message(self):
        result = FailureClassifier.classify(
            _make_error(message="Agent 'foo' not found in registry")
        )
        assert result.category == ErrorCategory.TOOL_NOT_FOUND
        assert result.severity == ErrorSeverity.FATAL
        assert result.suggested_action == FailureAction.ESCALATE

    def test_no_suitable_agent_message(self):
        result = FailureClassifier.classify(_make_error(message="no suitable agent for this task"))
        assert result.category == ErrorCategory.TOOL_NOT_FOUND

    def test_no_agent_available_message(self):
        result = FailureClassifier.classify(
            _make_error(message="no agent available to handle request")
        )
        assert result.category == ErrorCategory.TOOL_NOT_FOUND

    def test_not_found_in_registry_message(self):
        result = FailureClassifier.classify(_make_error(message="tool 'xyz' not found in registry"))
        assert result.category == ErrorCategory.TOOL_NOT_FOUND

    def test_context_overflow_message(self):
        result = FailureClassifier.classify(
            _make_error(message="maximum context length exceeded (128k)")
        )
        assert result.category == ErrorCategory.CONTEXT_OVERFLOW
        assert result.severity == ErrorSeverity.DEGRADED
        assert result.suggested_action == FailureAction.CONTEXT_REDUCE

    def test_token_limit_message(self):
        result = FailureClassifier.classify(
            _make_error(message="token limit reached for this model")
        )
        assert result.category == ErrorCategory.CONTEXT_OVERFLOW

    def test_too_many_tokens_message(self):
        result = FailureClassifier.classify(_make_error(message="too many tokens in input"))
        assert result.category == ErrorCategory.CONTEXT_OVERFLOW

    def test_context_length_exceeded_message(self):
        result = FailureClassifier.classify(
            _make_error(message="context length exceeded the limit")
        )
        assert result.category == ErrorCategory.CONTEXT_OVERFLOW

    def test_connection_refused_message(self):
        result = FailureClassifier.classify(_make_error(message="connection refused on port 8080"))
        assert result.category == ErrorCategory.CONNECTION
        assert result.severity == ErrorSeverity.RETRIABLE
        assert result.suggested_action == FailureAction.RETRY

    def test_connection_reset_message(self):
        result = FailureClassifier.classify(_make_error(message="connection reset by peer"))
        assert result.category == ErrorCategory.CONNECTION

    def test_dns_resolution_message(self):
        result = FailureClassifier.classify(
            _make_error(message="dns resolution failed for api.example.com")
        )
        assert result.category == ErrorCategory.CONNECTION

    def test_name_resolution_message(self):
        result = FailureClassifier.classify(_make_error(message="name resolution failed"))
        assert result.category == ErrorCategory.CONNECTION

    def test_out_of_memory_message(self):
        result = FailureClassifier.classify(
            _make_error(message="out of memory: cannot allocate 4GB")
        )
        assert result.category == ErrorCategory.RESOURCE
        assert result.severity == ErrorSeverity.FATAL
        assert result.suggested_action == FailureAction.ABORT

    def test_disk_full_message(self):
        result = FailureClassifier.classify(
            _make_error(message="disk full, cannot write checkpoint")
        )
        assert result.category == ErrorCategory.RESOURCE

    def test_no_space_left_message(self):
        result = FailureClassifier.classify(
            _make_error(message="no space left on device /dev/sda1")
        )
        assert result.category == ErrorCategory.RESOURCE

    def test_gpu_memory_message(self):
        result = FailureClassifier.classify(_make_error(message="CUDA: gpu memory exhausted"))
        assert result.category == ErrorCategory.RESOURCE

# ---- Priority 4: Default classification ----

class TestDefaultClassification:
    """Unknown errors get SEMANTIC/DEGRADED/ESCALATE with confidence=0.0."""

    def test_unknown_message(self):
        result = FailureClassifier.classify(_make_error(message="something unknown happened"))
        assert result.category == ErrorCategory.SEMANTIC
        assert result.severity == ErrorSeverity.DEGRADED
        assert result.suggested_action == FailureAction.ESCALATE
        assert result.confidence == 0.0

    def test_empty_error(self):
        result = FailureClassifier.classify(_make_error())
        assert result.category == ErrorCategory.SEMANTIC
        assert result.severity == ErrorSeverity.DEGRADED
        assert result.suggested_action == FailureAction.ESCALATE
        assert result.confidence == 0.0

# ---- Priority ordering tests ----

class TestPriorityOrdering:
    """HTTP > exception type > string pattern > default."""

    def test_http_overrides_message_pattern(self):
        """HTTP 429 should take priority over 'permission denied' in message."""
        result = FailureClassifier.classify(
            _make_error(http_status=429, message="permission denied")
        )
        assert result.category == ErrorCategory.RATE_LIMIT
        assert result.suggested_action == FailureAction.RETRY

    def test_exception_type_overrides_message_pattern(self):
        """TimeoutError type should take priority over 'permission denied' in message."""
        result = FailureClassifier.classify(
            _make_error(error_type="TimeoutError", message="permission denied")
        )
        assert result.category == ErrorCategory.TRANSIENT
        assert result.suggested_action == FailureAction.RETRY

    def test_http_overrides_exception_type(self):
        """HTTP status should override exception type classification."""
        result = FailureClassifier.classify(_make_error(http_status=401, error_type="TimeoutError"))
        assert result.category == ErrorCategory.AUTH
        assert result.suggested_action == FailureAction.ESCALATE

# ---- Confidence tests ----

class TestConfidence:
    """Verify confidence values for deterministic vs fallback classifications."""

    def test_deterministic_confidence_is_1(self):
        """All Priority 1-3 classifications should have confidence=1.0."""
        errors = [
            _make_error(http_status=429),
            _make_error(error_type="TimeoutError"),
            _make_error(message="rate limit exceeded"),
        ]
        for err in errors:
            result = FailureClassifier.classify(err)
            assert result.confidence == 1.0, (
                f"Expected confidence=1.0 for {err}, got {result.confidence}"
            )

    def test_default_confidence_is_0(self):
        """Default SEMANTIC classification should have confidence=0.0."""
        result = FailureClassifier.classify(_make_error(message="vague error happened"))
        assert result.confidence == 0.0

# ---- Return type tests ----

class TestReturnType:
    """Verify classify() always returns ErrorClassification."""

    def test_returns_error_classification(self):
        result = FailureClassifier.classify(_make_error(http_status=500))
        assert isinstance(result, ErrorClassification)

    def test_default_returns_error_classification(self):
        result = FailureClassifier.classify(_make_error(message="whatever"))
        assert isinstance(result, ErrorClassification)
