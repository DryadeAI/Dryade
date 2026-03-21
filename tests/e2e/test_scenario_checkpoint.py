"""E2E tests for scenario checkpoint endpoints."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.e2e

class TestScenarioCheckpoint:
    """Tests for checkpoint list and resume endpoints."""

    def test_list_checkpoints_empty(self, e2e_client):
        """List checkpoints for nonexistent execution returns empty list."""
        fake_exec_id = str(uuid.uuid4())
        resp = e2e_client.get(f"/api/workflow-scenarios/executions/{fake_exec_id}/checkpoints")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_checkpoints_with_data(self, e2e_client):
        """List checkpoints returns checkpoint info when executor has data."""
        exec_id = str(uuid.uuid4())
        fake_checkpoints = [
            {
                "node_id": "deploy_canary",
                "timestamp": "2025-01-01T00:00:00",
                "state": {"env": "staging", "version": "v1"},
            },
            {
                "node_id": "verify_health",
                "timestamp": "2025-01-01T00:01:00",
                "state": {"health": "ok"},
            },
        ]

        with patch("core.api.routes.workflow_scenarios._get_executor") as mock_get_exec:
            mock_exec = MagicMock()
            mock_exec.get_checkpoints.return_value = fake_checkpoints
            mock_get_exec.return_value = mock_exec

            resp = e2e_client.get(f"/api/workflow-scenarios/executions/{exec_id}/checkpoints")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 2
            assert data[0]["node_id"] == "deploy_canary"
            assert "state_keys" in data[0]

    def test_resume_invalid_checkpoint_404(self, e2e_client):
        """Resume with nonexistent checkpoint returns 404."""
        exec_id = str(uuid.uuid4())

        with patch("core.api.routes.workflow_scenarios._get_executor") as mock_get_exec:
            mock_exec = MagicMock()
            mock_exec.get_checkpoints.return_value = []
            mock_get_exec.return_value = mock_exec

            resp = e2e_client.post(
                "/api/workflow-scenarios/devops_deployment/resume",
                json={
                    "execution_id": exec_id,
                    "checkpoint_node": "nonexistent_node",
                },
            )
            assert resp.status_code == 404

    def test_resume_nonexistent_scenario_404(self, e2e_client):
        """Resume on nonexistent scenario returns 404."""
        resp = e2e_client.post(
            "/api/workflow-scenarios/totally_fake_scenario/resume",
            json={
                "execution_id": str(uuid.uuid4()),
                "checkpoint_node": "some_node",
            },
        )
        assert resp.status_code == 404
