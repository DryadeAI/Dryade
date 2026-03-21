"""E2E tests for the streaming pipeline (Phase 111 bug fixes).

Verifies token events flow through the WebSocket visibility filter,
complete events carry the ``content`` field, thinking events pass at
named-steps level, and empty complete events are handled gracefully.

Uses the same TestClient + mock route_request pattern as
test_websocket_protocol.py.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_conv_id() -> str:
    return f"stream-test-{uuid.uuid4().hex[:12]}"

@dataclass
class _Event:
    """Minimal event object matching what route_request yields."""

    type: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

def _collect_events(ws, *, max_messages: int = 20) -> list[dict]:
    """Receive messages from WS until the connection closes or limit hit.

    Filters out new_session and pong messages, keeps everything else.
    """
    events = []
    for _ in range(max_messages):
        try:
            msg = ws.receive_json()
        except Exception:
            break
        if msg.get("type") in ("new_session", "pong"):
            continue
        events.append(msg)
        # Stop after complete or error
        if msg.get("type") in ("complete", "error"):
            break
    return events

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ws_client(integration_test_app) -> TestClient:
    return TestClient(integration_test_app, raise_server_exceptions=False)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestStreamingPipeline:
    """E2E tests validating the streaming pipeline after Phase 111 fixes."""

    def test_token_events_reach_client(self, ws_client: TestClient):
        """Bug 1 fix: token events pass through the named-steps visibility
        filter and reach the WebSocket client.

        Before the fix, 'token' was in VISIBILITY_DENY['named-steps'],
        silently dropping all streaming answer tokens from ComplexHandler.
        """

        async def _fake_stream(message, **kwargs):
            yield _Event(type="token", content="Hello")
            yield _Event(type="token", content=" world")
            yield _Event(type="token", content="!")
            yield _Event(type="complete", content="Hello world!", metadata={"mode": "chat"})

        conv_id = _new_conv_id()
        with patch("core.api.routes.websocket.route_request", side_effect=_fake_stream):
            with ws_client.websocket_connect(f"/ws/chat/{conv_id}") as ws:
                # Consume new_session
                init = ws.receive_json()
                assert init["type"] == "new_session"

                # Send a chat message
                ws.send_json({"type": "message", "content": "test streaming"})

                # Consume message_ack
                ack = ws.receive_json()
                assert ack["type"] == "message_ack"

                # Collect streaming events
                events = _collect_events(ws)

                token_events = [e for e in events if e["type"] == "token"]
                complete_events = [e for e in events if e["type"] == "complete"]

                assert len(token_events) >= 3, (
                    f"Expected at least 3 token events, got {len(token_events)}. "
                    f"Events: {[e['type'] for e in events]}"
                )
                assert len(complete_events) == 1

    def test_complete_event_has_content_field(self, ws_client: TestClient):
        """Bug 2 fix: the complete event carries ``data.content`` (not
        ``data.response``), matching what the frontend expects after the fix.
        """

        async def _fake_stream(message, **kwargs):
            yield _Event(type="complete", content="Final answer here", metadata={"mode": "chat"})

        conv_id = _new_conv_id()
        with patch("core.api.routes.websocket.route_request", side_effect=_fake_stream):
            with ws_client.websocket_connect(f"/ws/chat/{conv_id}") as ws:
                init = ws.receive_json()
                assert init["type"] == "new_session"

                ws.send_json({"type": "message", "content": "test complete"})
                ack = ws.receive_json()
                assert ack["type"] == "message_ack"

                events = _collect_events(ws)
                complete_events = [e for e in events if e["type"] == "complete"]

                assert len(complete_events) == 1
                data = complete_events[0]["data"]
                assert data["content"] == "Final answer here", (
                    f"Expected content='Final answer here', got data={data}"
                )
                assert "response" not in data or data.get("response") is None, (
                    "Backend should not send a 'response' key in complete events"
                )

    def test_thinking_events_pass_at_named_steps(self, ws_client: TestClient):
        """Thinking events are allowed at named-steps visibility level
        and should reach the client alongside token events.
        """

        async def _fake_stream(message, **kwargs):
            yield _Event(
                type="thinking", content="Let me analyze...", metadata={"agent": "orchestrator"}
            )
            yield _Event(type="token", content="The answer is 42")
            yield _Event(type="complete", content="The answer is 42", metadata={"mode": "chat"})

        conv_id = _new_conv_id()
        with patch("core.api.routes.websocket.route_request", side_effect=_fake_stream):
            with ws_client.websocket_connect(f"/ws/chat/{conv_id}") as ws:
                init = ws.receive_json()
                assert init["type"] == "new_session"

                ws.send_json({"type": "message", "content": "test thinking"})
                ack = ws.receive_json()
                assert ack["type"] == "message_ack"

                events = _collect_events(ws)

                thinking_events = [e for e in events if e["type"] == "thinking"]
                token_events = [e for e in events if e["type"] == "token"]
                complete_events = [e for e in events if e["type"] == "complete"]

                assert len(thinking_events) >= 1, (
                    f"Expected thinking events, got types: {[e['type'] for e in events]}"
                )
                assert len(token_events) >= 1
                assert len(complete_events) == 1

    def test_empty_complete_event_handled(self, ws_client: TestClient):
        """An empty complete event should not crash the WebSocket handler."""

        async def _fake_stream(message, **kwargs):
            yield _Event(type="complete", content="", metadata={"mode": "chat"})

        conv_id = _new_conv_id()
        with patch("core.api.routes.websocket.route_request", side_effect=_fake_stream):
            with ws_client.websocket_connect(f"/ws/chat/{conv_id}") as ws:
                init = ws.receive_json()
                assert init["type"] == "new_session"

                ws.send_json({"type": "message", "content": "test empty"})
                ack = ws.receive_json()
                assert ack["type"] == "message_ack"

                events = _collect_events(ws)
                complete_events = [e for e in events if e["type"] == "complete"]

                assert len(complete_events) == 1, (
                    f"Expected 1 complete event even with empty content, got {len(complete_events)}"
                )
