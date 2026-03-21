"""Regression tests for WebSocket bug fixes.

These tests verify fixes for bugs discovered in Phase 53.
Each test should fail before the fix and pass after.

Tests cover:
- BUG-003: WebSocket null returns in error paths (verification that None is handled)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.api.routes.websocket import (
    WebSocketAuthError,
    WebSocketSession,
    authenticate_websocket,
)

class TestWebSocketAuthentication:
    """Tests for WebSocket authentication handling."""

    @pytest.mark.asyncio
    async def test_authenticate_websocket_returns_none_when_disabled(self):
        """Verify None return when auth is disabled is handled properly."""
        mock_websocket = MagicMock()

        with patch("core.api.routes.websocket.get_settings") as mock_settings:
            # Mock auth disabled
            mock_settings.return_value.auth_enabled = False
            mock_settings.return_value.jwt_secret = None

            user_id = await authenticate_websocket(mock_websocket)

            # Should return None when auth disabled
            assert user_id is None
            # Should not try to decode JWT
            mock_websocket.query_params.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_authenticate_websocket_missing_token_returns_pending(self):
        """Verify missing token returns 'pending' for first-message auth fallback.

        When no token is found in query params or Authorization header,
        authenticate_websocket returns 'pending' so the WebSocket handler
        can attempt first-message authentication after accepting the connection.
        This allows clients that send auth in the first message to connect.
        """
        mock_websocket = MagicMock()
        mock_websocket.accept = AsyncMock()
        mock_websocket.close = AsyncMock()
        mock_websocket.query_params.get.return_value = None
        mock_websocket.headers.get.return_value = ""

        with patch("core.api.routes.websocket.get_settings") as mock_settings:
            # Mock auth enabled but no token
            mock_settings.return_value.auth_enabled = True
            mock_settings.return_value.jwt_secret = "test-secret"

            result = await authenticate_websocket(mock_websocket)

            # Should return "pending" (not raise) when no token found
            # The caller should try first-message auth after accepting connection
            assert result == "pending"
            # Should NOT close the connection -- let the caller handle it
            mock_websocket.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_authenticate_websocket_expired_token_raises(self):
        """Verify expired token raises WebSocketAuthError."""
        mock_websocket = MagicMock()
        mock_websocket.accept = AsyncMock()
        mock_websocket.close = AsyncMock()
        mock_websocket.query_params.get.return_value = "expired-token"

        with patch("core.api.routes.websocket.get_settings") as mock_settings:
            mock_settings.return_value.auth_enabled = True
            mock_settings.return_value.jwt_secret = "test-secret"
            mock_settings.return_value.jwt_algorithm = "HS256"

            with patch("core.api.routes.websocket.jwt.decode") as mock_decode:
                import jwt

                mock_decode.side_effect = jwt.ExpiredSignatureError("Token expired")

                with pytest.raises(WebSocketAuthError, match="Token expired"):
                    await authenticate_websocket(mock_websocket)

                # Should accept before closing
                mock_websocket.accept.assert_called_once()
                # Should close with expired token code
                mock_websocket.close.assert_called_once()
                close_call_kwargs = mock_websocket.close.call_args[1]
                assert close_call_kwargs["code"] == 4003

    @pytest.mark.asyncio
    async def test_authenticate_websocket_invalid_token_raises(self):
        """Verify invalid token raises WebSocketAuthError."""
        mock_websocket = MagicMock()
        mock_websocket.accept = AsyncMock()
        mock_websocket.close = AsyncMock()
        mock_websocket.query_params.get.return_value = "invalid-token"

        with patch("core.api.routes.websocket.get_settings") as mock_settings:
            mock_settings.return_value.auth_enabled = True
            mock_settings.return_value.jwt_secret = "test-secret"
            mock_settings.return_value.jwt_algorithm = "HS256"

            with patch("core.api.routes.websocket.jwt.decode") as mock_decode:
                import jwt

                mock_decode.side_effect = jwt.InvalidTokenError("Invalid signature")

                with pytest.raises(WebSocketAuthError, match="Token validation failed"):
                    await authenticate_websocket(mock_websocket)

class TestWebSocketSession:
    """Tests for WebSocketSession handling None user_id."""

    def test_websocket_session_allows_none_user_id(self):
        """Verify WebSocketSession accepts None user_id (auth disabled case)."""
        session = WebSocketSession(
            client_id="test-client",
            user_id=None,
        )

        # Should allow None user_id
        assert session.user_id is None
        assert session.client_id == "test-client"

    def test_websocket_session_with_valid_user_id(self):
        """Verify WebSocketSession accepts valid user_id (auth enabled case)."""
        session = WebSocketSession(
            client_id="test-client",
            user_id="user-123",
        )

        # Should store user_id
        assert session.user_id == "user-123"
        assert session.client_id == "test-client"
