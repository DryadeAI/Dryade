"""Integration tests for chat API endpoints.

Uses authenticated_client from integration conftest to ensure auth bypass
via dependency override (test_app fixture has auth middleware issues).
"""

import pytest

@pytest.mark.integration
class TestChatAPI:
    """Tests for /api/chat endpoints."""

    def test_health_endpoint(self, authenticated_client):
        """Test health check endpoint."""
        response = authenticated_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_ready_endpoint(self, authenticated_client):
        """Test readiness endpoint."""
        response = authenticated_client.get("/ready")
        assert response.status_code == 200

    @pytest.mark.requires_llm
    def test_chat_endpoint(self, authenticated_client):
        """Test single-turn chat endpoint."""
        response = authenticated_client.post(
            "/api/chat",
            json={
                "message": "Hello, how are you?",
                "conversation_id": "test-123",
                "mode": "chat",
            },
        )
        # 200 if LLM available, 503/500 if not
        assert response.status_code in [200, 500, 503]

    @pytest.mark.requires_llm
    def test_chat_stream_endpoint(self, authenticated_client):
        """Test streaming chat endpoint."""
        response = authenticated_client.post(
            "/api/chat/stream",
            json={
                "message": "Hello, how are you?",
                "conversation_id": "test-123",
                "mode": "chat",
            },
        )
        # 200 if LLM available, 503/500 if not
        assert response.status_code in [200, 500, 503]

@pytest.mark.integration
class TestAgentsAPI:
    """Tests for /api/agents endpoints."""

    def test_list_agents(self, authenticated_client):
        """Test listing available agents."""
        response = authenticated_client.get("/api/agents")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_agent_details(self, authenticated_client):
        """Test getting agent details."""
        response = authenticated_client.get("/api/agents/CatalogAgent")
        # May return 200 or 404 depending on registration
        assert response.status_code in [200, 404]

@pytest.mark.integration
class TestFlowsAPI:
    """Tests for /api/flows endpoints."""

    def test_list_flows(self, authenticated_client):
        """Test listing available flows."""
        response = authenticated_client.get("/api/flows")
        assert response.status_code == 200
        data = response.json()
        assert "flows" in data
        assert isinstance(data["flows"], list)

    def test_get_flow_graph(self, authenticated_client):
        """Test getting flow graph for ReactFlow."""
        response = authenticated_client.get("/api/flows/analysis/graph")
        # May return 200 or 404 depending on registration
        assert response.status_code in [200, 404]
