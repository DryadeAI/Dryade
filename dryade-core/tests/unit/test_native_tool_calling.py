"""Tests for native tool calling in OrchestrationThinkingProvider.

Covers the Phase 99-02 native tool calling pathway:
- _TEXT_ONLY_PROVIDERS constant
- _supports_native_tools() provider detection
- _build_tools_for_agents() OpenAI format conversion
- _call_llm() with and without tools parameter
- _convert_tool_calls_to_json() response bridging
- orchestrate_think() native tools vs text fallback integration
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from core.adapters.protocol import AgentCapability, AgentCard, AgentFramework
from core.orchestrator.observation import ObservationHistory
from core.orchestrator.thinking.provider import (
    _TEXT_ONLY_PROVIDERS,
    OrchestrationThinkingProvider,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_agent_card(name, capabilities=None):
    """Create an AgentCard with optional capabilities."""
    return AgentCard(
        name=name,
        description=f"Agent {name}",
        version="1.0",
        framework=AgentFramework.MCP,
        capabilities=capabilities or [],
    )

def make_capability(name, description="", input_schema=None):
    """Create an AgentCapability."""
    return AgentCapability(
        name=name,
        description=description or f"Tool {name}",
        input_schema=input_schema or {"type": "object", "properties": {}},
    )

class _LLMSpec:
    """Minimal spec for mock LLM -- does NOT have supports_function_calling."""

    model: str = ""
    _token_usage: dict = {}

    def call(self, **kwargs): ...

def make_mock_llm(
    model="openai/gpt-4",
    response='{"reasoning":"test","is_final":true,"answer":"ok"}',
):
    """Create a mock LLM with configurable model string and response.

    Uses _LLMSpec so that hasattr(llm, 'supports_function_calling') is False
    by default (MagicMock auto-creates attributes otherwise).
    """
    llm = MagicMock(spec=_LLMSpec)
    llm.model = model
    llm.call.return_value = response
    llm._token_usage = {"prompt_tokens": 100, "completion_tokens": 50}
    return llm

def make_observation_history(observations=None):
    """Create an ObservationHistory optionally pre-populated."""
    history = ObservationHistory()
    for obs in observations or []:
        history.add(obs)
    return history

# ---------------------------------------------------------------------------
# Test _TEXT_ONLY_PROVIDERS constant
# ---------------------------------------------------------------------------

class TestTextOnlyProviders:
    """Verify _TEXT_ONLY_PROVIDERS denylist content."""

    def test_text_only_providers_contains_ollama(self):
        assert "ollama" in _TEXT_ONLY_PROVIDERS

    def test_text_only_providers_contains_ollama_chat(self):
        assert "ollama_chat" in _TEXT_ONLY_PROVIDERS

    def test_text_only_providers_is_frozenset(self):
        assert isinstance(_TEXT_ONLY_PROVIDERS, frozenset)

    def test_text_only_providers_does_not_contain_openai(self):
        assert "openai" not in _TEXT_ONLY_PROVIDERS

# ---------------------------------------------------------------------------
# Test _supports_native_tools()
# ---------------------------------------------------------------------------

class TestSupportsNativeTools:
    """Verify provider capability detection via model string prefix."""

    def test_supports_native_tools_openai_model(self):
        """OpenAI models should support native tools."""
        llm = make_mock_llm(model="openai/gpt-4")
        provider = OrchestrationThinkingProvider(llm=llm)
        assert provider._supports_native_tools() is True

    def test_supports_native_tools_ollama_model(self):
        """Ollama models should NOT support native tools."""
        llm = make_mock_llm(model="ollama/llama3")
        provider = OrchestrationThinkingProvider(llm=llm)
        assert provider._supports_native_tools() is False

    def test_supports_native_tools_ollama_chat_model(self):
        """Ollama_chat models should NOT support native tools."""
        llm = make_mock_llm(model="ollama_chat/llama3")
        provider = OrchestrationThinkingProvider(llm=llm)
        assert provider._supports_native_tools() is False

    def test_supports_native_tools_no_prefix(self):
        """Models without prefix (e.g. 'gpt-4') default to not in denylist."""
        llm = make_mock_llm(model="gpt-4")
        provider = OrchestrationThinkingProvider(llm=llm)
        # No "/" means provider="" which is not in denylist
        assert provider._supports_native_tools() is True

    def test_supports_native_tools_anthropic_model(self):
        """Anthropic models should support native tools."""
        llm = make_mock_llm(model="anthropic/claude-3-opus")
        provider = OrchestrationThinkingProvider(llm=llm)
        assert provider._supports_native_tools() is True

    def test_supports_native_tools_explicit_method(self):
        """If LLM has supports_function_calling(), use it even for ollama."""
        llm = make_mock_llm(model="ollama/llama3")
        llm.supports_function_calling = MagicMock(return_value=True)
        provider = OrchestrationThinkingProvider(llm=llm)
        # Explicit method should override the denylist
        assert provider._supports_native_tools() is True
        llm.supports_function_calling.assert_called_once()

    def test_supports_native_tools_explicit_method_returns_false(self):
        """Explicit method returning False should be respected."""
        llm = make_mock_llm(model="openai/gpt-4")
        llm.supports_function_calling = MagicMock(return_value=False)
        provider = OrchestrationThinkingProvider(llm=llm)
        assert provider._supports_native_tools() is False

    def test_supports_native_tools_empty_model_string(self):
        """Empty model string should default to not in denylist."""
        llm = make_mock_llm(model="")
        provider = OrchestrationThinkingProvider(llm=llm)
        assert provider._supports_native_tools() is True

    def test_supports_native_tools_none_model(self):
        """None model attribute should not crash."""
        llm = make_mock_llm()
        llm.model = None
        provider = OrchestrationThinkingProvider(llm=llm)
        # model is None -> "" after `or ""` -> no "/" -> provider="" -> not in denylist
        assert provider._supports_native_tools() is True

# ---------------------------------------------------------------------------
# Test _build_tools_for_agents()
# ---------------------------------------------------------------------------

class TestBuildToolsForAgents:
    """Verify OpenAI-format tool construction from AgentCard capabilities."""

    def test_build_tools_for_agents_basic(self):
        """Two agents with capabilities should produce correct tool list."""
        cap1 = make_capability(
            "read_file",
            "Read a file",
            {"type": "object", "properties": {"path": {"type": "string"}}},
        )
        cap2 = make_capability("list_dir", "List directory")
        agent1 = make_agent_card("agent-a", capabilities=[cap1])
        agent2 = make_agent_card("agent-b", capabilities=[cap2])

        provider = OrchestrationThinkingProvider()
        tools = provider._build_tools_for_agents([agent1, agent2])

        assert tools is not None
        assert len(tools) == 2

        # First tool
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "read_file"
        assert tools[0]["function"]["description"] == "Read a file"
        assert tools[0]["function"]["parameters"] == {
            "type": "object",
            "properties": {"path": {"type": "string"}},
        }

        # Second tool
        assert tools[1]["type"] == "function"
        assert tools[1]["function"]["name"] == "list_dir"
        assert tools[1]["function"]["description"] == "List directory"

    def test_build_tools_for_agents_empty(self):
        """Empty agent list should return None."""
        provider = OrchestrationThinkingProvider()
        result = provider._build_tools_for_agents([])
        assert result is None

    def test_build_tools_for_agents_no_capabilities(self):
        """Agent with no capabilities should return None."""
        agent = make_agent_card("agent-no-caps", capabilities=[])
        provider = OrchestrationThinkingProvider()
        result = provider._build_tools_for_agents([agent])
        assert result is None

    def test_build_tools_for_agents_mixed(self):
        """Mix of agents with and without capabilities."""
        cap = make_capability("search", "Search files")
        agent_with_caps = make_agent_card("mcp-agent", capabilities=[cap])
        agent_without_caps = make_agent_card("crew-agent", capabilities=[])

        provider = OrchestrationThinkingProvider()
        tools = provider._build_tools_for_agents([agent_with_caps, agent_without_caps])

        assert tools is not None
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "search"

    def test_build_tools_for_agents_no_input_schema(self):
        """Capability without input_schema gets default empty object."""
        cap = AgentCapability(name="ping", description="Ping service")
        agent = make_agent_card("agent-ping", capabilities=[cap])

        provider = OrchestrationThinkingProvider()
        tools = provider._build_tools_for_agents([agent])

        assert tools is not None
        assert tools[0]["function"]["parameters"] == {"type": "object", "properties": {}}

# ---------------------------------------------------------------------------
# Test _call_llm() with and without tools
# ---------------------------------------------------------------------------

class TestCallLlmWithTools:
    """Verify _call_llm passes tools/tool_choice correctly."""

    @pytest.mark.asyncio
    async def test_call_llm_passes_tools(self):
        """When tools are provided, call() should receive tools and tool_choice."""
        llm = make_mock_llm()
        provider = OrchestrationThinkingProvider(llm=llm)

        tools = [
            {
                "type": "function",
                "function": {"name": "test_tool", "description": "Test", "parameters": {}},
            }
        ]
        messages = [{"role": "user", "content": "hello"}]

        await provider._call_llm(messages, tools=tools)

        llm.call.assert_called_once()
        call_kwargs = llm.call.call_args
        # call() is invoked via asyncio.to_thread(llm.call, **call_kwargs)
        # so we check keyword arguments
        assert call_kwargs.kwargs.get("tools") == tools or (
            "tools" in call_kwargs.kwargs and call_kwargs.kwargs["tools"] == tools
        )

    @pytest.mark.asyncio
    async def test_call_llm_without_tools(self):
        """When no tools, call() should NOT receive tools or tool_choice kwargs."""
        llm = make_mock_llm()
        provider = OrchestrationThinkingProvider(llm=llm)

        messages = [{"role": "user", "content": "hello"}]
        await provider._call_llm(messages)

        llm.call.assert_called_once()
        call_kwargs = llm.call.call_args
        assert "tools" not in call_kwargs.kwargs
        assert "tool_choice" not in call_kwargs.kwargs

    @pytest.mark.asyncio
    async def test_call_llm_tool_calls_response(self):
        """Dict response with tool_calls should be converted to JSON via _convert_tool_calls_to_json."""
        tool_calls_response = {
            "tool_calls": [
                {
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": "/tmp/test.txt"}',
                    }
                }
            ]
        }
        llm = make_mock_llm()
        llm.call.return_value = tool_calls_response
        provider = OrchestrationThinkingProvider(llm=llm)

        messages = [{"role": "user", "content": "read file"}]
        content, reasoning = await provider._call_llm(messages, tools=[{"type": "function"}])

        # Should be valid JSON
        parsed = json.loads(content)
        assert parsed["task"]["tool"] == "read_file"
        assert parsed["task"]["arguments"] == {"path": "/tmp/test.txt"}
        assert parsed["is_final"] is False

    @pytest.mark.asyncio
    async def test_call_llm_tools_none_no_kwargs(self):
        """Passing tools=None should not add tools/tool_choice to call kwargs."""
        llm = make_mock_llm()
        provider = OrchestrationThinkingProvider(llm=llm)

        messages = [{"role": "user", "content": "hello"}]
        await provider._call_llm(messages, tools=None)

        call_kwargs = llm.call.call_args
        assert "tools" not in call_kwargs.kwargs
        assert "tool_choice" not in call_kwargs.kwargs

# ---------------------------------------------------------------------------
# Test _convert_tool_calls_to_json
# ---------------------------------------------------------------------------

class TestConvertToolCallsToJson:
    """Verify native tool_calls response bridging."""

    def test_basic_conversion(self):
        provider = OrchestrationThinkingProvider()
        response = {
            "tool_calls": [
                {
                    "function": {
                        "name": "list_directory",
                        "arguments": '{"path": "/home"}',
                    }
                }
            ]
        }

        result = provider._convert_tool_calls_to_json(response)
        parsed = json.loads(result)

        assert parsed["task"]["tool"] == "list_directory"
        assert parsed["task"]["arguments"] == {"path": "/home"}
        assert parsed["is_final"] is False
        assert "Native tool call" in parsed["reasoning"]

    def test_empty_tool_calls(self):
        provider = OrchestrationThinkingProvider()
        result = provider._convert_tool_calls_to_json({"tool_calls": []})
        assert result == ""

    def test_invalid_arguments_json(self):
        """Invalid arguments JSON should produce empty dict."""
        provider = OrchestrationThinkingProvider()
        response = {
            "tool_calls": [
                {
                    "function": {
                        "name": "some_tool",
                        "arguments": "not-valid-json",
                    }
                }
            ]
        }
        result = provider._convert_tool_calls_to_json(response)
        parsed = json.loads(result)
        assert parsed["task"]["arguments"] == {}

    def test_multiple_tool_calls_takes_first(self):
        """Only the first tool call is used."""
        provider = OrchestrationThinkingProvider()
        response = {
            "tool_calls": [
                {"function": {"name": "tool_a", "arguments": "{}"}},
                {"function": {"name": "tool_b", "arguments": "{}"}},
            ]
        }
        result = provider._convert_tool_calls_to_json(response)
        parsed = json.loads(result)
        assert parsed["task"]["tool"] == "tool_a"

# ---------------------------------------------------------------------------
# Test orchestrate_think integration with native tools
# ---------------------------------------------------------------------------

class TestOrchestrateThinkNativeTools:
    """Verify orchestrate_think uses native tools when supported."""

    @pytest.mark.asyncio
    async def test_orchestrate_think_uses_native_tools(self):
        """When provider supports tools, _call_llm should receive tool list."""
        valid_json = json.dumps(
            {
                "reasoning": "Using filesystem tool",
                "is_final": False,
                "task": {
                    "agent_name": "mcp-fs",
                    "description": "List files",
                    "tool": "list_directory",
                    "arguments": {"path": "/tmp"},
                },
            }
        )
        llm = make_mock_llm(model="openai/gpt-4", response=valid_json)
        provider = OrchestrationThinkingProvider(llm=llm)

        cap = make_capability("list_directory", "List directory contents")
        agents = [make_agent_card("mcp-fs", capabilities=[cap])]
        obs_history = make_observation_history()

        thought = await provider.orchestrate_think(
            goal="List files in /tmp",
            observations=[],
            available_agents=agents,
            observation_history=obs_history,
            lightweight=False,
        )

        # Verify _call_llm was called with tools
        call_kwargs = llm.call.call_args
        assert "tools" in call_kwargs.kwargs
        assert call_kwargs.kwargs["tools"] is not None
        # Phase 167: self-mod tools (11) are always-injected for function-calling providers.
        # Total = 1 MCP tool + 11 self-mod tools = 12. Check the MCP tool is present.
        tool_names = [t["function"]["name"] for t in call_kwargs.kwargs["tools"]]
        assert "list_directory" in tool_names

    @pytest.mark.asyncio
    async def test_orchestrate_think_text_fallback(self):
        """When provider does NOT support tools, _call_llm should get tools=None."""
        valid_json = json.dumps(
            {
                "reasoning": "test",
                "is_final": True,
                "answer": "ok",
            }
        )
        llm = make_mock_llm(model="ollama/llama3", response=valid_json)
        provider = OrchestrationThinkingProvider(llm=llm)

        cap = make_capability("list_directory", "List directory")
        agents = [make_agent_card("mcp-fs", capabilities=[cap])]
        obs_history = make_observation_history()

        thought = await provider.orchestrate_think(
            goal="List files",
            observations=[],
            available_agents=agents,
            observation_history=obs_history,
            lightweight=False,
        )

        # Verify _call_llm was NOT called with tools
        call_kwargs = llm.call.call_args
        assert "tools" not in call_kwargs.kwargs or call_kwargs.kwargs.get("tools") is None

    @pytest.mark.asyncio
    async def test_orchestrate_think_lightweight_skips_native_tools(self):
        """Lightweight mode should not pass native tools even for capable providers."""
        valid_json = json.dumps(
            {
                "reasoning": "test",
                "is_final": True,
                "answer": "ok",
            }
        )
        llm = make_mock_llm(model="openai/gpt-4", response=valid_json)
        provider = OrchestrationThinkingProvider(llm=llm)

        cap = make_capability("list_directory", "List directory")
        agents = [make_agent_card("mcp-fs", capabilities=[cap])]
        obs_history = make_observation_history()

        await provider.orchestrate_think(
            goal="List files",
            observations=[],
            available_agents=agents,
            observation_history=obs_history,
            lightweight=True,
        )

        # In lightweight mode, native_tools should be None
        call_kwargs = llm.call.call_args
        assert "tools" not in call_kwargs.kwargs or call_kwargs.kwargs.get("tools") is None

    @pytest.mark.asyncio
    async def test_orchestrate_think_no_capabilities_no_tools(self):
        """Agents with no capabilities should result in no tools passed."""
        valid_json = json.dumps(
            {
                "reasoning": "test",
                "is_final": True,
                "answer": "ok",
            }
        )
        llm = make_mock_llm(model="openai/gpt-4", response=valid_json)
        provider = OrchestrationThinkingProvider(llm=llm)

        agents = [make_agent_card("crew-agent", capabilities=[])]
        obs_history = make_observation_history()

        await provider.orchestrate_think(
            goal="Do something",
            observations=[],
            available_agents=agents,
            observation_history=obs_history,
            lightweight=False,
        )

        # _build_tools_for_agents returns None for no capabilities
        call_kwargs = llm.call.call_args
        assert "tools" not in call_kwargs.kwargs or call_kwargs.kwargs.get("tools") is None

# ---------------------------------------------------------------------------
# Test _call_llm dict handling bridge (Phase 101-02)
# ---------------------------------------------------------------------------

class TestCallLlmDictHandlingBridge:
    """Integration tests for _call_llm() handling dict responses from VLLMBaseLLM.

    These tests exercise the orchestrator's _call_llm() method with a mock LLM
    that returns dicts (simulating the fixed VLLMBaseLLM behavior).
    """

    @pytest.mark.asyncio
    async def test_call_llm_handles_dict_with_tool_calls(self):
        """Mock llm.call() returns dict with tool_calls -> _convert_tool_calls_to_json."""
        tool_calls_dict = {
            "tool_calls": [
                {
                    "function": {
                        "name": "list_directory",
                        "arguments": '{"path": "/home"}',
                    }
                }
            ]
        }
        llm = make_mock_llm()
        llm.call.return_value = tool_calls_dict
        provider = OrchestrationThinkingProvider(llm=llm)

        messages = [{"role": "user", "content": "List files"}]
        content, reasoning = await provider._call_llm(messages, tools=[{"type": "function"}])

        # _convert_tool_calls_to_json should produce valid JSON with task.tool
        parsed = json.loads(content)
        assert "task" in parsed
        assert parsed["task"]["tool"] == "list_directory"
        assert parsed["task"]["arguments"] == {"path": "/home"}
        assert parsed["is_final"] is False

    @pytest.mark.asyncio
    async def test_call_llm_dict_without_tool_calls_is_reasoning(self):
        """Dict with content + reasoning_content but no tool_calls -> content returned."""
        reasoning_dict = {
            "reasoning_content": "Let me think about this...",
            "content": "The answer is 42.",
        }
        llm = make_mock_llm()
        llm.call.return_value = reasoning_dict
        provider = OrchestrationThinkingProvider(llm=llm)

        messages = [{"role": "user", "content": "What is the meaning of life?"}]
        content, reasoning = await provider._call_llm(messages)

        # Content should be the "content" field value
        assert "42" in content
        # Reasoning should be extracted
        assert reasoning == "Let me think about this..."

    @pytest.mark.asyncio
    async def test_native_tools_disabled_via_config(self):
        """DRYADE_NATIVE_TOOLS_ENABLED=false -> _call_llm called WITHOUT tools."""
        valid_json = json.dumps(
            {
                "reasoning": "test",
                "is_final": True,
                "answer": "ok",
            }
        )
        llm = make_mock_llm(model="openai/gpt-4", response=valid_json)
        provider = OrchestrationThinkingProvider(llm=llm)

        cap = make_capability("list_directory", "List directory")
        agents = [make_agent_card("mcp-fs", capabilities=[cap])]
        obs_history = make_observation_history()

        with patch.dict("os.environ", {"DRYADE_NATIVE_TOOLS_ENABLED": "false"}):
            await provider.orchestrate_think(
                goal="List files",
                observations=[],
                available_agents=agents,
                observation_history=obs_history,
                lightweight=False,
            )

        # Config toggle should disable native tools -> no tools in call
        call_kwargs = llm.call.call_args
        assert "tools" not in call_kwargs.kwargs or call_kwargs.kwargs.get("tools") is None

    @pytest.mark.asyncio
    async def test_native_tools_enabled_passes_tools(self):
        """Default config (native_tools_enabled=True) with non-denylist provider passes tools."""
        valid_json = json.dumps(
            {
                "reasoning": "Using tool",
                "is_final": False,
                "task": {
                    "agent_name": "mcp-fs",
                    "description": "List files",
                    "tool": "list_directory",
                    "arguments": {"path": "/tmp"},
                },
            }
        )
        llm = make_mock_llm(model="openai/gpt-4", response=valid_json)
        provider = OrchestrationThinkingProvider(llm=llm)

        cap = make_capability("list_directory", "List directory contents")
        agents = [make_agent_card("mcp-fs", capabilities=[cap])]
        obs_history = make_observation_history()

        # Ensure config is default (native_tools_enabled=True)
        with patch.dict("os.environ", {}, clear=False):
            # Remove the env var if it exists so default True applies
            import os

            os.environ.pop("DRYADE_NATIVE_TOOLS_ENABLED", None)

            await provider.orchestrate_think(
                goal="List files in /tmp",
                observations=[],
                available_agents=agents,
                observation_history=obs_history,
                lightweight=False,
            )

        # Should have tools in call kwargs
        call_kwargs = llm.call.call_args
        assert "tools" in call_kwargs.kwargs
        assert call_kwargs.kwargs["tools"] is not None
        # Phase 167: self-mod tools (11) always-injected; MCP tool also present.
        tool_names = [t["function"]["name"] for t in call_kwargs.kwargs["tools"]]
        assert "list_directory" in tool_names
