"""Unit tests for RAGAgent.

Tests cover:
1. Agent card structure
2. Execute with results
3. Execute with no results (fallback)
4. Qdrant connection error handling
5. top_k override from context
"""

from unittest.mock import MagicMock, patch

import pytest

from core.adapters.protocol import AgentFramework
from core.agents.rag_agent import RAGAgent

class TestRAGAgentCard:
    """Tests for RAGAgent.get_card()."""

    def test_rag_agent_card(self):
        """Verify get_card() returns proper structure."""
        agent = RAGAgent()
        card = agent.get_card()

        assert card.name == "rag_assistant"
        assert card.version == "1.0"
        assert card.framework == AgentFramework.CUSTOM
        assert "semantic" in card.description.lower()
        assert len(card.capabilities) == 1
        assert card.capabilities[0].name == "semantic_search"
        assert "query" in card.capabilities[0].input_schema["properties"]

    def test_rag_agent_card_metadata(self):
        """Verify card metadata contains defaults."""
        agent = RAGAgent(collection_name="test_col", top_k=10, score_threshold=0.8)
        card = agent.get_card()

        assert card.metadata["default_collection"] == "test_col"
        assert card.metadata["default_top_k"] == 10
        assert card.metadata["score_threshold"] == 0.8

class TestRAGAgentExecute:
    """Tests for RAGAgent.execute()."""

    @pytest.mark.asyncio
    async def test_rag_agent_execute_with_results(self):
        """Mock storage.search to return results, verify formatting."""
        agent = RAGAgent()

        # Mock search results
        mock_results = [
            {"content": "Document 1 content", "score": 0.95, "metadata": {"source_id": "doc1"}},
            {"content": "Document 2 content", "score": 0.85, "metadata": {"source_id": "doc2"}},
        ]

        # Create mock storage
        mock_storage = MagicMock()
        mock_storage.search.return_value = mock_results

        # Patch the storage getter
        with patch.object(agent, "_get_storage", return_value=mock_storage):
            result = await agent.execute("test query")

        assert result.status == "ok"
        assert result.result is not None
        assert result.result["retrieved_count"] == 2
        assert len(result.result["documents"]) == 2
        assert result.result["documents"][0]["content"] == "Document 1 content"
        assert result.result["documents"][0]["score"] == 0.95
        mock_storage.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_rag_agent_execute_no_results(self):
        """Mock empty results, verify fallback message."""
        agent = RAGAgent()

        # Mock empty search results
        mock_storage = MagicMock()
        mock_storage.search.return_value = []

        with patch.object(agent, "_get_storage", return_value=mock_storage):
            result = await agent.execute("no match query")

        assert result.status == "ok"
        assert result.result is not None
        assert result.result["fallback"] is True
        assert "No matches" in result.result["message"]
        assert result.metadata["retrieved_count"] == 0

    @pytest.mark.asyncio
    async def test_rag_agent_qdrant_error(self):
        """Mock Qdrant connection error, verify error status."""
        agent = RAGAgent()

        # Mock storage getter to raise RuntimeError
        with patch.object(
            agent,
            "_get_storage",
            side_effect=RuntimeError("Qdrant connection failed"),
        ):
            result = await agent.execute("test query")

        assert result.status == "error"
        assert result.result is None
        assert "unavailable" in result.error.lower() or "failed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_rag_agent_top_k_override(self):
        """Verify context['top_k'] overrides default."""
        agent = RAGAgent(top_k=5)

        mock_results = [
            {"content": "Doc 1", "score": 0.9, "metadata": {}},
            {"content": "Doc 2", "score": 0.8, "metadata": {}},
            {"content": "Doc 3", "score": 0.7, "metadata": {}},
        ]

        mock_storage = MagicMock()
        mock_storage.search.return_value = mock_results

        with patch.object(agent, "_get_storage", return_value=mock_storage):
            result = await agent.execute("test query", {"top_k": 3})

        # Verify top_k=3 was passed to search
        call_args = mock_storage.search.call_args
        assert call_args.kwargs["limit"] == 3
        assert result.metadata["top_k"] == 3

    @pytest.mark.asyncio
    async def test_rag_agent_collection_override(self):
        """Verify context['collection'] overrides default."""
        agent = RAGAgent(collection_name="default_collection")

        mock_storage = MagicMock()
        mock_storage.search.return_value = []

        # Patch the imports at the location where they're used (inside the execute method)
        with (
            patch("core.knowledge.embedder.get_crew_embedder") as mock_embedder,
            patch("core.config.get_settings") as mock_settings,
            patch("core.knowledge.storage.CrewKnowledgeStorage") as mock_storage_class,
        ):
            # Setup mocks
            mock_settings.return_value = MagicMock(qdrant_url="http://localhost:6333")
            mock_storage_class.return_value = mock_storage

            result = await agent.execute("test query", {"collection": "custom_collection"})

        # Verify custom collection was used
        assert result.metadata["collection"] == "custom_collection"

class TestRAGAgentTools:
    """Tests for RAGAgent.get_tools()."""

    def test_get_tools_returns_semantic_search(self):
        """Verify get_tools returns semantic_search function definition."""
        agent = RAGAgent()
        tools = agent.get_tools()

        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "semantic_search"
        assert "query" in tools[0]["function"]["parameters"]["properties"]
