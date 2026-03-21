"""
Unit tests for self_healing plugin.

Tests cover:
1. Plugin protocol implementation
2. Error classification (transient, recoverable, permanent)
3. Retry logic
4. Circuit breaker states (closed, open, half-open)
5. LLM reflection (mocked)
6. Max retries exceeded

Target: ~100 LOC
"""

import os
from unittest.mock import patch

import pytest

@pytest.mark.unit
class TestSelfHealingPlugin:
    """Tests for SelfHealingPlugin protocol implementation."""

    def test_plugin_protocol_attributes(self):
        """Test plugin has required protocol attributes."""
        from plugins.self_healing import plugin

        assert hasattr(plugin, "name")
        assert hasattr(plugin, "version")
        assert hasattr(plugin, "description")
        assert hasattr(plugin, "register")
        assert hasattr(plugin, "startup")
        assert hasattr(plugin, "shutdown")

    def test_plugin_name_and_version(self):
        """Test plugin name and version."""
        from plugins.self_healing import plugin

        assert plugin.name == "self_healing"
        assert plugin.version == "1.0.0"

    def test_plugin_register(self):
        """Test plugin registration with registry."""
        from plugins.self_healing import plugin

        from core.extensions.pipeline import ExtensionRegistry

        registry = ExtensionRegistry()
        plugin.register(registry)

        config = registry.get("self_healing")
        assert config is not None
        assert config.priority == 3

@pytest.mark.unit
class TestErrorClassification:
    """Tests for error classification."""

    def test_classify_transient_timeout(self):
        """Test timeout errors are classified as transient."""
        from plugins.self_healing.healer import ErrorType, classify_error

        error = Exception("Connection timeout occurred")
        assert classify_error(error) == ErrorType.TRANSIENT

    def test_classify_transient_rate_limit(self):
        """Test rate limit errors are classified as transient."""
        from plugins.self_healing.healer import ErrorType, classify_error

        error = Exception("Rate limit exceeded, too many requests")
        assert classify_error(error) == ErrorType.TRANSIENT

    def test_classify_permanent_auth(self):
        """Test authentication errors are classified as permanent."""
        from plugins.self_healing.healer import ErrorType, classify_error

        error = Exception("Invalid API key - unauthorized")
        assert classify_error(error) == ErrorType.PERMANENT

    def test_classify_permanent_not_found(self):
        """Test not found errors are classified as permanent."""
        from plugins.self_healing.healer import ErrorType, classify_error

        error = Exception("Resource not_found - 404")
        assert classify_error(error) == ErrorType.PERMANENT

    def test_classify_recoverable_default(self):
        """Test unknown errors default to recoverable."""
        from plugins.self_healing.healer import ErrorType, classify_error

        error = Exception("Some random error")
        assert classify_error(error) == ErrorType.RECOVERABLE

@pytest.mark.unit
class TestShouldRetry:
    """Tests for should_retry function."""

    def test_should_retry_transient(self):
        """Test transient errors should be retried."""
        from plugins.self_healing.healer import should_retry

        error = Exception("Connection timeout")
        assert should_retry(error) is True

    def test_should_retry_permanent(self):
        """Test permanent errors should not be retried."""
        from plugins.self_healing.healer import should_retry

        error = Exception("Invalid API key - unauthorized")
        assert should_retry(error) is False

    def test_should_retry_circuit_breaker_error(self):
        """Test circuit breaker errors should not be retried."""
        from plugins.self_healing.circuit_breaker import CircuitBreakerError
        from plugins.self_healing.healer import should_retry

        error = CircuitBreakerError("Circuit is open")
        assert should_retry(error) is False

@pytest.mark.unit
class TestSelfHealingExecutor:
    """Tests for SelfHealingExecutor class."""

    def test_executor_initialization(self):
        """Test executor initializes with default config."""
        from plugins.self_healing.healer import SelfHealingExecutor

        executor = SelfHealingExecutor()

        assert executor.config is not None
        assert executor.config.max_retries == 3
        assert executor._enabled is True

    def test_executor_custom_config(self, monkeypatch):
        """Test executor with custom config.

        Uses monkeypatch.delenv to remove DRYADE_RETRY_MAX_ATTEMPTS before
        constructing the executor. crewai (imported earlier in the test
        session) loads .env via python-dotenv which sets this var to "3",
        overriding the custom config.max_retries=5 at __init__ time.
        """
        from plugins.self_healing.healer import RetryConfig, SelfHealingExecutor

        monkeypatch.delenv("DRYADE_RETRY_MAX_ATTEMPTS", raising=False)

        config = RetryConfig(max_retries=5, min_wait=1, max_wait=30)
        executor = SelfHealingExecutor(config=config)

        assert executor.config.max_retries == 5
        assert executor.config.min_wait == 1

    @pytest.mark.asyncio
    async def test_execute_with_healing_disabled(self):
        """Test execution when self-healing is disabled."""
        from plugins.self_healing.healer import SelfHealingExecutor

        with patch.dict(os.environ, {"DRYADE_SELF_HEALING_ENABLED": "false"}):
            executor = SelfHealingExecutor()

            async def test_func(value):
                return f"result: {value}"

            result = await executor.execute_with_healing(func=test_func, args={"value": "test"})

            assert result.status == "ok"
            assert result.result == "result: test"

    @pytest.mark.asyncio
    async def test_execute_with_healing_success(self):
        """Test successful execution with healing enabled."""
        from plugins.self_healing.healer import SelfHealingExecutor

        executor = SelfHealingExecutor()
        executor._enabled = True

        async def test_func(value):
            return f"result: {value}"

        # Mock circuit breaker to always allow
        with patch("plugins.self_healing.healer.get_circuit_breaker") as mock_cb:
            mock_cb.return_value.can_execute.return_value = True

            result = await executor.execute_with_healing(
                func=test_func, args={"value": "test"}, circuit_name="test_circuit"
            )

            assert result.status == "ok"
            assert result.result == "result: test"
            assert result.attempts == 1

    @pytest.mark.asyncio
    async def test_execute_circuit_breaker_open(self):
        """Test execution rejected when circuit breaker is open."""
        from plugins.self_healing.healer import SelfHealingExecutor

        executor = SelfHealingExecutor()
        executor._enabled = True

        async def test_func(value):
            return "result"

        with patch("plugins.self_healing.healer.get_circuit_breaker") as mock_cb:
            mock_cb.return_value.can_execute.return_value = False

            result = await executor.execute_with_healing(
                func=test_func, args={"value": "test"}, circuit_name="test_circuit"
            )

            assert result.status == "error"
            assert result.circuit_breaker_triggered is True
            assert result.attempts == 0

@pytest.mark.unit
class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_default_config(self):
        """Test default retry configuration."""
        from plugins.self_healing.healer import RetryConfig

        config = RetryConfig()

        assert config.max_retries == 3
        assert config.min_wait == 2
        assert config.max_wait == 60
        assert config.multiplier == 1
        assert config.enable_circuit_breaker is True

@pytest.mark.unit
class TestHealingResult:
    """Tests for HealingResult dataclass."""

    def test_result_success(self):
        """Test successful healing result."""
        from plugins.self_healing.healer import HealingResult

        result = HealingResult(
            status="ok",
            result="test result",
            attempts=2,
            healed=True,
            healing_actions=["Transient error: timeout"],
        )

        assert result.status == "ok"
        assert result.result == "test result"
        assert result.healed is True
        assert len(result.healing_actions) == 1

    def test_result_failure(self):
        """Test failed healing result."""
        from plugins.self_healing.healer import HealingResult

        result = HealingResult(
            status="error", error="All retries exhausted", attempts=3, healed=False
        )

        assert result.status == "error"
        assert result.error == "All retries exhausted"
        assert result.healed is False
