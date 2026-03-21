"""Unit tests for the FailoverEngine.

Covers: success on first provider, fallback on timeout/429/500/502/connection error,
circuit breaker skip, all-providers-exhausted, and cancel event behavior.
"""

import asyncio

import pytest

from core.orchestrator.circuit_breaker import CircuitBreaker, CircuitConfig
from core.providers.llm_adapter import LLMConfig
from core.providers.resilience import failover_engine as _fe
from core.providers.resilience.failover_engine import (
    AllProvidersExhaustedError,
    execute_with_fallback,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(provider: str, model: str) -> LLMConfig:
    return LLMConfig(
        provider=provider,
        model=model,
        base_url=None,
        api_key=f"key-{provider}",
        temperature=0.7,
        max_tokens=1024,
        timeout=30,
        source="test",
    )

CONFIG_A = _make_config("openai", "gpt-4o")
CONFIG_B = _make_config("anthropic", "claude-3-haiku")
CONFIG_C = _make_config("vllm", "local-model")

async def _success(config: LLMConfig) -> str:
    return f"response_from_{config.provider}"

async def _fail_with_timeout(config: LLMConfig) -> str:
    await asyncio.sleep(20)  # longer than any test timeout
    return "should not reach here"

def _fail_with_429(config: LLMConfig):
    """Return a coroutine that raises httpx 429."""

    async def _inner(cfg: LLMConfig) -> str:
        import httpx

        resp = httpx.Response(429, request=httpx.Request("POST", "https://api.test/chat"))
        raise httpx.HTTPStatusError("rate limited", request=resp.request, response=resp)

    return _inner(config)

def _fail_with_500(config: LLMConfig):
    async def _inner(cfg: LLMConfig) -> str:
        import httpx

        resp = httpx.Response(500, request=httpx.Request("POST", "https://api.test/chat"))
        raise httpx.HTTPStatusError("server error", request=resp.request, response=resp)

    return _inner(config)

def _fail_with_502(config: LLMConfig):
    async def _inner(cfg: LLMConfig) -> str:
        import httpx

        resp = httpx.Response(502, request=httpx.Request("POST", "https://api.test/chat"))
        raise httpx.HTTPStatusError("bad gateway", request=resp.request, response=resp)

    return _inner(config)

async def _fail_with_connection_error(config: LLMConfig) -> str:
    raise ConnectionError("Connection refused")

# ---------------------------------------------------------------------------
# Fresh circuit breaker per test (avoids state leak)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_module_circuit_breaker():
    """Replace the module-level PROVIDER_CIRCUIT_BREAKER with a fresh one before each test.

    This prevents state leakage between tests — the global circuit breaker
    accumulates failure state that would affect subsequent tests.
    """
    fresh = CircuitBreaker(
        config=CircuitConfig(
            failure_threshold=1,
            success_threshold=2,
            reset_timeout_seconds=60.0,
            sliding_window_seconds=120.0,
        )
    )
    original = _fe.PROVIDER_CIRCUIT_BREAKER
    _fe.PROVIDER_CIRCUIT_BREAKER = fresh
    yield fresh
    _fe.PROVIDER_CIRCUIT_BREAKER = original

@pytest.fixture()
def fresh_cb() -> CircuitBreaker:
    """Return a fresh CircuitBreaker with threshold=1 (aggressive config matching prod)."""
    return CircuitBreaker(
        config=CircuitConfig(
            failure_threshold=1,
            success_threshold=2,
            reset_timeout_seconds=60.0,
            sliding_window_seconds=120.0,
        )
    )

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFirstProviderSucceeds:
    async def test_returns_first_provider_result(self, fresh_cb: CircuitBreaker) -> None:
        calls: list[str] = []

        async def tracked_success(config: LLMConfig) -> str:
            calls.append(config.provider)
            return f"response_from_{config.provider}"

        result = await execute_with_fallback(
            chain=[CONFIG_A, CONFIG_B],
            call_fn=tracked_success,
        )

        assert result == "response_from_openai"
        assert calls == ["openai"]  # second provider never called

    async def test_success_returns_immediately(self) -> None:
        result = await execute_with_fallback(
            chain=[CONFIG_A],
            call_fn=_success,
        )
        assert result == "response_from_openai"

class TestFallbackOnTimeout:
    async def test_fallback_on_timeout(self, fresh_cb: CircuitBreaker) -> None:
        call_order: list[str] = []

        async def fn(config: LLMConfig) -> str:
            call_order.append(config.provider)
            if config.provider == "openai":
                # Simulate timeout via asyncio.wait_for
                raise asyncio.TimeoutError()
            return f"response_from_{config.provider}"

        result = await execute_with_fallback(
            chain=[CONFIG_A, CONFIG_B],
            call_fn=fn,
        )

        assert result == "response_from_anthropic"
        assert call_order == ["openai", "anthropic"]

    async def test_failover_callback_called_on_timeout(self) -> None:
        failovers: list[tuple[str, str]] = []

        async def fn(config: LLMConfig) -> str:
            if config.provider == "openai":
                raise asyncio.TimeoutError()
            return "ok"

        await execute_with_fallback(
            chain=[CONFIG_A, CONFIG_B],
            call_fn=fn,
            on_failover=lambda frm, to, reason: failovers.append((frm, to)),
        )

        assert len(failovers) == 1
        assert "openai" in failovers[0][0]
        assert "anthropic" in failovers[0][1]

class TestFallbackOnHTTPErrors:
    async def test_fallback_on_429(self) -> None:
        async def fn(config: LLMConfig) -> str:
            if config.provider == "openai":
                return await _fail_with_429(config)
            return f"ok_from_{config.provider}"

        result = await execute_with_fallback(
            chain=[CONFIG_A, CONFIG_B],
            call_fn=fn,
        )
        assert result == "ok_from_anthropic"

    async def test_fallback_on_500(self) -> None:
        async def fn(config: LLMConfig) -> str:
            if config.provider == "openai":
                return await _fail_with_500(config)
            return f"ok_from_{config.provider}"

        result = await execute_with_fallback(
            chain=[CONFIG_A, CONFIG_B],
            call_fn=fn,
        )
        assert result == "ok_from_anthropic"

    async def test_fallback_on_502(self) -> None:
        async def fn(config: LLMConfig) -> str:
            if config.provider == "openai":
                return await _fail_with_502(config)
            return f"ok_from_{config.provider}"

        result = await execute_with_fallback(
            chain=[CONFIG_A, CONFIG_B],
            call_fn=fn,
        )
        assert result == "ok_from_anthropic"

    async def test_fallback_on_connection_error(self) -> None:
        async def fn(config: LLMConfig) -> str:
            if config.provider == "openai":
                await _fail_with_connection_error(config)
            return f"ok_from_{config.provider}"

        result = await execute_with_fallback(
            chain=[CONFIG_A, CONFIG_B],
            call_fn=fn,
        )
        assert result == "ok_from_anthropic"

class TestAllProvidersExhausted:
    async def test_raises_when_all_fail(self) -> None:
        async def always_fail(config: LLMConfig) -> str:
            raise ConnectionError("mock failure")

        with pytest.raises(AllProvidersExhaustedError):
            await execute_with_fallback(
                chain=[CONFIG_A, CONFIG_B],
                call_fn=always_fail,
            )

    async def test_raises_on_empty_chain(self) -> None:
        with pytest.raises(AllProvidersExhaustedError):
            await execute_with_fallback(
                chain=[],
                call_fn=_success,
            )

class TestCircuitBreakerSkip:
    async def test_open_circuit_provider_skipped(
        self, reset_module_circuit_breaker: CircuitBreaker
    ) -> None:
        """Provider with open circuit should never have call_fn invoked."""
        cb = reset_module_circuit_breaker
        # Force openai's circuit open
        cb.record_failure("openai:gpt-4o")

        called: list[str] = []

        async def fn(config: LLMConfig) -> str:
            called.append(config.provider)
            return f"ok_from_{config.provider}"

        result = await execute_with_fallback(
            chain=[CONFIG_A, CONFIG_B],
            call_fn=fn,
        )

        assert result == "ok_from_anthropic"
        assert "openai" not in called

    async def test_all_circuits_open_raises_exhausted(
        self, reset_module_circuit_breaker: CircuitBreaker
    ) -> None:
        """If all providers have open circuits, AllProvidersExhaustedError is raised."""
        cb = reset_module_circuit_breaker
        cb.record_failure("openai:gpt-4o")
        cb.record_failure("anthropic:claude-3-haiku")

        with pytest.raises(AllProvidersExhaustedError):
            await execute_with_fallback(
                chain=[CONFIG_A, CONFIG_B],
                call_fn=_success,
            )

class TestCancelEvent:
    async def test_cancel_event_stops_chain_immediately(self) -> None:
        """If cancel_event is set before iteration, AllProvidersExhaustedError raised immediately."""
        cancel = asyncio.Event()
        cancel.set()

        with pytest.raises(AllProvidersExhaustedError):
            await execute_with_fallback(
                chain=[CONFIG_A, CONFIG_B],
                call_fn=_success,
                cancel_event=cancel,
            )

    async def test_cancel_event_stops_chain_between_providers(self) -> None:
        """If cancel is set after first provider fails, chain stops."""
        cancel = asyncio.Event()

        async def fn(config: LLMConfig) -> str:
            if config.provider == "openai":
                cancel.set()  # Set cancel after first failure
                raise ConnectionError("mock")
            return f"ok_from_{config.provider}"

        with pytest.raises(AllProvidersExhaustedError):
            await execute_with_fallback(
                chain=[CONFIG_A, CONFIG_B],
                call_fn=fn,
                cancel_event=cancel,
            )
