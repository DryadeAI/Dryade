"""LangChain adapter e2e tests against live vLLM inference.

Uses a minimal SimpleVLLMAgent (ainvoke path) to test the LangChain adapter
without requiring the langchain package. Tests skip when vLLM is offline.
"""

import httpx
import pytest

from core.adapters.langchain_adapter import LangChainAgentAdapter
from core.adapters.protocol import AgentFramework
from tests.integration.test_adapter_e2e_conftest import (
    VLLM_BASE_URL,
    get_vllm_model_name,
    requires_vllm,
)

class SimpleVLLMAgent:
    """Minimal agent that calls vLLM OpenAI API via ainvoke.

    Simulates a LangGraph-style agent with an ainvoke method,
    allowing us to test the LangChain adapter's ainvoke branch
    without importing langchain.
    """

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url
        self.model = model

    async def ainvoke(self, inputs: dict) -> str:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": inputs.get("input", "")},
                    ],
                    "max_tokens": 100,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

@pytest.mark.integration
class TestLangChainAdapterE2E:
    """End-to-end tests for LangChain adapter."""

    @requires_vllm
    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_langchain_adapter_ainvoke_execution(self):
        """LangChain adapter executes via ainvoke with real vLLM inference."""
        model = get_vllm_model_name()
        assert model is not None, "Could not discover vLLM model name"

        agent = SimpleVLLMAgent(base_url=VLLM_BASE_URL, model=model)
        adapter = LangChainAgentAdapter(agent=agent, name="vllm_test", description="Test agent")
        result = await adapter.execute(
            "What is the capital of France? Reply with just the city name."
        )

        assert result.status == "ok", f"Expected ok, got {result.status}: {result.error}"
        assert result.result is not None
        assert "paris" in str(result.result).lower(), (
            f"Expected 'paris' in result, got: {result.result}"
        )
        assert result.metadata["framework"] in ("langgraph", "langchain")

    def test_langchain_adapter_get_card(self):
        """LangChain adapter returns card with correct framework."""
        agent = object()  # Minimal agent, no methods needed for card
        adapter = LangChainAgentAdapter(agent=agent, name="vllm_test", description="Test agent")
        card = adapter.get_card()
        assert card.framework == AgentFramework.LANGCHAIN
        assert card.name == "vllm_test"

    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_langchain_adapter_no_method_error(self):
        """LangChain adapter returns error when agent has no execution method."""
        agent = object()  # No ainvoke/arun/run methods
        adapter = LangChainAgentAdapter(
            agent=agent, name="broken_agent", description="Agent without methods"
        )
        result = await adapter.execute("test")
        assert result.status == "error"
        assert "no compatible execution method" in result.error.lower()
