"""Dual-dialect smoke tests for SQLite and PostgreSQL compatibility.

These tests verify that core database operations work correctly
on SQLite (the community/dev default). PostgreSQL tests require
a running PostgreSQL instance and are skipped by default.

Run PostgreSQL tests with:
    TEST_PG_URL=postgresql+psycopg://user:pass@localhost/test pytest tests/test_dual_dialect.py -k pg
"""

import json
import os
import tempfile

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from core.database.models import Base

# --- SQLite Tests (always run) ---

class TestSQLiteDialect:
    """Verify all models work on SQLite."""

    def setup_method(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_url = f"sqlite:///{self.db_file.name}"
        self.engine = create_engine(self.db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def teardown_method(self):
        self.engine.dispose()
        os.unlink(self.db_file.name)

    def test_all_tables_created(self):
        """All ORM models produce tables on SQLite."""
        inspector = inspect(self.engine)
        tables = set(inspector.get_table_names())
        expected_tables = set(Base.metadata.tables.keys())
        missing = expected_tables - tables
        assert not missing, f"Missing tables on SQLite: {missing}"

    def test_session_crud(self):
        """Basic CRUD works on SQLite."""
        from core.database.models import User

        session = self.Session()
        try:
            # Create -- User model uses email (not username)
            user = User(
                id="test-1",
                email="test@example.com",
                password_hash="hash",
                role="member",
                is_active=True,
            )
            session.add(user)
            session.commit()

            # Read
            found = session.query(User).filter_by(id="test-1").first()
            assert found is not None
            assert found.email == "test@example.com"

            # Update
            found.display_name = "Updated Name"
            session.commit()
            assert session.query(User).filter_by(id="test-1").first().display_name == "Updated Name"

            # Delete
            session.delete(found)
            session.commit()
            assert session.query(User).filter_by(id="test-1").first() is None
        finally:
            session.close()

    def test_factory_artifact_record(self):
        """FactoryArtifactRecord works on SQLite."""
        from core.database.models import FactoryArtifactRecord

        session = self.Session()
        try:
            record = FactoryArtifactRecord(
                id="art-1",
                name="test-agent",
                artifact_type="agent",
                framework="crewai",
                source_prompt="create a test agent",
                config_json="{}",
                artifact_path="/tmp/test-agent",
                created_at="2026-01-01",
                updated_at="2026-01-01",
            )
            session.add(record)
            session.commit()
            found = session.get(FactoryArtifactRecord, "art-1")
            assert found is not None
            assert found.name == "test-agent"
        finally:
            session.close()

    def test_failure_history_record(self):
        """FailureHistoryRecord works on SQLite."""
        from core.database.models import FailureHistoryRecord

        session = self.Session()
        try:
            record = FailureHistoryRecord(
                timestamp="2026-01-01T00:00:00Z",
                tool_name="test_tool",
                server_name="test_server",
                error_category="NETWORK",
                action_taken="RETRY",
                recovery_success=1,
            )
            session.add(record)
            session.commit()
            found = session.query(FailureHistoryRecord).first()
            assert found is not None
            assert found.tool_name == "test_tool"
        finally:
            session.close()

    def test_json_column_roundtrip(self):
        """JSON columns store and retrieve data correctly on SQLite.

        Note: FactoryArtifactRecord.config_json is Text (stores serialized JSON),
        not a native JSON column. This test verifies Text-based JSON roundtrip.
        """
        from core.database.models import FactoryArtifactRecord

        session = self.Session()
        try:
            config = {"key": "value", "nested": {"a": 1}}
            tags = ["tag1", "tag2"]
            record = FactoryArtifactRecord(
                id="json-1",
                name="json-test",
                artifact_type="tool",
                framework="custom",
                source_prompt="json test",
                config_json=json.dumps(config),
                artifact_path="/tmp/json-test",
                tags=json.dumps(tags),
                created_at="2026-01-01",
                updated_at="2026-01-01",
            )
            session.add(record)
            session.commit()

            session.expire_all()
            found = session.get(FactoryArtifactRecord, "json-1")
            assert json.loads(found.config_json) == config
            assert json.loads(found.tags) == tags
        finally:
            session.close()

    def test_native_json_column_roundtrip(self):
        """Native JSON columns (SA JSON type) roundtrip correctly on SQLite."""
        from core.database.models import User

        session = self.Session()
        try:
            prefs = {"theme": "dark", "lang": "en", "notifications": True}
            user = User(
                id="json-user-1",
                email="json@example.com",
                preferences=prefs,
            )
            session.add(user)
            session.commit()

            session.expire_all()
            found = session.get(User, "json-user-1")
            assert found.preferences == prefs
        finally:
            session.close()

# --- PostgreSQL Tests (require running PG instance) ---

PG_URL = os.environ.get("TEST_PG_URL")

@pytest.mark.skipif(PG_URL is None, reason="TEST_PG_URL not set")
class TestPostgreSQLDialect:
    """Verify all models work on PostgreSQL."""

    def setup_method(self):
        self.engine = create_engine(PG_URL)
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def teardown_method(self):
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_all_tables_created(self):
        """All ORM models produce tables on PostgreSQL."""
        inspector = inspect(self.engine)
        tables = set(inspector.get_table_names())
        expected_tables = set(Base.metadata.tables.keys())
        missing = expected_tables - tables
        assert not missing, f"Missing tables on PostgreSQL: {missing}"

    def test_session_crud(self):
        """Basic CRUD works on PostgreSQL."""
        from core.database.models import User

        session = self.Session()
        try:
            user = User(
                id="pg-1",
                email="pg@example.com",
                password_hash="hash",
                role="member",
                is_active=True,
            )
            session.add(user)
            session.commit()
            found = session.query(User).filter_by(id="pg-1").first()
            assert found is not None
            assert found.email == "pg@example.com"
        finally:
            session.close()

    def test_json_column_roundtrip(self):
        """JSON columns work with PostgreSQL JSONB."""
        from core.database.models import FactoryArtifactRecord

        session = self.Session()
        try:
            config = {"key": "value", "nested": {"a": 1}}
            record = FactoryArtifactRecord(
                id="pgjson-1",
                name="json-test",
                artifact_type="tool",
                framework="custom",
                source_prompt="json test",
                config_json=json.dumps(config),
                artifact_path="/tmp/json-test",
                created_at="2026-01-01",
                updated_at="2026-01-01",
            )
            session.add(record)
            session.commit()
            session.expire_all()
            found = session.get(FactoryArtifactRecord, "pgjson-1")
            assert json.loads(found.config_json) == config
        finally:
            session.close()
