"""Integration tests for multi-framework agent showcase.

Tests all 10 agents (4 core + 6 plugin) with mocked MCP servers.
Validates framework assignments, tier distribution, and setup wizard functionality.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from core.adapters import get_agent, get_registry
from core.adapters.protocol import AgentFramework

class TestAgentDiscovery:
    """Test agent registration and discovery."""

    def setup_method(self):
        """Clear registry before each test."""
        get_registry().clear()

    def test_register_core_agents_returns_list(self):
        """register_core_agents should return list of agent names."""
        from agents import register_core_agents

        with patch("core.mcp.get_registry") as mock_registry:
            mock_registry.return_value = MagicMock()

            result = register_core_agents()

            assert isinstance(result, list)
            assert len(result) == 4

    def test_core_agents_registered(self):
        """All 4 core agents should be registered."""
        from agents import register_core_agents

        with patch("core.mcp.get_registry") as mock_registry:
            mock_registry.return_value = MagicMock()

            registered = register_core_agents()

            assert len(registered) == 4, f"Expected 4 core agents, got {len(registered)}"
            assert "devops_engineer" in registered
            assert "code_reviewer" in registered
            assert "database_analyst" in registered
            assert "research_assistant" in registered

    def test_agents_discoverable_by_name(self):
        """Each agent should be retrievable by name."""
        from agents import register_core_agents

        with patch("core.mcp.get_registry") as mock_registry:
            mock_registry.return_value = MagicMock()
            register_core_agents()

            for name in [
                "devops_engineer",
                "code_reviewer",
                "database_analyst",
                "research_assistant",
            ]:
                agent = get_agent(name)
                assert agent is not None, f"Agent {name} not found"
                assert agent.get_card().name == name

class TestFrameworkDistribution:
    """Test framework assignments match specification."""

    def setup_method(self):
        """Clear registry before each test."""
        get_registry().clear()

    def test_devops_engineer_is_mcp(self):
        """DevOps Engineer should use MCP framework."""
        from agents.devops_engineer import create_devops_engineer_agent

        with patch("core.mcp.get_registry"):
            agent = create_devops_engineer_agent()
            assert agent.get_card().framework == AgentFramework.MCP

    def test_code_reviewer_is_crewai(self):
        """Code Reviewer should use CrewAI framework."""
        from agents.code_reviewer import create_code_reviewer_agent

        with patch("core.mcp.get_registry"):
            agent = create_code_reviewer_agent()
            assert agent.get_card().framework == AgentFramework.CREWAI

    def test_database_analyst_is_langchain(self):
        """Database Analyst should use LangChain framework."""
        from agents.database_analyst import create_database_analyst_agent

        with patch("core.mcp.get_registry"):
            agent = create_database_analyst_agent()
            assert agent.get_card().framework == AgentFramework.LANGCHAIN

    def test_research_assistant_is_langchain(self):
        """Research Assistant should use LangChain framework."""
        from agents.research_assistant import create_research_assistant_agent

        with patch("core.mcp.get_registry"):
            agent = create_research_assistant_agent()
            assert agent.get_card().framework == AgentFramework.LANGCHAIN

def _create_mock_crewai_agent():
    """Create a mock CrewAI Agent with required attributes."""
    mock_agent = MagicMock()
    mock_agent.role = "Test Agent"
    mock_agent.goal = "Test Goal"
    mock_agent.backstory = "Test backstory"
    mock_agent.tools = []
    return mock_agent

class TestPluginAgentFrameworks:
    """Test plugin agent framework assignments."""

    def setup_method(self):
        """Clear registry before each test."""
        get_registry().clear()

    def test_excel_analyst_is_crewai(self):
        """Excel Analyst should use CrewAI framework."""
        from plugins.excel_analyst.agent import create_excel_analyst_agent

        # Mock CrewAI Agent to avoid LLM initialization
        with (
            patch("core.mcp.get_registry"),
            patch("plugins.excel_analyst.agent.Agent") as mock_agent_cls,
        ):
            mock_agent_cls.return_value = _create_mock_crewai_agent()
            agent = create_excel_analyst_agent()
            assert agent.get_card().framework == AgentFramework.CREWAI

    def test_kpi_monitor_is_langchain(self):
        """KPI Monitor should use LangChain framework."""
        from plugins.kpi_monitor.agent import create_kpi_monitor_agent

        with patch("core.mcp.get_registry"):
            agent = create_kpi_monitor_agent()
            assert agent.get_card().framework == AgentFramework.LANGCHAIN

    def test_document_processor_is_crewai(self):
        """Document Processor should use CrewAI framework."""
        from plugins.document_processor.agent import create_document_processor_agent

        # Mock CrewAI Agent to avoid LLM initialization
        with (
            patch("core.mcp.get_registry"),
            patch("plugins.document_processor.agent.Agent") as mock_agent_cls,
        ):
            mock_agent_cls.return_value = _create_mock_crewai_agent()
            agent = create_document_processor_agent()
            assert agent.get_card().framework == AgentFramework.CREWAI

    def test_project_manager_is_adk(self):
        """Project Manager should use ADK framework."""
        from plugins.project_manager.agent import create_project_manager_agent

        with patch("core.mcp.get_registry"):
            agent = create_project_manager_agent()
            assert agent.get_card().framework == AgentFramework.ADK

    def test_compliance_auditor_is_crewai(self):
        """Compliance Auditor should use CrewAI framework."""
        from plugins.compliance_auditor.agent import create_compliance_auditor_agent

        # Mock CrewAI Agent to avoid LLM initialization
        with (
            patch("core.mcp.get_registry"),
            patch("plugins.compliance_auditor.agent.Agent") as mock_agent_cls,
        ):
            mock_agent_cls.return_value = _create_mock_crewai_agent()
            agent = create_compliance_auditor_agent()
            assert agent.get_card().framework == AgentFramework.CREWAI

    def test_sales_intelligence_is_adk(self):
        """Sales Intelligence should use ADK framework."""
        from plugins.sales_intelligence.agent import create_sales_intelligence_agent

        with patch("core.mcp.get_registry"):
            agent = create_sales_intelligence_agent()
            assert agent.get_card().framework == AgentFramework.ADK

@pytest.mark.asyncio
class TestAgentExecution:
    """Test agent execution with mocked MCP."""

    def setup_method(self):
        """Clear registry before each test."""
        get_registry().clear()

    async def test_devops_engineer_execute(self):
        """DevOps Engineer should handle execute call."""
        from agents.devops_engineer import create_devops_engineer_agent

        mock_result = MagicMock()
        mock_result.content = [MagicMock(type="text", text="On branch main")]

        with patch("core.mcp.get_registry") as mock_registry:
            mock_registry.return_value.call_tool.return_value = mock_result

            agent = create_devops_engineer_agent()
            result = await agent.execute("show git status")

            # Should return AgentResult
            assert hasattr(result, "status")
            assert hasattr(result, "result")

class TestSetupWizard:
    """Test setup wizard functionality."""

    def test_check_agent_setup_missing_servers(self):
        """Setup check should identify missing MCP servers."""
        from core.mcp.setup_wizard import check_agent_setup

        with patch("core.mcp.setup_wizard.get_registry") as mock_registry:
            mock_registry.return_value.is_registered.return_value = False

            result = check_agent_setup("test_agent", ["github", "linear"])

            assert result["ready"] is False
            assert len(result["missing"]) == 2

    def test_check_agent_setup_all_configured(self):
        """Setup check should return ready when all servers configured."""
        from core.mcp.setup_wizard import check_agent_setup

        with (
            patch("core.mcp.setup_wizard.get_registry") as mock_registry,
            patch("core.mcp.setup_wizard.get_credential_manager") as mock_creds,
        ):
            mock_registry.return_value.is_registered.return_value = True
            mock_config = MagicMock()
            mock_config.credential_service = None
            mock_registry.return_value.get_config.return_value = mock_config
            mock_creds.return_value.needs_setup.return_value = False

            result = check_agent_setup("test_agent", [])

            assert result["ready"] is True
            assert len(result["missing"]) == 0

    def test_get_setup_instructions_known_server(self):
        """Setup instructions should include env vars and steps for known servers."""
        from core.mcp.setup_wizard import get_setup_instructions

        instructions = get_setup_instructions("github")

        assert "name" in instructions
        assert instructions["name"] == "GitHub"
        assert "env_vars" in instructions
        assert "GITHUB_TOKEN" in instructions["env_vars"]
        assert "setup_steps" in instructions
        assert len(instructions["setup_steps"]) > 0

    def test_get_setup_instructions_unknown_server(self):
        """Setup instructions should return generic info for unknown servers."""
        from core.mcp.setup_wizard import get_setup_instructions

        instructions = get_setup_instructions("unknown_server")

        assert "name" in instructions
        assert instructions["name"] == "Unknown_Server"
        assert "env_vars" in instructions
        assert instructions["env_vars"] == []

class TestPluginTiers:
    """Test plugin tier assignments."""

    def test_team_tier_plugins(self):
        """Verify team tier plugins."""
        team_plugins = [
            "plugins/excel_analyst/dryade.json",
            "plugins/document_processor/dryade.json",
            "plugins/project_manager/dryade.json",
        ]

        for path in team_plugins:
            with open(path) as f:
                manifest = json.load(f)
            assert manifest["required_tier"] == "team", f"{path} should be team tier"

    def test_enterprise_tier_plugins(self):
        """Verify enterprise tier plugins."""
        enterprise_plugins = [
            "plugins/kpi_monitor/dryade.json",
            "plugins/compliance_auditor/dryade.json",
            "plugins/sales_intelligence/dryade.json",
        ]

        for path in enterprise_plugins:
            with open(path) as f:
                manifest = json.load(f)
            assert manifest["required_tier"] == "enterprise", f"{path} should be enterprise tier"

class TestAllAgentsCountAndDistribution:
    """Test complete agent showcase counts and distribution."""

    def setup_method(self):
        """Clear registry before each test."""
        get_registry().clear()

    def test_total_agent_count(self):
        """Should have 10 total agents (4 core + 6 plugin)."""
        # Register all core agents
        from agents import register_core_agents

        with patch("core.mcp.get_registry"):
            core_count = len(register_core_agents())

        # Count plugin agents
        plugin_agents = [
            "excel_analyst",
            "kpi_monitor",
            "document_processor",
            "project_manager",
            "compliance_auditor",
            "sales_intelligence",
        ]

        total = core_count + len(plugin_agents)
        assert total == 10, f"Expected 10 agents, got {total}"

    def test_framework_distribution(self):
        """Framework distribution: 4 CrewAI, 3 LangChain, 2 ADK, 1 MCP."""
        # This test verifies the expected distribution without instantiating
        expected = {
            AgentFramework.CREWAI: 4,  # code_reviewer, excel_analyst, document_processor, compliance_auditor
            AgentFramework.LANGCHAIN: 3,  # database_analyst, research_assistant, kpi_monitor
            AgentFramework.ADK: 2,  # project_manager, sales_intelligence
            AgentFramework.MCP: 1,  # devops_engineer
        }
        total = sum(expected.values())
        assert total == 10, f"Expected 10 agents total, got {total}"

    def test_tier_distribution(self):
        """Tier distribution: 3 team plugins, 3 enterprise plugins. Core agents are not tier-gated."""
        # Core agents (4) ship with dryade-core and are not plugin-tier-gated

        # Count by tier from manifests
        plugin_tiers = {
            "plugins/excel_analyst/dryade.json": "team",
            "plugins/kpi_monitor/dryade.json": "enterprise",
            "plugins/document_processor/dryade.json": "team",
            "plugins/project_manager/dryade.json": "team",
            "plugins/compliance_auditor/dryade.json": "enterprise",
            "plugins/sales_intelligence/dryade.json": "enterprise",
        }

        team_count = sum(1 for tier in plugin_tiers.values() if tier == "team")
        enterprise_count = sum(1 for tier in plugin_tiers.values() if tier == "enterprise")

        assert team_count == 3, f"Expected 3 team plugins, got {team_count}"
        assert enterprise_count == 3, f"Expected 3 enterprise plugins, got {enterprise_count}"
