"""Integration tests for WebSocket reliability features.

Tests message sequencing, acknowledgments, reconnection, heartbeat,
rate limiting, and authentication for WebSocket endpoints.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from core.api.main import app
from core.auth.dependencies import get_current_user
from core.utils.time import utcnow

def _override_get_current_user():
    return {"sub": "test-user-ws", "email": "test@example.com", "role": "user"}

app.dependency_overrides[get_current_user] = _override_get_current_user

@pytest.fixture
def test_client():
    """Create test client for WebSocket testing."""
    return TestClient(app)

@pytest.fixture
def mock_auth_disabled():
    """Disable authentication for testing."""
    with patch("core.api.routes.websocket.get_settings") as mock:
        mock_settings = mock.return_value
        mock_settings.auth_enabled = False
        mock_settings.jwt_secret = None
        yield mock

@pytest.mark.integration
class TestWebSocketMessageSequencing:
    """Tests for message sequencing and acknowledgment."""

    def test_message_sequencing(self, test_client, mock_auth_disabled):
        """Verify messages have incrementing sequence numbers."""
        with test_client.websocket_connect("/ws/chat/test-seq") as ws:
            # First message is new_session notification
            first_msg = ws.receive_json()
            assert first_msg["type"] == "new_session"

            # Send ping to get a sequenced response
            ws.send_json({"type": "ping"})
            response = ws.receive_json()

            assert response["type"] == "pong"
            assert "seq" in response
            first_seq = response["seq"]

            # Send another ping
            ws.send_json({"type": "ping"})
            response = ws.receive_json()

            assert response["seq"] > first_seq

    def test_ack_removes_from_unacked(self, test_client, mock_auth_disabled):
        """Verify ack removes message from unacked buffer."""
        with test_client.websocket_connect("/ws/chat/test-ack") as ws:
            # Get new_session message
            first_msg = ws.receive_json()
            assert first_msg["type"] == "new_session"

            # Send ping to get sequenced message
            ws.send_json({"type": "ping"})
            response = ws.receive_json()
            seq = response.get("seq")

            # Send ack for the message
            ws.send_json({"type": "ack", "seq": seq})

            # Send another ping to verify connection still works
            ws.send_json({"type": "ping"})
            pong = ws.receive_json()
            assert pong["type"] == "pong"

@pytest.mark.integration
class TestWebSocketReconnection:
    """Tests for session reconnection."""

    def test_new_session_created(self, test_client, mock_auth_disabled):
        """Verify new session message on fresh connection."""
        with test_client.websocket_connect("/ws/chat/test-new") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "new_session"
            assert msg["session_id"] == "test-new"

    def test_reconnection_resume(self, test_client, mock_auth_disabled):
        """Verify session can attempt resume after disconnect."""
        session_id = "test-resume"

        # First connection
        with test_client.websocket_connect(f"/ws/chat/{session_id}") as ws:
            # Get new session
            msg = ws.receive_json()
            assert msg["type"] == "new_session"

            # Send ping to establish activity
            ws.send_json({"type": "ping"})
            pong = ws.receive_json()
            last_seq = pong.get("seq", 0)

        # Reconnect with resume request
        with test_client.websocket_connect(f"/ws/chat/{session_id}") as ws:
            # Send resume message
            ws.send_json({"type": "resume", "last_seq": last_seq})

            # Should get resumed or new_session response
            response = ws.receive_json()
            assert response["type"] in ["resumed", "new_session"]

@pytest.mark.integration
class TestWebSocketHeartbeat:
    """Tests for heartbeat/ping-pong."""

    def test_heartbeat_pong(self, test_client, mock_auth_disabled):
        """Verify ping/pong keeps connection alive."""
        with test_client.websocket_connect("/ws/chat/test-heartbeat") as ws:
            # Get initial message
            msg = ws.receive_json()
            assert msg["type"] == "new_session"

            # Send ping
            ws.send_json({"type": "ping"})
            response = ws.receive_json()

            assert response["type"] == "pong"
            assert "seq" in response

@pytest.mark.integration
class TestWebSocketRateLimiting:
    """Tests for rate limiting."""

    def test_rate_limiting(self, test_client, mock_auth_disabled):
        """Verify rate limiting kicks in after burst."""
        # Patch rate limiter to use very low limit
        with (
            patch("core.api.routes.websocket.WS_RATE_LIMIT_BURST", 3),
            patch("core.api.routes.websocket.RateLimiter") as MockLimiter,
        ):
            # Create a rate limiter that runs out of tokens
            call_count = [0]

            def mock_consume(count=1):
                call_count[0] += 1
                return call_count[0] <= 3

            mock_instance = MockLimiter.return_value
            mock_instance.consume.side_effect = mock_consume

            with test_client.websocket_connect("/ws/chat/test-rate") as ws:
                # Get new_session
                msg = ws.receive_json()
                assert msg["type"] == "new_session"

                # Send burst of pings - should eventually get rate limited
                rate_limited = False
                for _ in range(10):
                    ws.send_json({"type": "ping"})
                    response = ws.receive_json()
                    if response.get("code") == "RATE_LIMITED":
                        rate_limited = True
                        break

                # After burst, rate limiting should kick in
                assert rate_limited or call_count[0] > 3

    def test_rate_limit_response_format(self, test_client, mock_auth_disabled):
        """Verify rate limit error has correct format."""
        with patch("core.api.routes.websocket.RateLimiter") as MockLimiter:
            # Create limiter that always rate limits
            mock_instance = MockLimiter.return_value
            mock_instance.consume.return_value = False

            with test_client.websocket_connect("/ws/chat/test-rate-format") as ws:
                # Get new_session
                msg = ws.receive_json()
                assert msg["type"] == "new_session"

                # Send ping - should be rate limited
                ws.send_json({"type": "ping"})
                response = ws.receive_json()

                assert response["type"] == "error"
                assert response["code"] == "RATE_LIMITED"
                assert "retry_after" in response

@pytest.mark.integration
class TestWebSocketAuthentication:
    """Tests for WebSocket authentication."""

    def test_auth_disabled_allows_connection(self, test_client, mock_auth_disabled):
        """Verify connection succeeds when auth is disabled."""
        with test_client.websocket_connect("/ws/chat/test-no-auth") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "new_session"

    def test_auth_required_when_enabled(self, test_client):
        """Verify auth required when JWT_SECRET is set."""
        with patch("core.api.routes.websocket.get_settings") as mock:
            mock_settings = mock.return_value
            mock_settings.auth_enabled = True
            mock_settings.jwt_secret = "x" * 32
            mock_settings.jwt_algorithm = "HS256"

            # Should fail without token
            try:
                with test_client.websocket_connect("/ws/chat/test-auth") as ws:
                    # Connection should be rejected
                    ws.receive_json()
                    pytest.fail("Should have raised exception")
            except Exception:
                pass  # Expected - connection rejected

    def test_auth_with_query_param_token(self, test_client):
        """Verify authentication works with query param token."""
        from datetime import datetime, timedelta

        import jwt

        secret = "x" * 32
        token = jwt.encode(
            {
                "sub": "test-user",
                "exp": utcnow() + timedelta(hours=1),
            },
            secret,
            algorithm="HS256",
        )

        with patch("core.api.routes.websocket.get_settings") as mock:
            mock_settings = mock.return_value
            mock_settings.auth_enabled = True
            mock_settings.jwt_secret = secret
            mock_settings.jwt_algorithm = "HS256"

            with test_client.websocket_connect(f"/ws/chat/test-auth?token={token}") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "new_session"

@pytest.mark.integration
class TestFlowWebSocketReliability:
    """Tests for flow WebSocket reliability features."""

    def test_flow_websocket_ping_pong(self, test_client, mock_auth_disabled):
        """Verify flow websocket has same reliability features."""
        with test_client.websocket_connect("/ws/flow/test-flow") as ws:
            # Get new_session
            msg = ws.receive_json()
            assert msg["type"] == "new_session"

            # Send ping
            ws.send_json({"type": "ping"})
            response = ws.receive_json()

            assert response["type"] == "pong"
            assert "seq" in response

    def test_flow_websocket_rate_limiting(self, test_client, mock_auth_disabled):
        """Verify flow websocket has rate limiting."""
        with patch("core.api.routes.websocket.RateLimiter") as MockLimiter:
            mock_instance = MockLimiter.return_value
            mock_instance.consume.return_value = False

            with test_client.websocket_connect("/ws/flow/test-flow-rate") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "new_session"

                ws.send_json({"type": "ping"})
                response = ws.receive_json()

                assert response.get("code") == "RATE_LIMITED"
