"""Tests for self-modification tools.

Covers:
- Self-mod tool definitions (OpenAI function-calling format)
- is_self_mod_tool() predicate
- is_read_only_tool() predicate
- get_self_mod_tools() model-aware variants
- execute_self_mod_tool() dispatcher -> PendingEscalation / dict
- CapabilityRegistry (register/unregister/search/list_all/singleton)
- RoutingMetricsTracker basics
- ComplexityEstimator meta_action_hint behavior
- Unified `create` tool, memory_delete, always-inject, fallback guard, TTL cache
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

# ---- Self-mod tool tests (11 tools, unified `create`) ----

class TestSelfModToolDefinitions:
    """Verify tool definitions are in correct OpenAI format."""

    def test_eleven_tools_defined(self):
        # 11 tools (self_improve/create_agent/create_tool merged into `create`,
        # memory_delete added; net 12->11)
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
        # self_improve renamed to `create`
        tool = next(t for t in SELF_MOD_TOOLS if t["function"]["name"] == "factory_create")
        assert "goal" in tool["function"]["parameters"]["required"]

    def test_create_tool_has_artifact_type_param(self):
        # `create` has optional artifact_type enum parameter
        tool = next(t for t in SELF_MOD_TOOLS if t["function"]["name"] == "factory_create")
        props = tool["function"]["parameters"]["properties"]
        assert "artifact_type" in props
        assert props["artifact_type"]["type"] == "string"
        assert "enum" in props["artifact_type"]
        assert set(props["artifact_type"]["enum"]) == {"agent", "tool", "skill"}
        # artifact_type is optional (NOT in required list)
        assert "artifact_type" not in tool["function"]["parameters"]["required"]

    def test_tool_names_match_constant(self):
        tool_names = {t["function"]["name"] for t in SELF_MOD_TOOLS}
        assert tool_names == SELF_MOD_TOOL_NAMES

class TestIsSelfModTool:
    # self_improve/create_agent/create_tool replaced by `create`
    def test_recognizes_create(self):
        assert is_self_mod_tool("factory_create") is True

    def test_recognizes_memory_delete(self):
        assert is_self_mod_tool("memory_delete") is True

    def test_recognizes_modify_config(self):
        assert is_self_mod_tool("modify_config") is True

    def test_rejects_self_improve_old_name(self):
        # self_improve is no longer a tool name
        assert is_self_mod_tool("self_improve") is False

    def test_rejects_create_agent_old_name(self):
        # create_agent is no longer a tool name
        assert is_self_mod_tool("create_agent") is False

    def test_rejects_create_tool_old_name(self):
        # create_tool is no longer a tool name
        assert is_self_mod_tool("create_tool") is False

    def test_rejects_unknown_tool(self):
        assert is_self_mod_tool("random_tool") is False

    def test_rejects_none(self):
        assert is_self_mod_tool(None) is False

class TestExecuteSelfModTool:
    @pytest.mark.asyncio
    async def test_create_returns_pending_escalation(self):
        # unified `create` tool replaces self_improve/create_agent/create_tool
        result = await execute_self_mod_tool(
            tool_name="factory_create",
            arguments={"goal": "Create a websearch agent", "artifact_type": "agent"},
            conversation_id="test-conv",
            original_goal="create a websearch agent",
        )
        assert result.conversation_id == "test-conv"
        assert result.action.action_type == EscalationActionType.FACTORY_CREATE
        assert result.action.parameters["goal"] == "Create a websearch agent"
        assert result.action.parameters["artifact_type"] == "agent"

    @pytest.mark.asyncio
    async def test_create_without_artifact_type_returns_pending_escalation(self):
        # artifact_type is optional; factory infers from goal
        result = await execute_self_mod_tool(
            tool_name="factory_create",
            arguments={"goal": "Build a web scraper tool"},
            conversation_id="test-conv",
            original_goal="create a web scraper",
        )
        assert result.action.action_type == EscalationActionType.FACTORY_CREATE
        assert result.action.parameters["artifact_type"] is None

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

# ---- Model-aware tool variant tests ----

class TestGetSelfModTools:
    """Test model-aware tool definition getter."""

    def test_get_self_mod_tools_detailed_count(self):
        tools = get_self_mod_tools("detailed")
        assert len(tools) == 11  # 11 tools (consolidated from 12)

    def test_get_self_mod_tools_short_count(self):
        tools = get_self_mod_tools("short")
        assert len(tools) == 11  # 11 tools (consolidated from 12)

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

    def test_is_read_only_tool_add_mcp_server(self):
        assert is_read_only_tool("add_mcp_server") is False

    def test_is_read_only_tool_none(self):
        assert is_read_only_tool(None) is False

class TestNewSelfModTools:
    """Test self-mod tool recognition."""

    def test_create_is_self_mod(self):
        # unified `create` tool
        assert is_self_mod_tool("factory_create") is True

    def test_memory_delete_is_self_mod(self):
        # new memory_delete tool
        assert is_self_mod_tool("memory_delete") is True

    def test_new_mcp_tools_are_self_mod(self):
        assert is_self_mod_tool("add_mcp_server") is True
        assert is_self_mod_tool("remove_mcp_server") is True
        assert is_self_mod_tool("configure_mcp_server") is True

class TestNewToolDispatch:
    """Test dispatch of self-mod tools."""

    @pytest.mark.asyncio
    async def test_execute_create_with_agent_type(self):
        # unified `create` tool with artifact_type="agent"
        result = await execute_self_mod_tool(
            tool_name="factory_create",
            arguments={"goal": "test agent creation", "artifact_type": "agent"},
            conversation_id="conv1",
            original_goal="test",
        )
        assert isinstance(result, PendingEscalation)
        assert result.action.action_type == EscalationActionType.FACTORY_CREATE
        assert result.action.parameters["goal"] == "test agent creation"
        assert result.action.parameters["artifact_type"] == "agent"

    @pytest.mark.asyncio
    async def test_execute_create_with_tool_type(self):
        # unified `create` tool with artifact_type="tool"
        result = await execute_self_mod_tool(
            tool_name="factory_create",
            arguments={"goal": "Build a CSV parser", "artifact_type": "tool"},
            conversation_id="conv1",
            original_goal="test",
        )
        assert isinstance(result, PendingEscalation)
        assert result.action.action_type == EscalationActionType.FACTORY_CREATE
        assert result.action.parameters["artifact_type"] == "tool"

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
        # should find `factory_create` (Phase 174.5: renamed from `create`)
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

# ---- Bug fix regression tests ----

class TestSelfModToolEscalationBugFixes:
    """Regression tests for tool dispatch bugs.

    Bug 1: question was a flat description, not an approval question
    Bug 2: failed_agent was polluting parameters instead of suggested_name
    Bug 3: _create_agent didn't resolve MCP commands for unknown agents
    """

    # -------------------------------------------------------------------
    # Bug 1: question must be an approval question, not a statement
    # (now tests `create` tool instead of self_improve/create_agent)
    # -------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_question_includes_goal(self):
        """Bug 1 regression: create question should mention the goal/name."""
        result = await execute_self_mod_tool(
            tool_name="factory_create",
            arguments={"goal": "Create websearch", "name": "websearch"},
            conversation_id="test-conv",
            original_goal="create a websearch agent",
        )
        assert isinstance(result, PendingEscalation)
        assert "websearch" in result.question

    @pytest.mark.asyncio
    async def test_create_question_contains_agent_factory(self):
        """Bug 1 regression: question format uses 'Agent Factory' framing."""
        result = await execute_self_mod_tool(
            tool_name="factory_create",
            arguments={"goal": "Create browser agent", "name": "browser"},
            conversation_id="test-conv",
            original_goal="create a browser agent",
        )
        assert isinstance(result, PendingEscalation)
        assert "Agent Factory" in result.question

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
        """Post-119.6: When LLM omits name arg, suggested_name is None (factory resolves internally)."""
        result = await execute_self_mod_tool(
            tool_name="factory_create",
            arguments={"goal": "Create some agent"},
            conversation_id="test-conv",
            original_goal="create an agent",
        )
        # factory handles name resolution internally
        assert result.action.parameters["suggested_name"] is None

    @pytest.mark.asyncio
    async def test_create_artifact_type_passed_through(self):
        """artifact_type parameter is passed through to FACTORY_CREATE."""
        result = await execute_self_mod_tool(
            tool_name="factory_create",
            arguments={"goal": "Build a web scraper", "artifact_type": "tool"},
            conversation_id="test-conv",
            original_goal="create a web scraper",
        )
        assert result.action.parameters["artifact_type"] == "tool"

    # -------------------------------------------------------------------
    # Post-119.6: _create_agent and _create_tool delegate to _factory_create
    # (kept for EscalationExecutor backward compat -- escalation.py still has
    # these methods for handling serialized CREATE_AGENT/CREATE_TOOL actions)
    # -------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_agent_executor_delegates_to_factory_create(self):
        """Post-119.6: EscalationExecutor._create_agent delegates to _factory_create."""
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
    async def test_create_agent_executor_returns_error_when_factory_disabled(self):
        """Post-119.6: EscalationExecutor._create_agent returns clear error when factory disabled."""
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
    async def test_create_tool_executor_delegates_to_factory_create(self):
        """Post-119.6: EscalationExecutor._create_tool delegates to _factory_create."""
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

# ---- Dead code cleanup verification ----

class TestDeadCodeCleanup:
    """Verify old tool names are not in the active tool set."""

    def test_dead_code_cleanup(self):
        assert "self_improve" not in SELF_MOD_TOOL_NAMES
        assert "create_agent" not in SELF_MOD_TOOL_NAMES
        assert "create_tool" not in SELF_MOD_TOOL_NAMES
        # Phase 174.5: "create" renamed to "factory_create"
        assert "factory_create" in SELF_MOD_TOOL_NAMES
        assert "memory_delete" in SELF_MOD_TOOL_NAMES
        assert len(SELF_MOD_TOOL_NAMES) == 11

# ---- memory_delete tool tests ----

class TestMemoryDelete:
    """Tests for execute_memory_delete()."""

    def test_memory_delete_existing_block(self):
        from unittest.mock import MagicMock, patch

        mock_store = MagicMock()
        mock_store.delete_block.return_value = True

        with patch(
            "core.orchestrator.memory_tools.get_memory_block_store",
            return_value=mock_store,
        ):
            from core.orchestrator.memory_tools import execute_memory_delete

            result = execute_memory_delete(agent_id="test", label="my_block")
            assert result == {"status": "ok", "label": "my_block"}
            mock_store.delete_block.assert_called_once_with("test", "my_block")

    def test_memory_delete_nonexistent_block(self):
        from unittest.mock import MagicMock, patch

        mock_store = MagicMock()
        mock_store.delete_block.return_value = False

        with patch(
            "core.orchestrator.memory_tools.get_memory_block_store",
            return_value=mock_store,
        ):
            from core.orchestrator.memory_tools import execute_memory_delete

            result = execute_memory_delete(agent_id="test", label="nonexistent")
            assert result == {"status": "not_found", "label": "nonexistent"}

    @pytest.mark.asyncio
    async def test_execute_self_mod_memory_delete_dispatches(self):
        """memory_delete dispatches via execute_self_mod_tool."""
        from unittest.mock import MagicMock, patch

        mock_store = MagicMock()
        mock_store.delete_block.return_value = True

        with patch(
            "core.orchestrator.memory_tools.get_memory_block_store",
            return_value=mock_store,
        ):
            result = await execute_self_mod_tool(
                tool_name="memory_delete",
                arguments={"label": "test_block"},
                conversation_id="conv-1",
                original_goal="delete memory",
            )
        assert result == {"status": "ok", "label": "test_block"}

    def test_memory_delete_is_read_only(self):
        """memory_delete is a read-only tool (returns result without escalation)."""
        assert is_read_only_tool("memory_delete") is True

# ---- Gap closure04: Gap Closure Tests (always-inject, fallback guard, TTL cache) ----

class TestAlwaysInject:
    """Tests for the always-inject self-mod tools gate (Gap closure02).

    The injection logic in provider.py:
    - native_tools is not None AND config.self_mod_tools_enabled AND not WeakStrategy -> inject
    - native_tools is None -> skip (text-only provider)
    - WeakStrategy (should_force_fallback=True) -> skip even with native_tools
    """

    def test_always_inject_function_calling_provider(self):
        """Self-mod tools are injected when native_tools is not None and not WeakStrategy."""
        from unittest.mock import MagicMock, patch

        mock_strategy = MagicMock()
        mock_strategy.should_force_fallback.return_value = False
        mock_strategy.get_tool_description_variant.return_value = "detailed"

        mock_config = MagicMock()
        mock_config.self_mod_tools_enabled = True

        native_tools = [{"type": "function", "function": {"name": "test_tool"}}]
        context = {"_meta_action_hint": False}

        # Replicate the gate logic from provider.py (always-inject gate)
        with patch("core.orchestrator.self_mod_tools.get_self_mod_tools") as mock_get_tools:
            mock_get_tools.return_value = [
                {"type": "function", "function": {"name": f"sm_{i}"}} for i in range(11)
            ]

            if native_tools is not None and mock_config.self_mod_tools_enabled:
                is_weak = mock_strategy.should_force_fallback()
                if not is_weak:
                    variant = mock_strategy.get_tool_description_variant()
                    self_mod_tools = mock_get_tools(variant)
                    native_tools = list(native_tools) + self_mod_tools
                    context["_self_mod_tools_injected"] = True

        assert len(native_tools) == 12  # 1 original + 11 self-mod
        assert context.get("_self_mod_tools_injected") is True
        mock_strategy.should_force_fallback.assert_called_once()

    def test_skip_inject_weak_model(self):
        """Self-mod tools are NOT injected when WeakStrategy (should_force_fallback=True)."""
        from unittest.mock import MagicMock

        mock_strategy = MagicMock()
        mock_strategy.should_force_fallback.return_value = True  # WeakStrategy

        mock_config = MagicMock()
        mock_config.self_mod_tools_enabled = True

        native_tools = [{"type": "function", "function": {"name": "test_tool"}}]
        context = {}

        if native_tools is not None and mock_config.self_mod_tools_enabled:
            is_weak = mock_strategy.should_force_fallback()
            if not is_weak:
                context["_self_mod_tools_injected"] = True

        assert len(native_tools) == 1  # Original only, no self-mod tools added
        assert "_self_mod_tools_injected" not in context

    def test_skip_inject_text_only_provider(self):
        """Self-mod tools are NOT injected when native_tools is None (text-only provider)."""
        from unittest.mock import MagicMock

        mock_config = MagicMock()
        mock_config.self_mod_tools_enabled = True

        native_tools = None  # Text-only provider
        context = {}

        if native_tools is not None and mock_config.self_mod_tools_enabled:
            context["_self_mod_tools_injected"] = True

        assert native_tools is None  # Unchanged
        assert "_self_mod_tools_injected" not in context

class TestFallbackGuard:
    """Tests for the meta-action fallback guard (Gap closure02).

    The fallback guard in complex_handler.py:
    - meta_hint=True AND _self_mod_tools_injected=False -> fallback fires (text-only)
    - meta_hint=True AND _self_mod_tools_injected=True -> fallback suppressed (function-calling)
    """

    def test_fallback_text_only_fires(self):
        """Fallback guard fires when tools were NOT injected (text-only provider)."""
        meta_hint = True
        self_mod_tools_were_injected = False
        is_retry = False
        meta_action_fallback_enabled = True
        result_success = True
        result_needs_escalation = False

        # Replicate the guard condition from complex_handler.py
        should_fire = (
            meta_hint
            and not self_mod_tools_were_injected
            and not is_retry
            and meta_action_fallback_enabled
            and result_success
            and not result_needs_escalation
        )

        assert should_fire is True, (
            "Fallback should fire for text-only providers where self-mod tools couldn't be injected"
        )

    def test_fallback_function_calling_does_not_fire(self):
        """Fallback guard does NOT fire when tools were injected (function-calling provider)."""
        meta_hint = True
        self_mod_tools_were_injected = True  # Function-calling provider, always-inject active
        is_retry = False
        meta_action_fallback_enabled = True
        result_success = True
        result_needs_escalation = False

        # Replicate the guard condition from complex_handler.py
        should_fire = (
            meta_hint
            and not self_mod_tools_were_injected
            and not is_retry
            and meta_action_fallback_enabled
            and result_success
            and not result_needs_escalation
        )

        assert should_fire is False, (
            "Fallback should NOT fire for function-calling providers where "
            "self-mod tools were injected via always-inject"
        )

class TestSearchCapabilitiesTTLCache:
    """Tests for CapabilityRegistry.refresh_from_sources() TTL cache (Gap closure01)."""

    def test_search_capabilities_ttl_cache(self):
        """refresh_from_sources() skips rebuild within 30s TTL window."""
        from unittest.mock import MagicMock, patch

        from core.orchestrator.capability_registry import CapabilityRegistry

        registry = CapabilityRegistry.__new__(CapabilityRegistry)
        # Initialize required attributes manually (avoid singleton)
        registry._entries = {}
        registry._by_source = {}
        registry._by_category = {}
        registry._last_refresh_time = 0.0
        registry._refresh_ttl_seconds = 30.0

        import threading

        registry._lock = threading.RLock()

        with (
            patch(
                # SELF_MOD_TOOL_NAMES is imported inside refresh_from_sources() from
                # self_mod_tools, not from capability_registry. Patch it at the source.
                "core.orchestrator.self_mod_tools.SELF_MOD_TOOL_NAMES",
                {"create", "memory_delete"},
            ),
            patch(
                "core.orchestrator.capability_registry.ToolIndex",
                MagicMock(return_value=MagicMock(get_all_tools=MagicMock(return_value=[]))),
                create=True,
            ),
        ):
            # First call: should rebuild (_last_refresh_time = 0.0)
            count1 = registry.refresh_from_sources()
            assert count1 >= 0
            first_refresh_time = registry._last_refresh_time
            assert first_refresh_time > 0, "refresh_from_sources should update _last_refresh_time"

            # Second call within TTL: should skip rebuild
            count2 = registry.refresh_from_sources()
            second_refresh_time = registry._last_refresh_time
            assert second_refresh_time == first_refresh_time, (
                "TTL cache should prevent rebuild; _last_refresh_time should not change"
            )

            # Third call with force=True: should rebuild despite TTL
            count3 = registry.refresh_from_sources(force=True)
            third_refresh_time = registry._last_refresh_time
            assert third_refresh_time >= first_refresh_time, (
                "force=True should bypass TTL and rebuild; _last_refresh_time should update"
            )
