"""Unit tests for Compliance Auditor plugin.

Tests cover:
- Agent card and framework
- Tool creation and functionality
- Multi-agent crew structure
- Streaming support
- Graceful fallback on MCP errors
- Plugin enterprise tier validation
- Route endpoints
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

# Skip all tests if crewai not installed or API key not available
pytestmark = pytest.mark.skipif(
    os.getenv("OPENAI_API_KEY") is None,
    reason="OPENAI_API_KEY not set for CrewAI tests",
)

# =============================================================================
# Agent Tests
# =============================================================================

@pytest.mark.unit
class TestComplianceAuditorAgent:
    """Tests for ComplianceAuditorAgent class."""

    @pytest.fixture
    def mock_env(self):
        """Set up mock environment for CrewAI."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            yield

    def test_agent_card_framework(self, mock_env):
        """Test agent card reports CREWAI framework."""
        from plugins.compliance_auditor.agent import create_compliance_auditor_agent

        from core.adapters.protocol import AgentFramework

        agent = create_compliance_auditor_agent()
        card = agent.get_card()

        assert card.framework == AgentFramework.CREWAI

    def test_agent_card_name(self, mock_env):
        """Test agent card has correct name."""
        from plugins.compliance_auditor.agent import create_compliance_auditor_agent

        agent = create_compliance_auditor_agent()
        card = agent.get_card()

        assert card.name == "compliance_auditor"

    def test_agent_has_audit_tools(self, mock_env):
        """Test agent has all required compliance tools."""
        from plugins.compliance_auditor.agent import create_compliance_auditor_agent

        agent = create_compliance_auditor_agent()
        tools = agent.get_tools()

        tool_names = [t["function"]["name"] for t in tools]

        assert "read_policy" in tool_names
        assert "list_policies" in tool_names
        assert "extract_requirements" in tool_names
        assert "record_finding" in tool_names
        assert "search_findings" in tool_names
        assert "generate_report" in tool_names

    def test_agent_supports_streaming(self, mock_env):
        """Test agent supports streaming output."""
        from plugins.compliance_auditor.agent import create_compliance_auditor_agent

        agent = create_compliance_auditor_agent()

        assert agent.supports_streaming() is True

    def test_multi_agent_structure(self, mock_env):
        """Test crew has 3 specialized agents."""
        from plugins.compliance_auditor.agent import ComplianceAuditorAgent

        compliance_agent = ComplianceAuditorAgent()

        assert len(compliance_agent._agents) == 3
        assert "policy_analyst" in compliance_agent._agents
        assert "auditor" in compliance_agent._agents
        assert "report_writer" in compliance_agent._agents

# =============================================================================
# Tool Tests (Mocked MCP)
# =============================================================================

@pytest.mark.unit
class TestComplianceTools:
    """Tests for compliance MCP tool wrappers."""

    def test_read_policy_tool_calls_filesystem(self):
        """Test ReadPolicyTool calls filesystem/read_file."""
        from plugins.compliance_auditor.agent import ReadPolicyTool

        tool = ReadPolicyTool()

        with patch("plugins.compliance_auditor.agent.MCPToolWrapper") as mock_wrapper_class:
            mock_wrapper = MagicMock()
            mock_wrapper.call.return_value = "Policy content here"
            mock_wrapper_class.return_value = mock_wrapper

            result = tool._run(path="/policies/test.txt")

            mock_wrapper_class.assert_called_once_with(
                "filesystem", "read_file", "Read policy file"
            )
            mock_wrapper.call.assert_called_once_with(path="/policies/test.txt")
            assert "Policy content" in result

    def test_list_policies_tool_calls_filesystem(self):
        """Test ListPoliciesTool calls filesystem/list_directory."""
        from plugins.compliance_auditor.agent import ListPoliciesTool

        tool = ListPoliciesTool()

        with patch("plugins.compliance_auditor.agent.MCPToolWrapper") as mock_wrapper_class:
            mock_wrapper = MagicMock()
            mock_wrapper.call.return_value = "policy1.pdf\npolicy2.pdf"
            mock_wrapper_class.return_value = mock_wrapper

            result = tool._run(directory="/policies")

            mock_wrapper_class.assert_called_once_with(
                "filesystem", "list_directory", "List policy directory"
            )
            mock_wrapper.call.assert_called_once_with(path="/policies")
            assert "policy" in result

    def test_extract_requirements_tool_parses_text(self):
        """Test ExtractRequirementsTool extracts MUST/SHALL patterns."""
        from plugins.compliance_auditor.agent import ExtractRequirementsTool

        tool = ExtractRequirementsTool()

        with patch("plugins.compliance_auditor.agent.MCPToolWrapper") as mock_wrapper_class:
            mock_wrapper = MagicMock()
            mock_wrapper.call.return_value = (
                "Section 1: All users MUST use two-factor authentication. "
                "Section 2: Passwords SHALL be at least 12 characters."
            )
            mock_wrapper_class.return_value = mock_wrapper

            result = tool._run(path="/policies/security.pdf")

            # Should extract requirements
            data = json.loads(result)
            assert len(data) >= 2
            assert any("two-factor" in r["text"] for r in data)

    def test_record_finding_tool_calls_memory(self):
        """Test RecordFindingTool calls memory/create_entities."""
        from plugins.compliance_auditor.agent import RecordFindingTool

        tool = RecordFindingTool()

        with patch("plugins.compliance_auditor.agent.MCPToolWrapper") as mock_wrapper_class:
            mock_wrapper = MagicMock()
            mock_wrapper.call.return_value = "Entity created"
            mock_wrapper_class.return_value = mock_wrapper

            result = tool._run(
                requirement_id="REQ-001",
                status="compliant",
                evidence="Screenshot of 2FA config",
                notes="Verified manually",
            )

            mock_wrapper_class.assert_called_once_with(
                "memory", "create_entities", "Record finding"
            )
            assert "REQ-001" in result
            assert "compliant" in result

    def test_search_findings_tool_calls_memory(self):
        """Test SearchFindingsTool calls memory/search_nodes."""
        from plugins.compliance_auditor.agent import SearchFindingsTool

        tool = SearchFindingsTool()

        with patch("plugins.compliance_auditor.agent.MCPToolWrapper") as mock_wrapper_class:
            mock_wrapper = MagicMock()
            mock_wrapper.call.return_value = json.dumps([{"name": "finding_REQ-001"}])
            mock_wrapper_class.return_value = mock_wrapper

            result = tool._run(query="REQ-001")

            mock_wrapper_class.assert_called_once_with("memory", "search_nodes", "Search findings")
            mock_wrapper.call.assert_called_once_with(query="REQ-001")
            assert "REQ-001" in result

    def test_generate_report_tool_compiles_findings(self):
        """Test GenerateReportTool compiles findings from memory."""
        from plugins.compliance_auditor.agent import GenerateReportTool

        tool = GenerateReportTool()

        with patch("plugins.compliance_auditor.agent.MCPToolWrapper") as mock_wrapper_class:
            mock_wrapper = MagicMock()
            mock_wrapper.call.return_value = "finding_REQ-001: compliant"
            mock_wrapper_class.return_value = mock_wrapper

            result = tool._run(audit_id="audit-123")

            report = json.loads(result)
            assert report["audit_id"] == "audit-123"
            assert report["status"] == "complete"

# =============================================================================
# Plugin Tests
# =============================================================================

@pytest.mark.unit
class TestComplianceAuditorPlugin:
    """Tests for ComplianceAuditorPlugin class."""

    def test_plugin_enterprise_tier(self):
        """Test plugin manifest declares enterprise tier."""
        import json
        from pathlib import Path

        manifest_path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "plugins"
            / "compliance_auditor"
            / "dryade.json"
        )

        with open(manifest_path) as f:
            manifest = json.load(f)

        assert manifest["required_tier"] == "enterprise"

    def test_plugin_full_workspace_ui(self):
        """Test plugin has full workspace UI type."""
        import json
        from pathlib import Path

        manifest_path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "plugins"
            / "compliance_auditor"
            / "dryade.json"
        )

        with open(manifest_path) as f:
            manifest = json.load(f)

        assert manifest["ui"]["type"] == "full_workspace"

    def test_plugin_extends_enterprise_protocol(self):
        """Test plugin extends EnterprisePluginProtocol."""
        from plugins.compliance_auditor.plugin import ComplianceAuditorPlugin

        from core.ee.plugins_ee import EnterprisePluginProtocol

        assert issubclass(ComplianceAuditorPlugin, EnterprisePluginProtocol)

    def test_plugin_name_and_version(self):
        """Test plugin has correct name and version."""
        from plugins.compliance_auditor.plugin import plugin

        assert plugin.name == "compliance_auditor"
        assert plugin.version == "1.0.0"

    def test_plugin_core_version_constraint(self):
        """Test plugin has correct core version constraint."""
        from plugins.compliance_auditor.plugin import plugin

        assert plugin.core_version_constraint == ">=2.0.0,<3.0.0"

# =============================================================================
# Route Tests
# =============================================================================

@pytest.mark.unit
class TestComplianceAuditorRoutes:
    """Tests for compliance auditor API routes."""

    @pytest.fixture
    def client(self):
        """Create test client for routes."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from plugins.compliance_auditor.routes import router

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_status_endpoint(self, client):
        """Test GET /status returns 200."""
        with patch("core.mcp.registry.get_registry") as mock_registry:
            mock_reg = MagicMock()
            mock_reg.is_registered.return_value = False
            mock_registry.return_value = mock_reg

            response = client.get("/api/compliance-auditor/status")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "active"
            assert data["tier"] == "enterprise"

    def test_create_audit_endpoint(self, client):
        """Test POST /audits creates audit."""
        response = client.post(
            "/api/compliance-auditor/audits",
            json={
                "name": "Test Audit",
                "policy_paths": ["/policies/security.pdf"],
                "description": "Test compliance audit",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Audit"
        assert data["status"] == "in_progress"
        assert "id" in data

    def test_list_audits_endpoint(self, client):
        """Test GET /audits returns audits."""
        # Create an audit first
        client.post(
            "/api/compliance-auditor/audits",
            json={"name": "Audit 1", "policy_paths": []},
        )

        response = client.get("/api/compliance-auditor/audits")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["total"] >= 1

    def test_record_finding_endpoint(self, client):
        """Test POST /audits/{id}/findings records finding."""
        # Create audit first
        audit_response = client.post(
            "/api/compliance-auditor/audits",
            json={"name": "Finding Test Audit", "policy_paths": []},
        )
        audit_id = audit_response.json()["id"]

        # Record finding - mock the tool import inside the route
        with patch("plugins.compliance_auditor.agent.RecordFindingTool") as mock_tool:
            mock_instance = MagicMock()
            mock_instance._run.return_value = "Finding recorded"
            mock_tool.return_value = mock_instance

            response = client.post(
                f"/api/compliance-auditor/audits/{audit_id}/findings",
                json={
                    "requirement_id": "REQ-001",
                    "status": "compliant",
                    "evidence": "Config screenshot",
                    "notes": "Verified",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["requirement_id"] == "REQ-001"
        assert data["status"] == "compliant"

    def test_generate_report_endpoint(self, client):
        """Test GET /audits/{id}/report generates report."""
        # Create audit
        audit_response = client.post(
            "/api/compliance-auditor/audits",
            json={"name": "Report Test Audit", "policy_paths": []},
        )
        audit_id = audit_response.json()["id"]

        response = client.get(f"/api/compliance-auditor/audits/{audit_id}/report")

        assert response.status_code == 200
        data = response.json()
        assert data["audit_id"] == audit_id
        assert "compliance_score" in data
        assert "summary" in data

    def test_search_findings_endpoint(self, client):
        """Test GET /findings search works."""
        response = client.get("/api/compliance-auditor/findings?query=test")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data

# =============================================================================
# Graceful Fallback Tests
# =============================================================================

@pytest.mark.unit
class TestGracefulFallback:
    """Tests for graceful fallback on MCP errors."""

    def test_tool_returns_error_message_on_mcp_failure(self):
        """Test tool returns helpful error when MCP fails."""
        from plugins.compliance_auditor.agent import ReadPolicyTool

        tool = ReadPolicyTool()

        with patch("plugins.compliance_auditor.agent.MCPToolWrapper") as mock_wrapper_class:
            mock_wrapper = MagicMock()
            mock_wrapper.call.side_effect = Exception("MCP server not available")
            mock_wrapper_class.return_value = mock_wrapper

            result = tool._run(path="/policies/test.txt")

            assert "Error reading policy" in result
            assert "filesystem MCP server" in result

    @pytest.mark.asyncio
    async def test_agent_fallback_returns_structured_error(self):
        """Test agent fallback returns AgentResult with error details."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            from plugins.compliance_auditor.agent import ComplianceAuditorAgent

            agent = ComplianceAuditorAgent()

            # Mock the _execute_primary to raise an exception
            with patch.object(agent, "_execute_primary") as mock_execute:
                mock_execute.side_effect = Exception("MCP connection failed")

                result = await agent.execute_with_fallback("Run audit", {})

                assert result.status == "error"
                assert "MCP connection failed" in result.error
                assert result.metadata["recoverable"] is True
                assert "filesystem" in result.metadata["required_servers"]

    def test_memory_tool_fallback_on_error(self):
        """Test memory tools handle errors gracefully."""
        from plugins.compliance_auditor.agent import RecordFindingTool

        tool = RecordFindingTool()

        with patch("plugins.compliance_auditor.agent.MCPToolWrapper") as mock_wrapper_class:
            mock_wrapper = MagicMock()
            mock_wrapper.call.side_effect = Exception("Memory server offline")
            mock_wrapper_class.return_value = mock_wrapper

            result = tool._run(
                requirement_id="REQ-001",
                status="compliant",
                evidence="Test",
                notes="",
            )

            assert "Error recording finding" in result
            assert "memory MCP server" in result

# =============================================================================
# Multi-Agent Workflow Test
# =============================================================================

@pytest.mark.unit
class TestMultiAgentWorkflow:
    """Tests for multi-agent workflow patterns."""

    @pytest.fixture
    def mock_env(self):
        """Set up mock environment for CrewAI."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            yield

    def test_policy_analyst_has_correct_tools(self, mock_env):
        """Test policy analyst agent has policy tools."""
        from plugins.compliance_auditor.agent import ComplianceAuditorAgent

        agent = ComplianceAuditorAgent()
        policy_analyst = agent._agents["policy_analyst"]

        tool_names = [t.name for t in policy_analyst.tools]
        assert "read_policy" in tool_names
        assert "list_policies" in tool_names
        assert "extract_requirements" in tool_names

    def test_auditor_has_correct_tools(self, mock_env):
        """Test auditor agent has finding tools."""
        from plugins.compliance_auditor.agent import ComplianceAuditorAgent

        agent = ComplianceAuditorAgent()
        auditor = agent._agents["auditor"]

        tool_names = [t.name for t in auditor.tools]
        assert "record_finding" in tool_names
        assert "search_findings" in tool_names

    def test_report_writer_has_correct_tools(self, mock_env):
        """Test report writer agent has report tools."""
        from plugins.compliance_auditor.agent import ComplianceAuditorAgent

        agent = ComplianceAuditorAgent()
        report_writer = agent._agents["report_writer"]

        tool_names = [t.name for t in report_writer.tools]
        assert "search_findings" in tool_names
        assert "generate_report" in tool_names

    def test_agents_have_distinct_roles(self, mock_env):
        """Test each agent has a distinct role."""
        from plugins.compliance_auditor.agent import ComplianceAuditorAgent

        agent = ComplianceAuditorAgent()

        roles = [a.role for a in agent._agents.values()]
        assert len(roles) == len(set(roles))  # All unique

    def test_primary_agent_is_auditor(self, mock_env):
        """Test get_primary_agent returns the auditor."""
        from plugins.compliance_auditor.agent import ComplianceAuditorAgent

        agent = ComplianceAuditorAgent()
        primary = agent.get_primary_agent()

        assert primary.role == "Compliance Auditor"
