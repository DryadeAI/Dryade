"""ADK adapter e2e tests with session persistence validation.

Tier 1 tests (always run): card, capabilities, not-available guard.
Tier 2 tests (require google-adk + vLLM): live execution, session persistence.
"""

from unittest.mock import MagicMock

import pytest

from core.adapters.adk_adapter import _ADK_AVAILABLE, ADKAgentAdapter
from core.adapters.protocol import AgentFramework
from tests.integration.test_adapter_e2e_conftest import (
    VLLM_BASE_URL,
    get_vllm_model_name,
    vllm_is_reachable,
)

# Combined skip for Tier 2 tests
requires_adk_and_vllm = pytest.mark.skipif(
    not _ADK_AVAILABLE or not vllm_is_reachable(),
    reason="Requires google-adk package and live vLLM",
)

def _register_litellm_for_openai():
    """Register ADK's LiteLLM backend for openai/* model patterns.

    ADK's LiteLlm class returns an empty supported_models() list, so it is
    never auto-registered. We register it manually with an 'openai/.*' pattern
    so ADK can route to vLLM via LiteLLM's OpenAI-compatible provider.
    """
    if not _ADK_AVAILABLE:
        return
    try:
        from google.adk.models.lite_llm import LiteLlm
        from google.adk.models.registry import LLMRegistry

        LLMRegistry._register(r"openai/.*", LiteLlm)
    except Exception:
        pass

_register_litellm_for_openai()

def _make_mock_agent(name: str = "test_agent") -> MagicMock:
    """Create a mock ADK agent with required attributes."""
    agent = MagicMock()
    agent.name = name
    agent.instruction = "Test instruction"
    agent.description = "Test agent description"
    agent.tools = []
    agent.version = "1.0"
    agent.model = None
    return agent

@pytest.mark.integration
class TestADKAdapterE2E:
    """End-to-end tests for ADK adapter."""

    # ------------------------------------------------------------------
    # Tier 1: Always runs (no google-adk needed)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_adk_adapter_not_available(self, monkeypatch):
        """ADK adapter returns error when _ADK_AVAILABLE is False."""
        import core.adapters.adk_adapter as adk_module

        monkeypatch.setattr(adk_module, "_ADK_AVAILABLE", False)

        agent = _make_mock_agent()
        adapter = ADKAgentAdapter(agent)
        result = await adapter.execute("test")

        assert result.status == "error"
        assert result.error == "ADK not available"

    def test_adk_adapter_get_card(self):
        """ADK adapter returns card with correct framework and metadata."""
        agent = _make_mock_agent("test_agent")
        adapter = ADKAgentAdapter(agent)
        card = adapter.get_card()

        assert card.framework == AgentFramework.ADK
        assert card.name == "test_agent"
        assert card.metadata["session_persistent"] is True

    def test_adk_adapter_capabilities(self):
        """ADK adapter reports session and artifact support."""
        agent = _make_mock_agent()
        adapter = ADKAgentAdapter(agent)
        caps = adapter.capabilities()

        assert caps.supports_sessions is True
        assert caps.supports_artifacts is True
        assert caps.supports_streaming is True

    # ------------------------------------------------------------------
    # Tier 2: Requires google-adk + vLLM
    # ------------------------------------------------------------------

    @requires_adk_and_vllm
    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_adk_adapter_live_execution(self):
        """ADK adapter executes task against live vLLM with session tracking."""
        import os

        from google.adk import Agent as ADKAgent

        model_name = get_vllm_model_name()
        assert model_name is not None, "Could not discover vLLM model name"

        # Configure ADK to use vLLM via OpenAI-compatible endpoint
        os.environ["OPENAI_API_KEY"] = "dummy"
        os.environ["OPENAI_BASE_URL"] = VLLM_BASE_URL

        try:
            adk_agent = ADKAgent(
                name="calculator",
                instruction="You are a helpful assistant. Answer questions concisely.",
                model=f"openai/{model_name}",
            )
            adapter = ADKAgentAdapter(adk_agent)
            result = await adapter.execute("What is 3+5? Reply with just the number.")

            assert result.status == "ok", f"Expected ok, got {result.status}: {result.error}"
            assert result.metadata.get("session_id") is not None
            assert result.metadata["framework"] == "adk"
        finally:
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ.pop("OPENAI_BASE_URL", None)

    @requires_adk_and_vllm
    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_adk_adapter_session_persistence(self):
        """ADK adapter maintains session across multiple execute() calls."""
        import os

        from google.adk import Agent as ADKAgent

        model_name = get_vllm_model_name()
        assert model_name is not None

        os.environ["OPENAI_API_KEY"] = "dummy"
        os.environ["OPENAI_BASE_URL"] = VLLM_BASE_URL

        try:
            adk_agent = ADKAgent(
                name="memory_test",
                instruction="You are a helpful assistant. Remember what the user tells you.",
                model=f"openai/{model_name}",
            )
            adapter = ADKAgentAdapter(adk_agent)

            result1 = await adapter.execute("Remember the number 42.")
            assert result1.status == "ok", f"First call failed: {result1.error}"
            session_id_1 = result1.metadata.get("session_id")

            result2 = await adapter.execute("What number did I ask you to remember?")
            assert result2.status == "ok", f"Second call failed: {result2.error}"
            session_id_2 = result2.metadata.get("session_id")

            # Same session across calls
            assert session_id_1 == session_id_2, (
                f"Session IDs differ: {session_id_1} vs {session_id_2}"
            )
            # Check the model referenced 42 in its response
            assert "42" in str(result2.result), f"Expected '42' in response, got: {result2.result}"
        finally:
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ.pop("OPENAI_BASE_URL", None)

    @requires_adk_and_vllm
    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_adk_adapter_reset_session(self):
        """ADK adapter creates new session ID after reset."""
        import os

        from google.adk import Agent as ADKAgent

        model_name = get_vllm_model_name()
        assert model_name is not None

        os.environ["OPENAI_API_KEY"] = "dummy"
        os.environ["OPENAI_BASE_URL"] = VLLM_BASE_URL

        try:
            adk_agent = ADKAgent(
                name="reset_test",
                instruction="You are a helpful assistant.",
                model=f"openai/{model_name}",
            )
            adapter = ADKAgentAdapter(adk_agent)

            result = await adapter.execute("Hello")
            assert result.status == "ok"
            old_session_id = result.metadata.get("session_id")

            new_session_id = await adapter.reset_session()

            assert new_session_id != old_session_id, (
                f"Session ID should change after reset: {old_session_id}"
            )
        finally:
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ.pop("OPENAI_BASE_URL", None)
