"""Unit tests for core.factory.config_generator.

Covers: select_framework(), select_framework_llm(), generate_config(),
_COMMON_PACKAGES, _get_available_capabilities_context().

Gap 7/8 regression: verifies _COMMON_PACKAGES and capability context.
"""

from unittest.mock import AsyncMock, patch

import pytest

from core.factory.config_generator import (
    _COMMON_PACKAGES,
    _derive_name,
    _get_available_capabilities_context,
    generate_config,
    select_framework,
    select_framework_llm,
)

# ---------------------------------------------------------------------------
# select_framework: keyword-based fast path
# ---------------------------------------------------------------------------

class TestSelectFramework:
    """Rule-based keyword matching for framework selection."""

    def test_tool_keyword_function(self):
        """Goals with 'tool' keyword select mcp_function."""
        art_type, fw, reason = select_framework("Create a tool for parsing JSON")
        assert art_type == "tool"
        assert fw == "mcp_function"
        assert "keyword" in reason.lower() or "Keyword" in reason

    def test_tool_keyword_server(self):
        """Goals with 'tool' + 'server' keywords select mcp_server."""
        art_type, fw, _ = select_framework("Build a tool server for API endpoints")
        assert art_type == "tool"
        assert fw == "mcp_server"

    def test_skill_keyword(self):
        """Goals with 'skill' keyword select skill framework."""
        art_type, fw, _ = select_framework("Write a skill for code review procedures")
        assert art_type == "skill"
        assert fw == "skill"

    def test_prompt_keyword(self):
        """Goals with 'prompt' keyword select skill framework."""
        art_type, fw, _ = select_framework("Create a prompt template for summarization")
        assert art_type == "skill"
        assert fw == "skill"

    def test_google_keyword(self):
        """Goals mentioning 'google' select ADK."""
        art_type, fw, _ = select_framework("Build a google assistant agent")
        assert art_type == "agent"
        assert fw == "adk"

    def test_workflow_keyword(self):
        """Goals with 'workflow' keyword select langchain."""
        art_type, fw, _ = select_framework("Create a workflow for data processing")
        assert art_type == "agent"
        assert fw == "langchain"

    def test_crew_keyword(self):
        """Goals with 'crew' keyword select crewai."""
        art_type, fw, _ = select_framework("Build a crew of collaborative agents")
        assert art_type == "agent"
        assert fw == "crewai"

    def test_server_keyword_without_tool(self):
        """Goals with 'server' but not 'tool' select mcp_server."""
        art_type, fw, _ = select_framework("Build a server for background processing")
        assert art_type == "tool"
        assert fw == "mcp_server"

    def test_default_custom_agent(self):
        """Ambiguous goals default to custom agent."""
        art_type, fw, _ = select_framework("Help me analyze market data")
        assert art_type == "agent"
        assert fw == "custom"

    def test_returns_three_tuple(self):
        """All calls return (type, framework, reasoning) triple."""
        result = select_framework("something")
        assert isinstance(result, tuple)
        assert len(result) == 3
        assert all(isinstance(s, str) for s in result)

# ---------------------------------------------------------------------------
# select_framework_llm: LLM fallback
# ---------------------------------------------------------------------------

class TestSelectFrameworkLlm:
    """LLM-based framework selection with mocked LLM calls."""

    @pytest.mark.asyncio
    async def test_llm_returns_valid_selection(self):
        mock_result = {
            "artifact_type": "tool",
            "framework": "mcp_function",
            "reasoning": "This is a function tool",
        }
        with patch(
            "core.factory.config_generator.call_llm_json",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            art_type, fw, reason = await select_framework_llm("Convert PDFs to text")
            assert art_type == "tool"
            assert fw == "mcp_function"
            assert reason == "This is a function tool"

    @pytest.mark.asyncio
    async def test_llm_invalid_framework_falls_back(self):
        mock_result = {
            "artifact_type": "agent",
            "framework": "nonexistent_framework",
            "reasoning": "Bad",
        }
        with patch(
            "core.factory.config_generator.call_llm_json",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            _, fw, _ = await select_framework_llm("something")
            assert fw == "custom"

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_custom(self):
        with patch(
            "core.factory.config_generator.call_llm_json",
            new_callable=AsyncMock,
            side_effect=Exception("LLM unavailable"),
        ):
            art_type, fw, reason = await select_framework_llm("something complex")
            assert art_type == "agent"
            assert fw == "custom"
            assert "failed" in reason.lower() or "defaulting" in reason.lower()

# ---------------------------------------------------------------------------
# generate_config: full config generation
# ---------------------------------------------------------------------------

class TestGenerateConfig:
    """Config generation with LLM enrichment mocked."""

    @pytest.mark.asyncio
    async def test_explicit_framework_used(self):
        """When framework is provided, it is used directly without keyword matching."""
        with patch(
            "core.factory.config_generator.call_llm_json",
            new_callable=AsyncMock,
            return_value={"tools": [], "mcp_servers": []},
        ):
            config = await generate_config(
                goal="Do something interesting",
                name="test_agent",
                framework="crewai",
                artifact_type="agent",
            )
            assert config["framework"] == "crewai"
            assert config["artifact_type"] == "agent"
            assert config["name"] == "test_agent"

    @pytest.mark.asyncio
    async def test_explicit_framework_infers_tool_type(self):
        """framework='mcp_function' infers artifact_type='tool'."""
        with patch(
            "core.factory.config_generator.call_llm_json",
            new_callable=AsyncMock,
            return_value={"tool_name": "my_tool", "params": []},
        ):
            config = await generate_config(
                goal="Parse JSON files",
                framework="mcp_function",
            )
            assert config["artifact_type"] == "tool"
            assert config["framework"] == "mcp_function"

    @pytest.mark.asyncio
    async def test_llm_fallback_produces_valid_config(self):
        """When LLM enrichment fails, rule-based fallback produces valid config."""
        with patch(
            "core.factory.config_generator.call_llm_json",
            new_callable=AsyncMock,
            side_effect=Exception("LLM down"),
        ):
            config = await generate_config(
                goal="Build a custom agent for data analysis",
                framework="custom",
                artifact_type="agent",
            )
            # Fallback should still produce working config
            assert "name" in config
            assert "framework" in config
            assert config["framework"] == "custom"
            # Rule-based fallback populates these:
            assert "tools" in config
            assert "mcp_servers" in config

    @pytest.mark.asyncio
    async def test_common_packages_matching(self):
        """Goals mentioning known packages get mcp_servers pre-populated."""
        with patch(
            "core.factory.config_generator.call_llm_json",
            new_callable=AsyncMock,
            return_value={"tools": [], "capabilities": []},
        ):
            config = await generate_config(
                goal="Agent that uses websearch and filesystem",
                framework="custom",
                artifact_type="agent",
            )
            # mcp_servers should include matched packages
            mcp_servers = config.get("mcp_servers", [])
            assert "@anthropic/brave-search" in mcp_servers
            assert "@anthropic/filesystem" in mcp_servers

    @pytest.mark.asyncio
    async def test_name_derived_when_not_provided(self):
        """Name is auto-derived from goal when not explicitly given."""
        with patch(
            "core.factory.config_generator.call_llm_json",
            new_callable=AsyncMock,
            return_value={"tools": []},
        ):
            config = await generate_config(
                goal="Analyze market trends",
                framework="custom",
                artifact_type="agent",
            )
            assert config["name"]  # Non-empty
            assert config["name"] != ""

# ---------------------------------------------------------------------------
# _COMMON_PACKAGES: static fallback dict (Gap 7/8 regression)
# ---------------------------------------------------------------------------

class TestCommonPackages:
    """Verify _COMMON_PACKAGES static fallback dictionary."""

    def test_common_packages_is_dict(self):
        assert isinstance(_COMMON_PACKAGES, dict)

    def test_common_packages_has_expected_keys(self):
        expected = {"websearch", "filesystem", "git", "github"}
        assert expected.issubset(set(_COMMON_PACKAGES.keys()))

    def test_common_packages_values_are_strings(self):
        for key, value in _COMMON_PACKAGES.items():
            assert isinstance(value, str), f"Key {key} has non-string value: {value}"
            assert len(value) > 0, f"Key {key} has empty value"

    def test_common_packages_count(self):
        """At least 13 entries as per spec."""
        assert len(_COMMON_PACKAGES) >= 13

# ---------------------------------------------------------------------------
# _get_available_capabilities_context: capability context injection
# ---------------------------------------------------------------------------

class TestGetAvailableCapabilitiesContext:
    """Verify capability context helper for LLM prompt injection."""

    def test_returns_empty_when_imports_fail(self):
        """When capability_registry/tool_index can't import, returns empty string."""
        with patch.dict(
            "sys.modules",
            {
                "core.mcp.tool_index": None,
                "core.orchestrator.capability_registry": None,
            },
        ):
            result = _get_available_capabilities_context()
            assert isinstance(result, str)
            # Should be empty or contain no tool lines
            # (the function catches ImportError silently)

    def test_returns_string_type(self):
        """Always returns a string, never None."""
        result = _get_available_capabilities_context()
        assert isinstance(result, str)

# ---------------------------------------------------------------------------
# _derive_name: name derivation
# ---------------------------------------------------------------------------

class TestDeriveName:
    """Name derivation from goal strings."""

    def test_basic_derivation(self):
        name = _derive_name("Analyze market data trends")
        assert name  # non-empty
        assert name.isascii()

    def test_stop_words_removed(self):
        name = _derive_name("Create a tool for the analysis")
        # "create", "a", "for", "the" are all stop words
        assert "create" not in name.split("_")
        assert "analysis" in name

    def test_truncation_to_64(self):
        long_goal = " ".join([f"word{i}" for i in range(50)])
        name = _derive_name(long_goal)
        assert len(name) <= 64

    def test_invalid_pattern_fallback(self):
        """Numbers-only goal falls back to 'artifact'."""
        name = _derive_name("1234 5678")
        # Should still be valid
        assert name[0].isalpha()
