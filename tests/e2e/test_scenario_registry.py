"""E2E tests for workflow scenario registry endpoints."""

import pytest

pytestmark = pytest.mark.e2e

KNOWN_SCENARIOS = [
    "code_review_pipeline",
    "compliance_audit",
    "customer_onboarding",
    "devops_deployment",
    "financial_reporting",
    "invoice_processing",
    "multi_framework_demo",
    "prospect_research",
    "sprint_planning",
]

class TestScenarioRegistry:
    """Tests for listing and retrieving workflow scenarios via API."""

    def test_list_scenarios(self, e2e_client):
        """GET /api/workflow-scenarios returns all registered scenarios."""
        resp = e2e_client.get("/api/workflow-scenarios")
        assert resp.status_code == 200
        scenarios = resp.json()
        assert isinstance(scenarios, list)
        names = [s["name"] for s in scenarios]
        for name in KNOWN_SCENARIOS:
            assert name in names, f"Missing scenario: {name}"

    def test_get_scenario_detail(self, e2e_client):
        """GET /api/workflow-scenarios/{name} returns full scenario detail."""
        resp = e2e_client.get("/api/workflow-scenarios/devops_deployment")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "devops_deployment"
        assert data["display_name"]
        assert data["domain"]
        assert "inputs" in data
        assert len(data["inputs"]) > 0

    def test_get_scenario_workflow_graph(self, e2e_client):
        """GET /api/workflow-scenarios/{name}/workflow returns the flow graph."""
        resp = e2e_client.get("/api/workflow-scenarios/devops_deployment/workflow")
        assert resp.status_code == 200
        graph = resp.json()
        assert "nodes" in graph
        assert "edges" in graph
        assert isinstance(graph["nodes"], list)
        assert len(graph["nodes"]) > 0

    def test_unknown_scenario_returns_404(self, e2e_client):
        """GET /api/workflow-scenarios/nonexistent returns 404."""
        resp = e2e_client.get("/api/workflow-scenarios/totally_nonexistent_scenario")
        assert resp.status_code == 404
