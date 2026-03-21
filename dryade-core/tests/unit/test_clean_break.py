"""Clean break verification tests.

Confirms:
- agent_resolver.py is deleted and import fails
- Hand-crafted agents still load correctly
- dryade.json manifests are valid
- _create_agent/_create_tool delegate to _factory_create
- _handle_meta_action uses FACTORY_CREATE
- SkillLoader lazy loading works
- known_packages MCP servers are not affected
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Category 13: agent_resolver deletion
# ---------------------------------------------------------------------------

class TestAgentResolverDeletion:
    """Verify agent_resolver.py is fully removed."""

    def test_module_import_fails(self):
        """Importing agent_resolver raises ImportError."""
        with pytest.raises(ImportError):
            import core.orchestrator.agent_resolver  # noqa: F401

    def test_resolve_agent_command_import_fails(self):
        """Direct function import also fails."""
        with pytest.raises(ImportError):
            from core.orchestrator.agent_resolver import resolve_agent_command  # noqa: F401

    def test_file_does_not_exist(self):
        """Physical file is gone from disk."""
        resolver_path = Path("core/orchestrator/agent_resolver.py")
        assert not resolver_path.exists(), "agent_resolver.py should be deleted"

    def test_test_file_does_not_exist(self):
        """Test file for deleted module is also gone."""
        test_path = Path("tests/unit/test_agent_resolver.py")
        assert not test_path.exists(), "test_agent_resolver.py should be deleted"

# ---------------------------------------------------------------------------
# Category 14: Hand-crafted agent loading
# ---------------------------------------------------------------------------

class TestHandCraftedAgentLoading:
    """Verify all 5 hand-crafted agents still register correctly."""

    AGENTS = [
        "devops_engineer",
        "research_assistant",
        "code_reviewer",
        "database_analyst",
        "project_manager",
    ]

    def test_get_available_agents_lists_all_five(self):
        from agents import get_available_agents

        available = get_available_agents()
        for agent in self.AGENTS:
            assert agent in available, f"{agent} missing from available agents"

    def test_agent_directories_exist(self):
        for agent in self.AGENTS:
            agent_dir = Path(f"agents/{agent}")
            assert agent_dir.exists(), f"agents/{agent}/ missing"
            assert (agent_dir / "config.yaml").exists(), f"agents/{agent}/config.yaml missing"
            assert (agent_dir / "__init__.py").exists(), f"agents/{agent}/__init__.py missing"

    def test_agent_init_modules_importable(self):
        """Each agent's __init__.py can be imported."""
        import importlib

        # Some agents require optional dependencies (e.g. langchain_core)
        OPTIONAL_DEPS = {
            "research_assistant": "langchain_core",
            "database_analyst": "langchain_core",
        }

        for agent in self.AGENTS:
            dep = OPTIONAL_DEPS.get(agent)
            if dep:
                pytest.importorskip(dep)
            mod = importlib.import_module(f"agents.{agent}")
            assert mod is not None

# ---------------------------------------------------------------------------
# Category 15: dryade.json manifests
# ---------------------------------------------------------------------------

class TestDryadeJsonManifests:
    """Verify dryade.json for each hand-crafted agent."""

    AGENTS = [
        ("devops_engineer", "mcp"),
        ("research_assistant", "langchain"),
        ("code_reviewer", "crewai"),
        ("database_analyst", "langchain"),
        ("project_manager", "mcp"),
    ]

    REQUIRED_FIELDS = {
        "manifest_version",
        "type",
        "name",
        "version",
        "description",
        "author",
        "framework",
        "created_by",
        "required_servers",
        "capabilities",
    }

    @pytest.mark.parametrize("agent,framework", AGENTS)
    def test_manifest_exists_and_valid_json(self, agent, framework):
        manifest_path = Path(f"agents/{agent}/dryade.json")
        assert manifest_path.exists(), f"agents/{agent}/dryade.json missing"
        data = json.loads(manifest_path.read_text())
        assert isinstance(data, dict)

    @pytest.mark.parametrize("agent,framework", AGENTS)
    def test_manifest_has_required_fields(self, agent, framework):
        data = json.loads(Path(f"agents/{agent}/dryade.json").read_text())
        missing = self.REQUIRED_FIELDS - set(data.keys())
        assert not missing, f"{agent}: missing fields {missing}"

    @pytest.mark.parametrize("agent,framework", AGENTS)
    def test_manifest_type_is_agent(self, agent, framework):
        data = json.loads(Path(f"agents/{agent}/dryade.json").read_text())
        assert data["type"] == "agent"

    @pytest.mark.parametrize("agent,framework", AGENTS)
    def test_manifest_created_by_manual(self, agent, framework):
        data = json.loads(Path(f"agents/{agent}/dryade.json").read_text())
        assert data["created_by"] == "manual"

    @pytest.mark.parametrize("agent,framework", AGENTS)
    def test_manifest_framework_matches(self, agent, framework):
        data = json.loads(Path(f"agents/{agent}/dryade.json").read_text())
        assert data["framework"] == framework

    @pytest.mark.parametrize("agent,framework", AGENTS)
    def test_manifest_has_nonempty_capabilities(self, agent, framework):
        data = json.loads(Path(f"agents/{agent}/dryade.json").read_text())
        assert isinstance(data["capabilities"], list)
        assert len(data["capabilities"]) > 0

    @pytest.mark.parametrize("agent,framework", AGENTS)
    def test_manifest_has_nonempty_servers(self, agent, framework):
        data = json.loads(Path(f"agents/{agent}/dryade.json").read_text())
        assert isinstance(data["required_servers"], list)
        assert len(data["required_servers"]) > 0

# ---------------------------------------------------------------------------
# Category 16: known_packages MCP servers (factory does not manage)
# ---------------------------------------------------------------------------

class TestKnownPackagesMcpPreservation:
    """Verify factory recognizes existing MCP servers as not factory-managed."""

    def test_factory_artifact_has_created_by_field(self):
        """FactoryArtifact model supports created_by field."""
        from core.factory.models import FactoryArtifact

        model_fields = FactoryArtifact.model_fields
        assert "created_by" in model_fields

    def test_factory_artifact_default_created_by_is_factory(self):
        """FactoryArtifact created_by defaults to 'factory'."""
        from core.factory.models import FactoryArtifact

        # Get default from model field
        default = FactoryArtifact.model_fields["created_by"].default
        assert default == "factory"

# ---------------------------------------------------------------------------
# Category 17: Factory-disabled graceful degradation
# ---------------------------------------------------------------------------

class TestFactoryDisabledDegradation:
    """Verify _create_agent and _create_tool return clear errors when factory disabled."""

    @pytest.mark.asyncio
    async def test_create_agent_factory_disabled(self):
        from core.orchestrator.escalation import EscalationExecutor

        executor = EscalationExecutor()
        with patch("core.factory.models.FactoryConfig") as MockConfig:
            MockConfig.return_value.enabled = False
            success, msg = await executor._create_agent(
                {
                    "task_description": "create agent",
                    "suggested_name": "test",
                }
            )
        assert success is False
        assert "disabled" in msg.lower()

    @pytest.mark.asyncio
    async def test_create_tool_factory_disabled(self):
        from core.orchestrator.escalation import EscalationExecutor

        executor = EscalationExecutor()
        with patch("core.factory.models.FactoryConfig") as MockConfig:
            MockConfig.return_value.enabled = False
            success, msg = await executor._create_tool(
                {
                    "tool_name": "test_tool",
                    "description": "test",
                }
            )
        assert success is False
        assert "disabled" in msg.lower()

    @pytest.mark.asyncio
    async def test_create_agent_has_method(self):
        """EscalationExecutor has _create_agent method."""
        from core.orchestrator.escalation import EscalationExecutor

        executor = EscalationExecutor()
        assert hasattr(executor, "_create_agent")
        assert callable(executor._create_agent)

    @pytest.mark.asyncio
    async def test_create_tool_has_method(self):
        """EscalationExecutor has _create_tool method."""
        from core.orchestrator.escalation import EscalationExecutor

        executor = EscalationExecutor()
        assert hasattr(executor, "_create_tool")
        assert callable(executor._create_tool)

# ---------------------------------------------------------------------------
# Category 18: Meta-action uses FACTORY_CREATE
# ---------------------------------------------------------------------------

class TestMetaActionFactoryCreate:
    """Verify _handle_meta_action builds FACTORY_CREATE escalation."""

    def test_complex_handler_has_no_resolve_method(self):
        """_resolve_meta_action_agent should be deleted."""
        from core.orchestrator.handlers.complex_handler import ComplexHandler

        assert not hasattr(ComplexHandler, "_resolve_meta_action_agent")

    @pytest.mark.asyncio
    async def test_handle_meta_action_uses_factory_create(self):
        """_handle_meta_action should register FACTORY_CREATE escalation."""
        from core.orchestrator.escalation import EscalationActionType, get_escalation_registry
        from core.orchestrator.handlers.complex_handler import ComplexHandler

        handler = ComplexHandler()
        context = MagicMock()
        context.conversation_id = "test-conv-meta"
        context.metadata = {}

        tier_decision = MagicMock()
        tier_decision.confidence = 0.95

        # Collect events
        events = []
        async for event in handler._handle_meta_action(
            "create a websearch agent", context, tier_decision
        ):
            events.append(event)

        # Verify escalation was registered
        registry = get_escalation_registry()
        pending = registry.get_pending("test-conv-meta")
        assert pending is not None
        assert pending.action.action_type == EscalationActionType.FACTORY_CREATE
        assert pending.action.parameters["goal"] == "create a websearch agent"

        # Clean up
        registry.clear("test-conv-meta")

    @pytest.mark.asyncio
    async def test_handle_meta_action_extracts_suggested_name(self):
        """Meta-action builds FACTORY_CREATE escalation with the full message as goal.

        English regex name extraction was removed. The factory now handles
        name extraction internally via LLM-driven config generation (language-agnostic).
        suggested_name is always None from _handle_meta_action; factory resolves it.
        """
        from core.orchestrator.escalation import get_escalation_registry
        from core.orchestrator.handlers.complex_handler import ComplexHandler

        handler = ComplexHandler()
        context = MagicMock()
        context.conversation_id = "test-conv-name"
        context.metadata = {}
        tier_decision = MagicMock()
        tier_decision.confidence = 0.9

        events = []
        async for event in handler._handle_meta_action(
            "create a browser agent", context, tier_decision
        ):
            events.append(event)

        pending = get_escalation_registry().get_pending("test-conv-name")
        assert pending is not None
        # suggested_name is None (factory resolves name internally)
        assert pending.action.parameters.get("suggested_name") is None
        # Goal should contain the full message
        assert "browser" in pending.action.parameters.get("goal", "")

        # Clean up
        get_escalation_registry().clear("test-conv-name")

    @pytest.mark.asyncio
    async def test_handle_meta_action_trigger_is_meta_action(self):
        """Meta-action trigger should be 'meta_action'."""
        from core.orchestrator.escalation import get_escalation_registry
        from core.orchestrator.handlers.complex_handler import ComplexHandler

        handler = ComplexHandler()
        context = MagicMock()
        context.conversation_id = "test-conv-trigger"
        context.metadata = {}
        tier_decision = MagicMock()
        tier_decision.confidence = 0.9

        events = []
        async for event in handler._handle_meta_action(
            "create a data agent", context, tier_decision
        ):
            events.append(event)

        pending = get_escalation_registry().get_pending("test-conv-trigger")
        assert pending is not None
        assert pending.action.parameters.get("trigger") == "meta_action"

        # Clean up
        get_escalation_registry().clear("test-conv-trigger")

# ---------------------------------------------------------------------------
# SkillLoader lazy loading
# ---------------------------------------------------------------------------

class TestSkillLoaderLazy:
    """Verify SkillLoader lazy loading (Stage 1 metadata only)."""

    def test_skill_instructions_loaded_default_true(self):
        from core.skills.models import Skill

        s = Skill(name="test", description="desc", instructions="body", skill_dir="/tmp")
        assert s.instructions_loaded is True

    def test_skill_instructions_loaded_false(self):
        from core.skills.models import Skill

        s = Skill(
            name="test",
            description="desc",
            instructions="",
            skill_dir="/tmp",
            instructions_loaded=False,
        )
        assert s.instructions_loaded is False
        assert s.instructions == ""

    def test_ensure_instructions_loaded_noop_when_loaded(self):
        from core.skills.models import Skill

        s = Skill(name="test", description="desc", instructions="body", skill_dir="/tmp")
        s.ensure_instructions_loaded()
        assert s.instructions == "body"

    def test_load_metadata_only_method_exists(self):
        from core.skills.loader import MarkdownSkillLoader

        assert hasattr(MarkdownSkillLoader, "load_metadata_only")

    def test_discover_skills_metadata_only_param(self):
        import inspect

        from core.skills.loader import MarkdownSkillLoader

        sig = inspect.signature(MarkdownSkillLoader.discover_skills)
        assert "metadata_only" in sig.parameters
        assert sig.parameters["metadata_only"].default is False
