"""
Integration tests for model configuration API routes.

Tests the /api/models/* endpoints for configuration and API key management.
"""

import pytest

@pytest.mark.integration
class TestModelConfig:
    """Tests for /api/models/config endpoints."""

    def test_get_config_succeeds(self, authenticated_client):
        """Test getting config returns a valid response."""
        response = authenticated_client.get("/api/models/config")

        assert response.status_code == 200
        data = response.json()
        # Response should have expected keys (values may or may not be set)
        assert "llm_provider" in data
        assert "llm_model" in data
        assert "embedding_provider" in data

    def test_update_config(self, authenticated_client):
        """Test updating model configuration."""
        response = authenticated_client.patch(
            "/api/models/config",
            json={
                "llm_provider": "openai",
                "llm_model": "gpt-4o",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["llm_provider"] == "openai"
        assert data["llm_model"] == "gpt-4o"

    def test_update_config_partial(self, authenticated_client):
        """Test partial update of model configuration."""
        # First set some values
        authenticated_client.patch(
            "/api/models/config",
            json={
                "llm_provider": "anthropic",
                "llm_model": "claude-3-sonnet",
            },
        )

        # Then update only one field
        response = authenticated_client.patch(
            "/api/models/config",
            json={"llm_model": "claude-3-opus"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["llm_provider"] == "anthropic"  # Unchanged
        assert data["llm_model"] == "claude-3-opus"  # Updated

    def test_list_providers(self, authenticated_client):
        """Test listing supported providers."""
        response = authenticated_client.get("/api/models/providers")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        # Check expected providers exist
        provider_ids = [p["id"] for p in data]
        assert "openai" in provider_ids
        assert "anthropic" in provider_ids
        assert "ollama" in provider_ids

        # Check provider structure
        openai = next(p for p in data if p["id"] == "openai")
        assert openai["name"] == "OpenAI"
        assert openai["requires_api_key"] is True
        assert "models" in openai

    def test_get_config_unauthenticated(self, integration_test_app):
        """Test getting config without auth fails."""
        from fastapi.testclient import TestClient

        # Clear any existing overrides
        integration_test_app.dependency_overrides.clear()

        with TestClient(integration_test_app, raise_server_exceptions=False) as client:
            response = client.get("/api/models/config")
            assert response.status_code == 401

@pytest.mark.integration
class TestApiKeys:
    """Tests for /api/models/keys endpoints."""

    def test_store_key(self, authenticated_client):
        """Test storing an API key."""
        response = authenticated_client.post(
            "/api/models/keys",
            json={
                "provider": "openai",
                "api_key": "sk-test1234567890abcdefghij",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "openai"
        assert data["key_prefix"] == "sk-t..."
        assert data["is_global"] is True
        assert "key_encrypted" not in data  # Should not expose encrypted key

    def test_store_key_unknown_provider(self, authenticated_client):
        """Test storing key for unknown provider fails."""
        response = authenticated_client.post(
            "/api/models/keys",
            json={
                "provider": "unknown_provider",
                "api_key": "test-key-12345678",
            },
        )

        assert response.status_code == 400
        assert "Unknown provider" in response.json()["detail"]

    def test_list_keys(self, authenticated_client):
        """Test listing stored keys."""
        # First store a key
        authenticated_client.post(
            "/api/models/keys",
            json={
                "provider": "anthropic",
                "api_key": "sk-ant-test1234567890",
            },
        )

        response = authenticated_client.get("/api/models/keys")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have at least the key we just stored
        providers = [k["provider"] for k in data]
        assert "anthropic" in providers

    def test_delete_key(self, authenticated_client):
        """Test deleting a stored key."""
        # First store a key
        authenticated_client.post(
            "/api/models/keys",
            json={
                "provider": "groq",
                "api_key": "gsk_test1234567890abcd",
            },
        )

        # Then delete it
        response = authenticated_client.delete("/api/models/keys/groq")

        assert response.status_code == 200
        assert response.json()["status"] == "deleted"

    def test_delete_key_not_found(self, authenticated_client):
        """Test deleting nonexistent key fails."""
        response = authenticated_client.delete("/api/models/keys/nonexistent")

        assert response.status_code == 404

    def test_test_key_format_validation(self, authenticated_client):
        """Test API key connectivity test endpoint with mocked connector."""
        from unittest.mock import AsyncMock, patch

        # Mock the connector to avoid real API calls
        mock_result = AsyncMock()
        mock_result.success = True
        mock_result.message = "Connection successful"
        mock_result.models = ["gpt-4o"]

        mock_connector = AsyncMock()
        mock_connector.test_connection = AsyncMock(return_value=mock_result)

        with patch(
            "core.providers.connectors.get_connector",
            return_value=mock_connector,
        ):
            response = authenticated_client.post(
                "/api/models/test",
                json={
                    "provider": "openai",
                    "api_key": "sk-valid-key-format-test123",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "openai"
        assert data["valid"] is True

    def test_test_key_invalid_format(self, authenticated_client):
        """Test invalid API key format detection."""
        response = authenticated_client.post(
            "/api/models/test",
            json={
                "provider": "openai",
                "api_key": "invalid-no-sk-prefix",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False

    def test_test_key_local_provider(self, authenticated_client):
        """Test that local providers don't require API keys."""
        response = authenticated_client.post(
            "/api/models/test",
            json={"provider": "ollama"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert "does not require" in data["message"]

    def test_store_model_specific_key(self, authenticated_client):
        """Test storing a model-specific API key."""
        response = authenticated_client.post(
            "/api/models/keys",
            json={
                "provider": "openai",
                "api_key": "sk-model-specific-key1234",
                "model_override": "gpt-4o",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "openai"
        assert data["is_global"] is False
        assert data["model_override"] == "gpt-4o"
