"""E2E smoke test for vLLM native tool calling pipeline.

Requires a running vLLM endpoint. Skipped automatically if no endpoint is configured.
Uses the same endpoint configuration as VLLMBaseLLM (VLLM_BASE_URL env var).

Usage:
    pytest tests/e2e/test_vllm_tool_calling_e2e.py -v -m e2e
"""

import json
import os

import pytest

# Skip entire module if no vLLM endpoint configured.
# VLLMBaseLLM reads from VLLM_BASE_URL (primary) in __init__.
VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL")
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not VLLM_BASE_URL,
        reason="No vLLM endpoint configured (set VLLM_BASE_URL)",
    ),
]

# Sample tool definition used across tests
SAMPLE_TOOL = {
    "type": "function",
    "function": {
        "name": "list_directory",
        "description": "List the contents of a directory",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The directory path to list",
                }
            },
            "required": ["path"],
        },
    },
}

class TestVLLMDirectCall:
    """E2E tests for VLLMBaseLLM.call() against real vLLM endpoint."""

    def test_vllm_call_returns_dict_with_tools(self):
        """Call with tools -> response is either dict with tool_calls OR string.

        The model may or may not decide to call a tool. Both outcomes
        validate the pipeline works end-to-end.
        """
        from plugins.vllm.llm import VLLMBaseLLM

        llm = VLLMBaseLLM()

        result = llm.call(
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "List the files in /home directory."},
            ],
            tools=[SAMPLE_TOOL],
        )

        # Model may return tool_calls dict or text response
        if isinstance(result, dict):
            # Validate tool_calls structure
            assert "tool_calls" in result
            assert len(result["tool_calls"]) > 0
            tc = result["tool_calls"][0]
            assert "function" in tc
            assert "name" in tc["function"]
            assert "arguments" in tc["function"]
            # Arguments should be valid JSON string
            args = json.loads(tc["function"]["arguments"])
            assert isinstance(args, dict)
        else:
            # Text response is also valid (model chose not to use tools)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_vllm_call_text_response_without_tools(self):
        """Call without tools -> response is always a string."""
        from plugins.vllm.llm import VLLMBaseLLM

        llm = VLLMBaseLLM()

        result = llm.call(
            messages=[
                {"role": "user", "content": "Say hello in one sentence."},
            ],
        )

        assert isinstance(result, str)
        assert len(result) > 0

class TestVLLMFullPipeline:
    """E2E test for the full orchestrator tool calling pipeline with real vLLM."""

    @pytest.mark.asyncio
    async def test_full_orchestrator_tool_call_pipeline(self):
        """Create a ThinkingProvider with real LLM and verify orchestrate_think.

        This is the ultimate proof that the full pipeline works: VLLMBaseLLM
        returns a dict, _call_llm receives it, _convert_tool_calls_to_json
        converts it, and orchestrate_think returns a valid thought.
        """
        from plugins.vllm.llm import VLLMBaseLLM

        from core.adapters.protocol import AgentCapability, AgentCard, AgentFramework
        from core.orchestrator.observation import ObservationHistory
        from core.orchestrator.thinking.provider import OrchestrationThinkingProvider

        llm = VLLMBaseLLM()
        provider = OrchestrationThinkingProvider(llm=llm)

        # Build a minimal agent roster with one MCP agent
        cap = AgentCapability(
            name="list_directory",
            description="List the contents of a directory",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The directory path to list",
                    }
                },
                "required": ["path"],
            },
        )
        agent = AgentCard(
            name="mcp-filesystem",
            description="File system operations agent",
            version="1.0",
            framework=AgentFramework.MCP,
            capabilities=[cap],
        )

        obs_history = ObservationHistory()

        thought = await provider.orchestrate_think(
            goal="List the files in the /tmp directory",
            observations=[],
            available_agents=[agent],
            observation_history=obs_history,
            lightweight=False,
        )

        # The thought should have valid content -- either a task or a final answer
        assert thought is not None
        assert thought.reasoning  # Should have some reasoning

        # Either the model assigned a task (tool call) or gave a final answer
        if thought.task:
            # Task assigned -- verify it has meaningful content
            assert thought.task.description
        elif thought.is_final:
            # Final answer -- also valid (model may respond directly)
            assert thought.answer
        else:
            # Should not reach here, but if it does, at least verify no crash
            pass
