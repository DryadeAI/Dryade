"""Tests for self-modification tools (Phase 115.1 + 115.2 + Phase 167).

Covers:
- Self-mod tool definitions (OpenAI function-calling format)
- is_self_mod_tool() predicate
- is_read_only_tool() predicate
- get_self_mod_tools() model-aware variants
- execute_self_mod_tool() dispatcher -> PendingEscalation / dict
- CapabilityRegistry (register/unregister/search/list_all/singleton)
- RoutingMetricsTracker basics
- ComplexityEstimator meta_action_hint behavior

Phase 167: self_improve/create_agent/create_tool consolidated into unified `create` tool.
           memory_delete added. Total tools: 11 (was 12).
"""

import pytest

from core.orchestrator.escalation import EscalationActionType, PendingEscalation
from core.orchestrator.self_mod_tools import (
    SELF_MOD_TOOL_NAMES,
    SELF_MOD_TOOLS,
    execute_self_mod_tool,
    get_self_mod_tools,
    is_read_only_tool,
    is_self_mod_tool,
)

# ---- Phase 115.1 Tests (updated for Phase 167 consolidated tools) ----

class TestSelfModToolDefinitions:
    """Verify tool definitions are in correct OpenAI format."""

    def test_eleven_tools_defined(self):
        # Phase 167: 11 tools (was 12): create, modify_config, add/remove/configure_mcp_server,
        # search_capabilities, memory_insert/replace/rethink/search/delete
        assert len(SELF_MOD_TOOLS) == 11

    def test_tool_format_openai_function(self):
        for tool in SELF_MOD_TOOLS:
            assert tool["type"] == "function"
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]
            params = tool["function"]["parameters"]
            assert params["type"] == "object"
            assert "properties" in params
            assert "required" in params

    def test_create_tool_has_goal_required(self):
        """Phase 167: unified `create` tool has `goal` as required parameter."""
        tool = next(t for t in SELF_MOD_TOOLS if t["function"]["name"] == "factory_create")
        assert "goal" in tool["function"]["parameters"]["required"]

    def test_tool_names_match_constant(self):
        tool_names = {t["function"]["name"] for t in SELF_MOD_TOOLS}
        assert tool_names == SELF_MOD_TOOL_NAMES

class TestIsSelfModTool:
    def test_recognizes_create(self):
        """Phase 167: `create` replaces self_improve/create_agent/create_tool."""
        assert is_self_mod_tool("factory_create") is True

    def test_recognizes_memory_delete(self):
        """Phase 167: memory_delete is a new self-mod tool."""
        assert is_self_mod_tool("memory_delete") is True

    def test_recognizes_modify_config(self):
        assert is_self_mod_tool("modify_config") is True

    def test_rejects_unknown_tool(self):
        assert is_self_mod_tool("random_tool") is False

    def test_rejects_none(self):
        assert is_self_mod_tool(None) is False

    def test_old_names_no_longer_recognized(self):
        """Phase 167: old tool names self_improve/create_agent/create_tool are gone."""
        assert is_self_mod_tool("self_improve") is False
        assert is_self_mod_tool("create_agent") is False
        assert is_self_mod_tool("create_tool") is False

class TestExecuteSelfModTool:
    @pytest.mark.asyncio
    async def test_create_returns_pending_escalation(self):
        """Phase 167: unified `create` tool returns PendingEscalation with FACTORY_CREATE."""
        result = await execute_self_mod_tool(
            tool_name="factory_create",
            arguments={"goal": "Create a websearch agent"},
            conversation_id="test-conv",
            original_goal="create a websearch agent",
        )
        assert result.conversation_id == "test-conv"
        assert result.action.action_type == EscalationActionType.FACTORY_CREATE

    @pytest.mark.asyncio
    async def test_create_with_artifact_type_tool(self):
        """Phase 167: `create` with artifact_type=tool returns FACTORY_CREATE."""
        result = await execute_self_mod_tool(
            tool_name="factory_create",
            arguments={
                "goal": "Scrape web pages",
                "name": "web_scraper",
                "artifact_type": "tool",
            },
            conversation_id="test-conv",
            original_goal="create a web scraper tool",
        )
        assert result.action.action_type == EscalationActionType.FACTORY_CREATE
        assert result.action.parameters.get("artifact_type") == "tool"

    @pytest.mark.asyncio
    async def test_modify_config_returns_pending_escalation(self):
        result = await execute_self_mod_tool(
            tool_name="modify_config",
            arguments={"config_key": "timeout", "config_value": "120"},
            conversation_id="test-conv",
            original_goal="increase timeout",
        )
        assert result.action.action_type == EscalationActionType.MODIFY_CONFIG

    @pytest.mark.asyncio
    async def test_unknown_tool_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown self-mod tool"):
            await execute_self_mod_tool(
                tool_name="unknown",
                arguments={},
                conversation_id="test-conv",
                original_goal="test",
            )

class TestRoutingMetrics:
    def test_record_creates_metric(self):
        from core.orchestrator.routing_metrics import RoutingMetricsTracker

        tracker = RoutingMetricsTracker()
        tracker.record(message="test", hint_fired=True, hint_type="meta_action")
        assert len(tracker.records) == 1
        assert tracker.records[0].hint_fired is True
        assert tracker.records[0].hint_type == "meta_action"

    def test_message_hash_is_consistent(self):
        from core.orchestrator.routing_metrics import RoutingMetricsTracker

        tracker = RoutingMetricsTracker()
        tracker.record(message="hello", hint_fired=False)
        tracker.record(message="hello", hint_fired=True)
        assert tracker.records[0].message_hash == tracker.records[1].message_hash

class TestMetaActionHint:
    def test_classify_meta_action_returns_hint_not_bypass(self):
        """classify() returns meta_action_hint=True but still goes through COMPLEX."""
        from core.orchestrator.complexity import ComplexityEstimator
        from core.orchestrator.models import Tier

        estimator = ComplexityEstimator()
        agents = []
        result = estimator.classify("create a new websearch agent", agents)
        assert result.tier == Tier.COMPLEX
        assert result.meta_action_hint is True

    def test_meta_action_skips_simple_tier(self):
        """Meta-action hint prevents SIMPLE tier even when agent name matches."""
        from core.adapters.protocol import AgentCard
        from core.orchestrator.complexity import ComplexityEstimator
        from core.orchestrator.models import Tier

        estimator = ComplexityEstimator()
        agents = [
            AgentCard(
                name="websearch",
                description="websearch agent",
                version="1.0",
                framework="mcp",
            )
        ]
        result = estimator.classify("create a websearch agent", agents)
        assert result.tier == Tier.COMPLEX
        assert result.meta_action_hint is True

# ---- Phase 115.2 Tests (updated for Phase 167) ----

class TestGetSelfModTools:
    """Test model-aware tool definition getter."""

    def test_get_self_mod_tools_detailed_count(self):
        tools = get_self_mod_tools("detailed")
        assert len(tools) == 11  # Phase 167: 11 tools (was 12)

    def test_get_self_mod_tools_short_count(self):
        tools = get_self_mod_tools("short")
        assert len(tools) == 11  # Phase 167: 11 tools (was 12)

    def test_get_self_mod_tools_default_is_detailed(self):
        default = get_self_mod_tools()
        detailed = get_self_mod_tools("detailed")
        assert default is detailed

    def test_short_descriptions_are_shorter(self):
        short_tools = get_self_mod_tools("short")
        detailed_tools = get_self_mod_tools("detailed")
        for s_tool in short_tools:
            s_name = s_tool["function"]["name"]
            d_tool = next(t for t in detailed_tools if t["function"]["name"] == s_name)
            s_desc = s_tool["function"]["description"]
            d_desc = d_tool["function"]["description"]
            assert len(s_desc) < len(d_desc), (
                f"Short description for {s_name} ({len(s_desc)}) should be "
                f"shorter than detailed ({len(d_desc)})"
            )

    def test_tool_names_match_between_variants(self):
        short_names = {t["function"]["name"] for t in get_self_mod_tools("short")}
        detailed_names = {t["function"]["name"] for t in get_self_mod_tools("detailed")}
        assert short_names == detailed_names

class TestReadOnlyTools:
    """Test read-only tool detection."""

    def test_is_read_only_tool_search_capabilities(self):
        assert is_read_only_tool("search_capabilities") is True

    def test_is_read_only_tool_memory_delete(self):
        """Phase 167: memory_delete is read-only."""
        assert is_read_only_tool("memory_delete") is True

    def test_is_read_only_tool_add_mcp_server(self):
        assert is_read_only_tool("add_mcp_server") is False

    def test_is_read_only_tool_none(self):
        assert is_read_only_tool(None) is False

class TestNewSelfModTools:
    """Test self-mod tool recognition."""

    def test_create_is_self_mod(self):
        """Phase 167: unified `create` tool."""
        assert is_self_mod_tool("factory_create") is True

    def test_new_mcp_tools_are_self_mod(self):
        assert is_self_mod_tool("add_mcp_server") is True
        assert is_self_mod_tool("remove_mcp_server") is True
        assert is_self_mod_tool("configure_mcp_server") is True

class TestNewToolDispatch:
    """Test dispatch of self-mod tools."""

    @pytest.mark.asyncio
    async def test_execute_create_returns_factory_create(self):
        """Phase 167: unified `create` returns FACTORY_CREATE."""
        result = await execute_self_mod_tool(
            tool_name="factory_create",
            arguments={"goal": "test agent creation"},
            conversation_id="conv1",
            original_goal="test",
        )
        assert isinstance(result, PendingEscalation)
        assert result.action.action_type == EscalationActionType.FACTORY_CREATE
        assert result.action.parameters["goal"] == "test agent creation"

    @pytest.mark.asyncio
    async def test_execute_add_mcp_server(self):
        result = await execute_self_mod_tool(
            tool_name="add_mcp_server",
            arguments={
                "name": "postgres",
                "command": ["npx", "-y", "@modelcontextprotocol/server-postgres"],
                "description": "PostgreSQL",
            },
            conversation_id="conv1",
            original_goal="add postgres",
        )
        assert isinstance(result, PendingEscalation)
        assert result.action.action_type == EscalationActionType.ADD_MCP_SERVER
        assert result.action.parameters["name"] == "postgres"

    @pytest.mark.asyncio
    async def test_execute_remove_mcp_server(self):
        result = await execute_self_mod_tool(
            tool_name="remove_mcp_server",
            arguments={"name": "postgres"},
            conversation_id="conv1",
            original_goal="remove postgres",
        )
        assert isinstance(result, PendingEscalation)
        assert result.action.action_type == EscalationActionType.REMOVE_MCP_SERVER
        assert result.action.parameters["name"] == "postgres"

    @pytest.mark.asyncio
    async def test_execute_configure_mcp_server(self):
        result = await execute_self_mod_tool(
            tool_name="configure_mcp_server",
            arguments={
                "name": "postgres",
                "updates": {"env": {"POSTGRES_URL": "new_url"}, "timeout": 60},
            },
            conversation_id="conv1",
            original_goal="configure postgres",
        )
        assert isinstance(result, PendingEscalation)
        assert result.action.action_type == EscalationActionType.CONFIGURE_MCP_SERVER
        assert result.action.parameters["name"] == "postgres"
        assert result.action.parameters["updates"]["timeout"] == 60

    @pytest.mark.asyncio
    async def test_execute_search_capabilities_returns_dict(self):
        result = await execute_self_mod_tool(
            tool_name="search_capabilities",
            arguments={"query": "create"},
            conversation_id="conv1",
            original_goal="search capabilities",
        )
        assert isinstance(result, dict)
        assert result["type"] == "search_result"
        assert isinstance(result["results"], list)
        # Phase 167: Should find the `create` tool
        names = [r["name"] for r in result["results"]]
        assert "factory_create" in names

class TestCapabilityRegistry:
    """Test CapabilityRegistry register/unregister/search/list_all."""

    def test_capability_registry_register_and_search(self):
        from core.orchestrator.capability_registry import CapabilityEntry, CapabilityRegistry

        registry = CapabilityRegistry()
        entry = CapabilityEntry(
            name="test_tool",
            source="self_mod",
            category="tool_creation",
            description="A test tool for unit testing",
            description_short="A test tool",
            tags=["test", "unit"],
        )
        registry.register(entry)
        results = registry.search("test_tool")
        assert len(results) == 1
        assert results[0].name == "test_tool"

    def test_capability_registry_unregister(self):
        from core.orchestrator.capability_registry import CapabilityEntry, CapabilityRegistry

        registry = CapabilityRegistry()
        entry = CapabilityEntry(
            name="temp_tool",
            source="mcp",
            category="tool_creation",
            description="Temporary tool",
            description_short="Temp",
            tags=["temp"],
        )
        registry.register(entry)
        assert len(registry.search("temp_tool")) == 1
        registry.unregister("temp_tool")
        assert len(registry.search("temp_tool")) == 0

    def test_capability_registry_list_all_with_category_filter(self):
        from core.orchestrator.capability_registry import CapabilityEntry, CapabilityRegistry

        registry = CapabilityRegistry()
        registry.register(
            CapabilityEntry(
                name="tool_a",
                source="self_mod",
                category="tool_creation",
                description="Tool A",
                description_short="A",
            )
        )
        registry.register(
            CapabilityEntry(
                name="tool_b",
                source="self_mod",
                category="config",
                description="Tool B",
                description_short="B",
            )
        )
        registry.register(
            CapabilityEntry(
                name="tool_c",
                source="mcp",
                category="tool_creation",
                description="Tool C",
                description_short="C",
            )
        )
        all_entries = registry.list_all()
        assert len(all_entries) == 3
        tool_creation_entries = registry.list_all(category="tool_creation")
        assert len(tool_creation_entries) == 2
        config_entries = registry.list_all(category="config")
        assert len(config_entries) == 1
        assert config_entries[0].name == "tool_b"

    def test_capability_registry_singleton(self):
        from core.orchestrator.capability_registry import (
            get_capability_registry,
            reset_capability_registry,
        )

        reset_capability_registry()
        r1 = get_capability_registry()
        r2 = get_capability_registry()
        assert r1 is r2
        reset_capability_registry()  # Clean up

# ---- Phase 115.7 Bug Fix Regression Tests (updated for Phase 167) ----

class TestSelfModToolEscalationBugFixes:
    """Regression tests for Bug 1, Bug 2, Bug 3 fixed in Phase 115.7-01.

    Phase 167: Tests updated for unified `create` tool.

    Bug 1: question was a flat description, not an approval question
    Bug 2: failed_agent was polluting parameters instead of suggested_name
    Bug 3: _create_agent didn't resolve MCP commands for unknown agents
    """

    # -------------------------------------------------------------------
    # Bug 1: question format (Phase 167: uses "Agent Factory" format)
    # -------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_question_includes_agent_factory(self):
        """Phase 167: question format is '**Agent Factory** **name** -> goal'."""
        result = await execute_self_mod_tool(
            tool_name="factory_create",
            arguments={"goal": "Create websearch", "name": "websearch"},
            conversation_id="test-conv",
            original_goal="create a websearch agent",
        )
        assert isinstance(result, PendingEscalation)
        assert "Agent Factory" in result.question

    @pytest.mark.asyncio
    async def test_create_question_includes_agent_name(self):
        """Phase 167: question should mention the suggested agent name."""
        result = await execute_self_mod_tool(
            tool_name="factory_create",
            arguments={"goal": "Create websearch", "name": "websearch"},
            conversation_id="test-conv",
            original_goal="create a websearch agent",
        )
        assert "websearch" in result.question

    @pytest.mark.asyncio
    async def test_create_tool_question_includes_name(self):
        """Phase 167: unified `create` with artifact_type=tool includes name in question."""
        result = await execute_self_mod_tool(
            tool_name="factory_create",
            arguments={
                "goal": "Validate JSON",
                "name": "json_validator",
                "artifact_type": "tool",
            },
            conversation_id="test-conv",
            original_goal="create json validator",
        )
        assert isinstance(result, PendingEscalation)
        assert "json_validator" in result.question

    # -------------------------------------------------------------------
    # Bug 2: no failed_agent in parameters, use suggested_name instead
    # -------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_no_failed_agent_in_params(self):
        """Bug 2 regression: 'failed_agent' must NOT appear in action.parameters."""
        result = await execute_self_mod_tool(
            tool_name="factory_create",
            arguments={"goal": "Create websearch", "name": "websearch"},
            conversation_id="test-conv",
            original_goal="create a websearch agent",
        )
        assert "failed_agent" not in result.action.parameters

    @pytest.mark.asyncio
    async def test_create_has_suggested_name_in_params(self):
        """Bug 2 regression: suggested_name must be in parameters and match provided name."""
        result = await execute_self_mod_tool(
            tool_name="factory_create",
            arguments={"goal": "Create websearch", "name": "websearch"},
            conversation_id="test-conv",
            original_goal="create a websearch agent",
        )
        assert "suggested_name" in result.action.parameters
        assert result.action.parameters["suggested_name"] == "websearch"

    @pytest.mark.asyncio
    async def test_create_suggested_name_none_when_not_provided(self):
        """When LLM omits name arg, suggested_name is None (factory resolves internally)."""
        result = await execute_self_mod_tool(
            tool_name="factory_create",
            arguments={"goal": "Create some agent"},
            conversation_id="test-conv",
            original_goal="create an agent",
        )
        assert result.action.parameters["suggested_name"] is None

    @pytest.mark.asyncio
    async def test_create_suggested_name_none_for_unresolvable_goal(self):
        """When goal has no recognizable agent pattern, suggested_name stays None."""
        result = await execute_self_mod_tool(
            tool_name="factory_create",
            arguments={"goal": "Do something useful"},
            conversation_id="test-conv",
            original_goal="do something",
        )
        assert result.action.parameters["suggested_name"] is None

    # -------------------------------------------------------------------
    # Post-119.6: _create_agent and _create_tool delegate to _factory_create
    # -------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_agent_delegates_to_factory_create(self):
        """Post-119.6: _create_agent delegates to _factory_create."""
        from unittest.mock import AsyncMock, patch

        from core.orchestrator.escalation import EscalationExecutor

        executor = EscalationExecutor()
        executor._factory_create = AsyncMock(return_value=(True, "Created agent websearch"))

        with patch("core.factory.models.FactoryConfig") as mock_config:
            mock_config.return_value.enabled = True
            success, msg = await executor._create_agent(
                {
                    "task_description": "create a websearch agent",
                    "suggested_name": "websearch",
                }
            )

        assert success is True
        assert "websearch" in msg
        executor._factory_create.assert_called_once()
        call_args = executor._factory_create.call_args[0][0]
        assert call_args["goal"] == "create a websearch agent"
        assert call_args["suggested_name"] == "websearch"
        assert call_args["trigger"] == "escalation"

    @pytest.mark.asyncio
    async def test_create_agent_returns_error_when_factory_disabled(self):
        """Post-119.6: _create_agent returns clear error when factory disabled."""
        from unittest.mock import patch

        from core.orchestrator.escalation import EscalationExecutor

        executor = EscalationExecutor()

        with patch("core.factory.models.FactoryConfig") as mock_config:
            mock_config.return_value.enabled = False
            success, msg = await executor._create_agent(
                {
                    "task_description": "create a websearch agent",
                    "suggested_name": "websearch",
                }
            )

        assert success is False
        assert "disabled" in msg.lower()

    @pytest.mark.asyncio
    async def test_create_tool_delegates_to_factory_create(self):
        """Post-119.6: _create_tool delegates to _factory_create."""
        from unittest.mock import AsyncMock, patch

        from core.orchestrator.escalation import EscalationExecutor

        executor = EscalationExecutor()
        executor._factory_create = AsyncMock(return_value=(True, "Created tool json_validator"))

        with patch("core.factory.models.FactoryConfig") as mock_config:
            mock_config.return_value.enabled = True
            success, msg = await executor._create_tool(
                {
                    "tool_name": "json_validator",
                    "description": "Validate JSON documents",
                }
            )

        assert success is True
        executor._factory_create.assert_called_once()
        call_args = executor._factory_create.call_args[0][0]
        assert call_args["goal"] == "Validate JSON documents"
        assert call_args["suggested_name"] == "json_validator"
        assert call_args["artifact_type"] == "tool"
        assert call_args["trigger"] == "escalation"
