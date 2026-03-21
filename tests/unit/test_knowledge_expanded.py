"""Expanded tests for core/knowledge/ and core/database/ modules.

Tests knowledge config, chunking, sources registry, and database models.
Covers module-level functions without requiring external services (Qdrant, etc).
"""

import pytest

# ===========================================================================
# knowledge: config
# ===========================================================================

class TestKnowledgeConfig:
    """Tests for core/knowledge/config.py."""

    def test_get_knowledge_config_returns_config(self):
        """get_knowledge_config returns a KnowledgeConfig instance."""
        from core.knowledge.config import KnowledgeConfig, get_knowledge_config

        config = get_knowledge_config()
        assert isinstance(config, KnowledgeConfig)

    def test_knowledge_config_has_chunk_size(self):
        """KnowledgeConfig has chunk_size field."""
        from core.knowledge.config import KnowledgeConfig

        config = KnowledgeConfig()
        assert isinstance(config.chunk_size, int)
        assert config.chunk_size > 0

    def test_knowledge_config_has_chunk_overlap(self):
        """KnowledgeConfig has chunk_overlap field."""
        from core.knowledge.config import KnowledgeConfig

        config = KnowledgeConfig()
        assert isinstance(config.chunk_overlap, int)
        assert config.chunk_overlap >= 0

    def test_knowledge_config_has_top_k(self):
        """KnowledgeConfig has top_k retrieval parameter."""
        from core.knowledge.config import KnowledgeConfig

        config = KnowledgeConfig()
        assert isinstance(config.top_k, int)
        assert config.top_k > 0

    def test_knowledge_config_has_collection_name(self):
        """KnowledgeConfig has collection_name."""
        from core.knowledge.config import KnowledgeConfig

        config = KnowledgeConfig()
        assert isinstance(config.collection_name, str)
        assert len(config.collection_name) > 0

    def test_knowledge_config_singleton(self):
        """get_knowledge_config returns same instance."""
        from core.knowledge.config import get_knowledge_config

        a = get_knowledge_config()
        b = get_knowledge_config()
        assert a is b

    def test_knowledge_config_dense_dim(self):
        """KnowledgeConfig has dense_dim for embedding dimensions."""
        from core.knowledge.config import KnowledgeConfig

        config = KnowledgeConfig()
        assert config.dense_dim > 0

    def test_knowledge_config_score_threshold(self):
        """KnowledgeConfig has score_threshold between 0 and 1."""
        from core.knowledge.config import KnowledgeConfig

        config = KnowledgeConfig()
        assert 0.0 <= config.score_threshold <= 1.0

# ===========================================================================
# knowledge: chunker
# ===========================================================================

class TestChunkingService:
    """Tests for core/knowledge/chunker.py."""

    def _make_chunker(self, chunk_size=500, chunk_overlap=50):
        """Create a ChunkingService with test config."""
        from core.knowledge.chunker import ChunkingService
        from core.knowledge.config import KnowledgeConfig

        config = KnowledgeConfig(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        return ChunkingService(config)

    def test_chunk_short_text_returns_one_chunk(self):
        """Short text (< chunk_size) returns a single chunk."""
        chunker = self._make_chunker(chunk_size=500)
        chunks = chunker.chunk("This is a short text.")
        assert len(chunks) == 1
        assert chunks[0].text == "This is a short text."

    def test_chunk_empty_text_returns_empty(self):
        """Empty text returns empty list."""
        chunker = self._make_chunker()
        chunks = chunker.chunk("")
        assert chunks == []

    def test_chunk_whitespace_only_returns_empty(self):
        """Whitespace-only text returns empty list."""
        chunker = self._make_chunker()
        chunks = chunker.chunk("   \n  \t  ")
        assert chunks == []

    def test_chunk_adds_metadata(self):
        """Chunk attaches provided metadata to each chunk."""
        chunker = self._make_chunker()
        chunks = chunker.chunk("Some text", metadata={"source": "test.pdf"})
        assert chunks[0].metadata["source"] == "test.pdf"

    def test_chunk_adds_chunk_index(self):
        """Chunk adds chunk_index to metadata."""
        chunker = self._make_chunker()
        chunks = chunker.chunk("Text content")
        assert "chunk_index" in chunks[0].metadata
        assert chunks[0].metadata["chunk_index"] == 0

    def test_chunk_has_index_field(self):
        """Chunk objects have index field set."""
        chunker = self._make_chunker()
        chunks = chunker.chunk("Content here")
        assert chunks[0].index == 0

    def test_chunk_long_text_produces_multiple_chunks(self):
        """Long text produces multiple chunks."""
        chunker = self._make_chunker(chunk_size=50, chunk_overlap=5)
        long_text = "word " * 100  # 500 chars
        chunks = chunker.chunk(long_text)
        assert len(chunks) > 1

    def test_chunk_paragraph_split(self):
        """Text with paragraphs splits on double newlines."""
        chunker = self._make_chunker(chunk_size=100, chunk_overlap=0)
        text = "Para 1\n\nPara 2\n\nPara 3"
        chunks = chunker.chunk(text)
        # Should have multiple chunks (one per paragraph for small chunk_size)
        assert len(chunks) >= 1

    def test_chunk_object_fields(self):
        """Chunk dataclass has text, metadata, and index fields."""
        from core.knowledge.chunker import Chunk

        chunk = Chunk(text="test", metadata={"key": "val"}, index=2)
        assert chunk.text == "test"
        assert chunk.metadata["key"] == "val"
        assert chunk.index == 2

# ===========================================================================
# knowledge: sources
# ===========================================================================

class TestKnowledgeSources:
    """Tests for core/knowledge/sources.py."""

    def test_knowledge_source_info_importable(self):
        """KnowledgeSourceInfo model is importable."""
        from core.knowledge.sources import KnowledgeSourceInfo

        assert KnowledgeSourceInfo is not None

    def test_register_knowledge_source_importable(self):
        """register_knowledge_source function is importable."""
        from core.knowledge.sources import register_knowledge_source

        assert register_knowledge_source is not None

    def test_get_knowledge_source_importable(self):
        """get_knowledge_source function is importable."""
        from core.knowledge.sources import get_knowledge_source

        assert get_knowledge_source is not None

    def test_list_knowledge_sources_returns_list(self):
        """list_knowledge_sources() returns a list."""
        from core.knowledge.sources import list_knowledge_sources

        sources = list_knowledge_sources()
        assert isinstance(sources, list)

    def test_get_nonexistent_source_returns_none(self):
        """Getting non-existent source returns None."""
        from core.knowledge.sources import get_knowledge_source

        result = get_knowledge_source("nonexistent-source-id-xyz")
        assert result is None

    def test_knowledge_source_info_has_id(self):
        """KnowledgeSourceInfo has id field."""
        from core.knowledge.sources import KnowledgeSourceInfo

        info = KnowledgeSourceInfo(
            id="src-001",
            name="Test Source",
            source_type="text",
            file_paths=["doc.txt"],
            description="A test source",
        )
        assert info.id == "src-001"

    def test_knowledge_source_info_has_name(self):
        """KnowledgeSourceInfo has name field."""
        from core.knowledge.sources import KnowledgeSourceInfo

        info = KnowledgeSourceInfo(
            id="src-002",
            name="Named Source",
            source_type="pdf",
            file_paths=["doc.pdf"],
            description="desc",
        )
        assert info.name == "Named Source"

    def test_knowledge_source_info_has_source_type(self):
        """KnowledgeSourceInfo has source_type field."""
        from core.knowledge.sources import KnowledgeSourceInfo

        info = KnowledgeSourceInfo(
            id="src-003",
            name="Source",
            source_type="csv",
            file_paths=["data.csv"],
            description="desc",
        )
        assert info.source_type == "csv"

# ===========================================================================
# database: models
# ===========================================================================

class TestDatabaseModels:
    """Tests for core/database/models.py."""

    def test_conversation_model_importable(self):
        """Conversation model is importable."""
        from core.database.models import Conversation

        assert Conversation is not None

    def test_execution_plan_model_importable(self):
        """ExecutionPlan model is importable."""
        from core.database.models import ExecutionPlan

        assert ExecutionPlan is not None

    def test_user_model_importable(self):
        """User model is importable."""
        from core.database.models import User

        assert User is not None

    def test_workflow_model_importable(self):
        """Workflow model is importable."""
        from core.database.models import Workflow

        assert Workflow is not None

    def test_base_is_declarative_base(self):
        """Base is a SQLAlchemy declarative base."""
        from core.database.models import Base

        assert hasattr(Base, "metadata")
        assert hasattr(Base.metadata, "tables")

    def test_all_expected_tables_in_metadata(self):
        """All expected tables are in Base metadata."""
        from core.database.models import Base

        table_names = set(Base.metadata.tables.keys())
        expected = {"conversations", "execution_plans", "workflows", "users"}
        for expected_table in expected:
            assert expected_table in table_names, f"Missing table: {expected_table}"

    def test_conversation_model_fields(self):
        """Conversation model has required columns."""
        from sqlalchemy import inspect

        from core.database.models import Conversation

        mapper = inspect(Conversation)
        column_names = {c.key for c in mapper.mapper.column_attrs}
        assert "id" in column_names
        assert "user_id" in column_names
        assert "title" in column_names
        assert "status" in column_names

    def test_workflow_model_fields(self):
        """Workflow model has required columns."""
        from sqlalchemy import inspect

        from core.database.models import Workflow

        mapper = inspect(Workflow)
        column_names = {c.key for c in mapper.mapper.column_attrs}
        assert "id" in column_names
        assert "user_id" in column_names
        assert "name" in column_names
        assert "workflow_json" in column_names

    def test_execution_plan_model_fields(self):
        """ExecutionPlan model has required columns."""
        from sqlalchemy import inspect

        from core.database.models import ExecutionPlan

        mapper = inspect(ExecutionPlan)
        column_names = {c.key for c in mapper.mapper.column_attrs}
        assert "id" in column_names
        assert "user_id" in column_names
        assert "name" in column_names
        assert "status" in column_names
        assert "nodes" in column_names

    def test_create_conversation_instance(self):
        """Conversation can be instantiated with required fields."""
        from core.database.models import Conversation

        conv = Conversation(
            id="conv-001",
            user_id="user-001",
            title="Test Conv",
            mode="chat",
            status="active",
        )
        assert conv.id == "conv-001"
        assert conv.user_id == "user-001"

    def test_create_workflow_instance(self):
        """Workflow can be instantiated with workflow_json."""
        from core.database.models import Workflow

        wf = Workflow(
            name="Test Workflow",
            user_id="user-001",
            workflow_json={"nodes": [], "edges": []},
        )
        assert wf.name == "Test Workflow"
        assert wf.user_id == "user-001"
        assert wf.workflow_json == {"nodes": [], "edges": []}

# ===========================================================================
# database: session helpers
# ===========================================================================

@pytest.mark.integration
class TestDatabaseSessionHelpers:
    """Tests for core/database/session.py helper functions (requires PostgreSQL)."""

    def test_get_session_factory_with_engine(self):
        """get_session_factory creates sessions bound to given engine."""
        import os

        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import Session

        from core.database.models import Base
        from core.database.session import get_session_factory

        engine = create_engine(
            os.environ.get(
                "DRYADE_TEST_DATABASE_URL",
                "postgresql+psycopg://dryade:dryade_dev@localhost:5432/dryade_test",
            )
        )
        Base.metadata.create_all(engine)

        factory = get_session_factory(engine=engine)
        session = factory()
        assert isinstance(session, Session)
        # Basic query works
        session.execute(text("SELECT 1"))
        session.close()

    def test_drop_db_removes_all_tables(self):
        """drop_db removes all tables from the database.

        Note: The database may contain tables outside Base.metadata (e.g. from
        Alembic migrations).  We first drop those extra tables via raw SQL so
        that ``Base.metadata.drop_all()`` inside ``drop_db()`` can succeed
        without CASCADE issues caused by foreign-key references from untracked
        tables.
        """
        import os

        from sqlalchemy import create_engine, inspect, text

        from core.database.models import Base
        from core.database.session import drop_db, init_db

        engine = create_engine(
            os.environ.get(
                "DRYADE_TEST_DATABASE_URL",
                "postgresql+psycopg://dryade:dryade_dev@localhost:5432/dryade_test",
            )
        )
        init_db(engine=engine)

        # Verify tables exist
        inspector = inspect(engine)
        assert len(inspector.get_table_names()) > 0

        # Drop any tables NOT in Base.metadata first (prevents FK CASCADE issues)
        tracked_names = set(Base.metadata.tables.keys())
        all_tables = set(inspector.get_table_names())
        extra_tables = all_tables - tracked_names
        if extra_tables:
            with engine.begin() as conn:
                for table_name in extra_tables:
                    conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))

        drop_db(engine=engine)

        # All Base-tracked tables should be gone
        inspector = inspect(engine)
        remaining = set(inspector.get_table_names())
        assert len(remaining) == 0

    def test_get_session_commits_on_success(self):
        """get_session() commits transaction on successful exit."""
        import os
        import uuid
        from unittest.mock import patch

        from sqlalchemy import create_engine

        from core.database.models import Base, Conversation, User
        from core.database.session import get_session_factory

        engine = create_engine(
            os.environ.get(
                "DRYADE_TEST_DATABASE_URL",
                "postgresql+psycopg://dryade:dryade_dev@localhost:5432/dryade_test",
            )
        )
        Base.metadata.create_all(engine)

        factory = get_session_factory(engine=engine)

        # Use unique IDs to avoid conflicts with other tests
        user_id = f"user-{uuid.uuid4().hex[:8]}"
        conv_id = f"conv-{uuid.uuid4().hex[:8]}"

        with patch("core.database.session.get_session_factory", return_value=factory):
            from core.database.session import get_session

            # Create the user first to satisfy FK constraint
            with get_session() as session:
                user = User(
                    id=user_id,
                    email=f"{user_id}@example.com",
                    password_hash="hashed",
                    role="member",
                )
                session.add(user)

            with get_session() as session:
                conv = Conversation(
                    id=conv_id,
                    user_id=user_id,
                    title="Test",
                    mode="chat",
                    status="active",
                )
                session.add(conv)

            # After context manager exits, transaction should be committed
            session2 = factory()
            result = session2.query(Conversation).filter_by(id=conv_id).first()
            assert result is not None
            session2.close()
