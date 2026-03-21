"""Tests for knowledge source persistence and collection unification.

Phase 94.1-02: Verify KnowledgeSourceRecord model, persistence functions,
and RAGAgent unified collection name.
"""

from unittest.mock import MagicMock, patch

class TestKnowledgeSourceRecordModel:
    """Tests for the KnowledgeSourceRecord SQLAlchemy model."""

    def test_knowledge_source_record_model(self):
        """Verify KnowledgeSourceRecord has expected columns."""
        from core.database.models import KnowledgeSourceRecord

        cols = {c.name for c in KnowledgeSourceRecord.__table__.columns}
        expected = {
            "id",
            "name",
            "source_type",
            "file_paths",
            "description",
            "crew_ids",
            "agent_ids",
            "chunk_count",
            "created_at",
        }
        assert expected.issubset(cols), f"Missing columns: {expected - cols}"
        assert KnowledgeSourceRecord.__tablename__ == "knowledge_sources"

class TestPersistKnowledgeSource:
    """Tests for persist_knowledge_source function."""

    @patch("core.database.session.get_session")
    def test_persist_knowledge_source_creates_record(self, mock_get_session):
        """Mock session, verify INSERT for new record."""
        from core.knowledge.sources import persist_knowledge_source

        mock_session = MagicMock()
        mock_session.get.return_value = None  # No existing record
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        persist_knowledge_source(
            source_id="ks_test",
            name="Test Source",
            source_type="PDFKnowledgeSource",
            file_paths=["/tmp/test.pdf"],
            description="Test description",
            crew_ids=["crew1"],
            agent_ids=["agent1"],
            chunk_count=42,
        )

        mock_session.add.assert_called_once()
        added_record = mock_session.add.call_args[0][0]
        assert added_record.id == "ks_test"
        assert added_record.name == "Test Source"
        assert added_record.source_type == "PDFKnowledgeSource"
        assert added_record.chunk_count == 42

    @patch("core.database.session.get_session")
    def test_persist_knowledge_source_handles_db_error(self, mock_get_session):
        """Mock session to raise, verify no crash."""
        from core.knowledge.sources import persist_knowledge_source

        mock_get_session.side_effect = Exception("DB connection failed")

        # Should not raise -- errors are caught and logged
        persist_knowledge_source(
            source_id="ks_fail",
            name="Failing Source",
            source_type="TextFileKnowledgeSource",
            file_paths=["/tmp/fail.txt"],
        )

class TestDeletePersistedKnowledgeSource:
    """Tests for delete_persisted_knowledge_source function."""

    @patch("core.database.session.get_session")
    def test_delete_persisted_removes_record(self, mock_get_session):
        """Mock session, verify DELETE."""
        from core.knowledge.sources import delete_persisted_knowledge_source

        mock_record = MagicMock()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_record
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        delete_persisted_knowledge_source("ks_test")

        mock_session.delete.assert_called_once_with(mock_record)

class TestLoadRegistryFromDB:
    """Tests for load_knowledge_registry_from_db function."""

    @patch("core.database.session.get_session")
    def test_load_registry_from_db_populates_memory(self, mock_get_session):
        """Mock session with rows, verify _knowledge_registry populated."""
        from core.knowledge.sources import (
            _knowledge_registry,
            load_knowledge_registry_from_db,
        )

        # Clear registry first
        _knowledge_registry.clear()

        # Create mock DB rows
        mock_row = MagicMock()
        mock_row.id = "ks_from_db"
        mock_row.name = "DB Source"
        mock_row.source_type = "PDFKnowledgeSource"
        mock_row.description = "From database"
        mock_row.crew_ids = ["crew1"]
        mock_row.agent_ids = ["agent1"]
        mock_row.file_paths = ["/tmp/db.pdf"]
        mock_row.chunk_count = 10

        mock_session = MagicMock()
        mock_session.query.return_value.all.return_value = [mock_row]
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        load_knowledge_registry_from_db()

        assert "ks_from_db" in _knowledge_registry
        entry = _knowledge_registry["ks_from_db"]
        assert entry["name"] == "DB Source"
        assert entry["source"] is None  # Cannot reconstruct CrewAI source
        assert entry["source_type"] == "PDFKnowledgeSource"
        assert entry["file_paths"] == ["/tmp/db.pdf"]
        assert entry["chunk_count"] == 10
        assert entry["crew_ids"] == ["crew1"]

        # Clean up
        _knowledge_registry.clear()

class TestRegisterCallsPersist:
    """Tests for register_knowledge_source calling persist."""

    @patch("core.knowledge.sources.persist_knowledge_source")
    def test_register_calls_persist(self, mock_persist):
        """Verify register_knowledge_source() calls persist_knowledge_source()."""
        from core.knowledge.sources import (
            _knowledge_registry,
            register_knowledge_source,
        )

        mock_source = MagicMock()
        mock_source.file_paths = ["/tmp/test.pdf"]
        type(mock_source).__name__ = "PDFKnowledgeSource"
        # Ensure hasattr(source, "chunks") returns False
        del mock_source.chunks

        source_id = register_knowledge_source(
            name="test_persist_call",
            source=mock_source,
            description="Testing persist call",
        )

        mock_persist.assert_called_once()
        call_kwargs = mock_persist.call_args
        assert call_kwargs[1]["source_id"] == source_id
        assert call_kwargs[1]["name"] == "test_persist_call"

        # Clean up
        _knowledge_registry.pop(source_id, None)

class TestRAGAgentCollectionName:
    """Tests for RAGAgent unified collection name."""

    def test_rag_agent_uses_dryade_knowledge_collection(self):
        """Verify RAGAgent default is dryade_knowledge (upgraded from crew_knowledge in 97.2-03)."""
        from core.agents.rag_agent import RAGAgent

        agent = RAGAgent()
        assert agent.collection_name == "dryade_knowledge"
