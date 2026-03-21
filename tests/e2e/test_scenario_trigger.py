"""E2E tests for workflow scenario trigger (SSE streaming)."""

import json
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.e2e

SCENARIO = "devops_deployment"

def _parse_sse_events(response_text: str) -> list[dict]:
    """Parse SSE event stream into list of data payloads."""
    events = []
    for line in response_text.splitlines():
        line = line.strip()
        if line.startswith("data: "):
            raw = line[len("data: ") :]
            if raw == "[DONE]":
                continue
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return events

class TestScenarioTrigger:
    """Tests for POST /{scenario}/trigger with mocked executor."""

    def test_trigger_returns_sse_stream(self, e2e_client):
        """Triggering a valid scenario returns a text/event-stream response."""

        # Mock the trigger handler to yield a few SSE events
        async def _fake_trigger(name, inputs, source, **kw):
            yield f"data: {json.dumps({'type': 'workflow_start', 'scenario': name})}\n\n"
            yield f"data: {json.dumps({'type': 'workflow_complete', 'scenario': name})}\n\n"

        with patch("core.api.routes.workflow_scenarios._get_trigger_handler") as mock_handler:
            handler = MagicMock()
            handler.trigger = _fake_trigger
            mock_handler.return_value = handler

            resp = e2e_client.post(
                f"/api/workflow-scenarios/{SCENARIO}/trigger",
                json={"environment": "staging", "version": "v1.0.0"},
            )
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_trigger_events_contain_workflow_start(self, e2e_client):
        """SSE stream contains workflow_start and workflow_complete events."""

        async def _fake_trigger(name, inputs, source, **kw):
            yield f"data: {json.dumps({'type': 'workflow_start', 'scenario': name})}\n\n"
            yield f"data: {json.dumps({'type': 'node_start', 'node_id': 'check_env'})}\n\n"
            yield f"data: {json.dumps({'type': 'node_complete', 'node_id': 'check_env', 'output': 'ok'})}\n\n"
            yield f"data: {json.dumps({'type': 'workflow_complete', 'scenario': name})}\n\n"

        with patch("core.api.routes.workflow_scenarios._get_trigger_handler") as mock_handler:
            handler = MagicMock()
            handler.trigger = _fake_trigger
            mock_handler.return_value = handler

            resp = e2e_client.post(
                f"/api/workflow-scenarios/{SCENARIO}/trigger",
                json={"environment": "staging", "version": "v1.0.0"},
            )
            events = _parse_sse_events(resp.text)
            types = [e["type"] for e in events]
            assert "workflow_start" in types
            assert "workflow_complete" in types

    def test_trigger_nonexistent_scenario_404(self, e2e_client):
        """Triggering nonexistent scenario returns 404."""
        resp = e2e_client.post(
            "/api/workflow-scenarios/nonexistent_scenario_xyz/trigger",
            json={},
        )
        assert resp.status_code == 404

    def test_trigger_events_include_inputs(self, e2e_client):
        """Trigger passes inputs through to the SSE event data."""
        inputs_sent = {"environment": "production", "version": "v2.0"}

        async def _fake_trigger(name, inputs, source, **kw):
            yield f"data: {json.dumps({'type': 'workflow_start', 'scenario': name, 'inputs': inputs})}\n\n"
            yield f"data: {json.dumps({'type': 'workflow_complete'})}\n\n"

        with patch("core.api.routes.workflow_scenarios._get_trigger_handler") as mock_handler:
            handler = MagicMock()
            handler.trigger = _fake_trigger
            mock_handler.return_value = handler

            resp = e2e_client.post(
                f"/api/workflow-scenarios/{SCENARIO}/trigger",
                json=inputs_sent,
            )
            events = _parse_sse_events(resp.text)
            start_event = next(e for e in events if e["type"] == "workflow_start")
            assert start_event["inputs"]["environment"] == "production"
