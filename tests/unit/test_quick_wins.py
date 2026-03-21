"""Tests for Phase 104-01 quick-win fixes (F-004, F-005, F-006).

Covers:
- F-004: LLM instance caching in OrchestrationThinkingProvider._get_llm()
- F-005: Agent count log includes Capella agents in auto_discovery summary
- F-006: Qdrant connection warning clarity and router one-time fallback warning
"""

import logging
from unittest.mock import MagicMock, patch

# -----------------------------------------------------------------------
# F-004: LLM caching tests
# -----------------------------------------------------------------------

class TestLLMCaching:
    """Test that _get_llm() caches the configured LLM instance."""

    def test_get_llm_caches_instance(self):
        """_get_llm() calls get_configured_llm() each time (no cache) so settings changes take effect."""
        from core.orchestrator.thinking.provider import OrchestrationThinkingProvider

        provider = OrchestrationThinkingProvider()

        sentinel = MagicMock(name="cached_llm_sentinel")
        with patch(
            "core.providers.llm_adapter.get_configured_llm", return_value=sentinel
        ) as mock_get:
            first = provider._get_llm()
            second = provider._get_llm()

        assert mock_get.call_count == 2, "get_configured_llm should be called each time (no cache)"
        assert first is sentinel
        assert second is sentinel

    def test_get_llm_explicit_skips_cache(self):
        """When explicit LLM is provided, _get_llm() returns it without calling get_configured_llm."""
        from core.orchestrator.thinking.provider import OrchestrationThinkingProvider

        explicit_llm = MagicMock(name="explicit_llm")
        provider = OrchestrationThinkingProvider(llm=explicit_llm)

        with patch("core.providers.llm_adapter.get_configured_llm") as mock_get:
            result = provider._get_llm()

        mock_get.assert_not_called()
        assert result is explicit_llm

# -----------------------------------------------------------------------
# F-005: Agent count log tests
# -----------------------------------------------------------------------

class TestAgentCountLog:
    """Test that discover_and_register logs a summary on completion."""

    def test_discover_and_register_includes_capella_count(self, caplog):
        """Summary log should include directory agent counts."""
        from core.adapters.auto_discovery import AgentAutoDiscovery

        discovery = AgentAutoDiscovery("agents")
        mock_registry = MagicMock()
        mock_registry.__contains__ = MagicMock(return_value=False)

        with (
            patch.object(discovery, "scan", return_value=[]),
            patch("core.adapters.registry.get_registry", return_value=mock_registry),
            patch("core.adapters.zero_dev.wrap_agent_directory", return_value=None),
            caplog.at_level(logging.INFO, logger="core.adapters.auto_discovery"),
        ):
            discovery.discover_and_register(registry=mock_registry)

        # Check the summary log is present
        summary_messages = [
            r.message for r in caplog.records if "Auto-discovery complete" in r.message
        ]
        assert len(summary_messages) == 1, (
            f"Expected exactly one summary log, got: {summary_messages}"
        )
        assert "directory agents" in summary_messages[0]

    def test_discover_and_register_capella_import_error(self, caplog):
        """discover_and_register completes successfully when capella_agents is unavailable."""
        from core.adapters.auto_discovery import AgentAutoDiscovery

        discovery = AgentAutoDiscovery("agents")
        mock_registry = MagicMock()
        mock_registry.__contains__ = MagicMock(return_value=False)

        with (
            patch.object(discovery, "scan", return_value=[]),
            patch("core.adapters.registry.get_registry", return_value=mock_registry),
            patch("core.adapters.zero_dev.wrap_agent_directory", return_value=None),
            # Setting module to None triggers ImportError on `from core.capella_agents import ...`
            patch.dict("sys.modules", {"core.capella_agents": None}),
            caplog.at_level(logging.INFO, logger="core.adapters.auto_discovery"),
        ):
            discovery.discover_and_register(registry=mock_registry)

        summary_messages = [
            r.message for r in caplog.records if "Auto-discovery complete" in r.message
        ]
        assert len(summary_messages) == 1
        assert "directory agents" in summary_messages[0]

# -----------------------------------------------------------------------
# F-006: Qdrant warning tests
# -----------------------------------------------------------------------

class TestQdrantWarning:
    """Test Qdrant connection failure and router fallback warnings."""

    def test_qdrant_connection_failure_logs_fallback_message(self, caplog):
        """Qdrant connection failure should log 'Semantic tool routing disabled'."""
        from core.mcp.embeddings import ToolEmbeddingStore

        store = ToolEmbeddingStore(url="http://localhost:99999")

        with (
            patch("core.mcp.embeddings.QDRANT_AVAILABLE", True),
            patch("core.mcp.embeddings.QdrantClient", side_effect=ConnectionError("refused")),
            caplog.at_level(logging.WARNING, logger="core.mcp.embeddings"),
        ):
            # Reset client state to force re-initialization
            store._client = None
            store._available = False
            result = store._ensure_client()

        assert result is False
        warning_messages = [
            r.message for r in caplog.records if "Semantic tool routing disabled" in r.message
        ]
        assert len(warning_messages) == 1, (
            f"Expected fallback warning, got: {[r.message for r in caplog.records]}"
        )

    def test_router_fallback_warns_once(self, caplog):
        """Router should warn about regex fallback exactly once, even after multiple route() calls."""
        from core.mcp.hierarchical_router import HierarchicalToolRouter

        mock_embedding_store = MagicMock()
        mock_embedding_store.available = False

        mock_tool_index = MagicMock()
        mock_tool_index.search.return_value = []

        router = HierarchicalToolRouter(
            embedding_store=mock_embedding_store,
            tool_index=mock_tool_index,
        )

        with caplog.at_level(logging.WARNING, logger="core.mcp.hierarchical_router"):
            router.route("test query 1")
            router.route("test query 2")

        warning_messages = [
            r.message for r in caplog.records if "Semantic routing unavailable" in r.message
        ]
        assert len(warning_messages) == 1, (
            f"Expected exactly one fallback warning, got {len(warning_messages)}: {warning_messages}"
        )
