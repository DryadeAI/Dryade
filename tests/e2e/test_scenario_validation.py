"""E2E tests for workflow scenario input validation."""

import pytest

pytestmark = pytest.mark.e2e

SCENARIO = "devops_deployment"

class TestScenarioValidation:
    """Tests for the POST /{scenario}/validate endpoint."""

    def test_valid_inputs(self, e2e_client):
        """Valid inputs return valid=true with no errors."""
        resp = e2e_client.post(
            f"/api/workflow-scenarios/{SCENARIO}/validate",
            json={"environment": "staging", "version": "v1.0.0"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert len(data["errors"]) == 0

    def test_missing_required_input(self, e2e_client):
        """Missing required input returns valid=false with error message."""
        resp = e2e_client.post(
            f"/api/workflow-scenarios/{SCENARIO}/validate",
            json={"environment": "staging"},  # missing 'version'
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert any("version" in e for e in data["errors"])

    def test_wrong_type_input(self, e2e_client):
        """Non-numeric value for number field returns error."""
        resp = e2e_client.post(
            f"/api/workflow-scenarios/{SCENARIO}/validate",
            json={
                "environment": "staging",
                "version": "v1.0.0",
                "canary_percentage": "not-a-number",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert any("canary_percentage" in e for e in data["errors"])

    def test_unknown_input_warning(self, e2e_client):
        """Unknown input keys produce warnings, not errors."""
        resp = e2e_client.post(
            f"/api/workflow-scenarios/{SCENARIO}/validate",
            json={
                "environment": "staging",
                "version": "v1.0.0",
                "unknown_field": "value",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True  # unknown inputs are warnings, not errors
        assert any("unknown_field" in w for w in data["warnings"])

    def test_all_defaults_valid(self, e2e_client):
        """Providing only required fields (letting defaults fill rest) is valid."""
        resp = e2e_client.post(
            f"/api/workflow-scenarios/{SCENARIO}/validate",
            json={"environment": "production", "version": "abc123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True

    def test_nonexistent_scenario_returns_404(self, e2e_client):
        """Validating against nonexistent scenario returns 404."""
        resp = e2e_client.post(
            "/api/workflow-scenarios/nonexistent_scenario/validate",
            json={"foo": "bar"},
        )
        assert resp.status_code == 404
